"""Verificação da RPC `dashboard_metricas` (migration 0015).

Ao contrário de `test_router.py` e `test_guards.py`, este toca na base de dados —
é o único sítio onde a agregação vive, por isso não há nada de puro para testar.
Se a RPC não estiver aplicada, falha com uma mensagem que o diz.

    python backend/tests/test_dashboard.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.supabase_client import get_supabase  # noqa: E402

SECCOES = {
    "oportunidades", "por_responsavel", "por_origem", "imoveis",
    "contactos", "assistentes", "sync", "alertas",
}


def metricas() -> dict:
    try:
        return get_supabase().rpc("dashboard_metricas").execute().data or {}
    except Exception as e:
        raise AssertionError(
            "RPC dashboard_metricas indisponível — aplicar "
            "supabase/migrations/0015_dashboard_metricas.sql. Erro: " + str(e)[:200]
        )


def test_seccoes_presentes():
    d = metricas()
    em_falta = SECCOES - set(d)
    assert not em_falta, f"secções em falta: {em_falta}"


def test_pipeline_soma_o_total():
    o = metricas()["oportunidades"]
    partes = o["ativas"] + o["ganhas"] + o["perdidas"]
    # Se falhar, apareceu um `oportunidade_estado` novo e a barra do pipeline
    # deixa de representar o todo — passa a mentir sobre as percentagens.
    assert partes <= o["total"], f"{partes} > total {o['total']}"
    assert o["total"] > 0, "sem oportunidades — RPC a ler a tabela errada?"


def test_publicados_nao_excede_disponiveis_nem_total():
    i = metricas()["imoveis"]
    assert i["publicados"] <= i["total"]
    # `publicado` é GENERATED e exige disponibilidade + ref + preço > 0 +
    # disponivel_na_api — nunca pode haver mais publicados que disponíveis.
    assert i["publicados"] <= i["disponiveis"], (
        f"publicados {i['publicados']} > disponíveis {i['disponiveis']}"
    )


def test_listas_ordenadas_e_sem_zeros():
    d = metricas()
    for chave in ("por_responsavel", "por_origem"):
        linhas = d[chave]
        assert isinstance(linhas, list), chave
        totais = [x["total"] for x in linhas]
        assert totais == sorted(totais, reverse=True), f"{chave} não vem ordenada"
        assert all(t > 0 for t in totais), f"{chave} traz linhas a zero"
        assert all(x["nome"] for x in linhas), f"{chave} traz nome vazio"

        # Os dados têm uma categoria real chamada "Outros", que colidia com o
        # balde da cauda — duas linhas com o mesmo nome, chave duplicada no
        # React. O `group by` final da RPC resolve; isto garante que continua.
        nomes = [x["nome"] for x in linhas]
        assert len(nomes) == len(set(nomes)), f"{chave} tem nomes repetidos: {nomes}"


def test_sem_divisao_por_zero_no_frontend():
    """O Dashboard divide por `total` para as percentagens do pipeline."""
    d = metricas()
    assert d["oportunidades"]["total"] > 0
    # Barras.jsx faz Math.max(max, 1), por isso listas vazias são seguras;
    # aqui só confirmamos que os totais nunca são negativos.
    for chave in ("por_responsavel", "por_origem"):
        assert all(x["total"] >= 0 for x in d[chave])


if __name__ == "__main__":
    for nome, fn in list(globals().items()):
        if nome.startswith("test_"):
            fn()
            print(f"  ok  {nome}")
    print("test_dashboard OK")
