"""Registry de tools — definições e execução, partilhadas por todos os assistentes.

Cada assistante declara em `assistants.py` que tools pode usar; `tools_para()`
devolve o subconjunto correspondente. As tools de consulta interna
(`consultar_*`) existem aqui mas só o assistente `broker` lhes chega.
"""

import asyncio
import json
import logging
from datetime import date

from app.agents.broker.guards import (
    encerrar_lead_do_telefone,
    find_or_create_cliente,
    normalizar_telefone,
    visita_permitida,
)
from app.db.supabase_client import get_supabase
from app.models.lead import ESTADOS_FECHADOS
from app.notificacoes import notificar

logger = logging.getLogger(__name__)

_CAMPOS_FICHA = (
    "imovel_ref,natureza,titulo,quartos,casas_banho,area_util,venda_preco,"
    "arrendamento_preco,morada,concelho,freguesia,zona,conservacao,"
    "certificacao_energetica,descricao,foto_principal,piscina,garagem,jardim,"
    "terraco,varanda,vista_mar,vista_praia,ar_condicionado,elevador"
)

TOOL_DEFINITIONS = [
    # ── Cliente-facing (A1 / A2) ──────────────────────────────
    {
        "name": "pesquisar_imoveis",
        "description": (
            "Pesquisa imóveis disponíveis no portefólio da agência. Usa sempre que o "
            "cliente mencionar tipo de imóvel, quartos, zona ou preço. Devolve até 3 "
            "opções, das mais baratas para as mais caras."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "natureza": {
                    "type": "string",
                    "description": "Tipo de imóvel: Apartamento, Moradia, Terreno, Comercial, etc.",
                },
                "quartos": {"type": "integer", "description": "Número de quartos (T0=0, T1=1, T2=2, ...)"},
                "zona": {
                    "type": "string",
                    "description": "Concelho, freguesia ou zona (ex: Figueira da Foz, Buarcos)",
                },
                "tipo_negocio": {
                    "type": "string",
                    "enum": ["venda", "arrendamento"],
                    "description": "Se é para compra (venda) ou arrendamento",
                },
                "preco_max": {"type": "number", "description": "Preço máximo em euros"},
                "preco_min": {"type": "number", "description": "Preço mínimo em euros"},
            },
            "required": [],
        },
    },
    {
        "name": "ficha_imovel",
        "description": (
            "Obtém a ficha completa de UM imóvel, por referência (ex: FH2233) ou morada. "
            "Usa quando o cliente já identificou o imóvel de que quer saber."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "imovel_ref": {"type": "string", "description": "Referência do imóvel, ex: FH2233"},
                "morada": {"type": "string", "description": "Morada ou rua, se não houver referência"},
            },
            "required": [],
        },
    },
    {
        "name": "guardar_dados_cliente",
        "description": (
            "Guarda ou actualiza os dados do cliente. Chama assim que tiveres pelo menos "
            "o nome e o tipo de interesse."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "nome": {"type": "string"},
                "telefone": {"type": "string", "description": "Telefone de contacto, se diferente do WhatsApp"},
                "email": {"type": "string"},
                "tipo_interesse": {
                    "type": "string",
                    "enum": ["compra", "arrendamento", "venda", "outro"],
                },
                "orcamento": {"type": "number", "description": "Orçamento em euros"},
                "zona_preferida": {"type": "string"},
                "resumo": {"type": "string", "description": "Resumo breve da conversa"},
            },
            "required": ["nome", "tipo_interesse", "resumo"],
        },
    },
    {
        "name": "agendar_visita",
        "description": (
            "Regista um pedido de visita a um imóvel. A tool verifica se o orçamento "
            "declarado é compatível com o preço — se não for, recusa e devolve instruções. "
            "Propõe tu os horários ao cliente; não lhe peças que escolha sozinho. "
            "O horário fica por confirmar pelo consultor."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "imovel_ref": {"type": "string", "description": "Referência do imóvel, ex: FH2233"},
                "nome": {"type": "string", "description": "Nome completo do cliente"},
                "telefone": {"type": "string", "description": "Telefone de contacto"},
                "quando": {
                    "type": "string",
                    "description": "Data e hora pretendidas, como o cliente as disse (ex: 'sábado às 15h')",
                },
                "data_iso": {
                    "type": "string",
                    "description": "A mesma data em formato AAAA-MM-DD, se conseguires determiná-la",
                },
                "orcamento": {"type": "number", "description": "Orçamento declarado pelo cliente, em euros"},
            },
            "required": ["imovel_ref", "nome", "telefone", "quando"],
        },
    },
    {
        "name": "escalar_para_humano",
        "description": (
            "Regista uma tarefa para o consultor tratar. Usa para propostas de compra, "
            "negociação de preço, reclamações, assuntos legais, angariações, recrutamento, "
            "ou qualquer questão que não saibas responder."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "motivo": {
                    "type": "string",
                    "description": "Motivo curto, ex: 'proposta de compra', 'reclamação', 'angariação'",
                },
                "resumo": {"type": "string", "description": "Contexto completo da conversa para o consultor"},
                "nome": {"type": "string"},
                "telefone": {"type": "string"},
                "imovel_ref": {"type": "string", "description": "Imóvel em causa, se houver"},
                "urgente": {"type": "boolean", "description": "True para reclamações e assuntos legais"},
            },
            "required": ["motivo", "resumo"],
        },
    },
    {
        "name": "encerrar_lead",
        "description": (
            "Encerra o contacto. Usa quando a pessoa diz que foi engano (número errado, "
            "não preencheu formulário nenhum, não é com ela) ou que não tem interesse "
            "nenhum. Depois de chamares, despede-te numa frase e não voltes a insistir."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "motivo": {
                    "type": "string",
                    "enum": ["engano", "sem_interesse"],
                    "description": "'engano' se não é a pessoa certa; 'sem_interesse' se é mas não quer",
                },
                "nota": {"type": "string", "description": "O que a pessoa disse, em poucas palavras"},
            },
            "required": ["motivo"],
        },
    },
    # ── Internas (só o assistente `broker`) ───────────────────
    {
        "name": "consultar_clientes",
        "description": "Consulta clientes na base de dados com filtros opcionais.",
        "input_schema": {
            "type": "object",
            "properties": {
                "nome": {"type": "string", "description": "Filtrar por nome (parcial)"},
                "telefone": {"type": "string", "description": "Filtrar por telefone (exacto)"},
                "tipo_interesse": {
                    "type": "string",
                    "enum": ["compra", "arrendamento", "venda", "outro"],
                    "description": "Tipo de interesse do cliente",
                },
                "zona_preferida": {"type": "string", "description": "Zona/localização preferida (parcial)"},
                "criado_depois": {"type": "string", "description": "Data ISO 8601 — só clientes criados depois desta data"},
            },
        },
    },
    {
        "name": "consultar_imoveis",
        "description": "Consulta imóveis na base de dados com filtros opcionais.",
        "input_schema": {
            "type": "object",
            "properties": {
                "natureza": {"type": "string", "description": "Tipo de imóvel (ex: moradia, apartamento)"},
                "concelho": {"type": "string", "description": "Concelho/zona (parcial)"},
                "preco_max": {"type": "number", "description": "Preço máximo em euros"},
                "preco_min": {"type": "number", "description": "Preço mínimo em euros"},
                "disponibilidade": {
                    "type": "string",
                    "enum": ["Disponível", "Em Prospecção", "Por validar", "Retirado"],
                },
                "fonte": {"type": "string", "description": "Origem do imóvel (egorealestate, manual, csv, etc.)"},
            },
        },
    },
    {
        "name": "consultar_leads",
        "description": "Consulta leads (oportunidades de negócio) na base de dados.",
        "input_schema": {
            "type": "object",
            "properties": {
                "estado": {
                    "type": "string",
                    "enum": ["novo", "contactado", "qualificado", "proposta", "fechado", "perdido"],
                },
                "cliente_id": {"type": "string", "description": "UUID do cliente"},
                "criado_depois": {"type": "string", "description": "Data ISO 8601"},
            },
        },
    },
]

