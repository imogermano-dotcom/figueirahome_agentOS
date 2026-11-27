"""Esqueleto das oportunidades do eGO que o relatório ainda não trouxe (pedido #28, `docs/fases/oportunidades-em-falta-pela-api-plano.md`).

O relatório das 03:37 só lê as oportunidades *editadas* nas últimas 48 h e criar uma não conta: a linha demora dias (ou nunca vem) e as
notas dessa oportunidade não entram (FK). Aqui cria-se só o que a lista de ativas da API dá. **Só INSERT**; o relatório completa o resto
(o upsert dele só escreve os campos que traz). Nunca escreve no eGO nem toca em linhas que existam.
"""

import logging
import re

from app.db.supabase_client import get_supabase
from app.integrations import ego_api

logger = logging.getLogger(__name__)

MAX_POR_VOLTA = 50
_URL = "https://admin.egorealestate.com/egocore/Leads/{}"
# Medidos a 26/11 em 2 648 oportunidades (API contra BD).
_TIPO_OPORTUNIDADE = {1: "Angariação", 2: "Venda", 3: "Arrendamento"}  # masterLeadType.id
_TIPO_PEDIDO = {4: "Pedido de Informação", 3: "Pedido de Visita", 1: "Procura", 7: "Pedido de Contacto"}  # leadTypeId; 0 = vazio
_ABERTA = (0, 1)  # leadStage: 0/1 = Ativa (o 0 era «Criada»); 2 = Ganha, 3 = Perdida (a lista de ativas também as traz)


def _pt(campo: dict | None) -> str | None:
    return ((campo or {}).get("nameMls") or {}).get("PT-PT")


def esqueleto(o: dict, utilizadores: dict[int, str], etapa: str | None = None, imovel: dict | None = None) -> dict | None:
    """Linha mínima para `oportunidades`, ou `None` se não se deve criar (fechada, tipo desconhecido, sem referência).
    `etapa` (`IsReport`) e `imovel` (linha de `imoveis` + `distrito`: natureza, localização, proprietário, preços de venda e arrendamento)
    só se conhecidos. Os preços da oportunidade são os da altura e diferem dos do imóvel em ~20 % das linhas antigas, mas numa oportunidade
    criada hoje coincidem. `imovel_preco` (o da proposta) e a proposta ficam para o relatório."""
    if not o.get("name") or o.get("leadStage") not in _ABERTA:
        return None
    tipo = _TIPO_OPORTUNIDADE.get((o.get("masterLeadType") or {}).get("id"))
    if not tipo:
        return None
    linha = {
        "oportunidade_ref": o["name"], "oportunidade_estado": "Ativa", "tipo_oportunidade": tipo,
        "tipo_pedido": _TIPO_PEDIDO.get(o.get("leadTypeId")),
        "cliente_nome": o.get("title"), "cliente_email": o.get("email"), "cliente_telefone": o.get("phone"),
        "ego_lead_id": o.get("id"), "url": _URL.format(o["id"]) if o.get("id") else None,
        "ego_data_criacao": (o.get("createDate") or "")[:10] or None, "data_criacao_iso": (o.get("createDate") or "")[:10] or None,
        "ego_editado_em": (o.get("alterDate") or "")[:10] or None, "imovel_ref": o.get("realestateReference"),
        "origem": _pt(o.get("leadOrigin")), "sub_origem": _pt(o.get("leadSubOrigin")),
        "responsavel": utilizadores.get(o.get("assignToSecurityUserId")), "etapa_atual": etapa,
        "imovel_natureza": (imovel or {}).get("natureza"), "imovel_concelho": (imovel or {}).get("concelho"),
        "imovel_freguesia": (imovel or {}).get("freguesia"), "imovel_distrito": (imovel or {}).get("distrito"),
        "imovel_proprietario": (imovel or {}).get("proprietario"),
        "imovel_venda": (imovel or {}).get("venda_preco") or None, "imovel_arrendamento": (imovel or {}).get("arrendamento_preco") or None,
        "ponto_situacao": o.get("situationPoint"),
        "ponto_situacao_alterado_em": (o.get("situationPointAlterDate") or "")[:10] if o.get("situationPoint") else None,
    }
    return {k: v for k, v in linha.items() if v not in (None, "")}


