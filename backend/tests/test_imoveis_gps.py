from app.integrations.imoveis_sync import _rua, gps_fiavel, planear_morada_gps


def _i(lat, lon, rua="Rua A"):
    return {"gpsLat": lat, "gpsLon": lon, "address": rua}


def test_rua_ignora_resto_numeros_e_acentos():
    assert _rua("Rua do Pinhal, Buarcos") == _rua("Rua do Pinhal\nnº 5") == "rua do pinhal"
    assert _rua(None) == ""


def test_gps_unico_e_grupo_pequeno_da_mesma_rua_entram_centroide_nao():
    api = {"U": _i(40.1, -8.1), "A": _i(40.2, -8.2, "Rua X, 1"), "B": _i(40.2, -8.2, "Rua X, Buarcos"),
           "C": _i(40.3, -8.3, "Rua Y"), "D": _i(40.3, -8.3, "Rua Z")}
    api |= {f"G{n}": _i(40.4, -8.4, f"Rua {n}") for n in range(10)}
    assert set(gps_fiavel(api)) == {"U", "A", "B"}


def test_so_preenche_vazios_e_nunca_troca():
    api = {"A": _i(40.1, -8.1) | {"zipCode": "3080-000", "floor": "2"}, "B": _i(40.2, -8.2), "C": _i(40.3, -8.3)}
    bd = {"A": {"fonte": "manual", "piso": " "}, "B": {"morada": "Outra", "latitude": 40.2, "longitude": -8.2},
          "C": {"morada": "x", "latitude": 40.9, "longitude": -8.9}}
    p = planear_morada_gps(api, bd)
    assert p["valores"] == {"A": {"morada": "Rua A", "codigo_postal": "3080-000", "piso": "2", "latitude": 40.1, "longitude": -8.1}}
    assert (p["gps_igual"], p["gps_a_alterar"]) == (1, ["C"])


def test_endpoint_so_escreve_com_dry_0(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.api import imoveis_sync as api_sync
    from app.api.deps import require_sync_access

    chamadas = []

    async def _sync(origem, dry):
        chamadas.append(dry)
        return {}

    monkeypatch.setattr(api_sync, "sync_morada_gps", _sync)
    app = FastAPI()
    app.include_router(api_sync.router)
    app.dependency_overrides[require_sync_access] = lambda: "sync-secret"
    c = TestClient(app)
    c.post("/api/imoveis/sync/morada-gps")
    c.post("/api/imoveis/sync/morada-gps?dry=0")
    assert chamadas == [True, False]
