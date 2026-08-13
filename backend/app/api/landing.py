"""Landing pages por imóvel — página pública + gestão no painel.

Dois routers no mesmo ficheiro, com fronteiras diferentes de propósito:

* `publico` — sem autenticação (como o webhook do WhatsApp). Serve o HTML e
  recebe o formulário do gate. **Só lê colunas da allowlist**
  (`gerador.CAMPOS_PUBLICOS`); nunca `select("*")`.
* `painel` — `require_auth`, prefixo `/api`, como o resto da app.

O gate não guarda o lead à mão: passa por `guards.find_or_create_cliente`, o
mesmo caminho de escrita dos assistentes, para que uma pessoa que já falou pelo
WhatsApp não vire um segundo cliente por ter preenchido o formulário.
"""

import asyncio
import logging
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Optional
from urllib.parse import quote_plus

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

from app.agents.broker.guards import find_or_create_cliente, normalizar_telefone
from app.api.deps import require_auth
from app.config import settings
from app.db.supabase_client import get_supabase
from app.landing.gerador import (
    CAMPOS_PUBLICOS,
    CARACTERISTICAS,
    carregar_imovel,
    fonte_hash,
    gerar,
    gerar_slug,
)

logger = logging.getLogger(__name__)

publico = APIRouter(tags=["landing"])
painel = APIRouter(prefix="/api", tags=["landing"], dependencies=[Depends(require_auth)])

TABLE = "landing_pages"

# Os quatro escalões do gate. Escritos por extenso e não com `<`/`>`: vão para
# `agente_clientes.prazo_compra` e daí para relatórios e prompts, onde "<3 meses"
# chegaria escapado (`&lt;3 meses`) ou partido conforme o sítio.
PRAZOS = ("Até 3 meses", "3 a 6 meses", "Mais de 6 meses", "Só a pesquisar")

_TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "landing" / "templates"
_templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))


def _euro(valor) -> str:
    return f"{int(valor):,} €".replace(",", " ") if valor else ""


_templates.env.filters["euro"] = _euro


async def _run(fn, *args):
    return await asyncio.get_event_loop().run_in_executor(None, lambda: fn(*args))


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ══════════════════════════════════════════════════════════════
# Contexto dos templates
# ══════════════════════════════════════════════════════════════


def _factos(imovel: dict) -> list[tuple[str, str]]:
    """A linha de factos acima do gate. Só o que faz decidir se vale a pena."""
    pares = [
        ("Tipo", imovel.get("natureza")),
        ("Tipologia", f"T{imovel['quartos']}" if imovel.get("quartos") is not None else None),
        ("Área útil", f"{int(imovel['area_util'])} m²" if imovel.get("area_util") else None),
        ("Casas de banho", imovel.get("casas_banho")),
        ("Zona", imovel.get("freguesia") or imovel.get("zona") or imovel.get("concelho")),
    ]
    return [(r, str(v)) for r, v in pares if v not in (None, "")]


def _ficha(imovel: dict, mostrar_preco: bool) -> list[tuple[str, str]]:
    """A ficha detalhada, do lado de dentro do gate."""
    pares = [
        ("Referência", imovel.get("imovel_ref")),
        ("Tipo", imovel.get("natureza")),
        ("Tipologia", f"T{imovel['quartos']}" if imovel.get("quartos") is not None else None),
        ("Casas de banho", imovel.get("casas_banho")),
        ("Suites", imovel.get("suites")),
        ("Piso", imovel.get("piso")),
        ("Área útil", f"{int(imovel['area_util'])} m²" if imovel.get("area_util") else None),
        ("Área bruta", f"{int(imovel['area_bruta'])} m²" if imovel.get("area_bruta") else None),
        ("Terreno", f"{int(imovel['area_terreno'])} m²" if imovel.get("area_terreno") else None),
        ("Estado", imovel.get("conservacao")),
        ("Certificado energético", imovel.get("certificacao_energetica")),
        ("Concelho", imovel.get("concelho")),
        ("Freguesia", imovel.get("freguesia")),
    ]
    if mostrar_preco:
        pares.append(("Venda", _euro(imovel.get("venda_preco"))))
        pares.append(("Arrendamento", _euro(imovel.get("arrendamento_preco"))))
    return [(r, str(v)) for r, v in pares if v not in (None, "", "0")]


