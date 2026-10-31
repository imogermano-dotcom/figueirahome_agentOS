from scripts.ego_api_notas import chave, linha_de_nota, so_na_api, texto_de


def test_texto_de_tira_html_e_entidades():
    assert texto_de("<p>Ligou &amp; n&atilde;o atendeu</p><br/>Voltar a ligar") == "Ligou & não atendeu\nVoltar a ligar"


def test_so_na_api_ignora_vazias_existentes_e_repetidas():
    nome = {1: "VEN_1"}
    api = [
        {"id": 10, "objectId": 1, "createDate": "2026-10-05T10:00:00", "description": "<p>Nota A</p>"},
        {"id": 11, "objectId": 1, "createDate": "2026-10-05T11:00:00", "description": "<p>Nota A</p>"},  # mesma chave
        {"id": 12, "objectId": 1, "createDate": "2026-10-06T10:00:00", "description": "<p>Nota B</p>"},  # já na BD
        {"id": 13, "objectId": 1, "createDate": "2026-10-07T10:00:00", "description": "<br>"},  # evento sem texto
    ]
    r = so_na_api(api, nome, {chave("VEN_1", "2026-10-06", "Nota B")})
    assert [n["ego_id"] for n in r] == [10]
    assert linha_de_nota(r[0])["nota_data_raw"] == "05/10/2026"
