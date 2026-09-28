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

Correr localmente a partir de scraper/: python tarefas.py
"""
import datetime

import oportunidades_completo as oc

REPORT_NAME = "tarefas todas"


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
        "tarefa_status": row.get("Estado da Tarefa"),
        "tarefa_criado_em": _data_iso(row.get("Data de criação")),
        "tarefa_reagendamento_raw": row.get("Data de reagendamento"),
        "tarefa_reagendamento_iso": _data_iso(row.get("Data de reagendamento")),
        "tarefa_reagendada": row.get("Reagendada"),
        "cliente_nome": row.get("Potencial cliente"),
        "tipo_oportunidade": row.get("Tipo de negocio"),
        "url": row.get("Link"),
        "origem_lista": "tarefas_todas",
    }
    return {k: v for k, v in tarefa.items() if v not in (None, "")}


def map_rows(rows: list[dict]) -> list[dict]:
    return [t for t in (map_row(r) for r in rows) if t]


async def run(headless: bool = True) -> dict:
    import config
    import upsert
    from supabase import create_client

    print(f'A descarregar relatório "{REPORT_NAME}"...')
    download_path = await oc._trigger_and_download(headless=headless, report_name=REPORT_NAME)
    header, rows = oc._parse_rows(download_path)
    tarefas = map_rows(rows)
    print(f"{len(rows)} linhas no relatório, {len(tarefas)} tarefas com oportunidade_ref.")

    supabase = create_client(config.supabase_url, config.supabase_secret_key)
    gravadas = upsert._upsert_tabela(supabase, "tarefas", tarefas)
    return {"tarefas": gravadas}


def demo() -> None:
    """Auto-verificação do mapping. `python tarefas.py` de `scraper/`."""
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
    assert mapeadas[0]["tarefa_status"] == "Em Curso"
    assert "tarefa_descricao" not in mapeadas[0], "campo vazio não devia entrar no payload"

    print("tarefas: map OK")


if __name__ == "__main__":
    demo()
