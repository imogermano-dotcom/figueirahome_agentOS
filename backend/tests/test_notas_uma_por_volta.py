from app.api import oportunidades_sync as sync
from app.config import settings
from app.integrations import ego_notas


def _n(ref, dia, ego_id):
    return {"ref": ref, "dia": dia, "ego_id": ego_id}


def test_so_a_mais_antiga_de_cada_oportunidade_e_conta_as_adiadas():
    novas = [_n("VEN_1", "2026-11-23", 3), _n("VEN_1", "2026-11-22", 2), _n("VEN_1", "2026-11-22", 1), _n("VEN_2", "2026-11-23", 4)]
    agora, adiadas = ego_notas.uma_por_oportunidade(novas)
    assert sorted(n["ego_id"] for n in agora) == [1, 4] and adiadas == 2


def test_reconciliar_grava_so_uma_por_oportunidade(monkeypatch):
    gravadas = []
    monkeypatch.setattr(settings, "notas_api_ego", "1")
    monkeypatch.setattr(sync.ego_api, "oportunidades_ativas", lambda: [])
    monkeypatch.setattr(ego_notas, "novas", lambda desde="", ativas=None: [_n("VEN_1", "2026-11-23", 2), _n("VEN_1", "2026-11-22", 1)])
    monkeypatch.setattr(ego_notas, "gravar", lambda n, origem="manual": gravadas.extend(n) or {"inseridas": len(n), "erros": {}})
    r = sync.reconciliar_notas()
    assert [n["ego_id"] for n in gravadas] == [1] and r["gravadas"] == 1 and r["adiadas"] == 1 and r["por_gravar"] == 2


def test_gravar_salta_a_nota_de_oportunidade_que_ainda_nao_existe(monkeypatch):
    """26/11: notas de oportunidades criadas hoje no eGO davam 23503 todas as horas; agora contam-se à parte."""
    inseridas, logs = [], []

    class _BD:
        def table(self, nome):
            self.nome = nome
            return self

        def select(self, *_):
            return self

        def in_(self, *_):
            return self

        def insert(self, linha):
            (inseridas if self.nome == "notas" else logs).append(linha)
            return self

        def rpc(self, *_):
            return self

        def execute(self):
            dados = [{"oportunidade_ref": "VEN_1", "url": "u", "cliente_nome": None}] if self.nome == "oportunidades" else []
            return type("R", (), {"data": dados})()

    monkeypatch.setattr(ego_notas, "get_supabase", lambda: _BD())
    monkeypatch.setattr(ego_notas.ego_api, "utilizadores", lambda: {})
    monkeypatch.setattr(ego_notas.ego_api, "tipos_de_nota", lambda: {})
    novas = [{"ego_id": 1, "ref": "VEN_1", "dia": "2026-11-26", "texto": "a"},
             {"ego_id": 2, "ref": "VEN_NOVA", "dia": "2026-11-26", "texto": "b"}]
    r = ego_notas.gravar(novas, "cron")
    assert r["inseridas"] == 1 and r["sem_oportunidade"] == 1 and r["erros"] == {}
    assert [l["nota_ego_id"] for l in inseridas] == [1]


def test_linha_da_nota_leva_autor_e_tipo_conhecidos():
    n = {"ego_id": 1, "ref": "VEN_1", "dia": "2026-11-26", "texto": "a", "user_id": 7, "tipo_id": 58}
    linha = ego_notas.linha_de_nota(n, {7: "Consultora Teste"})
    assert linha["nota_autor"] == "Consultora Teste" and linha["nota_tipo"] == "Tarefa concluída"
    # nota normal (0), utilizador e tipo desconhecidos: ficam sem os campos, não inventam
    vazia = ego_notas.linha_de_nota({**n, "user_id": 99, "tipo_id": 0}, {7: "Consultora Teste"})
    assert "nota_autor" not in vazia and "nota_tipo" not in vazia
    assert "nota_autor" not in ego_notas.linha_de_nota(n), "sem o mapa dos utilizadores"


def test_so_na_api_passa_o_utilizador_e_o_tipo():
    api = [{"id": 5, "objectId": 1, "description": "texto", "createDate": "2026-11-26T10:00:00", "securityUserId": 7, "historicTypeId": 81}]
    (nota,) = ego_notas.so_na_api(api, {1: "VEN_1"}, set())
    assert nota["user_id"] == 7 and nota["tipo_id"] == 81