_POR_NOME = {t["name"]: t for t in TOOL_DEFINITIONS}


def tools_para(nomes: list[str]) -> list[dict]:
    """Subconjunto de definições para um assistente."""
    return [_POR_NOME[n] for n in nomes if n in _POR_NOME]


async def _run(fn, *args):
    return await asyncio.get_event_loop().run_in_executor(None, fn, *args)


# ══════════════════════════════════════════════════════════════
# Tools cliente-facing
# ══════════════════════════════════════════════════════════════


def _pesquisar_imoveis(filtros: dict) -> str:
    """Pesquisa com fallback de tipologia (spec §3.2 SI-B, fase 5, nível 1).

    O modelo traduz "T2" para `natureza="Apartamento"` e assim perde as
    moradias T2 — observado ao vivo: com T2/Figueira/150k dizia "não temos",
    havendo uma moradia T2 a 65k. Por isso, zero resultados com `natureza`
    dispara uma segunda pesquisa sem esse filtro, marcada como alternativa.
    O nível 1 do fallback fica determinístico em vez de depender do prompt.
    """
    resultado = _consulta_imoveis(filtros)
    if resultado or not filtros.get("natureza"):
        return resultado or "Não foram encontrados imóveis com esses critérios."

    alternativas = _consulta_imoveis({**filtros, "natureza": None})
    if not alternativas:
        return "Não foram encontrados imóveis com esses critérios."
    return (
        f"Sem resultados para '{filtros['natureza']}' com esses critérios. "
        "Alternativas na mesma zona e orçamento, noutra tipologia — "
        "apresenta-as como sugestão:\n" + alternativas
    )


