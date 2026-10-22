"""Cliente mínimo da API do eGO (api.egocrm.com). Só `inserir_lead`.

Procedimento e armadilhas: `docs/eGO-api/ego-api.md`. Login em 2 passos (o 1.º devolve as agências, o 2.º um
token preso à agência, válido 24 h); o Cloudflare recusa o User-Agent por omissão (403, erro 1010).
Escritas só pelo caminho de `leads_para_ego`: nunca `UpdateEntity` (ver o incidente de 14/10).
"""

import logging
import threading
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
_VALIDADE_S = 23 * 3600  # o token vale 24 h
_lock = threading.Lock()
_sessao: dict = {}  # token, application_id, security_user_id, ate

# Arrays que o `LeadRequestDto` marca como obrigatórios (mesmo vazios).
_ARRAYS = (
    "labels", "timelineCheckIDList", "accessSecurityUserIDList", "customFieldsValues", "financingChecklistId",
    "cpcvChecklistIDList", "scripturesChecklistIDList", "accessSecurityGroupIDList", "accessApplicationIDList",
    "accessExternalUserIDList", "bookingImprovementList", "assignToSecurityGroupIDList",
    "assignToSecurityUserIDList", "prospectionTimelineCheckIDList", "negotiationTimelineCheckIDList",
    "creditTypeModalityIDList",
)


class EgoApiErro(Exception):
    pass


def _dados(resp: httpx.Response):
    if resp.status_code >= 400:
        raise EgoApiErro(f"eGO API {resp.request.url.path}: HTTP {resp.status_code}")
    j = resp.json() if resp.content else {}
    return j.get("data", j) if isinstance(j, dict) else j


def _login(c: httpx.Client) -> dict:
    if not (settings.egorealestate_crm_username and settings.egorealestate_crm_password):
        raise EgoApiErro("Credenciais do eGO por configurar")
    d = _dados(c.post(f"{settings.egoapi_base_url}/authentication/Authentication/Login",
                      json={"username": settings.egorealestate_crm_username,
                            "password": settings.egorealestate_crm_password}))
    escritorio = settings.egorealestate_crm_office.upper()
    apps = d.get("applicationsAvailable") or []
    app = next((a for a in apps if str(a.get("name", "")).upper() == escritorio), None)
    if not app:
        raise EgoApiErro("Escritório do eGO não encontrado")
    app_id = app.get("id") or app.get("applicationId")
    d2 = _dados(c.get(f"{settings.egoapi_base_url}/authentication/Authentication/LoginToApplication",
                      params={"applicationId": app_id}, headers={"Authorization": f"Bearer {d['token']}"}))
    return {"token": d2["token"], "application_id": app_id, "security_user_id": d2.get("securityUserId"),
            "ate": time.time() + _VALIDADE_S}


def _sessao_valida(c: httpx.Client) -> dict:
    with _lock:
        if not _sessao or _sessao["ate"] < time.time():
            _sessao.clear()
            _sessao.update(_login(c))
        return dict(_sessao)


def corpo_de_lead(**campos) -> dict:
    """Corpo de `InsertLead` com os arrays obrigatórios vazios. `campos` sobrepõe."""
    corpo = {k: [] for k in _ARRAYS} | {"leadCIStatusBitFlag": 0}
    return corpo | {k: v for k, v in campos.items() if v is not None}


# O `GetLead` e o corpo do `UpdateLead` chamam de forma diferente ao mesmo campo (medido a 22/10 contra a especificação).
_RENOMEAR_LEITURA_ESCRITA = {
    "obs": "observation", "leadTypeId": "typeId", "masterTypeId": "masterLeadTypeId", "leadSubOriginId": "subOriginId",
    "leadCategoryId": "categoryId", "leadSubCategoryId": "subCategoryId", "leadDeleteReasonId": "deleteReasonId",
    "leadPaymentMethodId": "paymentMethodId", "leadPurchaseReasonId": "purchaseReasonId",
    "leadCreditSimulationId": "creditSimulationId", "LeadCIStatusBitFlag": "leadCIStatusBitFlag",
    "LeadQualificationResult": "leadQualificationResult", "LeadQualificationStatus": "leadQualificationStatus",
    "leadProbabilitySucess": "leadProbabilitySuccess",  # a API escreve «Sucess» ao ler e «Success» ao escrever
    "assignToSecurityUserIds": "assignToSecurityUserIDList", "assignToSecurityGroupIds": "assignToSecurityGroupIDList",
    "accessApplicationListId": "accessApplicationIDList", "accessExternalUserListId": "accessExternalUserIDList",
    "cpcvChecklistIds": "cpcvChecklistIDList", "scripturesChecklistIds": "scripturesChecklistIDList",
    "negotiationTimelineCheckIds": "negotiationTimelineCheckIDList",
    "prospectionTimelineCheckIds": "prospectionTimelineCheckIDList", "creditTypeModalityIDs": "creditTypeModalityIDList",
    "timelineCheckListId": "timelineCheckIDList", "financingChecklistIds": "financingChecklistId",
}


def corpo_de_atualizacao(atual: dict, **mudancas) -> dict:
    """Corpo do `UpdateLead` a partir do `GetLead`. ⚠️ O `UpdateLead` SUBSTITUI a lead: o que não for enviado fica vazio
    (22/10: um corpo só com o `id` e as observações apagou título, email e telefone). Por isso leva tudo o que o
    `GetLead` devolveu, com os nomes de escrita, e só depois as `mudancas`. Objetos aninhados (`leadOrigin`, …) são
    só de leitura e ficam de fora."""
    corpo = {k: [] for k in _ARRAYS} | {"leadCIStatusBitFlag": 0}
    for k, v in atual.items():
        if isinstance(v, dict) or (isinstance(v, list) and v and isinstance(v[0], dict)):
            continue
        corpo[_RENOMEAR_LEITURA_ESCRITA.get(k, k)] = v
    return corpo | mudancas


