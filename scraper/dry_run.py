"""Dry-run: mapeia + agrupa o relatório já descarregado (não bate no eGO de
novo) e mostra contagens + diffs contra a produção actual, SEM escrever
nada. Passo de validação antes de ligar upserts reais (task #6).

Correr a partir de scraper/: python dry_run.py [caminho_xlsx]
"""
import json
import sys
from pathlib import Path

from supabase import create_client

import config
import mapping_todas_colunas as m
import oportunidades_completo as o

DEFAULT_XLSX = Path(__file__).resolve().parent / "output" / "jmarques_todas_as_colunas_6429.xlsx"


def main() -> None:
    xlsx_path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_XLSX
    print(f"A parsear {xlsx_path.name}...")
    _, rows = o._parse_rows(xlsx_path)
    print(f"{len(rows)} linhas no relatório.")

    classified = [m.classify(m.map_row(r)) for r in rows]
    batch = m.group(classified)

    print("\n-- Contagens (o que seria escrito) --")
    for tabela in ("oportunidades", "notas", "tarefas", "prefs", "contactos"):
        print(f"  {tabela}: {len(batch[tabela])}")

    if not config.supabase_imoveis_url or not config.supabase_imoveis_key:
        print("\nSUPABASE_IMOVEIS_URL/KEY não configuradas — sem comparação com produção.")
        return

    supabase = create_client(config.supabase_imoveis_url, config.supabase_imoveis_key)

    print("\n-- Diff contra produção (5 primeiras oportunidades) --")
    for oport in batch["oportunidades"][:5]:
        ref = oport["oportunidade_ref"]
        resp = supabase.table("oportunidades").select("*").eq("oportunidade_ref", ref).execute()
        atual = resp.data[0] if resp.data else None
        print(f"\n{ref}:")
        if atual is None:
            print("  NÃO EXISTE em produção — seria criada.")
            continue
        mudancas = []
        for campo, novo in oport.items():
            antigo = atual.get(campo)
            if novo is not None and str(antigo) != str(novo):
                mudancas.append(f"    {campo}: {antigo!r} -> {novo!r}")
        if mudancas:
            print("  mudanças:")
            print("\n".join(mudancas))
        else:
            print("  sem mudanças nos campos mapeados.")

    print("\n-- Amostra de notas a inserir (3 primeiras) --")
    for nota in batch["notas"][:3]:
        print(json.dumps(nota, ensure_ascii=False, default=str))

    print("\n-- Amostra de contactos a upsert (3 primeiros) --")
    for contacto in batch["contactos"][:3]:
        print(json.dumps(contacto, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