def _consulta_imoveis(filtros: dict) -> str:
    q = get_supabase().table("imoveis").select(
        "imovel_ref,natureza,quartos,area_util,venda_preco,arrendamento_preco,"
        "concelho,freguesia,zona,descricao"
    )

    # `publicado` é GENERATED (migration 0008): disponibilidade + ref + preço > 0
    # + ainda devolvido pela API do eGO. Mais forte que filtrar `disponibilidade`,
    # e indexado. Sem isto a pesquisa devolvia imóveis vendidos e retirados.
    q = q.eq("publicado", True)

    natureza = filtros.get("natureza")
    quartos = filtros.get("quartos")
    zona = filtros.get("zona")
    tipo_negocio = filtros.get("tipo_negocio")
    preco_max = filtros.get("preco_max")
    preco_min = filtros.get("preco_min")

    if natureza:
        q = q.ilike("natureza", f"%{natureza}%")
    if quartos is not None:
        q = q.eq("quartos", quartos)
    if zona:
        # A zona que o cliente diz pode ser concelho, freguesia ou lugar.
        q = q.or_(f"concelho.ilike.%{zona}%,freguesia.ilike.%{zona}%,zona.ilike.%{zona}%")

    campo_preco = "arrendamento_preco" if tipo_negocio == "arrendamento" else "venda_preco"
    if tipo_negocio:
        q = q.gt(campo_preco, 0)
    if preco_max is not None:
        q = q.lte(campo_preco, preco_max)
    if preco_min is not None:
        q = q.gte(campo_preco, preco_min)

    resp = q.order(campo_preco).limit(3).execute()
    if not resp.data:
        return ""

    linhas = []
    for r in resp.data:
        if tipo_negocio == "arrendamento" and r.get("arrendamento_preco"):
            preco = f"{r['arrendamento_preco']}€/mês"
        elif r.get("venda_preco"):
            preco = f"{r['venda_preco']}€"
        else:
            preco = ""

        partes = [
            f"Ref {r.get('imovel_ref', '?')}",
            r.get("natureza", ""),
            f"T{r['quartos']}" if r.get("quartos") is not None else "",
            f"{r['area_util']}m²" if r.get("area_util") else "",
            preco,
            r.get("freguesia") or r.get("concelho", ""),
        ]
        linhas.append(" | ".join(p for p in partes if p))
        if r.get("descricao"):
            linhas.append(f"  {r['descricao'][:120]}")

    return "\n".join(linhas)


