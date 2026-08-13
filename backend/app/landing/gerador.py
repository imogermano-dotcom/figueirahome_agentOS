"""Geração do conteúdo de uma landing page por imóvel.

Uma chamada à API da Anthropic por imóvel, `httpx` directo (decisão do
projecto: não SDK), no mesmo molde de `agents/broker/engine.py`.

Duas coisas que aqui não são detalhe:

* **A saída é forçada por tool**, não pedida em prosa. `tool_choice` com um
  schema fixo é o que garante que o conteúdo chega sempre com as mesmas
  secções — "responde só JSON" falha mais cedo ou mais tarde e o template
  rebenta em produção, não em desenvolvimento.
* **`CAMPOS_PUBLICOS` é uma fronteira de segurança**, não uma optimização.
  `imoveis` tem `proprietario`, `angariador`, `vendedor` e três colunas de
  comissão; a página é anónima. Allowlist e nunca `select("*")` — um campo
  novo do eGO fica de fora por omissão, que é o lado seguro.
"""

import asyncio
import hashlib
import json
import logging
import re
import unicodedata

import httpx

from app.agents.broker.custos import calcular_custo, somar_usage
from app.config import settings
from app.db.supabase_client import get_supabase

logger = logging.getLogger(__name__)

_URL = "https://api.anthropic.com/v1/messages"
_MODEL = "claude-sonnet-4-6"
_TEMPERATURE = 0.7  # texto de marketing: mais variedade do que os assistentes (0.4)
_MAX_TOKENS = 2000

# Colunas que podem sair para uma página pública. Ver o docstring do módulo.
CAMPOS_PUBLICOS = (
    "imovel_ref,natureza,titulo,descricao,quartos,casas_banho,suites,piso,"
    "area_util,area_bruta,area_terreno,conservacao,certificacao_energetica,"
    "venda_preco,arrendamento_preco,morada,codigo_postal,concelho,freguesia,zona,"
    "piscina,garagem,jardim,terraco,varanda,vista_mar,vista_praia,ar_condicionado,"
    "elevador,aquecimento_central,arrecadacao,estacionamento,"
    "foto_principal,fotos,plantas,panoramic_url,video_url,publicado"
)

# Colunas que nunca podem aparecer em `CAMPOS_PUBLICOS`. O teste usa esta lista.
CAMPOS_PROIBIDOS = (
    "proprietario", "angariador", "vendedor",
    "comissao_agencia", "comissao_angariador", "comissao_vendedor",
    "exclusividade", "portais", "ego_id",
)

CARACTERISTICAS = (
    ("piscina", "piscina"),
    ("garagem", "garagem"),
    ("jardim", "jardim"),
    ("terraço", "terraco"),
    ("varanda", "varanda"),
    ("vista de mar", "vista_mar"),
    ("vista de praia", "vista_praia"),
    ("ar condicionado", "ar_condicionado"),
    ("elevador", "elevador"),
    ("aquecimento central", "aquecimento_central"),
    ("arrecadação", "arrecadacao"),
    ("estacionamento", "estacionamento"),
)

_TOOL = {
    "name": "escrever_landing_page",
    "description": "Entrega o conteúdo escrito da landing page do imóvel.",
    "input_schema": {
        "type": "object",
        "properties": {
            "headline": {
                "type": "string",
                "description": "Título principal, até 70 caracteres. Concreto, sem clichés.",
            },
            "subheadline": {
                "type": "string",
                "description": "Uma frase de apoio, até 140 caracteres.",
            },
            "destaques": {
                "type": "array",
                "items": {"type": "string"},
                "description": "4 a 6 pontos curtos (até 60 caracteres cada).",
            },
            "descricao_longa": {
                "type": "array",
                "items": {"type": "string"},
                "description": "2 a 3 parágrafos sobre o imóvel.",
            },
            "envolvente": {
                "type": "string",
                "description": "Um parágrafo sobre a zona. Só o que se deduz da localização dada.",
            },
            "cta": {
                "type": "string",
                "description": "Chamada à acção do formulário, até 60 caracteres.",
            },
        },
        "required": [
            "headline", "subheadline", "destaques",
            "descricao_longa", "envolvente", "cta",
        ],
    },
}

