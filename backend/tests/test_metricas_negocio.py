"""Filtro de PII nos argumentos das tools. Função pura, sem DB nem rede.

O que este teste protege: `tools_detalhe` existe para saber que ZONAS e
TIPOLOGIAS os clientes procuram. Se alguma vez passar a copiar também os
argumentos de `guardar_dados_cliente`, nomes, telefones e emails ficam
espalhados por uma segunda tabela sem ninguém dar por isso.

    python backend/tests/test_metricas_negocio.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agents.broker.engine import _TOOLS_INPUT_SEGURO, _detalhe_tool  # noqa: E402


def test_pesquisa_guarda_criterios():
    """São estes argumentos que alimentam o bloco de preferências."""
    d = _detalhe_tool({
        "name": "pesquisar_imoveis",
        "input": {"zona": "Figueira da Foz", "quartos": 2, "preco_max": 150000},
    })
    assert d == {
        "nome": "pesquisar_imoveis",
        "input": {"zona": "Figueira da Foz", "quartos": 2, "preco_max": 150000},
    }


def test_ficha_imovel_guarda_referencia():
    d = _detalhe_tool({"name": "ficha_imovel", "input": {"imovel_ref": "FH2550"}})
    assert d["input"]["imovel_ref"] == "FH2550"


def test_guardar_dados_cliente_nao_deixa_passar_pii():
    d = _detalhe_tool({
        "name": "guardar_dados_cliente",
        "input": {"nome": "João Silva", "telefone": "912345678",
                  "email": "joao@exemplo.pt", "orcamento": 200000},
    })
    assert d == {"nome": "guardar_dados_cliente"}, d
    assert "input" not in d


def test_agendar_visita_e_escalar_nao_deixam_passar_pii():
    for tool in ("agendar_visita", "escalar_para_humano"):
        d = _detalhe_tool({
            "name": tool,
            "input": {"nome": "Maria", "telefone": "913000000", "resumo": "quer visitar"},
        })
        assert d == {"nome": tool}, d


def test_tool_desconhecida_e_bloqueada_por_omissao():
    """Allowlist, não blocklist: uma tool nova entra no lado seguro."""
    d = _detalhe_tool({"name": "tool_inventada_amanha", "input": {"segredo": "x"}})
    assert d == {"nome": "tool_inventada_amanha"}


def test_allowlist_nao_cresceu_sem_reparar():
    """Trava de segurança: alargar a allowlist obriga a rever este teste."""
    assert _TOOLS_INPUT_SEGURO == {"pesquisar_imoveis", "ficha_imovel"}, (
        "A allowlist mudou — confirmar que a tool nova não recebe nome, "
        "telefone nem email nos argumentos antes de actualizar este teste."
    )


def test_bloco_sem_input_nao_rebenta():
    assert _detalhe_tool({"name": "pesquisar_imoveis"}) == {
        "nome": "pesquisar_imoveis", "input": {}}
    assert _detalhe_tool({}) == {"nome": ""}


if __name__ == "__main__":
    for nome, fn in list(globals().items()):
        if nome.startswith("test_"):
            fn()
            print(f"  ok  {nome}")
    print("test_metricas_negocio OK")