def atualizar_lead(lead_id: int, **mudancas) -> dict:
    """Altera campos de uma lead (`PUT /lead/Lead/UpdateLead`, corpo completo) e confirma lendo-a de volta. Devolve
    `{campo: (antes, depois)}` do que mudou; levanta se o eGO responder 0 ou se mudar algo além do pedido.
    Os campos de `mudancas` usam os nomes de ESCRITA (`observation`, `assignToSecurityUserId`, `realestateId`, …)."""
    with httpx.Client(timeout=30, headers={"User-Agent": _UA}) as c:
        s = _sessao_valida(c)
        h = {"Authorization": f"Bearer {s['token']}"}
        q = {"applicationId": s["application_id"], "securityUserId": s["security_user_id"]}

        def ler() -> dict:
            return _dados(c.get(f"{settings.egoapi_base_url}/lead/Lead/GetLead", params={"leadId": lead_id, **q}, headers=h))

        antes = ler()
        corpo = corpo_de_atualizacao(antes, id=lead_id, applicationId=s["application_id"], **mudancas)
        r = c.put(f"{settings.egoapi_base_url}/lead/Lead/UpdateLead", params=q, json=corpo, headers=h)
        resposta = _dados(r)
        if not resposta:  # `0`/`false`: nada foi alterado
            raise EgoApiErro(f"UpdateLead {lead_id} não alterou nada (resposta {resposta!r})")
        depois = ler()
    ignorar = {"alterDate", "updateDate", "assignToSecurityUserAlterDate", "assignToSecurityUserNames"}
    mudou = {k: (antes.get(k), depois.get(k)) for k in antes.keys() | depois.keys()
             if k not in ignorar and not isinstance(antes.get(k), (dict, list)) and antes.get(k) != depois.get(k)}
    pedidos = {_RENOMEAR_LEITURA_ESCRITA_INVERSO.get(k, k) for k in mudancas}
    inesperados = {k: v for k, v in mudou.items() if k not in pedidos}
    if inesperados:
        raise EgoApiErro(f"UpdateLead {lead_id} mudou campos que não pediste: {inesperados}")
    return mudou


_RENOMEAR_LEITURA_ESCRITA_INVERSO = {v: k for k, v in _RENOMEAR_LEITURA_ESCRITA.items()}


def _pedido(metodo: str, caminho: str, **kw):
    with httpx.Client(timeout=60, headers={"User-Agent": _UA}) as c:
        s = _sessao_valida(c)
        r = c.request(metodo, f"{settings.egoapi_base_url}{caminho}", params={"applicationId": s["application_id"]},
                      headers={"Authorization": f"Bearer {s['token']}"}, **kw)
        return _dados(r)


def leads_abertas() -> list[dict]:
    """Leads de internet ativas (a caixa que os consultores veem). ~80, uma página."""
    return _pedido("POST", "/lead/Lead/ListLeadByPage", json={}).get("leads") or []


def imovel_id(referencia: str) -> int | None:
    """Id do imóvel na API (≠ `imoveis.ego_id`) pela referência exata; o eGO atribui a consultora a partir dele."""
    d = _pedido("POST", "/realestate/Realestate/ListRealestateByPage", json={"reference": referencia})
    return next((x["id"] for x in d.get("realestatesByPageDto") or [] if x.get("reference") == referencia), None)


def imovel(referencia: str) -> dict | None:
    """Imóvel pela referência exata: `id` (o `realestateId` da lead) e `securityUserId` (a consultora do imóvel)."""
    d = _pedido("POST", "/realestate/Realestate/ListRealestateByPage", json={"reference": referencia})
    return next((x for x in d.get("realestatesByPageDto") or [] if x.get("reference") == referencia), None)


def oportunidades_editadas_desde(horas: int) -> int:
    """Quantas oportunidades ativas foram editadas nas últimas `horas` (hora de Lisboa, como o `alterDate` do eGO).

    Serve para distinguir «0 resultados» de uma falha do scraper: o relatório «Editado em > últimas 48 horas» não
    mostra o botão Relatórios quando ninguém editou nada (19/10: fim de semana sem edições)."""
    d = _pedido("POST", "/lead/Opportunity/ListOpportunityByPage", json={"leadArchived": 0})
    lista = next((v for v in d.values() if isinstance(v, list)), []) if isinstance(d, dict) else d
    limite = (datetime.now(ZoneInfo("Europe/Lisbon")).replace(tzinfo=None) - timedelta(hours=horas)).isoformat()
    return sum(1 for o in lista if (o.get("alterDate") or "") >= limite)


def inserir_lead(corpo: dict) -> int | None:
    """Cria a lead no eGO. Devolve o id, ou None se a resposta não o trouxer (a lead foi criada: HTTP 2xx)."""
    with httpx.Client(timeout=30, headers={"User-Agent": _UA}) as c:
        s = _sessao_valida(c)
        corpo = corpo | {"applicationId": s["application_id"], "securityUserId": s["security_user_id"]}
        r = c.post(f"{settings.egoapi_base_url}/lead/Lead/InsertLead",
                   params={"applicationId": s["application_id"], "securityUserId": s["security_user_id"]},
                   json=corpo, headers={"Authorization": f"Bearer {s['token']}"})
        if r.status_code == 401:  # token caducado antes do previsto: uma nova volta
            with _lock:
                _sessao.clear()
        d = _dados(r)
    novo = d.get("id") if isinstance(d, dict) else d
    return int(novo) if isinstance(novo, (int, str)) and str(novo).isdigit() else None