def _digitos9(texto: str | None) -> str:
    return re.sub(r"\D", "", texto or "")[-9:]


def _contacto_unico(sb, o: dict) -> tuple[str, str] | None:
    """(`contacto_id`, `contacto_match`) se o telefone ou, na falta, o email dão EXATAMENTE um contacto; com 2 ou mais não se adivinha."""
    tel = _digitos9(o.get("phone"))
    if len(tel) == 9:
        ids = {c["id"] for c in sb.table("contactos").select("id").or_(f"telefone.ilike.%{tel}%,telemovel.ilike.%{tel}%").limit(5).execute().data}
        if ids:
            return (next(iter(ids)), "telefone") if len(ids) == 1 else None
    email = (o.get("email") or "").strip().lower()
    if email:
        ids = {c["id"] for c in sb.table("contactos").select("id").ilike("email", email).limit(5).execute().data}
        if len(ids) == 1:
            return next(iter(ids)), "email"
    return None


_NEGOCIO = {1: "Venda", 2: "Arrendamento"}  # `BusinessSearch`; os outros (trespasse, férias…) não se usam na agência: ficam vazios


def _ids(texto) -> list[int]:
    return [int(x) for x in str(texto or "").split(",") if x.strip().isdigit()]


def pref_de_api(p: dict, naturezas: dict[int, str], estados: dict[int, str], local_de) -> dict:
    """Preferências da API → colunas `pref_*` (mesmos formatos do relatório). Só o que se traduz com certeza: um código desconhecido
    deixa o campo todo vazio, nunca se grava o código cru. `local_de(id)` → nome ou `None` (país não é zona)."""
    pref = {"pref_negocio": _NEGOCIO.get((_ids(p.get("BusinessSearch")) or [0])[0]),
            "pref_preco_min": p.get("PriceMin"), "pref_orcamento_max": p.get("PriceMax"),
            "pref_tipologia": f"T{int(p['RoomMin'])}" if p.get("RoomMin") is not None else None}
    for campo, ids, tabela in (("pref_natureza", _ids(p.get("NatureSearch")), naturezas), ("pref_disponibilidade", _ids(p.get("RealestateStatusSearch")), estados)):
        if ids and all(i in tabela for i in ids):
            pref[campo] = ",".join(sorted(tabela[i] for i in ids)) if campo == "pref_natureza" else ",".join(tabela[i] for i in ids)
    nomes = [local_de(i) for i in _ids(p.get("LocationSearch"))]
    if nomes and all(nomes):  # um país ou uma falha (nome vazio) deixa a zona toda vazia
        pref["pref_zona"] = ", ".join(nomes)
    return {k: v for k, v in pref.items() if v not in (None, "")}


def _gravar_prefs(sb, criadas: list[dict]) -> dict:
    """Preferências do eGO das oportunidades recém-criadas, pelo RPC `bulk_update_prefs` (COALESCE, só se `pref_extraido_em` é nulo:
    a extração por IA a partir das notas, que é mais rica, prevalece sempre). Nunca pára a volta."""
    r = {"com_prefs": 0, "erros": 0}
    try:
        naturezas, estados = ego_api.naturezas_de_imovel(), ego_api.estados_de_imovel()
    except Exception as e:
        logger.warning("oportunidades: tabelas de preferências indisponíveis (%s)", type(e).__name__)
        naturezas, estados = {}, {}
    locais: dict[int, str] = {}

    def local_de(i: int):  # "" = não é zona (país) ou falhou: o campo todo fica vazio
        if i not in locais:
            try:
                nome, nivel = ego_api.localizacao(i)
                locais[i] = nome if nome and (nivel or 0) >= 3 else ""
            except Exception:
                locais[i] = ""
        return locais[i]

    updates = []
    for o in criadas:
        try:
            p = ego_api.preferencias(o["id"])
            if p and (pref := pref_de_api(p, naturezas, estados, local_de)):
                updates.append({"oportunidade_ref": o["name"], **pref})
        except Exception as e:
            r["erros"] += 1
            logger.warning("oportunidades: preferências de %s por ler (%s)", o.get("name"), type(e).__name__)
    if updates:
        try:
            sb.rpc("bulk_update_prefs", {"updates": updates}).execute()
            r["com_prefs"] = len(updates)
        except Exception as e:
            r["erros"] += 1
            logger.warning("oportunidades: RPC bulk_update_prefs falhou (%s)", getattr(e, "code", type(e).__name__))
    return r


