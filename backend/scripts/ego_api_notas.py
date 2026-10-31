"""Notas das oportunidades ativas pela API do eGO vs `notas` no Supabase (fase A2). Dry-run por omissão: SÓ LEITURA, sem PII.

    python scripts/ego_api_notas.py                      # resumo das notas só na API, com texto
    python scripts/ego_api_notas.py --desde 2026-10-01   # só notas escritas a partir desta data
    python scripts/ego_api_notas.py --gravar             # ESCREVE em produção (com os gatilhos de IA suspensos, ver plano)

A lógica vive em `app/integrations/ego_notas.py` (usa-a também o cron das 04:17).
"""

import argparse
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.integrations import ego_notas  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--desde", default="")
    ap.add_argument("--gravar", action="store_true")
    a = ap.parse_args()
    novas = ego_notas.novas(a.desde)
    por_ref = Counter(n["ref"] for n in novas)
    print(f"notas por gravar: {len(novas)} em {len(por_ref)} oportunidades (desde {a.desde or 'sempre'})")
    print("por mês da nota:", sorted(Counter(n["dia"][:7] for n in novas).items()))
    print("notas por oportunidade (nº de oportunidades):", sorted(Counter(por_ref.values()).items()))
    if a.gravar:
        r = ego_notas.gravar(novas)
        print("gravadas:", r["inseridas"], "| erros:", len(r["erros"]), r["erros"], "| propagado:", r.get("propagado"))


if __name__ == "__main__":
    main()