_SISTEMA = """És copywriter imobiliário da Figueirahome, agência na Figueira da Foz.

Escreves o conteúdo de uma página de destino para um anúncio pago. Quem lá chega
vem de um anúncio no Facebook ou Instagram e decide em segundos se preenche o
formulário ou fecha o separador.

Regras:
- Português de Portugal. Nunca português do Brasil.
- **Só factos dos dados fornecidos.** Não inventes divisões, acabamentos,
  distâncias, ano de construção nem nada que não esteja nos dados. Se um campo
  não vem, não o mencionas — não escreves "consulte-nos" a tapar o buraco.
- Sobre a envolvente, escreve só o que decorre da localização indicada
  (concelho, freguesia, zona). Não inventes nomes de escolas, praias ou serviços.
- Concreto em vez de superlativo: "cozinha com 14 m²" vale mais que "cozinha
  ampla e sofisticada". Corta "único", "exclusivo", "sonho", "oportunidade
  imperdível", "nicho de mercado".
- Sem emojis. Sem exclamações a mais (no máximo uma na página inteira).
- O CTA pede o contacto para ver o imóvel completo, sem prometer preço nem
  visita imediata.

Chamas sempre a tool `escrever_landing_page`. Não escreves nada fora dela."""


def slugify(texto: str) -> str:
    """Texto → segmento de URL. Acentos fora, minúsculas, hífenes."""
    normalizado = unicodedata.normalize("NFKD", texto or "")
    ascii_only = normalizado.encode("ascii", "ignore").decode("ascii")
    limpo = re.sub(r"[^a-zA-Z0-9]+", "-", ascii_only).strip("-").lower()
    return re.sub(r"-{2,}", "-", limpo)


def gerar_slug(imovel: dict) -> str:
    """`fh2450-moradia-t3-buarcos`. A referência vai à frente: é única por si."""
    ref = slugify(imovel.get("imovel_ref") or "")
    partes = [
        imovel.get("natureza"),
        f"T{imovel['quartos']}" if imovel.get("quartos") is not None else None,
        imovel.get("freguesia") or imovel.get("zona") or imovel.get("concelho"),
    ]
    cauda = slugify(" ".join(p for p in partes if p))[:60].strip("-")
    return f"{ref}-{cauda}".strip("-") if cauda else ref


def dados_fonte(imovel: dict, extras: dict, mostrar_preco: bool) -> dict:
    """O que o modelo vê — e, por isso, o que decide se é preciso regenerar."""
    caracteristicas = [nome for nome, campo in CARACTERISTICAS if imovel.get(campo)]
    dados = {
        "referencia": imovel.get("imovel_ref"),
        "natureza": imovel.get("natureza"),
        "titulo": imovel.get("titulo"),
        "tipologia": f"T{imovel['quartos']}" if imovel.get("quartos") is not None else None,
        "casas_banho": imovel.get("casas_banho"),
        "suites": imovel.get("suites"),
        "piso": imovel.get("piso"),
        "area_util_m2": imovel.get("area_util"),
        "area_bruta_m2": imovel.get("area_bruta"),
        "area_terreno_m2": imovel.get("area_terreno"),
        "conservacao": imovel.get("conservacao"),
        "certificacao_energetica": imovel.get("certificacao_energetica"),
        "concelho": imovel.get("concelho"),
        "freguesia": imovel.get("freguesia"),
        "zona": imovel.get("zona"),
        "caracteristicas": caracteristicas,
        "descricao_do_crm": (imovel.get("descricao") or "")[:1500] or None,
        "tem_video": bool(extras.get("video_url") or imovel.get("video_url")),
        "tem_visita_virtual": bool(imovel.get("panoramic_url")),
        "notas_do_consultor": extras.get("notas"),
        "mostrar_preco": mostrar_preco,
    }
    if mostrar_preco:
        dados["venda_preco"] = imovel.get("venda_preco")
        dados["arrendamento_preco"] = imovel.get("arrendamento_preco")
    return {k: v for k, v in dados.items() if v not in (None, [], "")}