def _distritos(sb, concelhos: set[str]) -> dict[str, str]:
    """concelho → distrito, lido de oportunidades já gravadas (o relatório trazia-o). Vazio se falhar ou não houver."""
    if not concelhos:
        return {}
    try:
        linhas = sb.table("oportunidades").select("imovel_concelho,imovel_distrito").in_("imovel_concelho", sorted(concelhos)).not_.is_("imovel_distrito", "null").limit(500).execute().data
    except Exception as e:
        logger.warning("oportunidades: distritos por ler (%s)", getattr(e, "code", type(e).__name__))
        return {}
    return {x["imovel_concelho"]: x["imovel_distrito"] for x in linhas if x.get("imovel_distrito")}


def criar_em_falta(ativas: list[dict], gravar: bool) -> dict:
    """Cria o esqueleto das ativas do eGO que não estão em `oportunidades` (máx. `MAX_POR_VOLTA`). `gravar` falso só conta (`criaria`)."""
    nomes = [o["name"] for o in ativas if o.get("name")]
    if not nomes:
        return {"em_falta": 0}
    sb = get_supabase()
    existem: set[str] = set()
    for i in range(0, len(nomes), 300):
        existem |= {r["oportunidade_ref"] for r in sb.table("oportunidades").select("oportunidade_ref").in_("oportunidade_ref", nomes[i:i + 300]).execute().data}
    falta = [o for o in ativas if o.get("name") and o["name"] not in existem]
    if not falta:
        return {"em_falta": 0}
    try:
        utilizadores = ego_api.utilizadores()
    except Exception as e:  # sem o mapa cria sem responsável; o relatório completa-o
        logger.warning("oportunidades: utilizadores do eGO indisponíveis (%s)", type(e).__name__)
        utilizadores = {}
    try:  # a etapa vem de outra lista da API; sem ela cria sem etapa e o relatório completa
        etapas = ego_api.etapas_ativas()
    except Exception as e:
        logger.warning("oportunidades: etapas do eGO indisponíveis (%s)", type(e).__name__)
        etapas = {}
    imoveis: dict[str, dict] = {}
    refs_im = sorted({o["realestateReference"] for o in falta if o.get("realestateReference")})
    for i in range(0, len(refs_im), 300):
        try:
            imoveis |= {x["imovel_ref"]: x for x in sb.table("imoveis").select("imovel_ref,natureza,concelho,freguesia,proprietario,venda_preco,arrendamento_preco").in_("imovel_ref", refs_im[i:i + 300]).execute().data}
        except Exception as e:
            logger.warning("oportunidades: imóveis por ler (%s)", getattr(e, "code", type(e).__name__))
    distritos = _distritos(sb, {x["concelho"] for x in imoveis.values() if x.get("concelho")})
    for x in imoveis.values():  # `imoveis` não tem distrito: sai do que as oportunidades já gravaram para o mesmo concelho
        x["distrito"] = distritos.get(x.get("concelho"))
    prontas = [(o, esqueleto(o, utilizadores, etapas.get(o["name"]), imoveis.get(o.get("realestateReference")))) for o in falta]
    r = {"em_falta": len(falta), "saltadas": sum(1 for _, e in prontas if e is None)}
    prontas = [(o, e) for o, e in prontas if e][:MAX_POR_VOLTA]
    r["com_etapa"] = sum(1 for _, e in prontas if e.get("etapa_atual"))
    r["com_imovel"] = sum(1 for _, e in prontas if e.get("imovel_concelho"))
    if not gravar:
        r["criaria"] = len(prontas)
        return r
    r.update({"criadas": 0, "erros": 0, "ligadas": 0})
    pares, novas = [], []
    for o, e in prontas:
        try:
            sb.table("oportunidades").insert(e).execute()
            r["criadas"] += 1
            novas.append(o)
        except Exception as ex:  # chave duplicada = o relatório chegou entretanto: não é erro; só o código, a mensagem pode ter pessoas
            if getattr(ex, "code", None) != "23505":
                r["erros"] += 1
                logger.warning("oportunidades: esqueleto de %s falhou (%s)", e["oportunidade_ref"], getattr(ex, "code", type(ex).__name__))
            continue
        try:
            if par := _contacto_unico(sb, o):
                pares.append({"oportunidade_ref": e["oportunidade_ref"], "contacto_id": par[0], "contacto_match": par[1]})
        except Exception as ex:
            logger.warning("oportunidades: contacto de %s por ligar (%s)", e["oportunidade_ref"], getattr(ex, "code", type(ex).__name__))
    if novas:
        r["prefs"] = _gravar_prefs(sb, novas)
    if pares:
        try:
            sb.rpc("set_contacto_oportunidades", {"pares": pares}).execute()  # também propaga às notas, tarefas e visitas
            r["ligadas"] = len(pares)
        except Exception as ex:
            logger.warning("oportunidades: RPC set_contacto_oportunidades falhou (%s)", getattr(ex, "code", type(ex).__name__))
    return r


