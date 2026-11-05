"""Lead no eGO quando a pessoa responde à Matilde com interesse real (`docs/fases/lead-interesse-real-ego-plano.md`, pedido #17).

O assistente só MARCA o contacto (`guards.marcar_interesse_real`); o cron `leads_para_ego.processar` cria a lead.
Telefones de teste: `912345678`. Sem rede. Corre com `pytest backend/tests/`.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import leads_para_ego as lp  # noqa: E402
from app.agents.broker import guards  # noqa: E402
from app.config import settings  # noqa: E402
from tests.test_leads_para_ego import AGORA, ISO, _BD, _linha, _usa  # noqa: E402


# ── o sinal ───────────────────────────────────────────────────────────────

@pytest.mark.parametrize("motivo,compra", [
    ("negociação de preço", True), ("proposta de compra", True), ("pedido de visita", True), ("oferta pelo imóvel", True),
    # 01/11: qualquer escalada de comprador conta; só ficam de fora os motivos que não são compra
    ("pedido de informação sobre imóvel", True), ("procura de moradia", True), ("pesquisa de imóvel", True),
    ("Pedido de chamada telefónica", True), ("Elegibilidade para Garantia Pública e crédito habitação", True),
    ("entrevista de recrutamento", False), ("angariação", False), ("reclamação", False), ("assunto legal", False),
    ("proposta de angariação", False), ("", False), (None, False),
])
def test_motivo_de_compra(motivo, compra):
    assert guards.motivo_de_compra(motivo) is compra


class _Contactos:
    """Duplo de `contactos` para `marcar_interesse_real`: devolve `linhas` e regista os updates."""

    def __init__(self, linhas, rebenta=False):
        self.linhas, self.updates, self.rebenta, self._upd, self.tocou = linhas, [], rebenta, None, False

    def table(self, nome):
        assert nome == "contactos"
        self.tocou = True
        self._upd = None
        return self

    def __getattr__(self, nome):
        if nome == "not_":
            return self
        return lambda *a, **k: self

    def update(self, valores):
        self._upd = valores
        return self

    def eq(self, _, valor):
        if self._upd is not None:
            self.updates.append((valor, self._upd))
        return self

    def execute(self):
        if self.rebenta:
            raise RuntimeError("BD em baixo")
        return type("R", (), {"data": self.linhas})()


def _marcar(monkeypatch, bd, ligado=True):
    monkeypatch.setattr(settings, "lead_interesse_ego", "1" if ligado else "")
    monkeypatch.setattr(guards, "get_supabase", lambda: bd)


def test_desligado_nao_toca_na_bd(monkeypatch):
    bd = _Contactos([{"id": "c1"}])
    _marcar(monkeypatch, bd, ligado=False)
    assert guards.marcar_interesse_real("912345678", "visita", "x") is False and not bd.tocou


def test_primeiro_sinal_grava_motivo_e_resumo(monkeypatch):
    bd = _Contactos([{"id": "c1", "interesse_real_em": None, "interesse_real_resumo": None}])
    _marcar(monkeypatch, bd)
    assert guards.marcar_interesse_real("351912345678", "negociação de preço", "Quer negociar o preço.") is True
    (id_, valores), = bd.updates
    assert id_ == "c1" and valores["interesse_real_motivo"] == "negociação de preço"
    assert valores["interesse_real_resumo"] == "Quer negociar o preço." and valores["interesse_real_em"]


def test_segundo_sinal_acrescenta_ao_resumo_sem_mudar_o_primeiro(monkeypatch):
    bd = _Contactos([{"id": "c1", "interesse_real_em": ISO(1), "interesse_real_resumo": "Pediu visita."}])
    _marcar(monkeypatch, bd)
    assert guards.marcar_interesse_real("912345678", "negociação", "Quer negociar.") is True
    (_, valores), = bd.updates
    assert valores == {"interesse_real_resumo": "Pediu visita.\nQuer negociar."}


def test_sinal_repetido_nao_duplica_o_resumo(monkeypatch):
    bd = _Contactos([{"id": "c1", "interesse_real_em": ISO(1), "interesse_real_resumo": "Pediu visita."}])
    _marcar(monkeypatch, bd)
    assert guards.marcar_interesse_real("912345678", "visita", "Pediu visita.") is True and bd.updates == []


def test_sem_contacto_meta_de_comprador_nao_marca(monkeypatch):
    bd = _Contactos([])  # vendedor, recrutamento, sem meta_lead_id ou já com lead: a consulta não devolve nada
    _marcar(monkeypatch, bd)
    assert guards.marcar_interesse_real("912345678", "visita", "x") is False and bd.updates == []


def test_sem_telefone_nao_marca(monkeypatch):
    bd = _Contactos([{"id": "c1"}])
    _marcar(monkeypatch, bd)
    assert guards.marcar_interesse_real(None, "visita", "x") is False and not bd.tocou


def test_erro_da_bd_nao_levanta(monkeypatch):
    _marcar(monkeypatch, _Contactos([{"id": "c1"}], rebenta=True))
    assert guards.marcar_interesse_real("912345678", "visita", "x") is False


def test_resumo_enorme_e_cortado(monkeypatch):
    bd = _Contactos([{"id": "c1", "interesse_real_em": None, "interesse_real_resumo": None}])
    _marcar(monkeypatch, bd)
    guards.marcar_interesse_real("912345678", "visita", "a" * 5000)
    assert len(bd.updates[0][1]["interesse_real_resumo"]) == 1500


# ── as tools que marcam ───────────────────────────────────────────────────

def _tools(monkeypatch):
    import asyncio  # noqa: F401
    import app.agents.broker.tools as tools

    marcas = []
    monkeypatch.setattr(tools, "marcar_interesse_real", lambda tel, motivo, resumo: marcas.append((tel, motivo, resumo)))
    monkeypatch.setattr(tools, "_preco_do_imovel", lambda ref: {"imovel_ref": "FH0001", "venda_preco": 300000, "morada": "Rua X"})
    monkeypatch.setattr(tools, "_inserir_tarefa", lambda d: None)
    monkeypatch.setattr(tools, "notificar", lambda *a, **k: None)
    monkeypatch.setattr(tools, "_criar_lead_se_preciso", lambda *a, **k: None)
    monkeypatch.setattr(tools, "_tarefa_ja_registada", lambda *a: False)

    async def _sem_cliente(**kw):
        return None

    monkeypatch.setattr(tools, "find_or_create_cliente", _sem_cliente)
    return tools, marcas


CTX = {"canal": "whatsapp", "telefone": "912345678", "agente": "a1_vendedor", "conversa_id": "c-1"}


def test_pedir_visita_marca_interesse_real(monkeypatch):
    import asyncio
    tools, marcas = _tools(monkeypatch)
    asyncio.run(tools._pedir_visita({"imovel_ref": "FH0001", "nome": "Ana", "telefone": "912345678",
                                     "quando": "sábado", "orcamento": 290000}, CTX))
    (tel, motivo, resumo), = marcas
    assert tel == "912345678" and motivo == "visita" and "FH0001" in resumo and "sábado" in resumo


def test_pedir_visita_recusada_pelos_80_por_cento_nao_marca(monkeypatch):
    import asyncio
    tools, marcas = _tools(monkeypatch)
    r = asyncio.run(tools._pedir_visita({"imovel_ref": "FH0001", "nome": "Ana", "telefone": "912345678", "orcamento": 100000}, CTX))
    assert r.startswith("NÃO REGISTADO") and marcas == []


@pytest.mark.parametrize("motivo,marca", [("negociação de preço", True), ("proposta de compra", True),
                                           ("entrevista de recrutamento", False), ("angariação", False), ("reclamação", False)])
def test_escalar_so_marca_motivos_de_compra(monkeypatch, motivo, marca):
    import asyncio
    tools, marcas = _tools(monkeypatch)
    asyncio.run(tools._escalar_para_humano({"motivo": motivo, "resumo": "Quer negociar.", "nome": "Ana",
                                            "telefone": "912345678", "imovel_ref": "FH0001"}, CTX))
    assert bool(marcas) is marca
    if marca:
        assert marcas[0][1] == motivo and marcas[0][2] == "Quer negociar."


def test_escalada_repetida_nao_volta_a_marcar(monkeypatch):
    import asyncio
    tools, marcas = _tools(monkeypatch)
    monkeypatch.setattr(tools, "_tarefa_ja_registada", lambda *a: True)
    monkeypatch.setattr(tools, "_atualizar_escalada", lambda *a: False)
    asyncio.run(tools._escalar_para_humano({"motivo": "negociação de preço", "resumo": "x"}, CTX))
    assert marcas == []


def test_qualificada_marca_com_o_que_o_cliente_disse(monkeypatch):
    marcas = []
    monkeypatch.setattr(guards, "notificar", lambda *a, **k: pytest.fail("não devia mandar email"))
    monkeypatch.setattr(guards, "marcar_interesse_real", lambda tel, motivo, resumo: marcas.append((tel, motivo, resumo)))

    class _BDLead:
        def table(self, _): return self
        def __getattr__(self, n): return (lambda *a, **k: self)
        def execute(self): return type("R", (), {"data": [{"id": "l1", "estado": "contactada", "cliente_id": None,
                                                           "imovel_ref": None, "tipo": "arrendamento", "origem": "whatsapp"}]})()

    guards._promover_lead(_BDLead(), {"id": "cl1", "nome": "Ana", "telefone": "912345678", "email": None,
                                      "tipo_interesse": "arrendamento", "orcamento": 600, "zona_preferida": "Paranhos"})
    assert marcas == [("912345678", "qualificada", "procura arrendamento, orçamento 600, zona Paranhos")]


# ── o texto da lead ───────────────────────────────────────────────────────

def test_observacao_diz_que_respondeu_e_leva_o_resumo():
    o = lp.observacao_da_lead(_linha(interesse_real_em=ISO(1), interesse_real_motivo="visita",
                                     interesse_real_resumo="Pediu\nvisita ao FH0001. Procura arrendamento."), com_imovel=True)
    assert "interesse real (visita)" in o and "Resumo: Pediu visita ao FH0001. Procura arrendamento." in o
    assert "Contactar por telefone ou WhatsApp." in o and "sem resposta" not in o


def test_observacao_corta_o_resumo_a_600():
    o = lp.observacao_da_lead(_linha(interesse_real_em=ISO(1), interesse_real_resumo="palavra " * 200), com_imovel=True)
    assert len(o.split("Resumo: ")[1].split(" Contactar")[0]) <= 600


def test_observacao_sem_interesse_continua_igual():
    assert "sem resposta ao WhatsApp da Matilde" in lp.observacao_da_lead(_linha(), com_imovel=True)


# ── o cron ────────────────────────────────────────────────────────────────

def _interessada(**kw):
    """Já respondeu à Matilde (o cron das 2 h nunca a veria) e foi marcada."""
    return _linha(respondeu_em=ISO(5), interesse_real_em=ISO(1), interesse_real_motivo="visita",
                  interesse_real_resumo="Pediu visita.", **kw)


def _ligado(monkeypatch, ligado=True):
    monkeypatch.setattr(settings, "lead_interesse_ego", "1" if ligado else "")


def test_cron_cria_a_lead_de_quem_respondeu_com_interesse(monkeypatch):
    _ligado(monkeypatch)
    bd = _BD([_interessada()])
    corpos = []
    _usa(monkeypatch, bd, lambda nome, email, tel, obs, ego_id: corpos.append(obs) or "555")
    r = lp.processar(AGORA)
    assert (r["criadas"], r["erros"]) == (1, 0)
    assert bd.updates == [("c1", {"ego_lead_em": AGORA.isoformat(), "ego_lead_id": 555})]
    assert "interesse real (visita)" in corpos[0] and "Pediu visita." in corpos[0]


def test_cron_sem_o_segredo_ignora_quem_respondeu(monkeypatch):
    _ligado(monkeypatch, ligado=False)
    bd = _BD([_interessada()])
    _usa(monkeypatch, bd, lambda *a: pytest.fail("não devia criar"))
    r = lp.processar(AGORA)
    assert r["criadas"] == 0 and bd.updates == []


def test_cron_nao_duplica_a_lead_que_ja_esta_na_caixa(monkeypatch):
    _ligado(monkeypatch)
    bd = _BD([_interessada()])
    _usa(monkeypatch, bd, lambda *a: pytest.fail("não devia criar"), leads=[{"phone": "+351912345678"}])
    r = lp.processar(AGORA)
    assert r["ja_existiam"] == 1 and bd.updates == [("c1", {"ego_lead_em": AGORA.isoformat()})]


def test_cron_pessoa_com_oportunidade_ativa_nao_cria(monkeypatch):
    _ligado(monkeypatch)
    bd = _BD([_interessada()], oportunidade=True)
    _usa(monkeypatch, bd, lambda *a: pytest.fail("não devia criar"))
    assert lp.processar(AGORA)["ja_existiam"] == 1


def test_cron_quem_recusou_o_whatsapp_cria_na_mesma_para_o_telefone(monkeypatch):
    """`nao_contactar_em` é só do WhatsApp: a lead continua válida para contacto por telefone."""
    _ligado(monkeypatch)
    bd = _BD([_interessada(nao_contactar_em=ISO(1))])
    _usa(monkeypatch, bd, lambda *a: "555")
    assert lp.processar(AGORA)["criadas"] == 1


def test_cron_sem_email_fica_por_criar_e_conta_como_erro(monkeypatch):
    _ligado(monkeypatch)
    bd = _BD([_interessada(email=None)])
    _usa(monkeypatch, bd, lambda *a: pytest.fail("não devia criar"))
    r = lp.processar(AGORA)
    assert r["erros"] == 1 and bd.updates == []


def test_cron_contacto_que_entra_pelas_duas_vias_cria_uma_so_vez(monkeypatch):
    """Sem resposta há 3 h e marcada: aparece nas duas consultas e só se cria uma lead."""
    _ligado(monkeypatch)
    bd = _BD([_linha(interesse_real_em=ISO(1), interesse_real_motivo="visita")])
    criadas = []
    _usa(monkeypatch, bd, lambda *a: criadas.append(1) or "555")
    r = lp.processar(AGORA)
    assert r["criadas"] == 1 and len(criadas) == 1


# ── contacto antigo reaproveitado por uma lead Meta nova (26/10) ──────────

def test_entrou_pela_meta_em_ignora_o_criado_em_do_contacto_antigo():
    """O comprador escalado a 24/10 era uma pessoa do eGO de 14/08: o `criado_em` ficou em 14/08 e excluía-o de tudo."""
    assert lp.entrou_pela_meta_em({"criado_em": "2026-08-14", "meta_created_at": "2026-10-24T14:14:00+00:00"}) == "2026-10-24"
    assert lp.entrou_pela_meta_em({"criado_em": "2026-10-17"}) == "2026-10-17", "sem meta_created_at, cai para o criado_em"
    assert lp.entrou_pela_meta_em({}) == ""


def test_consultas_do_cron_filtram_pela_entrada_da_lead_meta(monkeypatch):
    filtros = []

    class _Q:
        def __getattr__(self, nome):
            if nome == "not_":
                return self
            return lambda *a, **k: self

        def gte(self, campo, valor):
            filtros.append(campo)
            return self

        def execute(self):
            return type("R", (), {"data": []})()

    monkeypatch.setattr(lp, "get_supabase", lambda: type("S", (), {"table": lambda self, n: _Q()})())
    monkeypatch.setattr(settings, "lead_compra_ego_desde", "2026-10-20")
    monkeypatch.setattr(settings, "lead_interesse_ego", "1")
    lp._candidatas(AGORA)
    lp._candidatas_interesse()
    assert filtros == ["meta_created_at", "meta_created_at"]


def test_recusa_de_contacto_antigo_com_lead_meta_recente_cria(monkeypatch):
    from tests.test_leads_para_ego import _recusa
    _, enviados = _recusa(monkeypatch, linha=_linha(meta_lead_id="m1", criado_em="2026-08-14",
                                                    meta_created_at="2026-10-24T14:14:00+00:00"))
    assert lp.recusou_whatsapp("m1")["resultado"] == "criada" and len(enviados) == 1


def test_recusa_com_lead_meta_anterior_a_ativacao_continua_a_nao_criar(monkeypatch):
    from tests.test_leads_para_ego import _recusa
    _, enviados = _recusa(monkeypatch, linha=_linha(meta_lead_id="m1", criado_em="2026-10-24",
                                                    meta_created_at="2026-10-01T10:00:00+00:00"))
    assert lp.recusou_whatsapp("m1")["resultado"] == "anterior_a_ativacao" and enviados == []


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))


@pytest.mark.parametrize("texto,pede", [
    # mensagens reais de compradores (20/10 a 01/11), anonimizadas
    ("Que informação pode dar-me", True), ("Sim quero saber tudo sobre o imóvel", True), ("Tenho interesse no imóvel FH2572", True),
    ("Podem ligar-me?", True), ("Sim se aceitam propostas de valor", True), ("Quanto custa o arrendamento", True),
    ("Gostava de saber mais informações e se é possível visitar", True), ("Pode fornecer localização e ano do apartamento", True),
    ("Onde fica o imóvel?", True), ("Tem fotos?", True), ("Está disponível para alugar?", True),
    ("Sim", False), ("Bom dia", False), ("Obrigado.", False), ("Arrendar", False), ("Preciso de um T2 eu e um amigo", False),
    ("Não tenho interesse", False), ("Já não preciso, obrigado", False), ("não me contactem mais", False), ("", False), (None, False),
    ("Já não tou interessado obrigado", False), ("Sem interesse, obrigado", False), ("Não estou interessada", False),
    ("Não sei o preço, pode dizer?", True),  # negação com pedido real continua a contar
])
def test_pedido_de_informacao(texto, pede):
    assert guards.e_pedido_de_informacao(texto) is pede


def test_angariador_do_imovel_para_o_responsavel_da_tarefa(monkeypatch):
    from app.agents.broker import tools

    class _Q:
        def __init__(self, dados): self.dados = dados
        def select(self, *_): return self
        def eq(self, *_): return self
        def limit(self, *_): return self
        def execute(self): return type("R", (), {"data": self.dados})()

    class _SB:
        def __init__(self, dados): self.dados = dados
        def table(self, _): return _Q(self.dados)

    monkeypatch.setattr(tools, "get_supabase", lambda: _SB([{"angariador": "Consultora Teste"}]))
    assert tools._angariador_do_imovel("FH0000") == "Consultora Teste"
    assert tools._angariador_do_imovel(None) is None  # sem ref nem sequer pergunta à base
    monkeypatch.setattr(tools, "get_supabase", lambda: _SB([]))
    assert tools._angariador_do_imovel("FH0000") is None
    monkeypatch.setattr(tools, "get_supabase", lambda: _SB([{"angariador": ""}]))
    assert tools._angariador_do_imovel("FH0000") is None


# ── quem pede arrendamento a partir de um anúncio de venda (03/11): a lead sai, com o aviso ────────────────────────

_ARRENDAR_TEXTOS = ["Boa noite gostaria de saber o valor", "Ok e para arrendamento tem alguma coisa ?", "Figueira da foz ou Buarcos"]


def test_deteta_quem_fala_em_arrendar():
    assert lp.procura_arrendar(_ARRENDAR_TEXTOS)
    assert not lp.procura_arrendar(["Quanto custa?", "Quero visitar a casa"])


_CONVERSA = [
    {"role": "assistant", "content": "Olá! Sou a Matilde. Posso ajudar com alguma informação?"},
    {"role": "user", "content": "Estou interessada em arrendar um t1"},
    {"role": "assistant", "content": "O FH0001 é para *venda*. Tem preferência por alguma zona? E qual o valor de renda que tem em mente?"},
    {"role": "user", "content": "Procuro no Porto, Matosinhos ou Gaia. A renda o mínimo possível"},
    {"role": "assistant", "content": [{"type": "tool_use"}]},
    {"role": "assistant", "content": "Posso registar o seu interesse."},
    {"role": "user", "content": "Sei que está difícil mas tenho fé"},
    {"role": "assistant", "content": "Fica registado!"},
    {"role": "user", "content": "Obrigada pela sua atenção"},
]


def test_respostas_em_pares_pergunta_resposta():
    r = lp.respostas_da_pessoa(_CONVERSA)
    assert r.startswith("Pediu: Estou interessada em arrendar um t1 | ")
    assert "Tem preferência por alguma zona? E qual o valor de renda que tem em mente? → Procuro no Porto" in r
    assert "Disse: Sei que está difícil mas tenho fé" in r  # sem pergunta antes
    assert "Obrigada pela sua atenção" not in r  # agradecimento fora
    assert "Fica registado" not in r and "tool_use" not in r  # nada do que a Matilde afirma


def test_respostas_cabem_no_limite_e_guardam_o_pedido():
    msgs = [{"role": "assistant", "content": "Olá?"}, {"role": "user", "content": "quero arrendar"}]
    for i in range(30):
        msgs += [{"role": "assistant", "content": f"Pergunta {i}?"}, {"role": "user", "content": f"resposta {i} " + "x" * 80}]
    r = lp.respostas_da_pessoa(msgs)
    assert len(r) <= 900 and r.startswith("Pediu: quero arrendar | … | ") and "resposta 29" in r and "resposta 0 " not in r


def test_respostas_vazias_se_a_pessoa_nunca_escreveu():
    assert lp.respostas_da_pessoa([{"role": "assistant", "content": "Olá! Sou a Matilde."}]) == ""


def test_observacao_diz_que_quer_arrendar_e_leva_as_respostas():
    o = lp.observacao_da_lead(_linha(interesse_real_em=ISO(1), interesse_real_motivo="pedido de informação do imóvel",
                                     interesse_real_resumo="x", procura_arrendar=True,
                                     respostas_da_pessoa=lp.respostas_da_pessoa(_CONVERSA)), com_imovel=True)
    assert lp.AVISO_ARRENDAR in o and "Respostas da pessoa: Pediu: Estou interessada em arrendar" in o
    assert o.index(lp.AVISO_ARRENDAR) < o.index("Contactar por telefone")


def test_observacao_sem_arrendar_nao_leva_aviso():
    o = lp.observacao_da_lead(_linha(interesse_real_em=ISO(1), interesse_real_resumo="Pediu visita."), com_imovel=True)
    assert "ARRENDAR" not in o


def test_cron_cria_a_lead_de_quem_pede_arrendamento_com_o_aviso_e_a_conversa(monkeypatch):
    _ligado(monkeypatch)
    monkeypatch.setattr(lp, "_mensagens_do", lambda tel: list(_CONVERSA))
    bd = _BD([_interessada()])
    corpos = []
    _usa(monkeypatch, bd, lambda nome, email, tel, obs, ego_id: corpos.append(obs) or "555")
    assert lp.processar(AGORA)["criadas"] == 1
    assert lp.AVISO_ARRENDAR in corpos[0] and "Respostas da pessoa: Pediu: Estou interessada em arrendar um t1" in corpos[0]


def test_cron_leva_a_conversa_mesmo_sem_falar_em_arrendar(monkeypatch):
    _ligado(monkeypatch)
    monkeypatch.setattr(lp, "_mensagens_do", lambda tel: [{"role": "user", "content": "Quero visitar a casa"}])
    bd = _BD([_interessada()])
    corpos = []
    _usa(monkeypatch, bd, lambda nome, email, tel, obs, ego_id: corpos.append(obs) or "555")
    lp.processar(AGORA)
    assert "Respostas da pessoa: Pediu: Quero visitar a casa" in corpos[0] and "ARRENDAR" not in corpos[0]


def test_cron_nao_para_se_a_conversa_falhar(monkeypatch):
    _ligado(monkeypatch)
    monkeypatch.setattr(lp, "_mensagens_do", lambda tel: (_ for _ in ()).throw(RuntimeError("bd em baixo")))
    bd = _BD([_interessada()])
    corpos = []
    _usa(monkeypatch, bd, lambda nome, email, tel, obs, ego_id: corpos.append(obs) or "555")
    assert lp.processar(AGORA)["criadas"] == 1 and "ARRENDAR" not in corpos[0]


def test_pergunta_longa_corta_sem_partir_palavras_e_resposta_com_cortesia_fica():
    longa = "Qual a zona " + "muito " * 30 + "que prefere?"
    r = lp.respostas_da_pessoa([{"role": "assistant", "content": "Olá?"}, {"role": "user", "content": "quero comprar"},
                                {"role": "assistant", "content": longa}, {"role": "user", "content": "Sim, prefiro Buarcos. Muito obrigada"},
                                {"role": "assistant", "content": "Registado."}, {"role": "user", "content": "Feliz noite"}])
    assert "…" in r and "→ Sim, prefiro Buarcos. Muito obrigada" in r and "Feliz noite" not in r
    assert not r.split("| …")[1].lstrip().startswith("uito")  # não começa a meio de «muito»
