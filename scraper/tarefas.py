"""Scraper dedicado ao relatório eGO "tarefas todas" — traz TODAS as tarefas
(pendentes/"Em Curso", não só as concluídas), ao contrário do relatório de
Oportunidades que só mostra tarefas concluídas, disfarçadas de nota
(`nota_tipo = "Tarefa concluída"`, achado 28/09).

Confirmado ao vivo com um ficheiro real (`docs/tarefas todas_6429.xlsx`,
28 linhas): a tarefa pendente da CAP_22235 ("Outro", Alexsandra Ferreira,
"Em Curso") está lá, ausente de 3 relatórios de Oportunidades diferentes
testados antes. Relatório "wide" mas achatado — 1 linha por tarefa, sem o
esquema de blocos/ocorrências do de Oportunidades: os campos vêm por nome
directo, sem alias.

Linhas sem `Referência` (tarefas internas, sem oportunidade associada —
12 de 28 no ficheiro de teste) são ignoradas: sem FK para onde ligar.

Mesma técnica de download que `oportunidades_completo.py` (report/export
directo, sem depender do popup) — reaproveita `_trigger_and_download`.

Sincroniza o SNAPSHOT das tarefas activas (2190 a 29/09; o eGO só dá download
directo até ~1000, por isso em fatias por data de criação) e fecha as nossas
"Em Curso" que já não lá estão. Plano e limites: docs/fases/tarefas-sync-plano.md

Correr localmente a partir de scraper/:
    python tarefas.py              # auto-teste (sem rede)
    python tarefas.py sync --dry   # descarrega e mostra, não escreve
    python tarefas.py sync         # escreve em `tarefas` (produção)
"""
import asyncio
import datetime
import functools
import re
import sys

import oportunidades_completo as oc

REPORT_NAME = "tarefas todas"
PAGE_PATH = "/egocore/tasks"
LIMITE_FATIA = 900  # o eGO manda por email acima de ~1000 linhas
INICIO = datetime.date(2000, 1, 1)
# Vocabulário que a tabela `tarefas` já tem (29/09: 'pendente' 5480, 'concluida' 17856;
# o mapping antigo emite "Em Curso"/"Concluído" e algo fora do repo normaliza).
ESTADO_ABERTA = "pendente"
ESTADO_FECHADA = "concluida"
_ESTADOS = {"Em Curso": ESTADO_ABERTA, "Pendente": ESTADO_ABERTA, "Concluído": ESTADO_FECHADA}
# `origem_lista` é um ENUM no Postgres (origem_lista_enum): "tarefas_todas" é rejeitado
# ("invalid input value for enum", apanhado no ensaio --dry). Usa-se o valor do nosso
# pipeline; 'Ativas'/'Arquivadas' são de outro e nunca se fecham daqui.
ORIGEM = "todas_as_colunas"
CHAVE = ["oportunidade_ref", "tarefa_titulo", "tarefa_due_raw"]  # = upsert._CONFLICT_KEYS
_FMT = "%d/%m/%Y"
_XHR = {"X-Requested-With": "XMLHttpRequest"}


async def _contar(client, desde: datetime.date, ate: datetime.date) -> int:
    """Nº de tarefas activas criadas em [desde, ate] — o título da lista que o
    eGO devolve ("N Tarefas"), sem descarregar nada."""
    body = {
        "Page": "1", "activeSearch": "1", "vt": "0", "date": "",
        "task[base][filter_active]": "on",
        "task[base][min_create_date]": desde.strftime(_FMT),
        "task[base][max_create_date]": ate.strftime(_FMT),
    }
    resp = await client.post("/egocore/search/eventsearch", data=body, headers=_XHR)
    titulo = (resp.json().get("replaces") or {}).get("#EventListTitle", "")
    m = re.search(r"(\d+)\s+Tarefas", titulo)
    if not m:
        raise RuntimeError(f"eventsearch sem contagem de tarefas: {titulo!r}")
    return int(m.group(1))


async def fatiar(contar, desde, ate, limite: int = LIMITE_FATIA) -> list[tuple]:
    """Parte [desde, ate] ao meio até cada fatia ter <= `limite` tarefas.
    Devolve `[(desde, ate, n)]`, fatias disjuntas e sem as vazias."""
    n = await contar(desde, ate)
    if n == 0:
        return []
    if n <= limite or desde == ate:
        return [(desde, ate, n)]
    meio = desde + (ate - desde) // 2
    return (
        await fatiar(contar, desde, meio, limite)
        + await fatiar(contar, meio + datetime.timedelta(days=1), ate, limite)
    )


