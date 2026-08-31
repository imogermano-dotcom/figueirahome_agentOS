"""As guardas dos fluxos do n8n, lidas dos JSON em `docs/n8n/`.

Não corre o n8n. Lê os ficheiros e verifica o que, quando falha, falha em
silêncio: o n8n não valida nomes de colunas, o PostgREST devolve linhas a mais
sem erro nenhum, e uma ligação apontada a um nó que não existe importa-se sem
queixa e nunca dispara.

A guarda que mais importa aqui é `contacto_humano_em` (migration 0032): trava
qualquer mensagem que nós iniciemos a uma lead que já está a ser tratada por
uma pessoa. Veio do cruzamento de 2026-08-29 — das 45 leads por reenviar, 8 já
existiam no eGO e 4 tinham oportunidade activa com consultora atribuída.

Corre com `pytest backend/tests/` ou `python backend/tests/test_n8n_guardas.py`.
"""

import json
import sys
from pathlib import Path

import pytest

N8N = Path(__file__).resolve().parents[2] / "docs" / "n8n"

_FLUXOS = ["01-enviar-template.json", "02-backfill-template.json", "03-follow-up-48h.json"]

# Os que mandam mensagem a partir de uma consulta à base. O `01` não está aqui:
# reage a um webhook do Make por `meta_lead_id`, não varre a tabela.
_QUE_VARREM = ["02-backfill-template.json", "03-follow-up-48h.json"]

_COLUNA = "contacto_humano_em"


def _fluxo(nome: str) -> dict:
    return json.loads((N8N / nome).read_text(encoding="utf-8"))


def _no(fluxo: dict, nome: str) -> dict:
    return next(n for n in fluxo["nodes"] if n["name"] == nome)


def _condicoes(fluxo: dict) -> str:
    return json.dumps(_no(fluxo, "Guardas")["parameters"]["conditions"], ensure_ascii=False)


# ── ligações ──────────────────────────────────────────────────────────────


@pytest.mark.parametrize("ficheiro", _FLUXOS)
def test_as_ligacoes_apontam_a_nos_que_existem(ficheiro):
    """O `03` tinha a agenda ligada a "Todos os dias às 10h" enquanto o nó se
    chamava "…às 12h" — o trigger não ia dar a lado nenhum e o fluxo nunca
    corria. O n8n importa isto sem um aviso."""
    fluxo = _fluxo(ficheiro)
    nomes = {n["name"] for n in fluxo["nodes"]}
    for origem, ligacoes in fluxo["connections"].items():
        assert origem in nomes, f"{ficheiro}: ligação a partir de '{origem}', que não existe"
        for ramo in ligacoes["main"]:
            for destino in ramo:
                assert destino["node"] in nomes, f"{ficheiro}: aponta a '{destino['node']}'"


# ── a guarda do contacto humano ───────────────────────────────────────────


@pytest.mark.parametrize("ficheiro", _QUE_VARREM)
def test_a_consulta_exclui_quem_ja_foi_contactado_por_uma_pessoa(ficheiro):
    fluxo = _fluxo(ficheiro)
    leitura = next(n for n in fluxo["nodes"] if n["name"].startswith("Ler leads"))
    assert f"{_COLUNA}=is.null" in leitura["parameters"]["filterString"]


@pytest.mark.parametrize("ficheiro", _FLUXOS)
def test_o_if_repete_a_guarda_do_contacto_humano(ficheiro):
    """Dita duas vezes de propósito: o `filterString` não é validado por
    ninguém. Um nome de coluna trocado devolve linhas a mais em silêncio, e no
    `02` a consulta corre UMA vez enquanto o ciclo demora minutos — quem for
    marcado a meio da corrida só é apanhado aqui."""
    assert _COLUNA in _condicoes(_fluxo(ficheiro))


def test_o_01_nao_poe_a_guarda_na_consulta():
    """No `01` a lead é procurada por `meta_lead_id`. Filtrar lá devolvia ZERO
    linhas para uma lead marcada, o nó morria antes das guardas, e ficava
    indistinguível de "lead não encontrada". Saltar é decisão do IF."""
    leitura = _no(_fluxo("01-enviar-template.json"), "Ler lead no Supabase")
    assert f"{_COLUNA}=is.null" not in leitura["parameters"]["filterString"]
    assert _COLUNA in leitura["parameters"]["filterString"], "mas tem de vir no select"


# ── o que os fluxos escrevem ──────────────────────────────────────────────


@pytest.mark.parametrize("ficheiro", _FLUXOS)
def test_o_n8n_nunca_escreve_as_colunas_que_nao_sao_dele(ficheiro):
    """`respondeu_em` é do backend (o sinal de que a pessoa falou) e
    `contacto_humano_em` é do painel (escrita por uma pessoa). O n8n lê ambas e
    não escreve nenhuma — se as escrevesse, apagava o próprio travão."""
    for no in _fluxo(ficheiro)["nodes"]:
        if no["parameters"].get("operation") != "update":
            continue
        campos = no["parameters"]["fieldsUi"]["fieldValues"]
        escritas = {c["fieldId"] for c in campos}
        assert "respondeu_em" not in escritas
        assert _COLUNA not in escritas


# ── nós nativos ───────────────────────────────────────────────────────────


@pytest.mark.parametrize("ficheiro", _FLUXOS)
def test_o_supabase_e_sempre_no_nativo(ficheiro):
    """O `01` falava com o PostgREST por HTTP Request com `$env.SUPABASE_URL` +
    Header Auth até 2026-08-29. Um URL da base dentro do fluxo é uma segunda
    configuração a manter a par da credencial — e o corpo do PATCH montado à
    mão obrigava a `JSON.stringify()` no `template_enviado`."""
    for no in _fluxo(ficheiro)["nodes"]:
        if no["type"] != "n8n-nodes-base.httpRequest":
            continue
        url = no["parameters"].get("url", "")
        assert "SUPABASE" not in url.upper() and "/rest/v1/" not in url, (
            f"{ficheiro}: '{no['name']}' fala com o Supabase por HTTP"
        )


def test_o_03_nao_tem_o_bug_do_offset_local():
    """`.toISO()` sozinho dá o offset local (+02:00); o `+` na query string vira
    espaço e o PostgREST rejeita ("invalid input syntax for type timestamp with
    time zone"). Apanhado em produção a 2026-08-29. `.toUTC()` antes resolve."""
    leitura = _no(_fluxo("03-follow-up-48h.json"), "Ler leads sem resposta")
    assert ".toUTC().toISO()" in leitura["parameters"]["filterString"]


def test_o_03_tem_o_template_de_followup_preenchido():
    """Ficou `NOME_DO_TEMPLATE_FOLLOWUP` de marcador até 2026-08-31 — importar
    assim falha ao carregar o template na Meta."""
    envio = _no(_fluxo("03-follow-up-48h.json"), "WhatsApp: enviar follow-up")
    assert envio["parameters"]["template"] != "NOME_DO_TEMPLATE_FOLLOWUP|pt_PT"
    assert "|" in envio["parameters"]["template"]


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
