"""Vigia das leads da Meta (`docs/fases/vigia-leads-meta-plano.md`): a Meta diz quantas leads houve por dia, o Supabase quantas chegaram.

O n8n pede à Marketing API (conta de anúncios) as leads por dia e manda-as para `POST /api/leads/meta/reconciliar`.
Só avisa quando a Meta tem MAIS do que o Supabase em duas verificações seguidas (a lead recém-chegada ainda vem a caminho)
e não repete o mesmo aviso em menos de 12 h. Diz quantas faltam e em que dia; se o n8n mandar também os ids (`ids`), diz quais.
ponytail: leads de recrutamento/angariação da mesma conta contam no Supabase e podem tapar a falta de uma de compra;
se a conta passar a misturar campanhas, separar a contagem por campanha/formulário.
"""

import logging
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from app.db.supabase_client import get_supabase
from app.notificacoes import _alertas_extra, notificar

logger = logging.getLogger(__name__)

LISBOA = ZoneInfo("Europe/Lisbon")
TIPO_VERIFICACAO = "vigia_leads_meta"
TIPO_ALERTA = "vigia_leads_alerta"
JANELA_VERIFICACAO_H = 3  # a verificação anterior só conta se for recente (o n8n corre de 30 em 30 min)
REPETIR_ALERTA_H = 12


def contar_no_supabase(dias: list[str]) -> dict[str, int]:
    """Leads Meta por dia (hora de Lisboa, como a conta de anúncios) em `contactos.meta_created_at`.

    Só as de anúncio (`ad_id` preenchido): a Meta conta anúncios, e testes ou leads orgânicas do formulário
    (sem `ad_id`) tapavam a falta de uma real (20/11: Supabase 4, Meta 3, faltavam 2 e o vigia dizia 1)."""
    desde = datetime.combine(date.fromisoformat(min(dias)), datetime.min.time(), tzinfo=LISBOA).astimezone(timezone.utc)
    linhas = (get_supabase().table("contactos").select("meta_created_at")
              .not_.is_("meta_lead_id", "null").not_.is_("ad_id", "null").gte("meta_created_at", desde.isoformat()).limit(5000).execute().data or [])
    contagem = dict.fromkeys(dias, 0)
    for l in linhas:
        dia = datetime.fromisoformat(l["meta_created_at"].replace("Z", "+00:00")).astimezone(LISBOA).date().isoformat()
        if dia in contagem:
            contagem[dia] += 1
    return contagem


def diferencas(meta: dict[str, int], supabase: dict[str, int]) -> dict[str, int]:
    """Só os dias em que a Meta tem mais leads do que o Supabase."""
    return {d: n - supabase.get(d, 0) for d, n in meta.items() if n > supabase.get(d, 0)}


def confirmadas(atuais: dict[str, int], anteriores: dict[str, int]) -> dict[str, int]:
    """Falta confirmada = a mesma falta nas duas verificações seguidas (vale o menor valor)."""
    return {d: min(n, anteriores[d]) for d, n in atuais.items() if anteriores.get(d, 0) >= 1}


def _ultimo(tipo: str, horas: float) -> dict | None:
    desde = (datetime.now(timezone.utc) - timedelta(hours=horas)).isoformat()
    r = (get_supabase().table("agente_sync_log").select("resumo,executado_em").eq("tipo", tipo)
         .gte("executado_em", desde).order("executado_em", desc=True).limit(1).execute().data)
    return r[0] if r else None


def _registar(tipo: str, resumo: dict) -> None:
    try:
        get_supabase().table("agente_sync_log").insert({"tipo": tipo, "resumo": resumo, "origem": "n8n"}).execute()
    except Exception:
        logger.exception("Falha a registar %s", tipo)


def _existentes(ids: set[str]) -> set[str]:
    """Quais destes `meta_lead_id` já estão em `contactos`."""
    lista, achados = sorted(ids), set()
    for i in range(0, len(lista), 100):
        linhas = get_supabase().table("contactos").select("meta_lead_id").in_("meta_lead_id", lista[i:i + 100]).execute().data or []
        achados |= {l["meta_lead_id"] for l in linhas}
    return achados


