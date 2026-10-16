"""Que contactos receberam (ou não) os templates do WhatsApp. Só leitura.

    cd backend && python scripts/entrega_whatsapp.py [dias]      # por omissão 7

Lê `contactos` com `template_enviado_em`/`follow_up_em` nos últimos N dias e diz, por contacto, o que
a Meta confirmou (migration 0048): **entregue**, **falhou** (131026) ou **sem recibo**. "Sem recibo" não
é falha: pode ser anterior ao webhook gravar, ou a mensagem ainda não chegou. Telefones só com os
3 últimos dígitos.
"""

import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.supabase_client import get_supabase  # noqa: E402


def estado(linha: dict) -> str:
    if linha.get("whatsapp_falhou_em"):
        return f"falhou ({linha.get('whatsapp_erro_codigo')})"
    return "entregue" if linha.get("whatsapp_entregue_em") else "sem recibo"


def main(dias: int = 7) -> None:
    desde = (datetime.now(timezone.utc) - timedelta(days=dias)).isoformat()
    sb = get_supabase()
    cols = "telefone,telemovel,tipo_contacto,template_enviado_em,follow_up_em,whatsapp_entregue_em,whatsapp_falhou_em,whatsapp_erro_codigo"
    linhas = {}
    for coluna in ("template_enviado_em", "follow_up_em"):
        for r in sb.table("contactos").select(cols).gte(coluna, desde).execute().data or []:
            linhas[(r.get("telefone") or r.get("telemovel"), r.get("template_enviado_em"))] = r
    contagem = Counter(estado(r) for r in linhas.values())
    print(f"Contactos com envio nos últimos {dias} dias: {len(linhas)}")
    for k, n in contagem.most_common():
        print(f"  {k}: {n}")
    for r in linhas.values():
        if estado(r).startswith("falhou"):
            tel = (r.get("telefone") or r.get("telemovel") or "")[-3:]
            print(f"  falha …{tel}  {r.get('tipo_contacto')}  {estado(r)}")


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 7)