# ---- P3 do plano acelerado: atualizar as oportunidades que já existem --------------------------------------------------------------
# Medido a 26/11 em 2 669 ativas contra o relatório (`scripts/comparar_oportunidades_api_relatorio.py`): estado, tipo, origem, responsável e
# datas ≥ 99,7 % iguais; 56 oportunidades (2,1 %) editadas no eGO depois de o relatório as ver. NÃO se escrevem pela API: cliente_* (a lista só traz
# o título da lead, é a pessoa que o tem: P4), imovel_* (o preço da oportunidade é o da altura) e preferências (já têm extração por IA).
MAX_ATUALIZACOES_POR_VOLTA = 300
_PORTAL = {33: "Página Web", 700: "Idealista PT", 3500: "SUPERCASA", 328: "Imovirtual", 680: "Properstar (Free)", 24: "Casa Sapo",
           51: "Pack Portais Mundo", 459: "Kyero Portugal"}  # `portalId` → nome (medido a 26/11 contra o relatório; um id novo fica vazio)
COLUNAS_ATUALIZAVEIS = ("oportunidade_estado", "tipo_oportunidade", "tipo_pedido", "origem", "sub_origem", "responsavel", "etapa_atual",
                        "estado_fechado_em", "ponto_situacao", "ponto_situacao_alterado_em", "valor_negocio", "data_escritura", "portal",
                        "ego_editado_em")
_ESTADO = {0: "Ativa", 1: "Ativa", 2: "Ganha", 3: "Perdida"}  # `leadStage`; o 0 era «Criada» e o scraper também o guarda como Ativa


def _dia(v) -> str | None:
    return str(v)[:10] if v else None


def campos_da_api(o: dict, etapa: str | None, utilizadores: dict[int, str]) -> dict:
    """Valores das `COLUNAS_ATUALIZAVEIS` que a API dá, no formato da BD. O que vem vazio fica de fora: nunca se escreve nulo."""
    try:
        valor = round(float(o["businessFinalPrice"]), 2) if o.get("businessFinalPrice") else None
    except (TypeError, ValueError):
        valor = None
    v = {
        "oportunidade_estado": _ESTADO.get(o.get("leadStage")), "tipo_oportunidade": _TIPO_OPORTUNIDADE.get((o.get("masterLeadType") or {}).get("id")),
        "tipo_pedido": _TIPO_PEDIDO.get(o.get("leadTypeId")), "origem": _pt(o.get("leadOrigin")), "sub_origem": _pt(o.get("leadSubOrigin")),
        "responsavel": utilizadores.get(o.get("assignToSecurityUserId")), "etapa_atual": etapa, "estado_fechado_em": _dia(o.get("closedDate")),
        "ponto_situacao": o.get("situationPoint"), "ponto_situacao_alterado_em": _dia(o.get("situationPointAlterDate")) if o.get("situationPoint") else None,
        "valor_negocio": valor, "data_escritura": _dia(o.get("businessExecutionDate")), "portal": _PORTAL.get(o.get("portalId")),
        "ego_editado_em": _dia(o.get("alterDate")),
    }
    return {k: x for k, x in v.items() if x not in (None, "")}


