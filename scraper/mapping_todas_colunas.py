"""Mapeamento do relatório eGO "jmarques_todas_as_colunas" (Oportunidades,
todas as colunas, filtro "Últimas 48 horas") para as tabelas de produção
`oportunidades` / `notas` / `tarefas` / `contactos`, documentadas (não como
código, só como spec) em `PIPELINE_SYNC_EGO_SUPABASE_DEV.md` §3/§6/§7.

Técnica: NÃO usa o offset `SHIFT` absoluto da doc (calibrado para o export
Wigo `todas_as_colunas_*.xlsx`, fonte diferente deste relatório eGO). Em vez
disso reutiliza o padrão já comprovado em
`backend/scripts/export_relatorio_oportunidades.py`: normaliza o cabeçalho e
usa o sufixo de ocorrência (" (2)", " (3)", ...) que `_dedupe_headers` já
aplica a nomes repetidos. Confirmado em 2 corridas reais (428 col/5 linhas e
473 col/945 linhas — `scraper/output/headers.txt` e `headers2.txt`) que a
CONTAGEM e ORDEM de ocorrências de cada nome repetido (ex: "Referência" 5x)
é estável mesmo quando a contagem total de colunas muda — a área de blocos
de imóvel/tags entre eles varia de tamanho, mas não afecta a ordem relativa
dos blocos seguintes (contactos → notas → tarefas → preferências → visitas).

O bloco de imóvel embutido na oportunidade (índices ~84-270, entre "Motivo
de transação" e "Nome") é DELIBERADAMENTE ignorado — `imoveis` já é
sincronizado por `backend/app/integrations/imoveis_sync.py`, escrever aqui
também duplicaria/conflituaria essa fonte.

Normalização: só a confirmada na doc (`oportunidade_estado`: "Activa"→
"Ativa"). `TIPO_OP_MAP`/`STATUS_MAP`/`PREF_QUARTOS_MAP` completos não estão
documentados (só exemplos parciais) — em vez de adivinhar valores errados
para produção, os campos correspondentes ficam com o valor bruto do eGO.
Rever no dry-run antes de activar upserts reais.
"""
import datetime
import re
import unicodedata

# ────────────────────────────────────────────────────────────────
# Normalização de cabeçalho (igual a export_relatorio_oportunidades.py)
# ────────────────────────────────────────────────────────────────


def normalize(header: str) -> str:
    text = unicodedata.normalize("NFKD", header).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-zA-Z0-9]+", "_", text).strip("_").lower()


def dedupe_headers(headers: list[str]) -> list[str]:
    seen: dict[str, int] = {}
    result = []
    for h in headers:
        seen[h] = seen.get(h, 0) + 1
        result.append(h if seen[h] == 1 else f"{h} ({seen[h]})")
    return result


# ────────────────────────────────────────────────────────────────
# Alias: cabeçalho normalizado (com sufixo de ocorrência) → campo destino.
# Calibrado contra scraper/output/headers2.txt (473 colunas, 945 linhas,
# corrida real 2026-07-28). Cabeçalhos sem alias e sem bater directo num
# nome já conhecido (`_KNOWN_COLUMNS`) vão para `extra`.
# ────────────────────────────────────────────────────────────────

