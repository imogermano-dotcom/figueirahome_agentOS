"""`pesquisar_imoveis` não filtra por estado/jardim/terraço/varanda (dados
esparsos: jardim=true em só 1/54 publicados) — mas tem de MOSTRAR essa
informação, para a Matilde não apresentar um imóvel "Usado, sem jardim" como
se batesse com um pedido de "recente, com espaço exterior"."""

from app.agents.broker import tools


class _FakeQuery:
    def __init__(self, data):
        self.data = data

    def __getattr__(self, _name):
        return lambda *a, **kw: self

    def execute(self):
        return self


class _FakeSupabase:
    def __init__(self, rows):
        self._rows = rows

    def table(self, _name):
        return _FakeQuery(self._rows)


def _pesquisar(monkeypatch, rows):
    monkeypatch.setattr(tools, "get_supabase", lambda: _FakeSupabase(rows))
    return tools._consulta_imoveis({"natureza": "Moradia"})


def test_mostra_estado_e_features_quando_existem(monkeypatch):
    resultado = _pesquisar(monkeypatch, [{
        "imovel_ref": "FH0001", "natureza": "Moradia", "quartos": 3,
        "area_util": 150, "venda_preco": 200000, "freguesia": "Tavarede",
        "estado": "Renovado", "jardim": True, "terraco": False, "varanda": True,
    }])
    assert "Renovado" in resultado
    assert "Tem: jardim, varanda" in resultado


def test_sem_linha_de_features_quando_nao_ha_nenhuma(monkeypatch):
    resultado = _pesquisar(monkeypatch, [{
        "imovel_ref": "FH0002", "natureza": "Moradia", "quartos": 3,
        "area_util": 144, "venda_preco": 110000, "freguesia": "Tavarede",
        "estado": "Usado", "jardim": False, "terraco": False, "varanda": False,
    }])
    assert "Usado" in resultado
    assert "Tem:" not in resultado
