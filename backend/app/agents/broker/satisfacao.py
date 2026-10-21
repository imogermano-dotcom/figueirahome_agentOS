"""Envio do inquérito de satisfação pós-venda (A5 "Sofia").

A fila vive no portal (`public.satisfacao_inqueritos`, criada todos os dias por `fn_satisf_gerar`);
`fn_satisf_para_enviar` só devolve linhas com o interruptor ligado e entre as 9h e as 20h de Lisboa.
Para cada uma: template aprovado com `{{1}}` = primeiro nome, conversa semeada com o mesmo texto
(agente `a5_satisfacao`, para a Sofia saber o que "disse" e o encaminhamento ficar com ela) e o envio
marcado. Plano: `docs/fases/satisfacao-pos-venda-plano.md`.
"""

import asyncio
import logging
import re
from datetime import datetime, timezone

from app.agents.broker.assistants import A5
from app.agents.broker.channels.whatsapp import meta_api
from app.agents.broker.conversation import save_conversation
from app.db.supabase_client import get_supabase

logger = logging.getLogger(__name__)

_TELEMOVEL_PT = re.compile(r"^9\d{8}$")
_POR_CORRIDA = 20


def texto_do_template(texto: str, primeiro_nome: str) -> str:
    """O texto aprovado com o `{{1}}` preenchido — é o que se semeia na conversa."""
    return (texto or "").replace("{{1}}", primeiro_nome)


def _rpc(fn: str, params: dict):
    return get_supabase().rpc(fn, params).execute().data


async def _marcar(inq_id: str, ok: bool, erro: str | None = None, texto: str | None = None) -> None:
    await asyncio.get_event_loop().run_in_executor(
        None, _rpc, "fn_satisf_marcar_envio", {"p_id": inq_id, "p_ok": ok, "p_erro": erro, "p_texto": texto},
    )


async def enviar_inqueritos() -> dict:
    fila = await asyncio.get_event_loop().run_in_executor(
        None, _rpc, "fn_satisf_para_enviar", {"p_limite": _POR_CORRIDA},
    ) or []
    enviados, erros = 0, 0
    for inq in fila:
        telefone = re.sub(r"\D", "", inq.get("telefone") or "")
        tpl = inq.get("template") or {}
        nome = (inq.get("primeiro_nome") or "").strip()
        problema = None
        if not _TELEMOVEL_PT.match(telefone):
            problema = "não é telemóvel português — contactar à mão"
        elif not (tpl.get("nome") and tpl.get("texto")):
            problema = "template não configurado"
        elif not nome:
            problema = "sem nome para o template — pôr o nome no eGO e reactivar"
        if problema:
            await _marcar(inq["id"], False, problema)
            erros += 1
            continue

        ok, detalhe = await meta_api.send_template(
            "351" + telefone, tpl["nome"], tpl.get("lingua") or "pt_PT", [nome],
        )
        if not ok:
            await _marcar(inq["id"], False, detalhe)
            erros += 1
            continue

        texto = texto_do_template(tpl["texto"], nome)
        try:
            await save_conversation(None, "whatsapp", "351" + telefone, [{
                "role": "assistant", "content": texto, "timestamp": datetime.now(timezone.utc).isoformat(),
            }], agente=A5)
        except Exception:
            # O template já saiu: o envio conta. Sem a thread semeada, o contexto da Sofia injecta o
            # template no 1.º turno (engine._contexto_satisfacao).
            logger.exception("Falha a semear a conversa do inquérito %s", inq["id"])
        await _marcar(inq["id"], True, None, texto)
        enviados += 1
    return {"na_fila": len(fila), "enviados": enviados, "erros": erros}