def _ficha_imovel(inputs: dict) -> str:
    ref = (inputs.get("imovel_ref") or "").strip()
    morada = (inputs.get("morada") or "").strip()
    if not ref and not morada:
        return "É preciso a referência ou a morada do imóvel."

    q = get_supabase().table("imoveis").select(_CAMPOS_FICHA).eq("publicado", True)
    if ref:
        q = q.ilike("imovel_ref", ref.replace(" ", ""))
    else:
        q = q.ilike("morada", f"%{morada}%")

    resp = q.limit(1).execute()
    if not resp.data:
        alvo = ref or morada
        return f"Não encontrei nenhum imóvel disponível para '{alvo}'."

    r = resp.data[0]
    caracteristicas = [
        nome
        for nome, campo in (
            ("piscina", "piscina"), ("garagem", "garagem"), ("jardim", "jardim"),
            ("terraço", "terraco"), ("varanda", "varanda"), ("vista de mar", "vista_mar"),
            ("vista de praia", "vista_praia"), ("ar condicionado", "ar_condicionado"),
            ("elevador", "elevador"),
        )
        if r.get(campo)
    ]

    ficha = {
        "referencia": r.get("imovel_ref"),
        "natureza": r.get("natureza"),
        "titulo": r.get("titulo"),
        "tipologia": f"T{r['quartos']}" if r.get("quartos") is not None else None,
        "casas_banho": r.get("casas_banho"),
        "area_util_m2": r.get("area_util"),
        "venda_preco": r.get("venda_preco"),
        "arrendamento_preco": r.get("arrendamento_preco"),
        "morada": r.get("morada"),
        "zona": r.get("freguesia") or r.get("zona") or r.get("concelho"),
        "concelho": r.get("concelho"),
        "conservacao": r.get("conservacao"),
        "certificacao_energetica": r.get("certificacao_energetica"),
        "caracteristicas": caracteristicas,
        "descricao": (r.get("descricao") or "")[:600] or None,
        "foto_principal": r.get("foto_principal"),
    }
    return json.dumps({k: v for k, v in ficha.items() if v not in (None, [], "")},
                      ensure_ascii=False, default=str)


async def _guardar_dados_cliente(inputs: dict, contexto: dict) -> str:
    cliente = await find_or_create_cliente(
        nome=inputs.get("nome"),
        telefone=inputs.get("telefone") or contexto.get("telefone"),
        email=inputs.get("email"),
        tipo_interesse=inputs.get("tipo_interesse"),
        orcamento=inputs.get("orcamento"),
        zona_preferida=inputs.get("zona_preferida"),
        notas=inputs.get("resumo"),
        origem=contexto.get("origem", "whatsapp"),
    )
    if not cliente:
        # Banco de ensaio do painel: sem telefone nem email não se cria cliente.
        return "Dados registados nesta conversa."

    if inputs.get("tipo_interesse"):
        await _run(_criar_lead_se_preciso, cliente["id"], inputs.get("resumo"))
    return "Dados guardados com sucesso."


def _criar_lead_se_preciso(cliente_id: str, resumo: str | None) -> None:
    """Uma lead aberta por cliente. Escreve em `leads` desde 2026-08-18 —
    `agente_leads` deixou de ser usada (ver `api/leads.py`)."""
    supabase = get_supabase()
    aberto = (
        supabase.table("leads")
        .select("id")
        .eq("cliente_id", cliente_id)
        .not_.in_("estado", list(ESTADOS_FECHADOS))
        .limit(1)
        .execute()
    )
    if not aberto.data:
        supabase.table("leads").insert(
            {"cliente_id": cliente_id, "estado": "nova", "origem": "assistente", "notas": resumo}
        ).execute()


def _preco_do_imovel(ref: str) -> dict | None:
    resp = (
        get_supabase()
        .table("imoveis")
        .select("imovel_ref,venda_preco,arrendamento_preco,morada")
        .ilike("imovel_ref", ref.replace(" ", ""))
        .limit(1)
        .execute()
    )
    return resp.data[0] if resp.data else None


