"""Verificação diária, lado Supabase (só leitura): syncs, leads Meta, turnos e conversas dos agentes.

    cd backend && python scripts/verificacao_diaria.py syncs|leads|turnos|conversas [horas=24]

`conversas` imprime texto de mensagens (telefones ocultados): usar só localmente, nunca colar em docs/commits.
"""
import collections
import datetime as dt
import json
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, ".")
from app.db.supabase_client import get_supabase  # noqa: E402

sb = get_supabase()
agora = dt.datetime.now(dt.timezone.utc)
horas = float(sys.argv[2]) if len(sys.argv) > 2 else 24
desde = (agora - dt.timedelta(hours=horas)).isoformat()


def syncs():
    """Último registo de cada tipo em agente_sync_log (os `*_erro` são falhas de cron)."""
    rows = sb.table("agente_sync_log").select("tipo,executado_em,resumo,origem").gte("executado_em", desde).order("executado_em").execute().data
    por = collections.defaultdict(list)
    for r in rows:
        por[r["tipo"]].append(r)
    for t, rs in sorted(por.items()):
        u = rs[-1]
        print(f"{t:42s} x{len(rs):<3d} ult {u['executado_em'][5:16]} {u['origem']} | {json.dumps(u['resumo'], ensure_ascii=False)[:230]}")


def leads():
    """Funil das leads Meta (48 h mín.): opt-in, template, entrega, falhas, recusas, eGO, sem responsável."""
    d48 = (agora - dt.timedelta(hours=max(horas, 48))).isoformat()
    cs = sb.table("contactos").select("meta_created_at,tipo_contacto,whatsapp_permissao,template_enviado_em,whatsapp_entregue_em,whatsapp_falhou_em,nao_contactar_em,ego_lead_em,responsavel").gte("meta_created_at", d48).execute().data
    print("contactos Meta:", len(cs))
    g = collections.defaultdict(list)
    for c in cs:
        g[",".join(c.get("tipo_contacto") or ["?"])].append(c)
    for t, l in g.items():
        atras = [c for c in l if c["whatsapp_permissao"] and not c["template_enviado_em"] and dt.datetime.fromisoformat(c["meta_created_at"]) < agora - dt.timedelta(hours=1)]
        print(f"  {t:14s} n={len(l):2d} opt-in={sum(1 for c in l if c['whatsapp_permissao'])} template={sum(1 for c in l if c['template_enviado_em'])} "
              f"entregue={sum(1 for c in l if c['whatsapp_entregue_em'])} falhou={sum(1 for c in l if c['whatsapp_falhou_em'])} "
              f"optin_sem_template>1h={len(atras)} recusou={sum(1 for c in l if c['nao_contactar_em'])} eGO={sum(1 for c in l if c['ego_lead_em'])} "
              f"sem_resp={sum(1 for c in l if not (c['responsavel'] or '').strip())}")
    ta = sb.table("agente_tarefas").select("tipo,estado,responsavel").gte("criado_em", desde).execute().data
    print("tarefas dos agentes:", collections.Counter((t.get("tipo"), t.get("estado"), bool(t.get("responsavel"))) for t in ta))


def turnos():
    """Por agente/canal: turnos, latência p50/p95, cache, erros, iterações>3, tools usadas, custo."""
    it = sb.table("agente_interacoes").select("conversa_id,agente,canal,custo_usd,latencia_ms,iteracoes,tools_usadas,erro,tokens_cache_read,tokens_input").gte("criado_em", desde).execute().data
    print("turnos:", len(it), "custo USD:", round(sum(float(i["custo_usd"] or 0) for i in it), 2))
    g = collections.defaultdict(list)
    for i in it:
        g[(i["agente"], i["canal"])].append(i)
    for k, l in sorted(g.items()):
        lat = sorted(i["latencia_ms"] or 0 for i in l)
        cache = sum(i["tokens_cache_read"] or 0 for i in l) / max(1, sum((i["tokens_cache_read"] or 0) + (i["tokens_input"] or 0) for i in l))
        tools = collections.Counter(t for i in l for t in (i["tools_usadas"] or []))
        print(f"{k} n={len(l)} conv={len({i['conversa_id'] for i in l})} p50={lat[len(lat)//2]}ms p95={lat[max(0, int(len(lat)*.95)-1)]}ms cache={cache:.0%} "
              f"erros={dict(collections.Counter(i['erro'] for i in l if i['erro']))} iter>3={sum(1 for i in l if (i['iteracoes'] or 0) > 3)} tools={dict(tools)}")


def conversas():
    """Últimas 14 mensagens de cada conversa tocada no período, para ler à mão."""
    cv = sb.table("agente_conversas").select("agente,canal,mensagens,criado_em,atualizado_em").gte("atualizado_em", desde).order("atualizado_em").execute().data
    for n, c in enumerate(cv, 1):
        m = c["mensagens"] or []
        print(f"\n=== C{n} {c['agente']} {c['canal']} msgs={len(m)} {c['criado_em'][5:16]}→{c['atualizado_em'][5:16]}")
        for x in m[-14:]:
            t = x.get("content")
            t = t if isinstance(t, str) else str(t)
            print(f"  {x['role'][:1].upper()}: {re.sub(r'\d{9,}', '<tel>', t)[:300]}".replace("\n", " / "))


if __name__ == "__main__":
    cmds = {"syncs": syncs, "leads": leads, "turnos": turnos, "conversas": conversas}
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    cmds.get(cmd, lambda: sys.exit(f"Uso: verificacao_diaria.py {'|'.join(cmds)} [horas]"))()
