"""Recibos de entrega da Meta -> colunas de `contactos` (migration 0048).

Plano: `docs/fases/recibos-whatsapp-plano.md`. `200 accepted` da Graph API não é entrega;
a verdade chega ao webhook em `statuses`. Aqui só se grava o que decide o próximo envio:

* `delivered`/`read`  -> `whatsapp_entregue_em`, e limpa a marca de falha (se for mais antiga);
* `failed` PERMANENTE -> `whatsapp_falhou_em` + `whatsapp_erro_codigo`;
* `sent` e os outros `failed` (limite de marketing, janela de 24 h...) não dizem nada sobre o
  número: ficam só no log, como antes.

Os eventos de uma mensagem chegam fora de ordem: só vale o mais recente. O mesmo telefone existe
em várias linhas de `contactos` (duplicados): marcam-se todas. UPDATE linha a linha por `id`,
nunca upsert em lote (invariante do PostgREST sobre colunas esparsas).
"""

import logging
from datetime import datetime, timedelta, timezone

from app.agents.broker.guards import normalizar_telefone, variantes_telefone
from app.db.supabase_client import get_supabase

logger = logging.getLogger(__name__)

# 131026 = mensagem não entregável (sem WhatsApp, número inativo, termos por aceitar): a Meta não
# distingue. Outros códigos (131049, 131047, 131030...) não são sobre o número: não marcam.
CODIGOS_PERMANENTES = {131026}

_COLUNAS = "id,whatsapp_entregue_em,whatsapp_falhou_em"


def _quando(ts) -> datetime:
    """`timestamp` da Meta (unix, em str ou int). Sem ele, agora."""
    try:
        return datetime.fromtimestamp(int(ts), tz=timezone.utc)
    except (TypeError, ValueError, OverflowError, OSError):
        return datetime.now(timezone.utc)


def _dt(valor: str | None) -> datetime | None:
    return datetime.fromisoformat(valor) if valor else None


def efeito_do_estado(estado: dict) -> dict | None:
    """O que um recibo muda em `contactos`, ou `None` se não muda nada. Função pura."""
    numero = normalizar_telefone(estado.get("recipient_id"))
    if not numero:
        return None
    qual = estado.get("status")
    if qual in ("delivered", "read"):
        return {"numero": numero, "tipo": "entregue", "quando": _quando(estado.get("timestamp"))}
    if qual == "failed":
        codigo = ((estado.get("errors") or [{}])[0]).get("code")
        if codigo in CODIGOS_PERMANENTES:
            return {
                "numero": numero, "tipo": "falhou", "codigo": codigo,
                "quando": _quando(estado.get("timestamp")),
            }
    return None


def _linhas(numero: str) -> list[dict]:
    """Linhas de `contactos` deste telefone (`telefone` ou `telemovel`, qualquer formato)."""
    sb = get_supabase()
    vistas: dict = {}
    for coluna in ("telefone", "telemovel"):
        resp = sb.table("contactos").select(_COLUNAS).in_(coluna, variantes_telefone(numero)).execute()
        for linha in resp.data or []:
            vistas[linha["id"]] = linha
    return list(vistas.values())


def _atualizar(linha_id, valores: dict) -> None:
    get_supabase().table("contactos").update(valores).eq("id", linha_id).execute()


def aplicar(efeito: dict) -> int:
    """Grava o efeito nas linhas do telefone. Devolve quantas linhas mudou."""
    quando: datetime = efeito["quando"]
    iso = quando.isoformat()
    mudadas = 0
    for linha in _linhas(efeito["numero"]):
        entregue, falhou = _dt(linha.get("whatsapp_entregue_em")), _dt(linha.get("whatsapp_falhou_em"))
        if efeito["tipo"] == "entregue":
            if entregue and entregue >= quando:
                continue
            valores = {"whatsapp_entregue_em": iso}
            if falhou and falhou <= quando:  # a falha era anterior a esta entrega
                valores |= {"whatsapp_falhou_em": None, "whatsapp_erro_codigo": None}
        else:
            if (entregue and entregue >= quando) or (falhou and falhou >= quando):
                continue
            valores = {"whatsapp_falhou_em": iso, "whatsapp_erro_codigo": efeito["codigo"]}
        _atualizar(linha["id"], valores)
        mudadas += 1
    return mudadas


def registar(estado: dict) -> None:
    """Ponto de entrada do webhook. Nunca levanta: a Meta lê um 500 como falha nossa e reenvia."""
    try:
        efeito = efeito_do_estado(estado)
        if efeito:
            aplicar(efeito)
    except Exception:
        logger.exception("Falha a gravar o recibo do WhatsApp em contactos")


def limpar_falha(numero_bruto: str | None) -> None:
    """Quem nos escreve tem WhatsApp: limpa a marca de falha. Nunca levanta."""
    try:
        numero = normalizar_telefone(numero_bruto)
        if not numero:
            return
        for linha in _linhas(numero):
            if linha.get("whatsapp_falhou_em"):
                _atualizar(linha["id"], {"whatsapp_falhou_em": None, "whatsapp_erro_codigo": None})
    except Exception:
        logger.exception("Falha a limpar a marca de falha do WhatsApp")


def falhas_recentes(horas: int = 24) -> list[dict]:
    """Números marcados como sem WhatsApp nas últimas `horas`, sem repetir o mesmo telefone."""
    desde = (datetime.now(timezone.utc) - timedelta(hours=horas)).isoformat()
    resp = (
        get_supabase().table("contactos")
        .select("telefone,telemovel,whatsapp_erro_codigo,whatsapp_falhou_em")
        .gte("whatsapp_falhou_em", desde).execute()
    )
    por_numero: dict = {}
    for r in resp.data or []:
        numero = normalizar_telefone(r.get("telefone") or r.get("telemovel"))
        if numero:
            por_numero[numero] = r.get("whatsapp_erro_codigo")
    return [{"numero": n, "codigo": c} for n, c in por_numero.items()]


def texto_do_resumo(falhas: list[dict], horas: int = 24) -> str:
    """Só os 3 últimos dígitos: o email não leva telefones completos."""
    por_codigo: dict = {}
    for f in falhas:
        por_codigo.setdefault(f["codigo"], []).append("…" + f["numero"][-3:])
    linhas = [f"{len(falhas)} número(s) sem WhatsApp nas últimas {horas} h.", ""]
    for codigo, finais in sorted(por_codigo.items(), key=lambda kv: str(kv[0])):
        linhas.append(f"Código {codigo}: {len(finais)} ({', '.join(finais)})")
    linhas += [
        "",
        "131026 = mensagem não entregável (sem WhatsApp, número inativo ou termos por aceitar). "
        "Estes contactos ficam marcados em `contactos.whatsapp_falhou_em`; a marca limpa-se se "
        "a pessoa responder ou se uma mensagem for entregue.",
    ]
    return "\n".join(linhas)
