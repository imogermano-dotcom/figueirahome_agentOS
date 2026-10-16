"""Cliente mínimo da API do eGO (api.egocrm.com). Só `inserir_lead`.

Procedimento e armadilhas: `docs/eGO-api/ego-api.md`. Login em 2 passos (o 1.º devolve as agências, o 2.º um
token preso à agência, válido 24 h); o Cloudflare recusa o User-Agent por omissão (403, erro 1010).
Escritas só pelo caminho de `leads_para_ego`: nunca `UpdateEntity` (ver o incidente de 14/10).
"""

import logging
import threading
import time

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
