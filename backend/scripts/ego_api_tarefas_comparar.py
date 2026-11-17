"""F2.0 (`docs/fases/tarefas-pela-api-plano.md`): compara as tarefas pendentes da API do eGO com as da BD. SÓ LEITURA.

Corre de `backend/`: `python scripts/ego_api_tarefas_comparar.py`. Não escreve na BD nem no eGO, e não imprime texto de tarefas,
nomes nem contactos: só contagens e referências de oportunidades (`VEN_…`).

Achados que o script confirma (17/11): `eventStatusIds` filtra; `searchList`/`searchCount` (não `totalRows`); `dateStart` vem sem fuso
e é UTC (converter para Lisboa); `tarefa_titulo` = nome do tipo (`ListTaskType`, `name["PT-PT"]`), não o `subject`, que é a descrição.
"""

import collections
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.supabase_client import get_supabase  # noqa: E402
from app.integrations import ego_api  # noqa: E402

LISBOA = ZoneInfo("Europe/Lisbon")
UTC = ZoneInfo("UTC")
ABERTAS_API = [1, 4]  # Pending, InProgress
ORIGEM = "todas_as_colunas"


def _lista(d) -> list[dict]:
    return d if isinstance(d, list) else next((v for v in d.values() if isinstance(v, list)), [])


def ler_tarefas(filtro: dict, por: int = 500) -> tuple[list[dict], int | None]:
    todas, pagina, total = [], 0, None
    while True:
        d = ego_api._pedido("POST", "/task/Task/ListTaskByPage", json={"pageIndex": pagina, "numberOfRecords": por, **filtro})
        lote = d["searchList"]
        total = d.get("searchCount", total)
        todas += lote
        if len(lote) < por:
            return todas, total
        pagina += 1


def com_espera(pedido, tentativas: int = 8):
    """O eGO responde 429 ao fim de umas dezenas de pedidos (`retry_after_seconds` 60): espera e repete."""
    for i in range(tentativas):
        try:
            return pedido()
        except ego_api.EgoApiErro as e:
            if "429" not in str(e) or i == tentativas - 1:
                raise
            time.sleep(65)


def data_lisboa(iso: str | None) -> str | None:
    """`dd/mm/aaaa` de Lisboa, o formato do relatório. A API manda instantes UTC sem fuso: «T23:00:00» no verão é a meia-noite seguinte."""
    if not iso:
        return None
    try:
        d = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except ValueError:
        return None
    return (d if d.tzinfo else d.replace(tzinfo=UTC)).astimezone(LISBOA).strftime("%d/%m/%Y")


def iso_lisboa(iso: str | None) -> str | None:
    d = data_lisboa(iso)
    return f"{d[6:]}-{d[3:5]}-{d[:2]}" if d else None


def bd_tarefas() -> list[dict]:
    out, desde = [], 0
    while True:
        lote = (get_supabase().table("tarefas")
                .select("id,oportunidade_ref,tarefa_titulo,tarefa_due_raw,tarefa_due_iso,tarefa_status,tarefa_descricao,"
                        "tarefa_responsavel,tarefa_criado_por,tarefa_criado_em,tarefa_reagendamento_iso,origem_lista")
                .eq("tarefa_status", "pendente").order("id").range(desde, desde + 999).execute().data)
        out += lote
        if len(lote) < 1000:
            return out
        desde += 1000


def norm(t: str | None) -> str:
    return re.sub(r"\s+", " ", (t or "")).strip()


def pct(a: int, b: int) -> str:
    return f"{a}/{b} ({100 * a / b:.1f}%)" if b else f"{a}/0"


