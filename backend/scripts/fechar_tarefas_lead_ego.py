"""Limpeza única: fecha as tarefas «Lead qualificada — passar ao eGO» antigas (sem `tipo`) cuja pessoa já tem lead no eGO.

    cd backend && python scripts/fechar_tarefas_lead_ego.py            # só lista (ids), não escreve
    cd backend && python scripts/fechar_tarefas_lead_ego.py --aplicar  # fecha

Cruza o título com `contactos.ego_lead_em` (mesma regra de `leads_para_ego.fechar_tarefas_da_lead`).
Não imprime nomes nem telefones. As tarefas sem lead no eGO (ex.: vendedores) ficam pendentes.
"""
import sys
from datetime import datetime, timezone

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, ".")
from app.db.supabase_client import get_supabase  # noqa: E402
from app.leads_para_ego import _TAREFA_QUALIFICADA, titulos_da_tarefa  # noqa: E402

sb = get_supabase()
aplicar = "--aplicar" in sys.argv

tarefas = (sb.table("agente_tarefas").select("id,titulo,criado_em").eq("estado", "pendente")
           .like("titulo", f"{_TAREFA_QUALIFICADA}%").execute().data)
contactos = (sb.table("contactos").select("nome,telefone,telemovel,email")
             .not_.is_("ego_lead_em", "null").execute().data)
com_ego = {t for c in contactos for t in titulos_da_tarefa(c)}

fechar = [t for t in tarefas if t["titulo"] in com_ego]
print(f"pendentes: {len(tarefas)} | com lead no eGO (a fechar): {len(fechar)} | ficam: {len(tarefas) - len(fechar)}")
for t in fechar:
    print(f"  {t['id'][:8]} {t['criado_em'][:10]}")

if aplicar and fechar:
    agora = datetime.now(timezone.utc).isoformat()
    sb.table("agente_tarefas").update({"estado": "concluida", "atualizado_em": agora}).in_("id", [t["id"] for t in fechar]).execute()
    print("fechadas.")
elif fechar:
    print("(dry) nada escrito; usar --aplicar")