# Bloco A — Oportunidade (índices ~0-83 do relatório real).
_ALIASES_OPORTUNIDADE = {
    "referencia": "oportunidade_ref",
    "potencial_cliente": "cliente_nome",
    "proprietario": "imovel_proprietario",
    "tipo_de_negocio": "tipo_oportunidade",
    "tipo_de_pedido": "tipo_pedido",
    "estado": "oportunidade_estado",
    "etapa": "etapa_atual",
    "data_da_proposta": "data_proposta",
    "estado_2": "estado_proposta",
    "etapa_2": "etapa_proposta",
    "data_de_criacao": "ego_data_criacao",
    "editado_em": "ego_editado_em",
    "email_da_agencia": "agencia_email",
    "telefone_da_agencia": "agencia_telefone",
    "etapas_de_cpcv": "etapas_cpcv",
    "etapas_de_escrituras": "etapas_escrituras",
    "checklist_de_financiamento": "checklist_financiamento",
    "checklist_de_cpcv": "checklist_cpcv",
    "checklist_de_escrituras": "checklist_escrituras",
    "referencia_2": "imovel_ref",
    "natureza": "imovel_natureza",
    "distrito": "imovel_distrito",
    "concelho": "imovel_concelho",
    "freguesia": "imovel_freguesia",
    "venda": "imovel_venda",  # "Venda (€)" — normaliza igual a "Venda" (tag), mas esta vem primeiro na ordem das colunas
    "link": "url",
    "ponto_de_situacao": "ponto_situacao",
    "ponto_de_situacao_alterado_em": "ponto_situacao_alterado_em",
    "data_da_escritura": "data_escritura",
    "valor_do_negocio": "valor_negocio",
    "equipa_do_responsavel": "equipa_responsavel",
    "motivo_de_transacao": "motivo_transacao",
}
# Campos cujo cabeçalho normalizado já bate direto com o nome destino
# (sem precisar de alias): origem, sub_origem, portal, imovel_preco,
# proposta, diferenca, probabilidade, agencia, responsavel,
# estado_fechado_em.

_KNOWN_OPORTUNIDADE = {
    "oportunidade_ref", "cliente_nome", "imovel_proprietario", "tipo_oportunidade",
    "tipo_pedido", "origem", "sub_origem", "portal", "oportunidade_estado", "etapa_atual",
    "imovel_preco", "proposta", "diferenca", "data_proposta", "estado_proposta",
    "etapa_proposta", "ego_data_criacao", "ego_editado_em", "probabilidade", "agencia",
    "agencia_email", "agencia_telefone", "responsavel", "etapas_cpcv", "etapas_escrituras",
    "checklist_financiamento", "checklist_cpcv", "checklist_escrituras", "imovel_ref",
    "imovel_natureza", "imovel_distrito", "imovel_concelho", "imovel_freguesia",
    "imovel_venda", "url", "estado_fechado_em", "ponto_situacao", "ponto_situacao_alterado_em",
    "data_escritura", "valor_negocio", "equipa_responsavel", "motivo_transacao",
}

# Bloco B — Contacto (só os 5 campos documentados; resto fica em extra).
_ALIASES_CONTACTO = {
    "nome": "nome",
    "telemovel": "telemovel",
    "email": "email",
    "link_2": "ego_link",
    "alterado_em": "ego_atualizado_em",
}
_KNOWN_CONTACTO = {"nome", "telemovel", "email", "ego_link", "ego_atualizado_em", "criado_em"}

# Bloco C — Notas.
_ALIASES_NOTA = {
    "descricao_4": "nota_texto",
    "criado_em_2": "nota_data_raw",
    "criado_por_2": "nota_autor",
    "tipo_de_nota": "nota_tipo",
    "anexos": "nota_anexos",
}
_KNOWN_NOTA = {"nota_texto", "nota_data_raw", "nota_autor", "nota_tipo", "nota_anexos"}

# Bloco D — Tarefas.
_ALIASES_TAREFA = {
    "assunto": "tarefa_titulo",
    "descricao_5": "tarefa_descricao",
    "data_de_agendamento": "tarefa_due_raw",
    "responsavel_4": "tarefa_responsavel",
    "criado_por_3": "tarefa_criado_por",
    "estado_da_tarefa": "tarefa_status",
    "data_de_criacao_3": "tarefa_criado_em",
    "data_de_reagendamento": "tarefa_reagendamento_raw",
    "reagendada": "tarefa_reagendada",
}
_KNOWN_TAREFA = {
    "tarefa_titulo", "tarefa_descricao", "tarefa_due_raw", "tarefa_responsavel",
    "tarefa_criado_por", "tarefa_status", "tarefa_criado_em", "tarefa_reagendamento_raw",
    "tarefa_reagendada",
}
_TAREFA_STATUS_VALIDOS = {"Concluído", "Em Curso", "Pendente"}