def _caminho_publico(request: Request) -> str:
    """O caminho que o visitante tem na barra de endereço.

    O Worker da Cloudflare serve isto em `site.pt/imovel/{slug}` e faz proxy
    para `/lp/{slug}` — o que este backend vê no seu próprio pedido é o caminho
    interno. Usá-lo no `action` do formulário ou na `og:url` mandava o visitante
    para um caminho que o domínio público não serve. O Worker manda o original
    em `X-Public-Path`; sem Worker (dev, ou o URL do Fly.io directo) o caminho
    do pedido já é o certo.
    """
    return (request.headers.get("x-public-path") or request.url.path).rstrip("/")


def _contexto_pagina(request: Request, lp: dict, imovel: dict) -> dict:
    caminho = _caminho_publico(request)
    base = settings.landing_base_url.rstrip("/")
    arrendamento = bool(imovel.get("arrendamento_preco") and not imovel.get("venda_preco"))
    preco = imovel.get("arrendamento_preco") if arrendamento else imovel.get("venda_preco")
    return {
        "request": request,
        "lp": lp,
        "c": lp.get("conteudo") or {},
        "imovel": imovel,
        "disponivel": bool(imovel.get("publicado")),
        "foto_principal": imovel.get("foto_principal") or (imovel.get("fotos") or [None])[0],
        "factos": _factos(imovel),
        "arrendamento": arrendamento,
        "preco": _euro(preco),
        "preco_rotulo": "Renda mensal" if arrendamento else "Preço",
        "prazos": PRAZOS,
        "acao_lead": f"{caminho}/lead",
        "page_url": f"{base}{caminho}" if base else str(request.url),
    }


def _contexto_conteudo(request: Request, lp: dict, imovel: dict, nome: str) -> dict:
    extras = lp.get("extras") or {}
    morada = " ".join(
        p for p in (imovel.get("morada"), imovel.get("codigo_postal"), imovel.get("concelho")) if p
    )
    mapa_url = extras.get("mapa_url") or (
        f"https://www.google.com/maps/search/?api=1&query={quote_plus(morada)}" if morada else None
    )
    return {
        "request": request,
        "c": lp.get("conteudo") or {},
        "imovel": imovel,
        "nome": nome.split()[0] if nome else "",
        "fotos": imovel.get("fotos") or [],
        "plantas": imovel.get("plantas") or [],
        "caracteristicas": [n for n, campo in CARACTERISTICAS if imovel.get(campo)],
        "ficha": _ficha(imovel, bool(lp.get("mostrar_preco"))),
        "morada": morada,
        "mapa_url": mapa_url,
        "video_url": extras.get("video_url") or imovel.get("video_url"),
        "notas": extras.get("notas"),
    }


# ══════════════════════════════════════════════════════════════
# Público
# ══════════════════════════════════════════════════════════════


def _por_slug(slug: str) -> dict | None:
    resp = get_supabase().table(TABLE).select("*").eq("slug", slug).limit(1).execute()
    return resp.data[0] if resp.data else None


async def _carregar(slug: str) -> tuple[dict, dict]:
    lp = await _run(_por_slug, slug)
    if not lp:
        raise HTTPException(status_code=404, detail="Página não encontrada.")
    imovel = await _run(carregar_imovel, lp["imovel_ref"])
    if not imovel:
        # A FK tem ON DELETE CASCADE, por isso não devia acontecer.
        logger.error("Landing page %s sem imóvel %s.", slug, lp["imovel_ref"])
        raise HTTPException(status_code=404, detail="Página não encontrada.")
    return lp, imovel


@publico.get("/lp/{slug}", response_class=HTMLResponse)
async def ver_landing_page(request: Request, slug: str):
    lp, imovel = await _carregar(slug)
    return _templates.TemplateResponse("imovel.html", _contexto_pagina(request, lp, imovel))


class GateForm(BaseModel):
    nome: str = Field(min_length=2, max_length=120)
    telefone: str = Field(min_length=6, max_length=30)
    email: str = Field(min_length=5, max_length=160)
    prazo_compra: str
    empresa: str = ""  # honeypot: um humano nunca vê este campo


