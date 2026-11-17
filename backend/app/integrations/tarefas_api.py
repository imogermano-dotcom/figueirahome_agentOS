"""Tarefas por fazer do eGO pela API, no formato da tabela `tarefas` (F2.1 de `docs/fases/tarefas-pela-api-plano.md`).

Mesma chave e mesmas colunas que `scraper/tarefas.map_row` (o relatório «tarefas todas»). Medido a 17/11 contra a BD: chave
`(oportunidade_ref, tarefa_titulo, tarefa_due_raw)` 2 049/2 049. Armadilhas que a medição apanhou:
- `dateStart`/`createdDate` vêm em UTC sem fuso: «T23:00:00» no verão é o dia seguinte em Lisboa;
- `rescheduledDate` **não** se converte: a data tal como vem bate 236/236 (convertida, 84 ficavam um dia à frente);
- `tarefa_titulo` é o nome do TIPO (`eventTypeId`), não o `subject`, que é a descrição;
- as tarefas de roteiro de visitas (`VisitRoadMap`) trazem a lead em `objectSecondaryId`.
Só leitura do eGO; quem grava na BD é o sync (F2.2).
"""

from datetime import datetime
from zoneinfo import ZoneInfo

from app.integrations import ego_api

LISBOA = ZoneInfo("Europe/Lisbon")
UTC = ZoneInfo("UTC")
ORIGEM = "todas_as_colunas"
ESTADO_ABERTA = "pendente"
CHAVE = ["oportunidade_ref", "tarefa_titulo", "tarefa_due_raw"]  # = a chave do upsert do relatório


def _lisboa(iso: str | None) -> datetime | None:
    if not iso:
        return None
    try:
        d = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except ValueError:
        return None
    return (d if d.tzinfo else d.replace(tzinfo=UTC)).astimezone(LISBOA)


def data_raw(iso: str | None) -> str | None:
    """`dd/mm/aaaa` de Lisboa, como o relatório (é o que entra na chave)."""
    d = _lisboa(iso)
    return d.strftime("%d/%m/%Y") if d else None


def data_iso(iso: str | None) -> str | None:
    d = _lisboa(iso)
    return d.date().isoformat() if d else None


def lead_id(t: dict) -> int | None:
    """Id da lead da tarefa; `None` para as de imóveis, entidades e processos (o relatório também as deixa de fora)."""
    if t.get("objectName") == "Lead":
        return t.get("objectId")
    return t.get("objectSecondaryId") if t.get("objectSecondaryName") == "Lead" else None


def mapear(t: dict, ref: str, tipos: dict[int, str], utilizadores: dict[int, str], oportunidade: dict | None = None) -> dict:
    """1 tarefa da API → registo de `tarefas`, sem valores vazios. `oportunidade` (linha de `oportunidades`) dá `cliente_nome`,
    `tipo_oportunidade` e `url`, que o relatório copia da oportunidade. Quem criou só vai se o id estiver em `ListEmployees`:
    sem o nome não se escreve nada e a linha existente mantém o que tem."""
    if t.get("eventTypeId") not in tipos:
        raise ego_api.EgoApiErro(f"tipo de tarefa {t.get('eventTypeId')} sem nome em ListTaskType")
    oportunidade = oportunidade or {}
    reag = (t.get("rescheduledDate") or "")[:10] or None
    registo = {
        "oportunidade_ref": ref,
        "tarefa_titulo": tipos[t["eventTypeId"]],
        "tarefa_descricao": t.get("subject"),
        "tarefa_due_raw": data_raw(t.get("dateStart")),
        "tarefa_due_iso": data_iso(t.get("dateStart")),
        "tarefa_responsavel": t.get("assignedSecurityUserName"),
        "tarefa_criado_por": utilizadores.get(t.get("ownerSecurityUserId")),
        "tarefa_status": ESTADO_ABERTA,
        "tarefa_criado_em": data_iso(t.get("createdDate")),
        "tarefa_reagendamento_iso": reag,
        "tarefa_reagendada": "Sim" if t.get("isRescheduled") else None,
        "cliente_nome": oportunidade.get("cliente_nome"),
        "tipo_oportunidade": oportunidade.get("tipo_oportunidade"),
        "url": oportunidade.get("url"),
        "origem_lista": ORIGEM,
    }
    return {k: v for k, v in registo.items() if v not in (None, "")}


def snapshot() -> dict:
    """Lê as pendentes e liga-as às oportunidades. Devolve `brutas` (todas as pendentes da API), `sem_lead` (imóveis, entidades,
    processos: ficam de fora) e `tarefas` já no formato da BD, sem os campos que vêm da oportunidade (o sync junta-os).
    Levanta se faltar um tipo, uma referência ou uma página (nunca se fecha com um snapshot parcial)."""
    api = ego_api.tarefas_pendentes()
    tipos, users = ego_api.tipos_de_tarefa(), ego_api.utilizadores()
    com_lead = [t for t in api if lead_id(t) is not None]
    refs = ego_api.refs_de_leads({lead_id(t) for t in com_lead})
    return {"brutas": len(api), "sem_lead": len(api) - len(com_lead),
            "tarefas": [mapear(t, refs[lead_id(t)], tipos, users) for t in com_lead]}