# Bloco E — Preferências (só os 7 campos documentados; escritos via RPC
# `bulk_update_prefs`, nunca update directo — ver doc §3.7).
_ALIASES_PREF = {
    "localizacao": "pref_zona",
    "natureza_3": "pref_natureza",
    "negocio": "pref_negocio",
    "minimo_de_quartos": "pref_tipologia_raw",  # nº de quartos, converter p/ "T#"
    "preco_minimo": "pref_preco_min",
    "preco_maximo": "pref_orcamento_max",
    "disponibilidade_2": "pref_disponibilidade",
}
_KNOWN_PREF = {
    "pref_zona", "pref_natureza", "pref_negocio", "pref_tipologia_raw",
    "pref_preco_min", "pref_orcamento_max", "pref_disponibilidade",
}

# Bloco F — Visitas (update directo sempre, nunca condicional — doc §3.8).
_ALIASES_VISITA = {
    "referencia_4": "visita_ref_ego",
    "visita_anulada_desmarcada": "visita_anulada",
    "ficou_interessado": "visita_interessado",
    "data": "visita_data",
    "proprietario_4": "visita_imovel_proprietario",
    "potencial_cliente_2": "visita_cliente",
    "pontos_positivos": "visita_pontos_positivos",
    "pontos_negativos": "visita_pontos_negativos",
    "sobre_o_negocio": "visita_sobre_negocio",
    "observacoes": "visita_observacoes",
    "responsavel_5": "visita_responsavel",
    "referencia_5": "visita_imovel_ref",  # também grava em imovel2_ref
    "distrito_4": "imovel2_distrito",
    "concelho_4": "imovel2_concelho",
    "freguesia_4": "imovel2_freguesia",
    "venda_3": "imovel2_venda",
}
_KNOWN_VISITA = {
    "visita_ref_ego", "visita_anulada", "visita_interessado", "visita_data",
    "visita_imovel_proprietario", "visita_cliente", "visita_pontos_positivos",
    "visita_pontos_negativos", "visita_sobre_negocio", "visita_observacoes",
    "visita_responsavel", "visita_imovel_ref", "imovel2_distrito", "imovel2_concelho",
    "imovel2_freguesia", "imovel2_venda",
}
_VISITA_ANULADA_VALIDOS = {"Sim", "Não"}

_ALL_ALIASES = {
    **_ALIASES_OPORTUNIDADE, **_ALIASES_CONTACTO, **_ALIASES_NOTA,
    **_ALIASES_TAREFA, **_ALIASES_PREF, **_ALIASES_VISITA,
}
_ALL_KNOWN = (
    _KNOWN_OPORTUNIDADE | _KNOWN_CONTACTO | _KNOWN_NOTA | _KNOWN_TAREFA
    | _KNOWN_PREF | _KNOWN_VISITA
)


def map_row(row: dict) -> dict:
    """1 linha do relatório → dict com todos os campos conhecidos + `extra`
    com o resto (bloco de imóvel embutido, tags, campos de preferência sem
    mapa, etc.)."""
    record: dict = {"extra": {}}
    for header, value in row.items():
        key = normalize(str(header))
        key = _ALL_ALIASES.get(key, key)
        if key in _ALL_KNOWN and key not in record:
            record[key] = None if value is None else str(value).strip()
        else:
            record["extra"][str(header)] = value

    if record.get("oportunidade_estado") == "Activa":
        record["oportunidade_estado"] = "Ativa"  # única normalização confirmada na doc §7

    # ego_data_criacao/ego_editado_em já estão em ISO em produção (confirmado
    # no dry-run) — o relatório eGO dá formato PT ("dd/mm/aaaa"); converter
    # em vez de escrever PT por cima de ISO existente (decisão utilizador).
    for campo in ("ego_data_criacao", "ego_editado_em"):
        iso = _data_iso(record.get(campo))
        if iso:
            record[campo] = iso

    return record


def _data_iso(valor: str | None) -> str | None:
    if not valor:
        return None
    try:
        return datetime.datetime.strptime(valor.strip(), "%d/%m/%Y").date().isoformat()
    except (ValueError, AttributeError):
        return None


_ORIGEM_LISTA = "todas_as_colunas"  # valor fixo (doc §3.2/§3.5/§3.6)

# Campos `numeric` no Postgres — o relatório eGO dá formato PT ("240.000,0",
# vírgula decimal), Postgres só aceita ponto. Confirmado ao vivo: upsert
# falhou com "invalid input syntax for type numeric" até isto ser aplicado.
_CAMPOS_NUMERICOS = {
    "imovel_preco", "proposta", "diferenca", "imovel_venda", "valor_negocio",
    "imovel2_venda", "pref_preco_min", "pref_orcamento_max",
}