def ids_em_falta(ids: dict[str, list[str]], dias: list[str]) -> dict[str, list[str]]:
    """Dos ids que a Meta lista por dia, os que não estão no Supabase (só nos `dias` pedidos). Podem incluir leads de teste,
    que o fluxo filtra de propósito (o email diz-o)."""
    pedidos = {i for d in dias for i in ids.get(d, [])}
    if not pedidos:
        return {}
    ja = _existentes(pedidos)
    falta = {d: [i for i in ids.get(d, []) if i not in ja] for d in dias}
    return {d: v for d, v in falta.items() if v}


def texto_do_alerta(faltam: dict[str, int], meta: dict[str, int], supabase: dict[str, int],
                    ids_falta: dict[str, list[str]] | None = None, ids: dict[str, list[str]] | None = None) -> str:
    ids_falta, ids = ids_falta or {}, ids or {}
    linhas = [f"A conta de anúncios da Meta tem mais leads do que as que chegaram ao Supabase (duas verificações seguidas):", ""]
    for dia in sorted(faltam):
        linhas.append(f"  {dia}: Meta {meta[dia]} · Supabase {supabase.get(dia, 0)} · faltam {faltam[dia]}")
        if ids_falta.get(dia):
            linhas.append(f"    ids da Meta que não estão no Supabase: {', '.join(ids_falta[dia])}")
        if ids and len(ids.get(dia, [])) < meta[dia]:
            linhas.append(f"    atenção: a lista de ids deste dia está incompleta ({len(ids.get(dia, []))} de {meta[dia]})")
    com_ids = bool(ids_falta)
    linhas += ["", "O que fazer (a lead não chegou, a pessoa está à espera do template):",
               "1. No n8n, execuções de 'Meta leads to supabase' à hora da lead: se não há nenhuma, a Meta não chamou o webhook "
               "(subscrição `leadgen` da página); se há com erro, ver o nó que falhou.",
               ("2. Os ids acima são os candidatos (podem incluir leads de teste, que o fluxo ignora). Confirmar no Meta Business Suite "
                "→ Caixa de entrada de leads." if com_ids else
                "2. Apanhar o id da lead (`leadgen_id`) no Meta Business Suite → Caixa de entrada de leads (ou Gestor de anúncios → Formulários)."),
               "3. Reinjetar: POST ao webhook do n8n com {\"entry\":[{\"changes\":[{\"value\":{\"leadgen_id\":\"<id>\"}}]}]} "
               "(comando em docs/n8n/README.md, «Reinjetar uma lead da Meta»). O fluxo cria a lead e envia o template.",
               "O Make já não faz parte do caminho." + ("" if com_ids else " São contagens, não ids: a conta de anúncios não diz quais faltam.")]
    return "\n".join(linhas)


def verificar(meta: dict[str, int], dry: bool = False, ids: dict[str, list[str]] | None = None) -> dict:
    """Uma verificação. Nunca escreve nem envia com `dry`. O envio falha para o lado de avisar a mais.
    `ids` (opcional): ids das leads por dia segundo a Meta, para dizer quais faltam."""
    supabase = contar_no_supabase(list(meta))
    atuais = diferencas(meta, supabase)
    anterior = _ultimo(TIPO_VERIFICACAO, JANELA_VERIFICACAO_H)
    faltam = confirmadas(atuais, (anterior or {}).get("resumo", {}).get("diferencas", {}))
    resposta = {"meta": meta, "supabase": supabase, "diferencas": atuais, "confirmadas": faltam, "avisou": False}
    if dry:
        return resposta
    _registar(TIPO_VERIFICACAO, {"diferencas": atuais, "meta": meta, "supabase": supabase})
    if not faltam:
        return resposta
    ultimo = _ultimo(TIPO_ALERTA, REPETIR_ALERTA_H)
    if ultimo and ultimo["resumo"].get("faltam") == faltam:
        return resposta | {"repetido": True}
    try:
        ids_falta = ids_em_falta(ids, list(faltam)) if ids else {}
    except Exception:
        logger.exception("Falha a comparar os ids das leads da Meta")  # o aviso sai na mesma, só sem os ids
        ids_falta = {}
    notificar(f"Leads da Meta em falta no Supabase: {sum(faltam.values())}", texto_do_alerta(faltam, meta, supabase, ids_falta, ids),
              para_extra=_alertas_extra())
    _registar(TIPO_ALERTA, {"faltam": faltam, "ids_em_falta": ids_falta})
    return resposta | {"avisou": True, "ids_em_falta": ids_falta}
