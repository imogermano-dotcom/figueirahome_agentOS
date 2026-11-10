"""Vigia das leads da Meta (`docs/fases/vigia-leads-meta-plano.md`): a Meta diz quantas leads houve por dia, o Supabase quantas chegaram.

O n8n pede à Marketing API (conta de anúncios) as leads por dia e manda-as para `POST /api/leads/meta/reconciliar`.
Só avisa quando a Meta tem MAIS do que o Supabase em duas verificações seguidas (a lead recém-chegada ainda vem a caminho)
e não repete o mesmo aviso em menos de 12 h. São contagens, não ids: diz quantas faltam e em que dia, não quais.
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
TIPO_FALHA = "vigia_leads_falha"
JANELA_VERIFICACAO_H = 3  # a verificação anterior só conta se for recente (o n8n corre de 30 em 30 min)
REPETIR_ALERTA_H = 12


def contar_no_supabase(dias: list[str]) -> dict[str, int]:
    """Leads Meta por dia (hora de Lisboa, como a conta de anúncios) em `contactos.meta_created_at`."""
    desde = datetime.combine(date.fromisoformat(min(dias)), datetime.min.time(), tzinfo=LISBOA).astimezone(timezone.utc)
    linhas = (get_supabase().table("contactos").select("meta_created_at")
              .not_.is_("meta_lead_id", "null").gte("meta_created_at", desde.isoformat()).limit(5000).execute().data or [])
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


def texto_do_alerta(faltam: dict[str, int], meta: dict[str, int], supabase: dict[str, int]) -> str:
    linhas = [f"A conta de anúncios da Meta tem mais leads do que as que chegaram ao Supabase (duas verificações seguidas):", ""]
    for dia in sorted(faltam):
        linhas.append(f"  {dia}: Meta {meta[dia]} · Supabase {supabase.get(dia, 0)} · faltam {faltam[dia]}")
    linhas += ["", "Ver, por esta ordem: o cenário do Make está ligado e sem erros? O webhook do n8n recebeu (execuções de "
               "'Meta leads to supabase')? A lead pode ter sido filtrada como teste.",
               "São contagens, não ids: a Meta não diz quais faltam sem acesso à página."]
    return "\n".join(linhas)


def avisar_falha(erro: str, dry: bool = False) -> dict:
    """O próprio vigia falhou (token da Meta expirado, 10/11: ficou cego um dia sem aviso). O n8n chama-nos pela saída de
    erro do nó. Um email por falha em 12 h (o fluxo corre de 30 em 30 min). Nunca avisa com `dry`.
    ponytail: só apanha o vigia que corre e falha; n8n parado ou fluxo desligado ficam por detectar."""
    erro = (erro or "sem detalhe").strip()[:500]
    if _ultimo(TIPO_FALHA, REPETIR_ALERTA_H):
        return {"avisou": False, "repetido": True}
    if dry:
        return {"avisou": False, "dry": True}
    notificar("O vigia das leads da Meta falhou", "\n".join((
        "O fluxo «Vigia leads Meta» (n8n) falhou e deixou de comparar as leads da Meta com o Supabase.", "",
        f"Erro: {erro}", "",
        "Causa mais provável: o token da credencial «Facebook Figueira Home» (n8n) expirou. O fluxo «Meta leads to supabase» "
        "usa a MESMA credencial para ler cada lead: se o token está morto, as leads novas podem não estar a entrar. "
        "Ver também se o cenário do Make está ligado e com a ligação ao Facebook válida.", "",
        "Este aviso não se repete em 12 h.")), para_extra=_alertas_extra())
    _registar(TIPO_FALHA, {"erro": erro})
    return {"avisou": True}


def verificar(meta: dict[str, int], dry: bool = False) -> dict:
    """Uma verificação. Nunca escreve nem envia com `dry`. O envio falha para o lado de avisar a mais."""
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
    notificar(f"Leads da Meta em falta no Supabase: {sum(faltam.values())}", texto_do_alerta(faltam, meta, supabase),
              para_extra=_alertas_extra())
    _registar(TIPO_ALERTA, {"faltam": faltam})
    return resposta | {"avisou": True}