# Campos `date`/`timestamptz` no Postgres — mesmo problema dos numéricos:
# relatório dá "dd/mm/aaaa", Postgres com datestyle ISO rejeita ("date/time
# field value out of range"). Confirmado ao vivo em estado_fechado_em.
_CAMPOS_DATA = {
    "estado_fechado_em", "ponto_situacao_alterado_em", "data_escritura",
    "data_proposta", "visita_data",
}


def _numero_pt(valor: str | None) -> str | None:
    if not valor:
        return None
    limpo = valor.replace(".", "").replace(",", ".")
    try:
        float(limpo)
    except ValueError:
        return valor  # não é número (ex: já teria falhado antes) — devolver como veio
    return limpo


def classify(record: dict) -> dict:
    """Separa 1 registo já mapeado (`map_row`) nos sub-registos que a linha
    do relatório representa: sempre oportunidade + contacto; nota se tiver
    texto/autor; tarefa se `tarefa_status` for um valor válido; visita se
    `visita_anulada` for Sim/Não. Datas convertidas p/ ISO onde a doc pede."""
    oportunidade = {k: record.get(k) for k in _KNOWN_OPORTUNIDADE if record.get(k) is not None}
    if oportunidade.get("ego_data_criacao"):
        # já convertido p/ ISO em map_row — reaproveitar em vez de re-parsear.
        oportunidade["data_criacao_iso"] = oportunidade["ego_data_criacao"]
    oportunidade["origem_lista"] = _ORIGEM_LISTA
    for campo in _CAMPOS_NUMERICOS:
        if oportunidade.get(campo) is not None:
            oportunidade[campo] = _numero_pt(oportunidade[campo])
    for campo in _CAMPOS_DATA:
        if oportunidade.get(campo) is not None:
            iso = _data_iso(oportunidade[campo])
            if iso:
                oportunidade[campo] = iso

    contacto = {k: record.get(k) for k in _KNOWN_CONTACTO if record.get(k) is not None}
    if contacto.get("ego_atualizado_em"):
        # produção guarda ISO (timestamptz) — confirmado ao vivo — mesma
        # fonte alimenta `criado_em` (doc §3.4, I(458)).
        iso = _data_iso(contacto["ego_atualizado_em"])
        if iso:
            contacto["ego_atualizado_em"] = iso
            contacto["criado_em"] = iso

    # notas/tarefas replicam estes campos da própria oportunidade (doc
    # §3.5/§3.6: cliente_nome, url, tipo_oportunidade, origem_lista).
    _denorm = {
        "cliente_nome": oportunidade.get("cliente_nome"),
        "url": oportunidade.get("url"),
        "tipo_oportunidade": oportunidade.get("tipo_oportunidade"),
        "origem_lista": _ORIGEM_LISTA,
    }

    nota = None
    if record.get("nota_texto") or record.get("nota_autor"):
        nota = {k: record.get(k) for k in _KNOWN_NOTA if record.get(k) is not None}
        if nota.get("nota_texto"):
            nota["nota_texto"] = nota["nota_texto"][:1200]  # limite do índice btree Postgres (doc §7)
        if nota.get("nota_data_raw"):
            iso = _data_iso(nota["nota_data_raw"])
            if iso:
                nota["nota_data_iso"] = iso
        nota.update({k: v for k, v in _denorm.items() if v is not None})

    tarefa = None
    if record.get("tarefa_status") in _TAREFA_STATUS_VALIDOS:
        tarefa = {k: record.get(k) for k in _KNOWN_TAREFA if record.get(k) is not None}
        if tarefa.get("tarefa_due_raw"):
            iso = _data_iso(tarefa["tarefa_due_raw"])
            if iso:
                tarefa["tarefa_due_iso"] = iso
        if tarefa.get("tarefa_reagendamento_raw"):
            iso = _data_iso(tarefa.pop("tarefa_reagendamento_raw"))
            if iso:
                tarefa["tarefa_reagendamento_iso"] = iso
        tarefa.update({k: v for k, v in _denorm.items() if v is not None})

    visita = None
    if record.get("visita_anulada") in _VISITA_ANULADA_VALIDOS:
        visita = {k: record.get(k) for k in _KNOWN_VISITA if record.get(k) is not None}
        if visita.get("visita_imovel_ref"):
            visita["imovel2_ref"] = visita["visita_imovel_ref"]
        if visita.get("imovel2_venda") is not None:
            visita["imovel2_venda"] = _numero_pt(visita["imovel2_venda"])
        if visita.get("visita_data") is not None:
            iso = _data_iso(visita["visita_data"])
            if iso:
                visita["visita_data"] = iso

    pref = {k: record.get(k) for k in _KNOWN_PREF if record.get(k) is not None}
    for campo in ("pref_preco_min", "pref_orcamento_max"):
        if pref.get(campo) is not None:
            pref[campo] = _numero_pt(pref[campo])

    return {
        "oportunidade": oportunidade,
        "contacto": contacto or None,
        "nota": nota,
        "tarefa": tarefa,
        "visita": visita,
        "pref": pref or None,
    }


