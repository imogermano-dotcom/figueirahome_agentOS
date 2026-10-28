"""Lead no eGO de quem respondeu à Matilde e deixou a conversa parada (pedido #47, 27/10).

Quem responde, mas não pede visita, não escala nem recusa, ficava para sempre fora do eGO (5 de 14 leads de 26–27/10).
Interruptor `LEAD_RESPONDEU_EGO` (vazio = nada muda). Telefones de teste: `912345678`. Sem rede.
"""

import sys
from datetime import timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import leads_para_ego as lp  # noqa: E402
from app.config import settings  # noqa: E402
from tests.test_leads_para_ego import AGORA, ISO, _BD, _linha, _usa  # noqa: E402


def _respondeu(**kw):
    return _linha(respondeu_em=ISO(30), **kw)


def _conversa(monkeypatch, horas_parada, textos=("Gostaria de ir ver a casa", "O valor desta casa", "Não")):
    """A conversa de WhatsApp deste número: última atividade há `horas_parada` horas."""
    monkeypatch.setattr(lp, "_conversa_do", lambda tel: (AGORA - timedelta(hours=horas_parada), list(textos)))


def _ligado(monkeypatch, ligado=True):
    monkeypatch.setattr(settings, "lead_respondeu_ego", "1" if ligado else "")


def test_conversa_parada_ha_mais_de_4h_cria_a_lead_com_o_que_a_pessoa_disse(monkeypatch):
    _ligado(monkeypatch)
    _conversa(monkeypatch, 5)
    bd = _BD([_respondeu()])
    corpos = []
    _usa(monkeypatch, bd, lambda nome, email, tel, obs, ego_id: corpos.append(obs) or "555")
    r = lp.processar(AGORA)
    assert (r["criadas"], r["erros"]) == (1, 0)
    assert bd.updates == [("c1", {"ego_lead_em": AGORA.isoformat(), "ego_lead_id": 555})]
    assert "respondeu à Matilde mas a conversa parou sem pedido de visita" in corpos[0]
    assert "Disse: Gostaria de ir ver a casa | O valor desta casa | Não" in corpos[0]
    assert "Contactar por telefone" in corpos[0]


def test_conversa_ainda_viva_espera(monkeypatch):
    _ligado(monkeypatch)
    _conversa(monkeypatch, 3.9)
    bd = _BD([_respondeu()])
    _usa(monkeypatch, bd, lambda *a: pytest.fail("não devia criar"))
    assert lp.processar(AGORA)["criadas"] == 0 and bd.updates == []


def test_desligado_nao_consulta_conversas(monkeypatch):
    _ligado(monkeypatch, ligado=False)
    monkeypatch.setattr(lp, "_conversa_do", lambda tel: pytest.fail("não devia consultar"))
    bd = _BD([_respondeu()])
    _usa(monkeypatch, bd, lambda *a: pytest.fail("não devia criar"))
    assert lp.processar(AGORA)["criadas"] == 0


@pytest.mark.parametrize("campo", ["nao_contactar_em", "contacto_humano_em", "ego_lead_em"])
def test_recusa_consultor_ou_lead_ja_criada_nao_entram(monkeypatch, campo):
    _ligado(monkeypatch)
    _conversa(monkeypatch, 9)
    bd = _BD([_respondeu(**{campo: ISO(2)})])
    _usa(monkeypatch, bd, lambda *a: pytest.fail("não devia criar"))
    assert lp.processar(AGORA)["criadas"] == 0


@pytest.mark.parametrize("ultima", ["Obrigado", "Até muito breve", "Não tenho interesse", "Já não preciso"])
def test_quem_se_despediu_ou_recusou_no_fim_nao_entra(monkeypatch, ultima):
    _ligado(monkeypatch)
    _conversa(monkeypatch, 9, textos=("Quero saber mais", ultima))
    bd = _BD([_respondeu()])
    _usa(monkeypatch, bd, lambda *a: pytest.fail("não devia criar"))
    assert lp.processar(AGORA)["criadas"] == 0


def test_so_olha_para_as_leads_das_ultimas_semanas(monkeypatch):
    _ligado(monkeypatch)
    _conversa(monkeypatch, 9)
    filtros = []

    class _Q(_BD):
        def gte(self, campo, valor):
            filtros.append((campo, valor))
            return self

    bd = _Q([_respondeu()])
    _usa(monkeypatch, bd, lambda *a: "555")
    lp.processar(AGORA)
    cortes = [v for c, v in filtros if c == "meta_created_at"]
    assert (AGORA - timedelta(days=lp.IDADE_MAX_PARADA_DIAS)).isoformat() in cortes


