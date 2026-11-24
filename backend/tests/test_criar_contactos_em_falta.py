import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from criar_contactos_em_falta import classificar, digitos9, indices, pessoa_do_ego


def _linha(id, tel=None, email=None, ego_link=None, ego_person_id=None):
    return {"id": id, "telefone": tel, "telemovel": None, "email": email, "ego_link": ego_link, "ego_person_id": ego_person_id}


def _caso(pid, pessoa, linhas):
    por_tel, por_email, por_pessoa = indices(linhas)
    return classificar(pid, pessoa, {c["id"]: c for c in linhas}, por_tel, por_email, por_pessoa)


def test_telefones_em_varios_formatos_e_listas():
    assert digitos9("+351 912 345 678") == {"912345678"}
    assert digitos9("00351912345678, 233 111 222") == {"912345678", "233111222"}
    assert digitos9("123") == set()


def test_pessoa_do_ego_separa_telefone_e_email_pelo_conteudo():
    p = pessoa_do_ego({"firstName": "Ana", "lastName": "X", "isCompany": False, "alterDate": "2026-11-20T10:00:00",
                       "personalContacts": [{"personalContactTypeId": 2, "contact": "912 345 678"}, {"personalContactTypeId": 1, "contact": "A@B.pt"}]})
    assert p["telefones"] == ["912345678"] and p["emails"] == ["a@b.pt"] and p["alter"] == "2026-11-20" and p["nome"] == "Ana X"


def test_classifica_a_b_c_d():
    pessoa = {"telefones": ["912345678"], "emails": ["a@b.pt"]}
    assert _caso(9, pessoa, [_linha("1", ego_person_id=9, ego_link="x")])[0] == "a"
    assert _caso(9, pessoa, [_linha("1", tel="912345678")]) == ("b", ["1"])  # uma só, sem ego_link: completar
    assert _caso(9, pessoa, [_linha("1", tel="912345678"), _linha("2", email="a@b.pt")])[0] == "c"  # duas: não se adivinha
    assert _caso(9, pessoa, [_linha("1", tel="912345678", ego_person_id=7, ego_link="y")])[0] == "c"  # já é de outra pessoa do eGO
    assert _caso(9, pessoa, [_linha("1", tel="999999999")]) == ("d", [])  # sem correspondência: criar


from criar_contactos_em_falta import campos_a_completar, linha_nova, mesmo_nome, montar_plano  # noqa: E402

PREFIXO = "https://exemplo.invalid/egocore/person/"


def test_mesmo_nome_aceita_igual_e_contido_nunca_vazio():
    assert mesmo_nome("Ana Maria Silva", "ana  silva")
    assert mesmo_nome("José Ação", "Jose Acao")
    assert not mesmo_nome("Ana Silva", "Rui Costa")
    assert not mesmo_nome("Ana Silva", "Ana Costa")  # só um nome em comum: não chega
    assert not mesmo_nome("", "Ana") and not mesmo_nome(None, None)


def _p(nome="Ana Silva", tel=("912345678",), mail=("a@b.pt",), empresa=False):
    return {"nome": nome, "telefones": list(tel), "emails": list(mail), "tipos": [], "empresa": empresa, "alter": "2026-11-20"}


def test_plano_completa_cria_e_deixa_ao_miguel():
    linhas = [_linha("1", tel="912345678"), _linha("2", tel="933333333"), _linha("3", tel="944444444"), _linha("4", tel="944444444")]
    linhas[0]["nome"], linhas[1]["nome"], linhas[2]["nome"], linhas[3]["nome"] = "Ana Silva", "Outra Pessoa", "Rui Costa", "Rui Costa"
    por_tel, por_email, por_pessoa = indices(linhas)
    por_id = {c["id"]: c for c in linhas}
    cache = {"1": _p(), "2": _p("Ana Silva", tel=("933333333",), mail=()), "3": _p("Rui Costa", tel=("944444444",), mail=()),
             "4": _p("Nova Pessoa", tel=("955555555",), mail=()), "5": _p("Sem Contacto", tel=(), mail=())}
    plano = montar_plano({1, 2, 3, 4, 5}, cache, por_id, por_tel, por_email, por_pessoa)
    assert plano["completar"] == [(1, "1")]  # nome igual, uma só linha
    assert plano["criar"] == [4]  # sem correspondência e com telefone
    assert plano["miguel"] == {"b com nome diferente": 1, "c (varias linhas ou outra pessoa)": 1, "sem telefone nem email": 1}


def test_completar_so_preenche_o_que_esta_vazio():
    novo = campos_a_completar(9, _p(), {"telefone": None, "telemovel": None, "email": None}, PREFIXO)
    assert novo == {"ego_person_id": 9, "ego_link": PREFIXO + "9", "telefone": "912345678", "telemovel": "912345678", "email": "a@b.pt"}
    novo = campos_a_completar(9, _p(), {"telefone": "933333333", "telemovel": None, "email": "x@y.pt"}, PREFIXO)
    assert novo == {"ego_person_id": 9, "ego_link": PREFIXO + "9"}  # nunca por cima do que existe


def test_linha_nova_nunca_traz_consentimento_de_whatsapp():
    linha = linha_nova(9, _p(tel=(), mail=("a@b.pt",)), PREFIXO)
    assert linha["whatsapp_permissao"] is False and linha["origem"] == "ego_api" and linha["criado_em"] == "2026-11-20"
    assert "telefone" not in linha and linha["email"] == "a@b.pt"
