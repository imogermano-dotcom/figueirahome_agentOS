"""Lembrete dentro da janela de 24h — quando a Matilde fica sem resposta a
meio de uma conversa activa e ninguém mais toca no assunto.

Frente A de `docs/fases/matilde-followup-plano.md`. Distinto do follow-up por
template (n8n `01`/`02`/`03`): aqui a lead já respondeu pelo menos uma vez, a
conversa está viva, e o que falta é um empurrão de texto livre — por isso a
restrição real não é a nossa TTL de 48h (`conversation.py`), é a janela de
mensagem livre da Cloud API, 24h desde a última mensagem da pessoa. Disparar
perto desse limite arrisca a Meta rejeitar; a janela de disparo fica bem
dentro dela.
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from app.agents.broker import guards
from app.agents.broker.assistants import A1, A3, A4
from app.agents.broker.channels.whatsapp import meta_api
from app.agents.broker.conversation import save_conversation
from app.db.supabase_client import get_supabase
from app.models.lead import ESTADOS_FECHADOS

logger = logging.getLogger(__name__)

_JANELA_MIN_HORAS = 2
_JANELA_MAX_HORAS = 20  # margem de segurança antes das 24h da Cloud API

TEXTO_NUDGE = (
    "Ainda está interessado? Fico a postos para continuar, ou diga-me só que "
    "não para eu não voltar a incomodar."
)

TEXTO_NUDGE_A3 = (
    "Ainda tem interesse em avançar com a candidatura? Fico a postos para "
    "continuar, ou diga-me só que não para eu não voltar a incomodar."
)

TEXTO_NUDGE_A4 = (
    "Ainda tem interesse em avançar com a venda do seu imóvel? Fico a postos "
    "para continuar, ou diga-me só que não para eu não voltar a incomodar."
)

# Os detetores de despedida/agradecimento/recusa vivem em `guards` (o motor também os usa). Nomes antigos mantidos.
_e_despedida = guards.e_despedida
_e_agradecimento = guards.e_agradecimento


async def _pode_enviar_a1(telefone: str | None) -> bool:
    """Só recusa quando há mesmo lead **fechada**, **pausada** ou já entregue
    a um humano.

    Não usar `guards.lead_aberta`: devolve `None` tanto para "nunca houve
    lead" como para "lead fechada" — indistinguíveis, e é precisamente a
    primeira categoria que mais precisa do nudge. Achado ao vivo (2026-09-09):
    o caso que motivou esta funcionalidade (proposta de 110 000€ ao FH2571,
    nome/telefone nunca chegaram a ser pedidos com sucesso) nunca teve
    `cliente_id` nem `leads` associada — com `lead_aberta` ficaria sempre de
    fora, o oposto do que se queria.

    `pausa` (achado 28/09, Sandra Nascimento — pediu para não ser contactada
    por 60 dias) fica FORA de `ESTADOS_FECHADOS` de propósito (routing tem de
    a reconhecer quando ela voltar) — por isso o nudge trata-a à parte aqui,
    e não com o resto dos fechados.
    """
    numero = guards.normalizar_telefone(telefone)
    if not numero:
        return True

    def _fetch():
        return (
            get_supabase()
            .table("leads")
            .select("estado,contacto_humano_em")
            .in_("telefone", guards.variantes_telefone(numero))
            .order("criado_em", desc=True)
            .limit(1)
            .execute()
        )

    resp = await asyncio.get_event_loop().run_in_executor(None, _fetch)
    if not resp.data:
        return True  # nunca houve lead — nada a respeitar, nada a apagar
    lead = resp.data[0]
    if lead.get("estado") in ESTADOS_FECHADOS or lead.get("estado") == "pausa":
        return False
    return not lead.get("contacto_humano_em")


# Config por assistente — "um motor, N assistentes", mesmo princípio do
# resto do broker. `guarda` é opcional: A3/A4 não têm hoje nenhum sinal de
# "conversa encerrada" em `contactos` (nada escreve lá um estado fechado),
# por isso ficam só com a detecção de despedida — travão real, não código
# morto à espera de um `estado` que ninguém grava.
_AGENTES = {
    A1: {"texto": TEXTO_NUDGE, "log_tipo": "nudge_matilde", "guarda": _pode_enviar_a1},
    A3: {"texto": TEXTO_NUDGE_A3, "log_tipo": "nudge_ines", "guarda": None},
    A4: {"texto": TEXTO_NUDGE_A4, "log_tipo": "nudge_barbara", "guarda": None},
}


async def _conversas_escaladas(ids: list[str]) -> set[str]:
    """Conversas cujo caso já foi entregue a um humano (`escalar_para_humano`).

    Sinal gravado em código, não pelo modelo — ao contrário de `_MARCAS_FECHO`,
    que falha com cada despedida nova ("Boa semana! 🌟", achado 05/10: a Inês
    despediu-se de uma candidata já escalada e o nudge perguntou-lhe, 3h
    depois, se ainda queria avançar). Uma query para todas as conversas.

    Falha fechado: sem saber, não se envia — um nudge a menos custa menos do
    que um nudge indevido.
    """
    if not ids:
        return set()

    def _fetch():
        return (
            get_supabase()
            .table("agente_tarefas")
            .select("conversa_id")
            .in_("conversa_id", ids)
            .eq("tipo", "escalar")
            .execute()
        )

    try:
        resp = await asyncio.get_event_loop().run_in_executor(None, _fetch)
    except Exception:
        logger.exception("Falha a consultar escaladas — nenhum nudge nesta volta")
        return set(ids)
    return {t["conversa_id"] for t in resp.data}


async def _numeros_sem_contacto(participantes: list[str]) -> set[str]:
    """Números (9 dígitos) que recusaram: `contactos.nao_contactar_em` preenchido (`encerrar_lead` ou opt-out explícito).
    Vale para os 3 assistentes e para contactos sem linha em `leads` (angariação e recrutamento), que era o buraco do
    pedido #49 (24/10). Falha fechado: sem saber, não se envia nada nesta volta."""
    numeros = {n for n in (guards.normalizar_telefone(p) for p in participantes) if n}
    if not numeros:
        return set()
    variantes = [v for n in numeros for v in guards.variantes_telefone(n)]
    lista = ",".join(variantes)

    def _fetch():
        return (
            get_supabase().table("contactos").select("telefone,telemovel")
            .or_(f"telefone.in.({lista}),telemovel.in.({lista})").not_.is_("nao_contactar_em", "null").execute()
        )

    try:
        resp = await asyncio.get_event_loop().run_in_executor(None, _fetch)
    except Exception:
        logger.exception("Falha a consultar nao_contactar_em — nenhum nudge nesta volta")
        return set(numeros)
    return {n for r in resp.data for n in (guards.normalizar_telefone(r.get("telefone")), guards.normalizar_telefone(r.get("telemovel"))) if n}