def _igual(a, b) -> bool:
    if isinstance(a, (int, float)) or isinstance(b, (int, float)):
        try:
            return round(float(a), 2) == round(float(b), 2)
        except (TypeError, ValueError):
            return False
    return str(a).strip().lower() == str(b).strip().lower()


def planear_atualizacao(o: dict, linha: dict, api: dict) -> tuple[dict, bool]:
    """(campos a escrever, atrasada). Atrasada = a edição da API é de um dia posterior ao `ego_editado_em` da BD: o relatório ainda não a viu,
    por isso a API manda e corrige o que mudou. Senão só se preenchem os campos que a BD tem vazios. Nunca nulo, nunca apagar."""
    editado, alterado = _dia(linha.get("ego_editado_em")), _dia(o.get("alterDate"))
    atrasada = bool(editado and alterado and editado < alterado)
    if atrasada:
        campos = {c: x for c, x in api.items() if linha.get(c) in (None, "") or not _igual(linha.get(c), x)}
    else:
        campos = {c: x for c, x in api.items() if c != "ego_editado_em" and linha.get(c) in (None, "")}
    return campos, atrasada


def atualizar_existentes(ativas: list[dict], gravar: bool) -> dict:
    """Atualiza as `oportunidades` que já existem (máx. `MAX_ATUALIZACOES_POR_VOLTA` por volta). `gravar` falso só conta."""
    sb = get_supabase()
    nomes = [o["name"] for o in ativas if o.get("name")]
    bd: dict[str, dict] = {}
    for i in range(0, len(nomes), 300):
        for x in sb.table("oportunidades").select("oportunidade_ref," + ",".join(COLUNAS_ATUALIZAVEIS)).in_("oportunidade_ref", nomes[i:i + 300]).execute().data:
            bd[x["oportunidade_ref"]] = x
    try:
        utilizadores = ego_api.utilizadores()
    except Exception as e:
        logger.warning("oportunidades: utilizadores do eGO indisponíveis (%s)", type(e).__name__)
        utilizadores = {}
    try:  # sem etapas a etapa fica como está
        etapas = ego_api.etapas_ativas()
    except Exception as e:
        logger.warning("oportunidades: etapas do eGO indisponíveis (%s)", type(e).__name__)
        etapas = {}
    plano, atrasadas, por_coluna = {}, 0, {}
    for o in ativas:
        linha = bd.get(o.get("name"))
        if not linha:
            continue
        campos, atrasada = planear_atualizacao(o, linha, campos_da_api(o, etapas.get(o["name"]), utilizadores))
        atrasadas += atrasada
        if campos:
            plano[o["name"]] = campos
            for c in campos:
                por_coluna[c] = por_coluna.get(c, 0) + 1
    r = {"atrasadas": atrasadas, "a_atualizar": len(plano), "por_coluna": por_coluna}
    if not gravar:
        return r
    r.update({"atualizadas": 0, "erros": 0})
    for ref, campos in list(plano.items())[:MAX_ATUALIZACOES_POR_VOLTA]:
        try:
            sb.table("oportunidades").update(campos).eq("oportunidade_ref", ref).execute()
            r["atualizadas"] += 1
        except Exception as e:  # só o código: a mensagem pode ter pessoas
            r["erros"] += 1
            logger.warning("oportunidades: %s por atualizar (%s)", ref, getattr(e, "code", type(e).__name__))
    return r