def _validar(form: GateForm) -> None:
    if "@" not in form.email or "." not in form.email.rsplit("@", 1)[-1]:
        raise HTTPException(status_code=422, detail="Email inválido.")
    if not normalizar_telefone(form.telefone):
        raise HTTPException(status_code=422, detail="Telefone inválido.")
    if form.prazo_compra not in PRAZOS:
        raise HTTPException(status_code=422, detail="Prazo inválido.")


def _registar_lead(cliente_id: str, imovel_ref: str, prazo: str) -> None:
    """Lead + tarefa para o consultor.

    Uma lead por cliente e imóvel: quem volta à página e preenche outra vez não
    gera uma segunda lead — molde de `tools.py::_criar_lead_se_preciso`.
    """
    supabase = get_supabase()
    aberta = (
        supabase.table("agente_leads")
        .select("id")
        .eq("cliente_id", cliente_id)
        .eq("imovel_ref", imovel_ref)
        .not_.in_("estado", ["fechado", "perdido"])
        .limit(1)
        .execute()
    )
    if aberta.data:
        return

    supabase.table("agente_leads").insert({
        "cliente_id": cliente_id,
        "imovel_ref": imovel_ref,
        "estado": "novo",
        "notas": f"Landing page do imóvel {imovel_ref}. Prazo de compra: {prazo}.",
    }).execute()

    supabase.table("agente_tarefas").insert({
        "titulo": f"LANDING PAGE — contactar lead do imóvel {imovel_ref}",
        "descricao": f"Lead da landing page. Prazo de compra declarado: {prazo}.",
        "imovel_ref": imovel_ref,
        "prazo": date.today().isoformat(),
        "estado": "pendente",
        "tipo": "lead",
        "motivo": "landing_page",
    }).execute()


@publico.post("/lp/{slug}/lead", response_class=HTMLResponse)
async def submeter_gate(request: Request, slug: str, form: GateForm):
    lp, imovel = await _carregar(slug)
    _validar(form)

    # Honeypot preenchido: devolve a página como a qualquer outro visitante, mas
    # não escreve nada. Dizer ao bot que foi apanhado só o ensina a contornar.
    if not form.empresa.strip():
        cliente = await find_or_create_cliente(
            nome=form.nome.strip(),
            telefone=form.telefone,
            email=form.email,
            prazo_compra=form.prazo_compra,
            tipo_interesse="arrendamento" if imovel.get("arrendamento_preco")
            and not imovel.get("venda_preco") else "compra",
            zona_preferida=imovel.get("concelho"),
            origem="landing_page",
        )
        if cliente:
            try:
                await _run(_registar_lead, cliente["id"], lp["imovel_ref"], form.prazo_compra)
            except Exception:
                # O visitante já se identificou; falhar a tarefa não pode negar-lhe
                # o conteúdo. Fica o log para se recuperar à mão.
                logger.exception("Falha a registar lead da landing page %s", slug)

    return _templates.TemplateResponse(
        "conteudo.html", _contexto_conteudo(request, lp, imovel, form.nome)
    )


# ══════════════════════════════════════════════════════════════
# Painel
# ══════════════════════════════════════════════════════════════


class LandingPageCreate(BaseModel):
    imovel_ref: str
    mostrar_preco: bool = True
    extras: dict = Field(default_factory=dict)


class LandingPageUpdate(BaseModel):
    mostrar_preco: Optional[bool] = None
    extras: Optional[dict] = None


def _listar() -> list[dict]:
    supabase = get_supabase()
    paginas = supabase.table(TABLE).select("*").order("criado_em", desc=True).execute().data or []
    if not paginas:
        return []

    refs = [p["imovel_ref"] for p in paginas]
    imoveis = (
        supabase.table("imoveis")
        .select("imovel_ref,titulo,natureza,quartos,concelho,publicado,foto_principal")
        .in_("imovel_ref", refs)
        .execute()
    ).data or []
    por_ref = {i["imovel_ref"]: i for i in imoveis}

    leads = (
        supabase.table("agente_leads").select("imovel_ref").in_("imovel_ref", refs).execute()
    ).data or []
    contagem: dict[str, int] = {}
    for lead in leads:
        contagem[lead["imovel_ref"]] = contagem.get(lead["imovel_ref"], 0) + 1

    for p in paginas:
        p["imovel"] = por_ref.get(p["imovel_ref"])
        p["leads"] = contagem.get(p["imovel_ref"], 0)
    return paginas