async def _candidatos(agente: str, guarda) -> list[dict]:
    agora = datetime.now(timezone.utc)
    desde = (agora - timedelta(hours=_JANELA_MAX_HORAS)).isoformat()
    ate = (agora - timedelta(hours=_JANELA_MIN_HORAS)).isoformat()

    def _fetch():
        return (
            get_supabase()
            .table("agente_conversas")
            .select("id,participante,mensagens")
            .eq("agente", agente)
            .eq("canal", "whatsapp")
            .is_("nudge_em", "null")
            .gte("atualizado_em", desde)
            .lte("atualizado_em", ate)
            .execute()
        )

    resp = await asyncio.get_event_loop().run_in_executor(None, _fetch)
    escaladas = await _conversas_escaladas([r["id"] for r in resp.data])
    recusaram = await _numeros_sem_contacto([r["participante"] for r in resp.data])

    candidatos = []
    for row in resp.data:
        if row["id"] in escaladas or guards.normalizar_telefone(row["participante"]) in recusaram:
            continue
        mensagens = row.get("mensagens") or []
        if not mensagens:
            continue
        ultima = mensagens[-1]
        if ultima.get("role") != "assistant":
            continue
        if _e_despedida(ultima.get("content", "")):
            continue
        da_pessoa = next((m for m in reversed(mensagens) if m.get("role") == "user"), None)
        if da_pessoa and (_e_agradecimento(da_pessoa.get("content", "")) or guards.e_recusa(da_pessoa.get("content", ""))):
            continue
        if guarda is not None and not await guarda(row["participante"]):
            continue
        candidatos.append(row)
    return candidatos


async def enviar_nudges(agente: str) -> dict:
    config = _AGENTES[agente]
    texto, log_tipo, guarda = config["texto"], config["log_tipo"], config["guarda"]

    candidatos = await _candidatos(agente, guarda)
    enviados = 0
    erros = 0
    detalhes: list[dict] = []
    now = datetime.now(timezone.utc).isoformat()

    for row in candidatos:
        try:
            await meta_api.send_text_message(row["participante"], texto)
            mensagens = [*row["mensagens"], {"role": "assistant", "timestamp": now, "content": texto}]
            await save_conversation(row["id"], "whatsapp", row["participante"], mensagens, agente)

            def _marcar(conversa_id=row["id"]):
                get_supabase().table("agente_conversas").update({"nudge_em": now}).eq("id", conversa_id).execute()

            await asyncio.get_event_loop().run_in_executor(None, _marcar)
            enviados += 1
            detalhes.append({"conversa_id": row["id"], "participante": row["participante"], "tipo": "enviado"})
        except Exception:
            logger.exception("Falha a enviar nudge para a conversa %s", row["id"])
            erros += 1
            detalhes.append({"conversa_id": row["id"], "tipo": "erro"})

    resumo = {"candidatos": len(candidatos), "enviados": enviados, "erros": erros}

    def _log():
        return get_supabase().table("agente_sync_log").insert({
            "tipo": log_tipo, "resumo": resumo, "detalhes": detalhes, "origem": "cron",
        }).execute()

    try:
        await asyncio.get_event_loop().run_in_executor(None, _log)
    except Exception:
        logger.exception("Falha a gravar o log do nudge — o envio em si correu.")

    return resumo


async def enviar_todos_nudges() -> dict:
    resultados = {}
    for agente in _AGENTES:
        resultados[agente] = await enviar_nudges(agente)
    return resultados


def demo() -> None:
    assert _e_despedida("Cuide-se, Maria. Até quando precisar! 👋")
    assert _e_despedida("Boa continuação, João! 😊")
    assert not _e_despedida("Antes de lhe dar o preço, só duas perguntas rápidas:")
    assert _e_agradecimento("Obrigado.") and not _e_agradecimento("Obrigado, mas e o preço?")
    print("nudge.demo: ok")


if __name__ == "__main__":
    demo()