def group(classified: list[dict]) -> dict:
    """Uma oportunidade tem várias linhas no relatório (1 por nota/tarefa/
    visita) — agrupa por `oportunidade_ref` (oportunidades/notas/tarefas,
    fundindo campos da própria oportunidade de todas as linhas) e por
    `ego_link` (contactos, podem repetir-se entre oportunidades diferentes).

    Visita/imovel2_* são campos da PRÓPRIA tabela `oportunidades` (doc §3.8,
    não uma tabela à parte) — fundidos aqui, update directo sempre. Prefs
    ficam num lote SEPARADO (`prefs`, chave `oportunidade_ref`) porque só
    podem ser escritas via RPC `bulk_update_prefs` (doc §3.7, respeita
    `pref_extraido_em`) — nunca upsert directo na tabela `oportunidades`."""
    oportunidades: dict[str, dict] = {}
    notas: list[dict] = []
    tarefas: list[dict] = []
    prefs: dict[str, dict] = {}
    contactos: dict[str, dict] = {}
    ignoradas = 0

    for c in classified:
        ref = c["oportunidade"].get("oportunidade_ref")
        if not ref:
            ignoradas += 1
            continue

        if ref not in oportunidades:
            oportunidades[ref] = dict(c["oportunidade"])
        else:
            for k, v in c["oportunidade"].items():
                if v is not None:
                    oportunidades[ref].setdefault(k, v)
        if c["visita"]:
            for k, v in c["visita"].items():
                oportunidades[ref].setdefault(k, v)

        if c["pref"]:
            if ref not in prefs:
                prefs[ref] = {}
            for k, v in c["pref"].items():
                prefs[ref].setdefault(k, v)

        if c["nota"]:
            notas.append({**c["nota"], "oportunidade_ref": ref})
        if c["tarefa"]:
            tarefas.append({**c["tarefa"], "oportunidade_ref": ref})

        if c["contacto"] and c["contacto"].get("ego_link"):
            link = c["contacto"]["ego_link"]
            if link not in contactos:
                contactos[link] = dict(c["contacto"])

    if ignoradas:
        print(f"  {ignoradas} linha(s) sem oportunidade_ref ignoradas")

    # cliente_nome/tipo_oportunidade/url em notas/tarefas vêm da linha
    # individual do relatório — se essa linha em particular tiver o campo
    # vazio (comum quando a linha só existe p/ carregar uma nota), preenche
    # a partir do registo final e já fundido da oportunidade.
    for lote in (notas, tarefas):
        for reg in lote:
            oport = oportunidades.get(reg["oportunidade_ref"])
            if not oport:
                continue
            for campo in ("cliente_nome", "tipo_oportunidade", "url"):
                if reg.get(campo) is None and oport.get(campo) is not None:
                    reg[campo] = oport[campo]

    return {
        "oportunidades": list(oportunidades.values()),
        "notas": notas,
        "tarefas": tarefas,
        "prefs": [{**v, "oportunidade_ref": ref} for ref, v in prefs.items()],
        "contactos": list(contactos.values()),
    }
