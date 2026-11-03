"""Resumo diário das tarefas dos agentes por tratar (`docs/fases/tarefas-pendentes-plano.md`, Parte B).

Ninguém abre o painel das tarefas: o email do momento é o único aviso. Este resumo repete, uma vez por dia, o que
continua pendente entre 12 h e 7 dias. Não fecha nada. Cron `resumo-tarefas-pendentes` (X-Automacao-Secret).
"""
import asyncio
import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException

from app.agents.broker.guards import _TAREFA_QUALIFICADA
from app.api.deps import require_automacao_access
from app.db.supabase_client import get_supabase
from app.notificacoes import notificar

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api")

MIN_HORAS = 12  # antes disto o email do momento ainda é o aviso
JANELA_DIAS = 7  # depois disto só entra na linha «fora da janela» (ninguém as fecha: sem limite, repetiam para sempre)
_TIPOS = ("escalar", "visita", "lead_ego")
_GRUPOS = (
    ("a1_vendedor", "Compra / arrendamento (Matilde)"),
    ("a3_recrutamento", "Recrutamento (Inês)"),
    ("a4_angariador", "Angariação (Bárbara)"),
    ("a2_geral", "Geral (Maria)"),
)


def _dt(valor: str) -> datetime:
    return datetime.fromisoformat(valor.replace("Z", "+00:00"))


def _e_nossa(t: dict) -> bool:
    # as «Lead qualificada…» antigas nasceram sem `tipo`
    return t.get("tipo") in _TIPOS or (t.get("tipo") is None and (t.get("titulo") or "").startswith(_TAREFA_QUALIFICADA))


def selecionar(tarefas: list[dict], agora: datetime) -> tuple[list[dict], int]:
    """(pendentes na janela, mais antigas), só dos tipos que pedem uma pessoa."""
    na_janela, antigas = [], 0
    for t in tarefas:
        if t.get("estado") != "pendente" or not _e_nossa(t):
            continue
        idade = agora - _dt(t["criado_em"])
        if idade >= timedelta(days=JANELA_DIAS):
            antigas += 1
        elif idade >= timedelta(hours=MIN_HORAS):
            na_janela.append(t)
    return na_janela, antigas


def _idade(t: dict, agora: datetime) -> str:
    h = (agora - _dt(t["criado_em"])).total_seconds() / 3600
    return f"{int(h)} h" if h < 48 else f"{int(h // 24)} d"


def texto_do_resumo(tarefas: list[dict], antigas: int, agora: datetime) -> str:
    por_agente: dict[str | None, list[dict]] = {}
    for t in tarefas:
        por_agente.setdefault(t.get("agente"), []).append(t)
    nomes = dict(_GRUPOS)
    ordem = [a for a, _ in _GRUPOS if a in por_agente] + [a for a in por_agente if a not in nomes]
    linhas = [f"{len(tarefas)} tarefa(s) dos assistentes continuam por tratar (criadas há mais de {MIN_HORAS} h, nos últimos {JANELA_DIAS} dias).", ""]
    for a in ordem:
        linhas.append(nomes.get(a, "Leads qualificadas (passar ao eGO)" if a is None else a))
        for t in sorted(por_agente[a], key=lambda x: x["criado_em"]):
            ref = f" · {t['imovel_ref']}" if t.get("imovel_ref") else ""
            linhas.append(f"  - há {_idade(t, agora)} · {t.get('tipo') or 'lead_ego'}{ref} · {(t.get('titulo') or '')[:110]}")
        linhas.append("")
    if antigas:
        linhas.append(f"+{antigas} pendente(s) com mais de {JANELA_DIAS} dias, fora desta lista (continuam abertas no painel).")
    linhas.append("Estas tarefas fecham-se no painel dos agentes; este resumo não as fecha.")
    return "\n".join(linhas)


def ler_pendentes() -> list[dict]:
    return (get_supabase().table("agente_tarefas")
            .select("titulo,tipo,estado,agente,imovel_ref,criado_em").eq("estado", "pendente")
            .order("criado_em").limit(1000).execute().data or [])


@router.post("/tarefas/pendentes/resumo")
async def resumo_de_pendentes(dry: int = 0, acesso=Depends(require_automacao_access)):
    loop = asyncio.get_event_loop()
    agora = datetime.now(timezone.utc)
    try:
        todas = await loop.run_in_executor(None, ler_pendentes)
    except Exception:
        logger.exception("Falha a ler as tarefas pendentes")
        raise HTTPException(status_code=502, detail="Falha a ler as tarefas pendentes.")
    tarefas, antigas = selecionar(todas, agora)
    resposta = {"pendentes": len(tarefas), "fora_da_janela": antigas, "enviado": False}
    if not tarefas:
        return resposta
    texto = texto_do_resumo(tarefas, antigas, agora)
    if dry:
        return resposta | {"texto": texto}
    await loop.run_in_executor(None, lambda: notificar(f"Tarefas por tratar: {len(tarefas)}", texto))
    return resposta | {"enviado": True}
