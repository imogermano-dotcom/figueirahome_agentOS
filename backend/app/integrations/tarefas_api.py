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
        "ego_id": t.get("id"),  # F2.5 (migration 0060): a chave de upsert continua a ser `CHAVE`, o id só se grava
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


ESTADO_FECHADA = "concluida"
LIMITE_FECHO_MIN = 50  # travão: fechar mais de max(50, 5% das abertas) aborta (hoje fecha ~3 por dia)
_LOTE = 200


def _paginar(consulta) -> list[dict]:
    """`consulta(inicio, fim)` devolve um lote; ordenado, senão a paginação do PostgREST salta e repete linhas."""
    out, inicio = [], 0
    while True:
        lote = consulta(inicio, inicio + 999)
        out += lote
        if len(lote) < 1000:
            return out
        inicio += 1000


def _chave(t: dict) -> tuple:
    return tuple(t.get(c) for c in CHAVE)


def _gravar(sb, registos: list[dict]) -> int:
    """Upsert por lotes **do mesmo conjunto de colunas**: uma coluna presente num só registo do lote escreveria NULL nos outros
    (o `tarefa_criado_por` falta nas de utilizadores que já saíram do eGO)."""
    grupos: dict[frozenset, list[dict]] = {}
    for r in registos:
        grupos.setdefault(frozenset(r), []).append(r)
    for grupo in grupos.values():
        for i in range(0, len(grupo), _LOTE):
            sb.table("tarefas").upsert(grupo[i:i + _LOTE], on_conflict=",".join(CHAVE)).execute()
    return len(registos)


def sincronizar(sb, dry: bool = True) -> dict:
    """Snapshot das pendentes pela API → `tarefas`: upsert, fecha as nossas `pendente` que saíram e propaga o `contacto_id`.
    Mesmas chaves de resumo que o scraper (`activas`, `com_ref`, `gravadas`, `fechadas`, `contacto_id`) mais `via: "api"`.
    `dry` só conta. Levanta (sem escrever) se o snapshot falhar ou se fechasse demais."""
    snap = snapshot()
    opps = {o["oportunidade_ref"]: o for o in _paginar(lambda a, b: sb.table("oportunidades")
            .select("oportunidade_ref,cliente_nome,tipo_oportunidade,url").order("oportunidade_ref").range(a, b).execute().data)}
    unicas = {_chave(t): t for t in snap["tarefas"]}  # a última ganha, como o relatório
    com_fk = [t | {k: v for k, v in opps[t["oportunidade_ref"]].items() if k != "oportunidade_ref" and v not in (None, "")}
              for t in unicas.values() if t["oportunidade_ref"] in opps]
    sem_fk = len(unicas) - len(com_fk)
    abertas = _paginar(lambda a, b: sb.table("tarefas").select("id," + ",".join(CHAVE)).eq("origem_lista", ORIGEM)
                       .eq("tarefa_status", ESTADO_ABERTA).order("id").range(a, b).execute().data)
    vistas = {_chave(t) for t in com_fk}
    fechar = [e for e in abertas if _chave(e) not in vistas]
    limite = max(LIMITE_FECHO_MIN, len(abertas) // 20)
    resumo = {"via": "api", "activas": snap["brutas"], "sem_lead": snap["sem_lead"], "com_ref": len(com_fk), "sem_fk": sem_fk,
              "colisoes_chave": len(snap["tarefas"]) - len(unicas),  # tarefas que partilham a chave: só a última fica (o `ego_id` distingue-as)
              "abertas_nossas": len(abertas), "a_fechar": len(fechar), "limite_fecho": limite}
    if len(fechar) > limite:
        raise ego_api.EgoApiErro(f"travão: fecharia {len(fechar)} tarefas (limite {limite}), nada gravado — {resumo}")
    if dry:
        existentes = {_chave(r) for r in _paginar(lambda a, b: sb.table("tarefas").select(",".join(CHAVE)).order("id").range(a, b).execute().data)}
        ja = sum(1 for t in com_fk if _chave(t) in existentes)
        return resumo | {"a_atualizar": ja, "a_inserir": len(com_fk) - ja, "gravadas": 0, "fechadas": 0, "dry": True}
    gravadas = _gravar(sb, com_fk)
    for e in fechar:
        sb.table("tarefas").update({"tarefa_status": ESTADO_FECHADA}).eq("id", e["id"]).execute()
    try:  # best-effort, como no scraper: sem a migration 0046 a RPC não existe e o sync não pode falhar
        propagado = sb.rpc("propagar_contacto_id", {}).execute().data
    except Exception:
        propagado = None
    return resumo | {"gravadas": gravadas, "fechadas": len(fechar), "contacto_id": propagado}


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
