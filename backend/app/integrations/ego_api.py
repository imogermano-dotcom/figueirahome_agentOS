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


# Estado da proposta no eGO → texto que o relatório grava em `oportunidades.estado_proposta`. Os códigos não vêm
# documentados: deduzidos a 22/10/2026 por correspondência com o Supabase (88 de 90 oportunidades ativas coincidiam).
_ESTADO_PROPOSTA = {1: "Em avaliação", 3: "Aceite", 4: "Rejeitado"}
_PRECEDENCIA = ("Aceite", "Em avaliação", "Rejeitado")  # com várias propostas manda a melhor (visto: {Aceite, Rejeitado} → Aceite)


def estados_de_proposta(desde: str = "2020-01-01T00:00:00") -> dict[str, str]:
    """`{referência da oportunidade: estado da proposta}` para as oportunidades ativas com proposta desde `desde`.

    O sync das oportunidades só lê as editadas nas últimas 48 h e aceitar/recusar uma proposta não conta como edição
    (VEN_22173, VEN_20521, VEN_20311): esta consulta apanha-as sem depender dessa data. Três pedidos, uma página cada;
    se vier menos do que o `totalRows` levanta, porque comparar com dados parciais corrigiria linhas à toa.
    ponytail: propostas anteriores a `desde` e oportunidades arquivadas ficam de fora; alargar se aparecer um caso."""
    por_ref: dict[str, set[str]] = {}
    for codigo, estado in _ESTADO_PROPOSTA.items():
        d = _pedido("POST", "/lead/Opportunity/ListOpportunityByPage",
                    json={"leadArchived": 0, "proposalMinDate": desde, "proposalStatusIDList": [codigo]})
        lista = next((v for v in d.values() if isinstance(v, list)), []) if isinstance(d, dict) else d
        if isinstance(d, dict) and d.get("totalRows", len(lista)) > len(lista):
            raise EgoApiErro(f"propostas com estado {codigo}: página incompleta ({len(lista)} de {d['totalRows']})")
        for o in lista:
            por_ref.setdefault(o["name"], set()).add(estado)
    return {ref: next(e for e in _PRECEDENCIA if e in estados) for ref, estados in por_ref.items()}


def todos_os_imoveis(por_pagina: int = 500) -> list[dict]:
    """Todos os imóveis do eGO, de todos os estados (`ListRealestateByPage`, ~11 pedidos de 500 a 25/10: 5 163 linhas).
    A Web API pública só lista os publicados; esta lista tudo (pedido #45). Levanta se vierem menos linhas do que o
    `totalRows`: comparar com dados parciais atualizaria imóveis à toa."""
    todos: list[dict] = []
    pagina = 0
    total = None
    while True:
        d = _pedido("POST", "/realestate/Realestate/ListRealestateByPage",
                    json={"pageIndex": pagina, "numberOfRecords": por_pagina})
        lote = next((v for v in d.values() if isinstance(v, list)), []) if isinstance(d, dict) else d
        todos += lote
        total = d.get("totalRows") if isinstance(d, dict) else total
        if len(lote) < por_pagina:
            break
        pagina += 1
    if total is not None and len(todos) < total:
        raise EgoApiErro(f"imóveis: página incompleta ({len(todos)} de {total})")
    return todos


def um_por_referencia(imoveis: list[dict]) -> dict[str, dict]:
    """Uma linha por `reference`: o mesmo imóvel pode ter vários registos internos (FH2483_A: 3). Fica o ativo
    (`fieldStatusId` 0) de `lastUpdate` mais recente; empate pelo `id` maior. Sem referência não entra."""
    def chave(x):
        return (x.get("fieldStatusId") in (0, None), x.get("lastUpdate") or "", x.get("id") or 0)

    por_ref: dict[str, dict] = {}
    for i in imoveis:
        ref = (i.get("reference") or "").strip()
        if ref and (ref not in por_ref or chave(i) > chave(por_ref[ref])):
            por_ref[ref] = i
    return por_ref


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