def main() -> None:
    print("== 1. API: pendentes (eventStatusIds=[1,4])")
    api, total = ler_tarefas({"eventStatusIds": ABERTAS_API})
    por_estado = {e: ego_api._pedido("POST", "/task/Task/ListTaskByPage",
                                      json={"pageIndex": 0, "numberOfRecords": 1, "eventStatusIds": [e]}).get("searchCount") for e in range(1, 7)}
    print(f"linhas {len(api)}, searchCount {total}; contagem por estado (1 Pend, 2 Concl, 3 Canc, 4 EmCurso, 5 NãoAplic, 6 Arquiv): {por_estado}")
    print("estados devolvidos:", dict(collections.Counter(t["eventStatusId"] for t in api)))
    print("objectName:", dict(collections.Counter(t.get("objectName") for t in api)),
          "| secundário das de roteiro de visitas:", dict(collections.Counter(t.get("objectSecondaryName") for t in api if t["objectName"] == "VisitRoadMap")))
    print("horas de dateStart:", collections.Counter((t.get("dateStart") or "")[10:19] for t in api).most_common(4), "| com fuso:",
          sum(1 for t in api if re.search(r"(Z|[+-]\d\d:\d\d)$", t.get("dateStart") or "")))

    print("== 2. objectId -> referência da oportunidade")
    mapa = {o["id"]: o["name"] for o in ego_api.oportunidades_ativas() if o.get("name")}
    n_ativas = len(mapa)
    pagina = 0
    while True:  # as arquivadas (19 mil) em páginas, a esperar pelo 429; só se guarda `id` e `name`
        d = com_espera(lambda: ego_api._pedido("POST", "/lead/Opportunity/ListOpportunityByPage",
                                               json={"leadArchived": 1, "pageIndex": pagina, "numberOfRecords": 500}))
        lote = d["opportunities"]
        mapa.update({o["id"]: o["name"] for o in lote if o.get("name")})
        if len(lote) < 500:
            break
        pagina += 1
    print(f"ids {n_ativas} ativas + {len(mapa) - n_ativas} arquivadas")

    def lead_id(t):
        return t["objectId"] if t["objectName"] == "Lead" else (t.get("objectSecondaryId") if t.get("objectSecondaryName") == "Lead" else None)

    ids = {lead_id(t) for t in api} - {None}
    orfaos = sorted(i for i in ids if i not in mapa)
    for i in orfaos:  # `GetOpportunity` resolve o que a listagem não devolve (leads arquivadas com isOpportunity 2)
        nome = (com_espera(lambda: ego_api._pedido("GET", "/lead/Opportunity/GetOpportunity", params={"opportunityId": i})) or {}).get("name")
        if nome:
            mapa[i] = nome
    print(f"ids de lead nas tarefas {len(ids)}; fora da listagem {len(orfaos)}, resolvidos por GetOpportunity {sum(1 for i in orfaos if i in mapa)}")
    sem_ref = [t for t in api if lead_id(t) is None]
    print(f"tarefas sem lead (imóveis, entidades, processos): {len(sem_ref)} {dict(collections.Counter(t['objectName'] for t in sem_ref))}")

    print("== 3. tipos e utilizadores")
    tipos = {x["id"]: (x["name"].get("PT-PT") if isinstance(x["name"], dict) else x["name"]) for x in _lista(ego_api._pedido("GET", "/task/TaskMetadata/ListTaskType"))}
    sem_tipo = {t["eventTypeId"] for t in api} - set(tipos)
    print(f"tipos {len(tipos)}, usados nas pendentes {len({t['eventTypeId'] for t in api})}, sem nome {sorted(sem_tipo)}")
    func = _lista(ego_api._pedido("GET", "/organization/SecurityUser/ListEmployees"))
    nomes = {f["id"]: norm(f"{f.get('entityFirstName') or ''} {f.get('entityLastName') or ''}") for f in func}

    print("== 4. BD: pendentes")
    bd = bd_tarefas()
    nossas = [r for r in bd if r["origem_lista"] == ORIGEM]
    legado = [r for r in bd if r["origem_lista"] != ORIGEM]
    print(f"pendentes {len(bd)}: nossas {len(nossas)}, outras origens {len(legado)} {dict(collections.Counter(r['origem_lista'] for r in legado))}")

    print("== 5. chave (oportunidade_ref, titulo, due_raw)")
    api_ch: dict[tuple, list[dict]] = collections.defaultdict(list)
    for t in api:
        i = lead_id(t)
        if i in mapa:
            api_ch[(mapa[i], tipos.get(t["eventTypeId"]), data_lisboa(t.get("dateStart")))].append(t)
    bd_ch = {(r["oportunidade_ref"], r["tarefa_titulo"], r["tarefa_due_raw"]): r for r in nossas}
    comum = api_ch.keys() & bd_ch.keys()
    so_api, so_bd = api_ch.keys() - bd_ch.keys(), bd_ch.keys() - api_ch.keys()
    print(f"API {len(api_ch)} chaves ({sum(len(v) for v in api_ch.values())} tarefas; {sum(1 for v in api_ch.values() if len(v) > 1)} chaves com mais de 1 tarefa), "
          f"BD {len(bd_ch)}; iguais {pct(len(comum), len(bd_ch))}; só API {len(so_api)}; só BD {len(so_bd)}")
    refs_bd = {r["oportunidade_ref"] for r in get_supabase().table("oportunidades").select("oportunidade_ref")
               .in_("oportunidade_ref", sorted({k[0] for k in so_api})[:900]).execute().data} if so_api else set()
    print(f"só API: com oportunidade em `oportunidades` {sum(1 for k in so_api if k[0] in refs_bd)}, sem (FK, ficam saltadas) {sum(1 for k in so_api if k[0] not in refs_bd)}")
    print("só BD (iriam fechar-se):", len(so_bd), sorted({k[0] for k in so_bd})[:15])

    print("== 6. campos, nas chaves em comum")
    c = collections.Counter()
    for k in comum:
        a, b = api_ch[k][0], bd_ch[k]
        c["descrição (subject)"] += norm(a.get("subject")) == norm(b.get("tarefa_descricao"))
        c["responsável"] += norm(a.get("assignedSecurityUserName")) == norm(b.get("tarefa_responsavel"))
        c["criado por (ListEmployees)"] += nomes.get(a.get("ownerSecurityUserId")) == norm(b.get("tarefa_criado_por"))
        c["criado em"] += iso_lisboa(a.get("createdDate")) == b.get("tarefa_criado_em")
        c["data de agendamento (iso)"] += iso_lisboa(a.get("dateStart")) == b.get("tarefa_due_iso")
        c["reagendamento"] += iso_lisboa(a.get("rescheduledDate")) == b.get("tarefa_reagendamento_iso")
    for nome, n in c.items():
        print(f"{nome}: {pct(n, len(comum))}")

    print("== 7. pendentes legadas (outras origens) contra a API")
    refs_api = {k[0] for k in api_ch}
    com_ref = sum(1 for r in legado if r["oportunidade_ref"] in refs_api)
    print(f"legadas {len(legado)}: oportunidade com alguma pendente na API {com_ref}; sem nenhuma na API {len(legado) - com_ref}")


if __name__ == "__main__":
    main()