async def _agendar_visita(inputs: dict, contexto: dict) -> str:
    ref = (inputs.get("imovel_ref") or "").strip()
    imovel = await _run(_preco_do_imovel, ref)
    if not imovel:
        return f"Não encontrei o imóvel '{ref}'. Confirma a referência com o cliente."

    venda_preco = imovel.get("venda_preco")
    orcamento = inputs.get("orcamento")

    # Regra dos 80% (spec §3.2 SV). Aplicada aqui, antes de qualquer escrita —
    # não no prompt. Arrendamento fica isento: 80% de uma renda mensal não
    # significa nada e a spec é omissa nesse caso.
    if venda_preco and venda_preco > 0 and not visita_permitida(orcamento, venda_preco):
        if orcamento:
            return (
                f"NÃO MARCADA. Este imóvel custa {venda_preco:.0f}€, acima do orçamento "
                f"de {orcamento:.0f}€ que o cliente indicou. Explica que preferes procurar "
                "imóveis semelhantes que se enquadrem melhor, e usa pesquisar_imoveis "
                "com os critérios que já conheces."
            )
        return (
            "NÃO MARCADA. Falta saber o orçamento. Pergunta o intervalo de investimento "
            "que o cliente tem em mente, explicando que ajuda a preparar a visita e que "
            "não é compromisso nenhum. Se recusar dizer, usa escalar_para_humano."
        )

    telefone = normalizar_telefone(inputs.get("telefone") or contexto.get("telefone"))
    nome = inputs.get("nome")
    quando = inputs.get("quando") or "data a confirmar"

    await find_or_create_cliente(
        nome=nome,
        telefone=telefone,
        orcamento=orcamento,
        origem=contexto.get("origem", "whatsapp"),
    )

    # ponytail: a visita vive em agente_tarefas — `prazo` é date, por isso a
    # hora fica no título. Sem coluna de tempo não dá para fazer a query do
    # lembrete 24h; criar `agente_visitas` quando os lembretes entrarem.
    descricao = "\n".join(
        p for p in (
            f"Pedido de visita via {contexto.get('canal', 'assistente')}.",
            f"Imóvel: {imovel.get('imovel_ref')} — {imovel.get('morada') or ''}".strip(),
            f"Preço: {venda_preco:.0f}€" if venda_preco else None,
            f"Orçamento declarado: {orcamento:.0f}€" if orcamento else None,
            f"Contacto: {nome or '?'} — {telefone or '?'}",
            f"Quando: {quando}",
        ) if p
    )

    await _run(
        _inserir_tarefa,
        {
            "titulo": f"Visita {imovel.get('imovel_ref')} — {nome or '?'} {telefone or ''} — {quando}".strip(),
            "descricao": descricao,
            "imovel_ref": imovel.get("imovel_ref"),
            "prazo": _data_valida(inputs.get("data_iso")),
            "estado": "pendente",
            # Campos de métrica (migration 0018). O título continua legível
            # para o corretor, mas deixa de ser a fonte de verdade.
            "tipo": "visita",
            "agente": contexto.get("agente"),
            "conversa_id": contexto.get("conversa_id"),
        },
    )
    # A visita era a única escrita cliente-facing que ficava só na tarefa. A spec
    # §2.2 ("Interesse real") manda avisar por email, e é o desfecho que mais o
    # merece: a pessoa está a pedir para ver a casa. `notificar` engole os
    # próprios erros e resolve sozinho a consultora do imóvel — ver notificacoes.py.
    await _run(
        notificar,
        f"Pedido de visita — {imovel.get('imovel_ref')}",
        "\n".join(p for p in (
            f"Pedido de visita pelo {contexto.get('agente') or 'assistente'} em "
            f"{contexto.get('canal', '?')}.",
            "",
            f"Imóvel:    {imovel.get('imovel_ref')} — {imovel.get('morada') or '—'}",
            f"Preço:     {venda_preco:.0f}€" if venda_preco else None,
            f"Contacto:  {nome or '—'} — {telefone or '—'}",
            f"Orçamento: {orcamento:.0f}€" if orcamento else None,
            f"Quando:    {quando}",
            "",
            "Foi dito ao cliente que o consultor confirma o horário e entra em contacto.",
        ) if p is not None),
        imovel.get("imovel_ref"),
    )

    return (
        "Pedido de visita registado. Confirma ao cliente que o consultor valida "
        "o horário e entra em contacto."
    )


