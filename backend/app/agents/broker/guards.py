"""Regras de negócio que não podem depender do modelo.

Duas guardas, ambas da spec `assistentes-ia-especificacao.md`:

* **Deduplicação de clientes** (§2.7) — regra transversal a todos os
  assistentes: pesquisar sempre antes de criar, por telefone -> email -> nome.
  Todos os caminhos de escrita passam por `find_or_create_cliente`; é essa
  partilha que a torna eficaz. Antes desta função havia quatro upserts
  artesanais quase iguais (WhatsApp, voz, e cada tool que gravava cliente).

* **Regra dos 80%** (§3.2 SV) — não marcar visita se o orçamento declarado
  for inferior a 80% do preço de venda. Aplicada dentro de `agendar_visita`,
  antes de qualquer escrita: o modelo fica impedido de marcar, em vez de ser
  apenas instruído a não o fazer.
"""

import asyncio
import logging
import re

from app.db.supabase_client import get_supabase

logger = logging.getLogger(__name__)

_LIMIAR_VISITA = 0.80

_SO_DIGITOS = re.compile(r"\D+")


def normalizar_telefone(raw: str | None) -> str | None:
    """Reduz um número português à sua forma nacional de 9 dígitos.

    A Meta entrega `351912345678`, o cliente escreve `+351 912 345-678` e o
    painel guarda `912345678` — todos a mesma pessoa.
    Números não-portugueses ficam só sem pontuação.
    """
    if not raw:
        return None
    digitos = _SO_DIGITOS.sub("", raw)
    digitos = digitos.lstrip("0")  # prefixo internacional 00; nº PT nunca começa por 0
    if len(digitos) > 9 and digitos.startswith("351"):
        digitos = digitos[3:]
    return digitos or None


def normalizar_email(raw: str | None) -> str | None:
    if not raw:
        return None
    return raw.strip().lower() or None


def variantes_telefone(numero: str) -> list[str]:
    """Formatos sob os quais o mesmo número pode já estar gravado.

    As linhas existentes em produção guardam o que a Meta enviou. Normalizar
    só para a frente faria os lookups novos falharem e duplicarem o cliente.
    """
    return [numero, f"351{numero}", f"+351{numero}", f"00351{numero}"]


def visita_permitida(orcamento: float | None, preco: float | None) -> bool:
    """Regra dos 80% (spec §3.2 SV).

    Limiar inclusivo: a spec dá o exemplo de €240k sobre €300k a avançar
    (com ressalva verbal do assistente). Sem orçamento declarado recusa —
    a spec manda insistir e, se o cliente persistir, escalar.
    Sem preço recusa também, em vez de dividir por zero.
    """
    if not orcamento or not preco or preco <= 0:
        return False
    return orcamento / preco >= _LIMIAR_VISITA


def _procurar_cliente(supabase, telefone: str | None, email: str | None, nome: str | None):
    """Telefone -> email -> nome, a ordem de prioridade da spec §2.7."""
    if telefone:
        resp = (
            supabase.table("agente_clientes")
            .select("id,nome,telefone,email")
            .in_("telefone", variantes_telefone(telefone))
            .limit(1)
            .execute()
        )
        if resp.data:
            return resp.data[0]

    if email:
        resp = (
            supabase.table("agente_clientes")
            .select("id,nome,telefone,email")
            .eq("email", email)
            .limit(1)
            .execute()
        )
        if resp.data:
            return resp.data[0]

    # Nome é só confirmação (spec §2.7) — mas é preciso tentá-lo mesmo quando
    # há telefone ou email que não deram correspondência.
    #
    # Bug real (2026-08-03): `guardar_dados_cliente` gravava o nome sem
    # telefone (o modelo nem sempre o passa) e, no turno seguinte,
    # `agendar_visita` trazia o telefone. A procura por telefone falhava e a
    # procura por nome era saltada — duas linhas para a mesma pessoa. É o
    # padrão normal de uma conversa: dados parciais primeiro, completos depois.
    #
    # Só se aceita a correspondência por nome quando o registo encontrado
    # **não contradiz** os identificadores que trazemos: telefone/email vazios
    # ou iguais. Dois "João Silva" com telefones diferentes continuam a ser
    # duas pessoas — a spec proíbe fundir por nome sozinho.
    if nome:
        resp = (
            supabase.table("agente_clientes")
            .select("id,nome,telefone,email")
            .ilike("nome", nome.strip())
            .limit(5)
            .execute()
        )
        for candidato in resp.data or []:
            if _compativel(candidato, telefone, email):
                return candidato

    return None


def _compativel(candidato: dict, telefone: str | None, email: str | None) -> bool:
    """O candidato pode ser a mesma pessoa? Só se nada contradisser."""
    tel_c = normalizar_telefone(candidato.get("telefone"))
    if telefone and tel_c and tel_c != telefone:
        return False
    email_c = normalizar_email(candidato.get("email"))
    if email and email_c and email_c != email:
        return False
    return True


async def find_or_create_cliente(
    nome: str | None = None,
    telefone: str | None = None,
    email: str | None = None,
    **campos,
) -> dict | None:
    """Devolve o cliente existente (actualizado) ou cria um novo.

    Devolve `None` quando não há identificador nenhum — é assim que o banco
    de ensaio do painel (participante `painel_a1_vendedor`, sem telefone)
    não polui `agente_clientes`.
    """
    telefone = normalizar_telefone(telefone)
    email = normalizar_email(email)
    if not telefone and not email and not nome:
        return None

    dados = {"nome": nome, "telefone": telefone, "email": email, **campos}
    dados = {k: v for k, v in dados.items() if v is not None}

    def _run():
        supabase = get_supabase()
        existente = _procurar_cliente(supabase, telefone, email, nome)

        if existente:
            resp = (
                supabase.table("agente_clientes")
                .update(dados)  # grava já na forma normalizada
                .eq("id", existente["id"])
                .execute()
            )
            return resp.data[0] if resp.data else existente

        resp = supabase.table("agente_clientes").insert(dados).execute()
        return resp.data[0] if resp.data else None

    try:
        cliente = await asyncio.get_event_loop().run_in_executor(None, _run)
    except Exception:
        logger.exception("Falha ao guardar cliente (telefone=%s)", telefone)
        return None

    if cliente:
        logger.info("Cliente %s (telefone=%s)", cliente.get("id"), telefone)
    return cliente


def demo() -> None:
    """Auto-verificação das funções puras. `python -m app.agents.broker.guards`"""
    assert normalizar_telefone("+351 912 345-678") == "912345678"
    assert normalizar_telefone("00351912345678") == "912345678"
    assert normalizar_telefone("351912345678") == "912345678"
    assert normalizar_telefone("912345678") == "912345678"
    assert normalizar_telefone("") is None
    assert normalizar_telefone(None) is None

    assert normalizar_email("  A@B.COM ") == "a@b.com"
    assert normalizar_email(None) is None

    assert visita_permitida(240000, 300000) is True  # limiar exacto: avança
    assert visita_permitida(239999, 300000) is False
    assert visita_permitida(None, 300000) is False
    assert visita_permitida(100000, None) is False
    assert visita_permitida(100000, 0) is False

    print("guards OK")


if __name__ == "__main__":
    demo()