def test_gravar_conta_autor_e_tipo_desconhecidos_e_sobrevive_ao_mapa_em_baixo(monkeypatch):
    inseridas = []

    class _BD:
        def table(self, nome):
            self.nome = nome
            return self

        def select(self, *_):
            return self

        def in_(self, *_):
            return self

        def insert(self, linha):
            if self.nome == "notas":
                inseridas.append(linha)
            return self

        def rpc(self, *_):
            return self

        def execute(self):
            dados = [{"oportunidade_ref": "VEN_1"}] if self.nome == "oportunidades" else []
            return type("R", (), {"data": dados})()

    monkeypatch.setattr(ego_notas, "get_supabase", lambda: _BD())
    novas = [{"ego_id": 1, "ref": "VEN_1", "dia": "2026-11-26", "texto": "a", "user_id": 7, "tipo_id": 58},
             {"ego_id": 2, "ref": "VEN_1", "dia": "2026-11-26", "texto": "b", "user_id": 99, "tipo_id": 12345},
             {"ego_id": 3, "ref": "VEN_1", "dia": "2026-11-26", "texto": "c", "user_id": 7, "tipo_id": 0}]
    monkeypatch.setattr(ego_notas.ego_api, "utilizadores", lambda: {7: "Consultora Teste"})
    monkeypatch.setattr(ego_notas.ego_api, "tipos_de_nota", lambda: {})
    r = ego_notas.gravar(novas, "cron")
    assert r["inseridas"] == 3 and r["autor_desconhecido"] == 1 and r["tipo_desconhecido"] == 1, r
    assert [l.get("nota_autor") for l in inseridas] == ["Consultora Teste", None, "Consultora Teste"]

    def _rebenta():
        raise RuntimeError("503")

    inseridas.clear()
    monkeypatch.setattr(ego_notas.ego_api, "utilizadores", _rebenta)
    r = ego_notas.gravar(novas[:1], "cron")
    assert r["inseridas"] == 1 and "nota_autor" not in inseridas[0], "sem o mapa grava sem autor"


def test_codigos_de_motivo_medidos_dao_o_nome_e_os_isolados_ficam_vazios():
    base = {"ego_id": 1, "ref": "VEN_1", "dia": "2026-11-26", "texto": "a", "user_id": 7}
    for codigo, nome in ((82, "Email enviado"), (34898448, "engano"), (34887372, "Outra"), (34899663, "impossível contactar")):
        assert ego_notas.linha_de_nota({**base, "tipo_id": codigo})["nota_tipo"] == nome
    # um só par no relatório não chega para fixar o nome (Desistência, Agência…): continua a contar como desconhecido
    assert "nota_tipo" not in ego_notas.linha_de_nota({**base, "tipo_id": 34887296})


def test_tipo_da_nota_vem_do_endpoint_e_a_reserva_cobre_a_falha(monkeypatch):
    """26/11: `ListNoteType` dá o nome de qualquer código (o 34 é «Com Tel Out»); o mapa fixo só serve se o endpoint falhar."""
    base = {"ego_id": 1, "ref": "VEN_1", "dia": "2026-11-26", "texto": "a", "user_id": 7}
    assert ego_notas.linha_de_nota({**base, "tipo_id": 34}, {}, {34: "Com Tel Out"})["nota_tipo"] == "Com Tel Out"
    assert ego_notas.linha_de_nota({**base, "tipo_id": 82}, {}, {})["nota_tipo"] == "Email enviado", "reserva"
    assert ego_notas.linha_de_nota({**base, "tipo_id": 82}, {}, {82: "Outro nome"})["nota_tipo"] == "Outro nome", "o endpoint manda"
    assert "nota_tipo" not in ego_notas.linha_de_nota({**base, "tipo_id": 777}, {}, {34: "Com Tel Out"})


def test_tipos_de_nota_le_o_nome_em_pt_pt(monkeypatch):
    from app.integrations import ego_api

    monkeypatch.setattr(ego_api, "_pedido", lambda *a, **k: {"items": [{"id": 34, "name": "Com Tel Out"}, {"id": 5, "name": {"PT-PT": "Sistema"}}, {"id": 0, "name": "x"}]})
    assert ego_api.tipos_de_nota() == {34: "Com Tel Out", 5: "Sistema"}