async def _preparar(page, desde, ate, esperadas: int) -> None:
    """Pesquisa avançada de /egocore/tasks: activas, de toda a gente, criadas em
    [desde, ate]. Confirma que a lista ficou com o nº esperado de tarefas."""
    print(f"A aplicar fatia {desde:%d/%m/%Y} → {ate:%d/%m/%Y} ({esperadas} esperadas)...")
    # /egocore/tasks abre com o filtro rápido "Minhas tarefas" (assinguser_id do
    # scraper), que a pesquisa avançada NÃO substitui — sem desselecioná-lo dá 0.
    clicou = await page.evaluate(
        """() => {
            const a = Array.from(document.querySelectorAll('a')).find(e =>
                e.textContent.trim() === 'Minhas tarefas' &&
                (e.getAttribute('onclick') || '').includes('filterAction'));
            if (!a) return false;
            a.click();
            return true;
        }"""
    )
    if not clicou:
        raise RuntimeError('Filtro "Minhas tarefas" não encontrado em /egocore/tasks.')
    await page.wait_for_timeout(4000)
    await page.evaluate(
        """() => {
            const a = Array.from(document.querySelectorAll('a')).find(e =>
                (e.getAttribute('onclick') || '').includes('openSearchPopup'));
            a.click();
        }"""
    )
    await page.wait_for_selector('[name="task[base][min_create_date]"]', state="attached", timeout=15000)
    await page.evaluate(
        """([desde, ate]) => {
            const q = n => document.querySelector(`[name="task[base][${n}]"]`);
            q('assinguser_id').value = '';
            q('filter_active').checked = true;
            // "Criado em" = Intervalo: é o que mostra e activa os campos de data.
            q('since').value = '-1';
            q('since').dispatchEvent(new Event('change', {bubbles: true}));
            if (window.jQuery) window.jQuery(q('since')).trigger('change');
            q('min_create_date').value = desde;
            q('max_create_date').value = ate;
            Array.from(document.querySelectorAll('a')).find(e =>
                (e.getAttribute('onclick') || '').includes('byAdvanced')).click();
        }""",
        [desde.strftime(_FMT), ate.strftime(_FMT)],
    )
    await page.wait_for_timeout(5000)
    titulo = await page.evaluate("() => document.querySelector('#EventListTitle')?.innerText || ''")
    m = re.search(r"(\d+)", titulo)
    if not m or int(m.group(1)) != esperadas:
        raise RuntimeError(f"Fatia {desde}→{ate}: a lista mostra {titulo!r}, esperadas {esperadas}.")


def _data_iso(valor: str | None) -> str | None:
    if not valor:
        return None
    try:
        return datetime.datetime.strptime(valor.strip(), "%d/%m/%Y").date().isoformat()
    except (ValueError, AttributeError):
        return None


def map_row(row: dict) -> dict | None:
    """1 linha do relatório "tarefas todas" → registo para a tabela `tarefas`.
    `None` se não tiver `Referência` (sem FK, nada a fazer)."""
    ref = row.get("Referência")
    if not ref:
        return None

    tarefa = {
        "oportunidade_ref": ref,
        "tarefa_titulo": row.get("Assunto"),
        "tarefa_descricao": row.get("Descrição"),
        "tarefa_due_raw": row.get("Data de agendamento"),
        "tarefa_due_iso": _data_iso(row.get("Data de agendamento")),
        "tarefa_responsavel": row.get("Responsável"),
        "tarefa_criado_por": row.get("Criado por"),
        "tarefa_status": _ESTADOS.get(row.get("Estado da Tarefa"), row.get("Estado da Tarefa")),
        "tarefa_criado_em": _data_iso(row.get("Data de criação")),
        "tarefa_reagendamento_iso": _data_iso(row.get("Data de reagendamento")),
        "tarefa_reagendada": row.get("Reagendada"),
        "cliente_nome": row.get("Potencial cliente"),
        "tipo_oportunidade": row.get("Tipo de negocio"),
        "url": row.get("Link"),
        "origem_lista": ORIGEM,
    }
    return {k: v for k, v in tarefa.items() if v not in (None, "")}