async def _encerrar_lead(inputs: dict, contexto: dict) -> str:
    """Desfecho "Engano" (e "Sem interesse") da spec §2.2 — "Sem mais ações".

    Sem cliente, sem tarefa, sem email: a única coisa que acontece é o estado da
    lead, e é isso que faz a pessoa deixar de ser contactada. A escrita vive em
    `guards` com o resto do ciclo de vida da lead.
    """
    await encerrar_lead_do_telefone(
        contexto.get("telefone"),
        (inputs.get("motivo") or "").strip(),
        inputs.get("nota"),
    )
    # Mesmo quando não há lead para fechar (chat do painel, número desconhecido),
    # a instrução ao modelo é a mesma: a pessoa disse que não quer, e insistir é
    # o erro — não o estado que ficou ou deixou de ficar na base.
    return "Registado. Despede-te com uma frase curta e não faças mais perguntas."


async def _escalar_para_humano(inputs: dict, contexto: dict) -> str:
    telefone = normalizar_telefone(inputs.get("telefone") or contexto.get("telefone"))
    nome = inputs.get("nome")
    motivo = inputs.get("motivo") or "assunto para consultor"

    await find_or_create_cliente(
        nome=nome, telefone=telefone, notas=inputs.get("resumo"),
        origem=contexto.get("origem", "whatsapp"),
    )

    prefixo = "URGENTE — " if inputs.get("urgente") else ""
    await _run(
        _inserir_tarefa,
        {
            "titulo": f"{prefixo}ESCALAR — {motivo} — {nome or telefone or 'contacto desconhecido'}",
            "descricao": "\n".join(
                p for p in (
                    f"Canal: {contexto.get('canal', '?')}",
                    f"Contacto: {nome or '?'} — {telefone or '?'}",
                    f"Motivo: {motivo}",
                    inputs.get("resumo"),
                ) if p
            ),
            "imovel_ref": inputs.get("imovel_ref"),
            "prazo": date.today().isoformat(),
            "estado": "pendente",
            "tipo": "escalar",
            "agente": contexto.get("agente"),
            "conversa_id": contexto.get("conversa_id"),
            # Agregável: antes o motivo só existia dentro do título.
            "motivo": motivo,
        },
    )

    # O assistente acabou de prometer ao cliente que alguém entra em contacto.
    # Se isso ficar só numa linha do painel, a promessa depende de o corretor
    # abrir o painel. `notificar` engole os próprios erros — ver notificacoes.py.
    await _run(
        notificar,
        f"{prefixo}Escalado pelo assistente — {motivo}",
        "\n".join(p for p in (
            f"O {contexto.get('agente') or 'assistente'} escalou uma conversa em {contexto.get('canal', '?')}.",
            "",
            f"Contacto: {nome or '—'} — {telefone or '—'}",
            f"Motivo:   {motivo}",
            f"Imóvel:   {inputs.get('imovel_ref') or '—'}",
            "",
            inputs.get("resumo"),
            "",
            "Foi dito ao cliente que entram em contacto (próximo dia útil se fora de horas).",
        ) if p is not None),
        inputs.get("imovel_ref"),
    )

    return (
        "Registado para o consultor. Confirma ao cliente que entram em contacto, "
        "e no próximo dia útil se for fora de horas."
    )


def _data_valida(valor: str | None) -> str | None:
    """Só aceita AAAA-MM-DD; qualquer outra coisa fica de fora (a hora vai no título)."""
    if not valor:
        return None
    try:
        return date.fromisoformat(valor.strip()).isoformat()
    except ValueError:
        return None


