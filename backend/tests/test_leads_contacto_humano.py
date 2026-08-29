"""`contacto_humano` (o botão) → `contacto_humano_em` (o carimbo).

A coluna é da migration `0032` e trava os envios que nós iniciamos: o template
do fluxo 02 e o follow-up do 03 filtram `contacto_humano_em=is.null`, e o 01
tem a mesma guarda no `IF`. Quem a escreve é o painel, e mais ninguém.

O que estes testes seguram é a tradução no `atualizar_lead`, que existe por
causa de um pormenor que se vê mal: `model_dump(exclude_none=True)` corta os
`None` antes de o payload sair. Com um campo `datetime` no modelo, marcar
funcionava e **desmarcar não** — uma consultora marcada por engano ficava
marcada para sempre, e a lead nunca mais recebia mensagem nenhuma. Com um
booleano, `False` sobrevive ao filtro e limpa a coluna.

Corre com `pytest backend/tests/` ou
`python backend/tests/test_leads_contacto_humano.py`.
"""

import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.api import leads as api_leads  # noqa: E402
from app.models.lead import LeadUpdate  # noqa: E402


class _FakeQuery:
    def __init__(self, caixa):
        self._caixa = caixa

    def update(self, dados):
        self._caixa.append(dados)
        return self

    def eq(self, *a, **k):
        return self

    def execute(self):
        return SimpleNamespace(data=[{"id": "0"}])


class _FakeSupabase:
    def __init__(self, caixa):
        self._caixa = caixa

    def table(self, nome):
        return _FakeQuery(self._caixa)


def _payload(monkeypatch, **corpo) -> dict:
    """O que sai mesmo para o PostgREST."""
    caixa = []
    monkeypatch.setattr(api_leads, "get_supabase", lambda: _FakeSupabase(caixa))
    asyncio.run(api_leads.atualizar_lead(uuid4(), LeadUpdate(**corpo)))
    return caixa[0]


def test_marcar_carimba_a_hora_do_servidor(monkeypatch):
    saiu = _payload(monkeypatch, contacto_humano=True, responsavel="Alexandra Santos")
    assert isinstance(saiu["contacto_humano_em"], str) and saiu["contacto_humano_em"]
    assert saiu["responsavel"] == "Alexandra Santos"


def test_desmarcar_limpa_a_coluna(monkeypatch):
    """A regressão que interessa. `False` tem de chegar cá — se algum dia o
    campo voltar a ser um `datetime`, ou o `exclude_none` virar `exclude_unset`
    mal posto, isto passa a devolver a chave em falta e a lead fica travada
    para sempre."""
    saiu = _payload(monkeypatch, contacto_humano=False)
    assert "contacto_humano_em" in saiu, "desmarcar tem de chegar ao PostgREST"
    assert saiu["contacto_humano_em"] is None


def test_o_botao_nunca_vai_no_payload(monkeypatch):
    """`contacto_humano` não é coluna. O PostgREST responde PGRST204 e o
    guardar do painel rebenta com um erro que não diz nada a ninguém."""
    for valor in (True, False):
        assert "contacto_humano" not in _payload(monkeypatch, contacto_humano=valor)


def test_uma_edicao_normal_nao_toca_na_coluna(monkeypatch):
    """Mudar o estado ou as notas não pode desmarcar sozinho — seria a Matilde
    a voltar a escrever a quem uma consultora já tinha apanhado."""
    saiu = _payload(monkeypatch, estado="qualificada", notas="ligou de volta")
    assert "contacto_humano_em" not in saiu
    assert saiu["estado"] == "qualificada"


def test_criar_lead_nao_conhece_o_campo():
    """Só no update, de propósito: uma lead que nasce já contactada por uma
    pessoa não passa por esta página."""
    from app.models.lead import LeadCreate

    assert "contacto_humano" not in LeadCreate.model_fields


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