def map_rows(rows: list[dict]) -> list[dict]:
    return [t for t in (map_row(r) for r in rows) if t]


def chave(t: dict) -> tuple:
    return tuple(t.get(c) for c in CHAVE)


def a_fechar(existentes: list[dict], snapshot: list[dict]) -> list[dict]:
    """Nossas tarefas abertas que já não estão no snapshot das activas."""
    vistas = {chave(t) for t in snapshot}
    return [e for e in existentes if chave(e) not in vistas]


async def _descarregar_snapshot(headless: bool) -> tuple[list[dict], int]:
    """Devolve (tarefas mapeadas, nº de linhas brutas). Falha se a soma das fatias
    não bater com o total das activas — nunca se escreve com um snapshot parcial."""
    import ego_auth

    async with ego_auth.authenticated_client() as client:
        await ego_auth.login(client)
        hoje = datetime.date.today()
        total = await _contar(client, INICIO, hoje)
        fatias = await fatiar(lambda d, a: _contar(client, d, a), INICIO, hoje)
    if sum(n for _, _, n in fatias) != total:
        raise RuntimeError(f"Fatias somam {sum(n for _, _, n in fatias)}, o total das activas é {total}.")
    print(f"{total} tarefas activas em {len(fatias)} fatias: {[n for _, _, n in fatias]}")

    mapeadas, brutas = [], 0
    for desde, ate, n in fatias:
        caminho = await oc._trigger_and_download(
            headless=headless, report_name=REPORT_NAME, page_path=PAGE_PATH,
            preparar=functools.partial(_preparar, desde=desde, ate=ate, esperadas=n),
        )
        _, rows = oc._parse_rows(caminho)
        # O relatório traz 1 linha base por tarefa (sem Referência) + 1 linha extra
        # por cada oportunidade associada (com Referência): 5 tarefas, 4 com
        # oportunidade = 9 linhas. As tarefas contam-se pelas linhas sem Referência.
        tarefas_no_relatorio = sum(1 for r in rows if not r.get("Referência"))
        if tarefas_no_relatorio != n:
            raise RuntimeError(
                f"Fatia {desde}→{ate}: relatório com {tarefas_no_relatorio} tarefas "
                f"({len(rows)} linhas), esperadas {n}."
            )
        brutas += tarefas_no_relatorio
        mapeadas += map_rows(rows)
    return mapeadas, brutas


def _refs_oportunidades(supabase) -> set[str]:
    out, desde = set(), 0
    while True:
        lote = supabase.table("oportunidades").select("oportunidade_ref").order("oportunidade_ref").range(desde, desde + 999).execute().data
        out.update(r["oportunidade_ref"] for r in lote)
        if len(lote) < 1000:
            return out
        desde += 1000


def _abertas_nossas(supabase) -> list[dict]:
    out, desde = [], 0
    while True:
        lote = (
            supabase.table("tarefas")
            .select("id," + ",".join(CHAVE))
            .eq("origem_lista", ORIGEM)
            .eq("tarefa_status", ESTADO_ABERTA)
            .order("id")
            .range(desde, desde + 999)
            .execute()
            .data
        )
        out += lote
        if len(lote) < 1000:
            return out
        desde += 1000


def _chaves_existentes(supabase) -> dict[tuple, str | None]:
    """chave -> origem_lista, de toda a tabela `tarefas` (paginado)."""
    out, desde = {}, 0
    while True:
        lote = (
            supabase.table("tarefas")
            .select(",".join(CHAVE) + ",origem_lista")
            .order("id")
            .range(desde, desde + 999)
            .execute()
            .data
        )
        for r in lote:
            out[chave(r)] = r.get("origem_lista")
        if len(lote) < 1000:
            return out
        desde += 1000


