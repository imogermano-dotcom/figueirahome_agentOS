"""Mapeamento eGO Web API → tabela `imoveis` — função pura, sem DB nem rede.

O payload abaixo é um recorte real de `GET /v1/Properties` (2026-08-12), com as
tags que interessam ao mapeamento. Corre com `pytest backend/tests/`.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.integrations.imoveis_sync import _map_extras, _map_property  # noqa: E402


def _payload(**over) -> dict:
    p = {
        "ID": 15720217,
        "Reference": "FH2483_C",
        "Type": "Apartamento",
        "Condition": "Usado",
        "Availability": "Disponível",
        "EnergyCertification": "E",
        "ExclusiveRegime": 0,
        "CreatedDate": "2025-05-21T10:57:20",
        "LastModified": "2026-08-10T10:18:48",
        "PropertyAgents": [
            {"AgentID": 1, "AgentName": "Lina Galvão", "Roles": [{"ID": 4, "Name": "Angariador"}]}
        ],
        "FeatureTags": [
            {"Tag": "PROPERTY_HAS_GARAGE", "Value": ""},
            {"Tag": "PROPERTY_NUM_PARKING_SPACES", "Value": "1"},
            {"Tag": "PROPERTY_HAS_ELEVATOR", "Value": ""},
            {"Tag": "PROPERTY_HAS_BALCONY", "Value": "2"},
            {"Tag": "PROPERTY_HAS_AC", "Value": ""},
            {"Tag": "PROPERTY_HAS_SUITE", "Value": "1"},
            {"Tag": "FEATURE_CONDITION", "Value": "Excelente"},
            # Zona envolvente — NÃO são features do imóvel:
            {"Tag": "SWIMMING_POOLS", "Value": ""},
            {"Tag": "PROPERTY_NEAR_GARDENS", "Value": ""},
            {"Tag": "BEACH", "Value": ""},
        ],
    }
    p.update(over)
    return p


def test_booleanos_do_imovel():
    r = _map_property(_payload())
    assert r["garagem"] is True
    assert r["estacionamento"] is True
    assert r["elevador"] is True
    assert r["varanda"] is True
    assert r["ar_condicionado"] is True
    # ausentes no payload → False explícito, não None
    assert r["terraco"] is False
    assert r["aquecimento_central"] is False
    assert r["vista_mar"] is False


def test_zona_envolvente_nunca_vira_feature_do_imovel():
    """Regressão: `SWIMMING_POOLS` é "há piscinas na zona" e
    `PROPERTY_NEAR_GARDENS` é "espaços verdes perto". Apanhá-las põe o A1 a
    afirmar ao comprador que o imóvel tem piscina e jardim que não tem."""
    r = _map_property(_payload())
    assert r["piscina"] is False
    assert "jardim" not in r  # sem fonte na API — nunca escrito, não se apaga

    # a piscina do próprio imóvel é outra tag
    com_piscina = _payload(FeatureTags=[{"Tag": "PROPERTY_HAS_POOL", "Value": ""}])
    assert _map_property(com_piscina)["piscina"] is True


def test_vista_praia_e_vista_mar_sao_vistas_nao_proximidade():
    """`BEACH` (perto da praia) não é `BEACH_VIEW` (vista para praia)."""
    assert _map_property(_payload())["vista_praia"] is False
    vista = _payload(FeatureTags=[{"Tag": "BEACH_VIEW", "Value": ""}])
    assert _map_property(vista)["vista_praia"] is True


def test_upsert_com_chaves_uniformes():
    """O invariante que faltava em 2026-08-12, e que custou 40 coordenadas.

    O PostgREST manda o lote como um `INSERT ... ON CONFLICT` sobre a UNIÃO das
    chaves de todos os registos: uma chave presente num só registo vira coluna
    do statement e escreve NULL em todos os outros. Um registo com chaves a
    menos não se protege — apaga os vizinhos. Por isso `_map_property` tem de
    devolver sempre exactamente as mesmas chaves, e o que é esparso sai por
    `_map_extras`, aplicado linha a linha."""
    variados = [
        _payload(),
        _payload(FeatureTags=[], EnergyCertification="", PropertyAgents=[], Floor=3),
        _payload(HasGPSLocation=True, GPSLat=40.1, GPSLon=-8.8, ExclusiveRegime=1),
        _payload(CreatedDate=None, LastModified=None),
    ]
    chaves = {frozenset(_map_property(p)) for p in variados}
    assert len(chaves) == 1, f"registos com chaves diferentes no mesmo lote: {chaves}"


def test_campos_esparsos_saem_fora_do_upsert():
    """Sem valor na API a chave não pode existir — senão apaga o que veio do
    Excel/CRM. E nenhuma delas pode aparecer no registo do upsert."""
    e = _map_extras(_payload())
    assert e["conservacao"] == "Excelente"
    assert e["certificacao_energetica"] == "E"
    assert e["angariador"] == "Lina Galvão"
    assert e["suites"] == 1

    vazio = _map_extras(_payload(FeatureTags=[], EnergyCertification="", PropertyAgents=[]))
    assert vazio == {}, f"chave a None apagaria o valor existente: {vazio}"

    record = _map_property(_payload())
    for col in ("conservacao", "certificacao_energetica", "angariador", "suites",
                "piso", "latitude", "longitude"):
        assert col not in record, f"{col} no upsert volta a apagar as outras linhas"


def test_datas_truncadas_e_exclusividade():
    r = _map_property(_payload())
    assert r["data_criacao"] == "2025-05-21"      # colunas são `date`, não timestamp
    assert r["data_alteracao"] == "2026-08-10"
    assert r["ego_atualizado_em"] == "2026-08-10T10:18:48+00:00"
    assert r["exclusividade"] == "Regime aberto"
    assert _map_property(_payload(ExclusiveRegime=1))["exclusividade"] == "Exclusivo"


def test_gps_so_quando_o_eGO_diz_que_e_real():
    """`GPSLat`/`GPSLon` vêm sempre; sem `HasGPSLocation` são o centróide da
    zona — 42 dos 54 imóveis, 19 no mesmo ponto. Marcá-los é inventar morada."""
    aproximado = _payload(HasGPSLocation=False, GPSLat=40.16661, GPSLon=-8.845518)
    e = _map_extras(aproximado)
    assert "latitude" not in e and "longitude" not in e

    real = _payload(HasGPSLocation=True, GPSLat=40.15253, GPSLon=-8.857521)
    e = _map_extras(real)
    assert (e["latitude"], e["longitude"]) == (40.15253, -8.857521)


def test_piso_usa_a_tag_quando_Floor_nao_vem():
    sem_floor = _payload(FeatureTags=[{"Tag": "PROPERTY_FLOOR", "Value": "3"}])
    assert _map_extras(sem_floor)["piso"] == "3"

    assert _map_extras(_payload(Floor=2))["piso"] == "2"
    # INT32_MIN é o "sem valor" do eGO, não um piso
    assert "piso" not in _map_extras(_payload(Floor=-2147483648))


def test_angariador_so_do_role_certo():
    outro = _payload(PropertyAgents=[{"AgentName": "X", "Roles": [{"ID": 9, "Name": "Vendedor"}]}])
    assert "angariador" not in _map_property(outro)


if __name__ == "__main__":
    for nome, fn in sorted(globals().items()):
        if nome.startswith("test_"):
            fn()
            print(f"ok  {nome}")