@painel.get("/landing-pages")
async def listar_landing_pages():
    return await _run(_listar)


async def _gerar_e_gravar(lp: dict, imovel: dict) -> dict:
    """Gera o conteúdo e faz upsert da linha. Devolve a linha gravada."""
    extras = lp.get("extras") or {}
    mostrar_preco = bool(lp.get("mostrar_preco"))
    conteudo, meta = await gerar(imovel, extras, mostrar_preco)

    linha = {
        "imovel_ref": imovel["imovel_ref"],
        "slug": lp.get("slug") or gerar_slug(imovel),
        "conteudo": conteudo,
        "extras": extras,
        "mostrar_preco": mostrar_preco,
        "fonte_hash": fonte_hash(imovel, extras, mostrar_preco),
        "gerado_em": _now(),
        "atualizado_em": _now(),
        **meta,
    }

    def _upsert():
        return get_supabase().table(TABLE).upsert(linha, on_conflict="imovel_ref").execute()

    resp = await _run(_upsert)
    return resp.data[0] if resp.data else linha


def _obter(imovel_ref: str) -> dict | None:
    resp = get_supabase().table(TABLE).select("*").eq("imovel_ref", imovel_ref).limit(1).execute()
    return resp.data[0] if resp.data else None


@painel.post("/landing-pages", status_code=201)
async def criar_landing_page(body: LandingPageCreate):
    ref = body.imovel_ref.strip()
    if await _run(_obter, ref):
        raise HTTPException(status_code=409, detail="Este imóvel já tem landing page.")

    imovel = await _run(carregar_imovel, ref)
    if not imovel:
        raise HTTPException(status_code=404, detail="Imóvel não encontrado.")

    try:
        return await _gerar_e_gravar(
            {"mostrar_preco": body.mostrar_preco, "extras": body.extras}, imovel
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc))


@painel.put("/landing-pages/{imovel_ref}")
async def atualizar_landing_page(imovel_ref: str, body: LandingPageUpdate):
    """Guarda os campos do painel e regenera **só se** os dados-fonte mudarem."""
    lp = await _run(_obter, imovel_ref)
    if not lp:
        raise HTTPException(status_code=404, detail="Landing page não encontrada.")
    imovel = await _run(carregar_imovel, imovel_ref)
    if not imovel:
        raise HTTPException(status_code=404, detail="Imóvel não encontrado.")

    if body.mostrar_preco is not None:
        lp["mostrar_preco"] = body.mostrar_preco
    if body.extras is not None:
        lp["extras"] = body.extras

    novo_hash = fonte_hash(imovel, lp.get("extras") or {}, bool(lp["mostrar_preco"]))
    if novo_hash == lp.get("fonte_hash"):
        def _update():
            return (
                get_supabase()
                .table(TABLE)
                .update({
                    "mostrar_preco": lp["mostrar_preco"],
                    "extras": lp.get("extras") or {},
                    "atualizado_em": _now(),
                })
                .eq("imovel_ref", imovel_ref)
                .execute()
            )

        resp = await _run(_update)
        return resp.data[0] if resp.data else lp

    try:
        return await _gerar_e_gravar(lp, imovel)
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc))


@painel.post("/landing-pages/{imovel_ref}/regenerar")
async def regenerar_landing_page(imovel_ref: str, forcar: bool = False):
    """Sem `forcar`, não gasta API se o imóvel não mudou desde a última geração."""
    lp = await _run(_obter, imovel_ref)
    if not lp:
        raise HTTPException(status_code=404, detail="Landing page não encontrada.")
    imovel = await _run(carregar_imovel, imovel_ref)
    if not imovel:
        raise HTTPException(status_code=404, detail="Imóvel não encontrado.")

    novo_hash = fonte_hash(imovel, lp.get("extras") or {}, bool(lp["mostrar_preco"]))
    if not forcar and novo_hash == lp.get("fonte_hash"):
        return {**lp, "regenerado": False}

    try:
        return {**await _gerar_e_gravar(lp, imovel), "regenerado": True}
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc))


@painel.delete("/landing-pages/{imovel_ref}", status_code=204)
async def apagar_landing_page(imovel_ref: str):
    def _delete():
        return get_supabase().table(TABLE).delete().eq("imovel_ref", imovel_ref).execute()

    await _run(_delete)