async def run(headless: bool = True, gravar: bool = True) -> dict:
    import config
    import upsert
    from supabase import create_client

    mapeadas, brutas = await _descarregar_snapshot(headless)
    snapshot = upsert._dedupe([upsert._strip_none(t) for t in mapeadas], CHAVE)
    print(f"{brutas} tarefas activas, {len(snapshot)} com oportunidade_ref (chaves únicas).")
    supabase = create_client(config.supabase_url, config.supabase_secret_key)
    # FK `tarefas_oportunidade_ref_fkey`: uma referência que ainda não está em
    # `oportunidades` (ex.: VEN_21398) faz falhar o lote inteiro. `oportunidades`
    # é do pipeline de fora — aqui só se saltam, e conta-se.
    refs = _refs_oportunidades(supabase)
    sem_fk = [t for t in snapshot if t["oportunidade_ref"] not in refs]
    snapshot = [t for t in snapshot if t["oportunidade_ref"] in refs]
    print(f"{len(sem_fk)} tarefas saltadas: oportunidade_ref ausente de `oportunidades` "
          f"({sorted({t['oportunidade_ref'] for t in sem_fk})[:8]}...)")
    abertas = _abertas_nossas(supabase)
    fechar = a_fechar(abertas, snapshot)
    if not gravar:
        # Ensaio: quantas chaves do snapshot já existem (e de que origem) — o upsert
        # sobrepõe-as, incluindo linhas de outros pipelines.
        existentes = _chaves_existentes(supabase)
        ja = [chave(t) for t in snapshot if chave(t) in existentes]
        origens = {}
        for k in ja:
            origens[existentes[k]] = origens.get(existentes[k], 0) + 1
        print(f"{len(ja)} das {len(snapshot)} chaves já existem em `tarefas`, por origem_lista: {origens}")
        print(f"{len(abertas)} abertas nossas em `tarefas`; {len(fechar)} fechar-se-iam (já não estão no snapshot).")
        return {"activas": brutas, "com_ref": len(snapshot), "gravadas": 0, "fechadas": 0}

    gravadas = upsert._upsert_tabela(supabase, "tarefas", snapshot)

    for e in fechar:
        supabase.table("tarefas").update({"tarefa_status": ESTADO_FECHADA}).eq("id", e["id"]).execute()
    return {"activas": brutas, "com_ref": len(snapshot), "gravadas": gravadas, "fechadas": len(fechar)}


def demo() -> None:
    """Auto-verificação sem rede. `python tarefas.py` de `scraper/`."""
    com_ref = {
        "Referência": "CAP_1", "Assunto": "Contactar", "Estado da Tarefa": "Em Curso",
        "Data de agendamento": "29/09/2026", "Responsável": "Alexsandra Ferreira",
    }
    sem_ref = {"Assunto": "Notificação", "Estado da Tarefa": "Em Curso"}

    mapeadas = map_rows([com_ref, sem_ref])
    assert len(mapeadas) == 1, "linha sem Referência não devia gerar tarefa"
    assert mapeadas[0]["oportunidade_ref"] == "CAP_1"
    assert mapeadas[0]["tarefa_titulo"] == "Contactar"
    assert mapeadas[0]["tarefa_due_iso"] == "2026-09-29"
    assert mapeadas[0]["tarefa_status"] == "pendente", "Em Curso deve sair no vocabulário da tabela"
    assert "tarefa_descricao" not in mapeadas[0], "campo vazio não devia entrar no payload"

    # fatiar: tarefas espalhadas por dia, limite 300 → fatias disjuntas que somam o total
    d0 = datetime.date(2026, 1, 1)
    por_dia = {d0 + datetime.timedelta(days=i): (3 if i % 2 else 1) for i in range(500)}

    async def contar(desde, ate):
        return sum(v for d, v in por_dia.items() if desde <= d <= ate)

    fatias = asyncio.run(fatiar(contar, datetime.date(2000, 1, 1), datetime.date(2030, 1, 1), limite=300))
    assert sum(n for _, _, n in fatias) == sum(por_dia.values()), "fatias não somam o total"
    assert all(n <= 300 for _, _, n in fatias), "fatia acima do limite"
    assert all(a[1] < b[0] for a, b in zip(fatias, fatias[1:])), "fatias sobrepostas"

    # a_fechar: só as que saíram do snapshot
    snap = [{"oportunidade_ref": "A", "tarefa_titulo": "x", "tarefa_due_raw": "1"}]
    exist = [
        {"id": 1, "oportunidade_ref": "A", "tarefa_titulo": "x", "tarefa_due_raw": "1"},
        {"id": 2, "oportunidade_ref": "B", "tarefa_titulo": "y", "tarefa_due_raw": "2"},
    ]
    assert [e["id"] for e in a_fechar(exist, snap)] == [2], "devia fechar só a que saiu do snapshot"

    print("tarefas: map + fatiar + a_fechar OK")


if __name__ == "__main__":
    if sys.argv[1:2] == ["sync"]:
        print(asyncio.run(run(gravar="--dry" not in sys.argv)))
    else:
        demo()