def fonte_hash(imovel: dict, extras: dict, mostrar_preco: bool) -> str:
    """Impressão digital do input. Igual = não vale a pena voltar a pagar API."""
    fonte = dados_fonte(imovel, extras, mostrar_preco)
    canonico = json.dumps(fonte, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(canonico.encode("utf-8")).hexdigest()


def carregar_imovel(imovel_ref: str) -> dict | None:
    """Só as colunas públicas. Nunca `select("*")` — ver docstring do módulo."""
    resp = (
        get_supabase()
        .table("imoveis")
        .select(CAMPOS_PUBLICOS)
        .eq("imovel_ref", imovel_ref)
        .limit(1)
        .execute()
    )
    return resp.data[0] if resp.data else None


async def gerar(imovel: dict, extras: dict, mostrar_preco: bool) -> tuple[dict, dict]:
    """Devolve `(conteudo, meta)`. `meta` traz modelo, tokens e custo em USD.

    Levanta `RuntimeError` se a API falhar ou não devolver a tool — ao contrário
    do `engine.py`, aqui não há cliente à espera de resposta: é melhor o botão
    do painel mostrar erro do que gravar uma página meia feita.
    """
    fonte = dados_fonte(imovel, extras, mostrar_preco)
    pedido = (
        "Escreve a landing page deste imóvel.\n\n"
        + json.dumps(fonte, ensure_ascii=False, indent=2, default=str)
    )

    headers = {
        "x-api-key": settings.anthropic_api_key,
        "anthropic-version": "2023-06-01",
        "anthropic-beta": "prompt-caching-2024-07-31",
        "content-type": "application/json",
    }
    payload = {
        "model": _MODEL,
        "max_tokens": _MAX_TOKENS,
        "temperature": _TEMPERATURE,
        # Cacheado: gerar 10 imóveis seguidos reaproveita o mesmo system a 10%.
        "system": [
            {"type": "text", "text": _SISTEMA, "cache_control": {"type": "ephemeral"}}
        ],
        "tools": [_TOOL],
        "tool_choice": {"type": "tool", "name": _TOOL["name"]},
        "messages": [{"role": "user", "content": pedido}],
    }

    async with httpx.AsyncClient(timeout=120.0) as client:
        try:
            resp = await client.post(_URL, headers=headers, json=payload)
            resp.raise_for_status()
        except Exception as exc:
            logger.exception("Erro na API Anthropic ao gerar %s", imovel.get("imovel_ref"))
            raise RuntimeError(f"Falha na geração: {type(exc).__name__}") from exc

    data = resp.json()
    conteudo = next(
        (b.get("input") for b in data.get("content", []) if b.get("type") == "tool_use"),
        None,
    )
    if not conteudo:
        raise RuntimeError("O modelo não devolveu conteúdo utilizável.")

    tokens = somar_usage({}, data.get("usage"))
    meta = {
        "modelo": _MODEL,
        "custo_usd": calcular_custo(tokens, _MODEL),
        "tokens_input": tokens.get("tokens_input", 0) + tokens.get("tokens_cache_read", 0)
        + tokens.get("tokens_cache_write", 0),
        "tokens_output": tokens.get("tokens_output", 0),
    }
    logger.info(
        "Landing page gerada para %s — %s tokens, $%.4f",
        imovel.get("imovel_ref"), meta["tokens_output"], meta["custo_usd"],
    )
    return conteudo, meta


def demo() -> None:
    """Auto-verificação das funções puras. `python -m app.landing.gerador`"""
    assert slugify("Moradia T3 — Buarcos, Figueira da Foz") == "moradia-t3-buarcos-figueira-da-foz"
    assert slugify("Apartamento  //  T2") == "apartamento-t2"
    assert slugify("") == ""

    imovel = {
        "imovel_ref": "FH2450", "natureza": "Moradia", "quartos": 3,
        "freguesia": "Buarcos", "venda_preco": 350000, "piscina": True,
    }
    assert gerar_slug(imovel) == "fh2450-moradia-t3-buarcos"
    assert gerar_slug({"imovel_ref": "FH1"}) == "fh1"

    # Nenhuma coluna sensível pode ter entrado na allowlist pública.
    publicos = set(CAMPOS_PUBLICOS.split(","))
    assert not publicos & set(CAMPOS_PROIBIDOS), publicos & set(CAMPOS_PROIBIDOS)
    assert "*" not in CAMPOS_PUBLICOS

    h1 = fonte_hash(imovel, {}, True)
    assert h1 == fonte_hash(dict(imovel), {}, True)          # estável
    assert h1 != fonte_hash(imovel, {}, False)               # esconder preço regenera
    assert h1 != fonte_hash({**imovel, "venda_preco": 340000}, {}, True)
    assert h1 != fonte_hash(imovel, {"notas": "vista de mar"}, True)
    # O preço não entra no hash quando está escondido: baixá-lo não deve gastar API.
    assert fonte_hash(imovel, {}, False) == fonte_hash({**imovel, "venda_preco": 1}, {}, False)

    print("gerador OK")


if __name__ == "__main__":
    demo()