def test_sem_conversa_de_whatsapp_nao_cria(monkeypatch):
    _ligado(monkeypatch)
    monkeypatch.setattr(lp, "_conversa_do", lambda tel: (None, []))
    bd = _BD([_respondeu()])
    _usa(monkeypatch, bd, lambda *a: pytest.fail("não devia criar"))
    assert lp.processar(AGORA)["criadas"] == 0


def test_quem_nao_respondeu_continua_pelo_caminho_das_2h(monkeypatch):
    """Sem resposta há 3 h: cria a lead das 2 h, não a da conversa parada (e não consulta conversas)."""
    _ligado(monkeypatch)
    monkeypatch.setattr(lp, "_conversa_do", lambda tel: pytest.fail("não tem conversa"))
    bd = _BD([_linha()])
    corpos = []
    _usa(monkeypatch, bd, lambda nome, email, tel, obs, ego_id: corpos.append(obs) or "555")
    assert lp.processar(AGORA)["criadas"] == 1 and "sem resposta ao WhatsApp" in corpos[0]


def test_interesse_real_e_conversa_parada_criam_uma_so_vez(monkeypatch):
    _ligado(monkeypatch)
    monkeypatch.setattr(settings, "lead_interesse_ego", "1")
    _conversa(monkeypatch, 9)
    bd = _BD([_respondeu(interesse_real_em=ISO(8), interesse_real_motivo="visita", interesse_real_resumo="Pediu visita.")])
    corpos = []
    _usa(monkeypatch, bd, lambda nome, email, tel, obs, ego_id: corpos.append(obs) or "555")
    r = lp.processar(AGORA)
    assert r["criadas"] == 1 and len(corpos) == 1 and "interesse real (visita)" in corpos[0], "o sinal de interesse ganha"


def test_fora_do_horario_espera(monkeypatch):
    from datetime import datetime, timezone

    _ligado(monkeypatch)
    monkeypatch.setattr(settings, "lead_compra_ego_desde", "2026-10-17T00:00:00+00:00")
    monkeypatch.setattr(lp, "get_supabase", lambda: pytest.fail("não devia tocar na BD"))
    assert lp.processar(datetime(2026, 10, 17, 22, 0, tzinfo=timezone.utc)) == {"ativo": True, "fora_do_horario": True}


def test_resumo_usa_as_ultimas_3_e_corta():
    assert lp.resumo_da_conversa(["um", "dois", "três", "quatro"]) == "dois | três | quatro"
    assert len(lp.resumo_da_conversa(["x" * 500] * 3)) <= 600
    assert lp.resumo_da_conversa(["  ", "olá   mundo\n"]) == "olá mundo"
    assert lp.resumo_da_conversa([]) == ""


def test_conversa_do_procura_pelas_variantes_do_numero(monkeypatch):
    visto = {}

    class _Q:
        def __getattr__(self, nome):
            def _f(*a, **k):
                visto[nome] = a
                return self
            return _f

        def execute(self):
            return type("R", (), {"data": [{"atualizado_em": "2026-10-17T08:00:00+00:00",
                                            "mensagens": [{"role": "user", "content": "olá"}, {"role": "assistant", "content": "oi"},
                                                          {"role": "user", "content": [{"x": 1}]}]}]})()

    monkeypatch.setattr(lp, "get_supabase", lambda: type("S", (), {"table": lambda self, n: _Q()})())
    ultima, textos = lp._conversa_do("912345678")
    assert textos == ["olá"], "só o que a pessoa escreveu, em texto"
    assert ultima.isoformat() == "2026-10-17T08:00:00+00:00"
    assert "912345678" in visto["in_"][1] and "351912345678" in visto["in_"][1]
    assert visto["eq"] == ("canal", "whatsapp")


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))


def test_recusa_a_meio_da_conversa_e_agradecimento_com_emoji_nao_criam_lead(monkeypatch):
    _ligado(monkeypatch)
    _conversa(monkeypatch, 5, textos=("Quero ver a casa", "Do momento não tenho", "Muito obrigado pela atenção 🤩"))
    bd = _BD([_respondeu()])
    _usa(monkeypatch, bd, lambda *a: pytest.fail("não devia criar"))
    assert lp.processar(AGORA)["criadas"] == 0 and bd.updates == []