def _inserir_tarefa(dados: dict) -> None:
    get_supabase().table("agente_tarefas").insert(
        {k: v for k, v in dados.items() if v is not None}
    ).execute()


# ══════════════════════════════════════════════════════════════
# Tools internas (broker)
# ══════════════════════════════════════════════════════════════


def _consultar_clientes(filtros: dict) -> list[dict]:
    q = get_supabase().table("agente_clientes").select("*")
    if filtros.get("nome"):
        q = q.ilike("nome", f"%{filtros['nome']}%")
    if filtros.get("telefone"):
        q = q.eq("telefone", filtros["telefone"])
    if filtros.get("tipo_interesse"):
        q = q.eq("tipo_interesse", filtros["tipo_interesse"])
    if filtros.get("zona_preferida"):
        q = q.ilike("zona_preferida", f"%{filtros['zona_preferida']}%")
    if filtros.get("criado_depois"):
        q = q.gte("criado_em", filtros["criado_depois"])
    return q.order("criado_em", desc=True).limit(20).execute().data or []


def _consultar_imoveis(filtros: dict) -> list[dict]:
    q = get_supabase().table("imoveis").select("*")
    if filtros.get("natureza"):
        q = q.ilike("natureza", f"%{filtros['natureza']}%")
    if filtros.get("concelho"):
        q = q.ilike("concelho", f"%{filtros['concelho']}%")
    # preco_max/min aplicam-se ao preço de venda — para arrendamento o
    # assistente comercial usa `pesquisar_imoveis`, que distingue os dois.
    if filtros.get("preco_max") is not None:
        q = q.lte("venda_preco", filtros["preco_max"])
    if filtros.get("preco_min") is not None:
        q = q.gte("venda_preco", filtros["preco_min"])
    if filtros.get("disponibilidade"):
        q = q.eq("disponibilidade", filtros["disponibilidade"])
    if filtros.get("fonte"):
        q = q.eq("fonte", filtros["fonte"])
    return q.order("data_alteracao", desc=True).limit(20).execute().data or []


def _consultar_leads(filtros: dict) -> list[dict]:
    q = get_supabase().table("agente_leads").select("*, agente_clientes(nome, telefone)")
    if filtros.get("estado"):
        q = q.eq("estado", filtros["estado"])
    if filtros.get("cliente_id"):
        q = q.eq("cliente_id", filtros["cliente_id"])
    if filtros.get("criado_depois"):
        q = q.gte("criado_em", filtros["criado_depois"])
    return q.order("criado_em", desc=True).limit(20).execute().data or []


_CONSULTAS = {
    "consultar_clientes": _consultar_clientes,
    "consultar_imoveis": _consultar_imoveis,
    "consultar_leads": _consultar_leads,
}


async def execute_tool(name: str, inputs: dict, contexto: dict | None = None) -> str:
    """Executa uma tool. `contexto` traz canal, telefone e origem da conversa."""
    contexto = contexto or {}
    try:
        if name == "pesquisar_imoveis":
            return await _run(_pesquisar_imoveis, inputs)
        if name == "ficha_imovel":
            return await _run(_ficha_imovel, inputs)
        if name == "guardar_dados_cliente":
            return await _guardar_dados_cliente(inputs, contexto)
        if name == "agendar_visita":
            return await _agendar_visita(inputs, contexto)
        if name == "escalar_para_humano":
            return await _escalar_para_humano(inputs, contexto)
        if name == "encerrar_lead":
            return await _encerrar_lead(inputs, contexto)

        if name in _CONSULTAS:
            resultado = await _run(_CONSULTAS[name], inputs)
            if not resultado:
                return "Nenhum resultado encontrado."
            # JSON, não `str(list)` — o repr do Python usa plicas e o modelo
            # gasta tokens a decifrá-lo.
            return json.dumps(resultado, ensure_ascii=False, default=str)

        return f"Tool desconhecida: {name}"
    except Exception:
        logger.exception("Erro a executar tool %s", name)
        return "Erro ao consultar a base de dados."
