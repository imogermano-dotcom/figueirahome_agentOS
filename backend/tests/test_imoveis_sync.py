"""Mapeamento eGO Web API → tabela `imoveis` — função pura, sem DB nem rede.

O payload abaixo é um recorte real de `GET /v1/Properties` (2026-08-12), com as
tags que interessam ao mapeamento. Corre com `pytest backend/tests/`.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.integrations.imoveis_sync import (  # noqa: E402
    _dedup_por_ref,
    _map_extras,
    _map_property,
)


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
    assert r["jardim"] is False

    # as do próprio imóvel são outras tags. FH2581 traz `PROPERTY_HAS_GARDEN`
    # ([Infraestruturas] Jardim) e `PROPERTY_NEAR_GARDENS` ([Zona Envolvente]
    # Espaços Verdes) ao mesmo tempo — o caso que prova que são coisas distintas.
    proprio = _payload(FeatureTags=[
        {"Tag": "PROPERTY_HAS_POOL", "Value": ""},
        {"Tag": "PROPERTY_HAS_GARDEN", "Value": ""},
        {"Tag": "PROPERTY_NEAR_GARDENS", "Value": ""},
    ])
    r = _map_property(proprio)
    assert r["piscina"] is True
    assert r["jardim"] is True


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


def test_dedup_fica_com_a_copia_mais_recente():
    """Caso real FH2460 4D: o eGO devolve dois imóveis com a mesma Reference e
    a ordem da lista escolhia o que não tinha `Floor` — 4.º andar gravado como
    piso 0. Desempata a data de alteração, não a posição."""
    velho = _map_property(_payload(ID=24968319, Floor=-2147483648, LastModified="2026-06-19T14:13:27"))
    novo = _map_property(_payload(ID=24968346, Floor=4, LastModified="2026-06-19T14:13:28"))

    # a boa aparece primeiro na lista — a ordem não pode decidir
    assert _dedup_por_ref([novo, velho])["FH2483_C"]["ego_id"] == 24968346
    # e também quando aparece depois
    assert _dedup_por_ref([velho, novo])["FH2483_C"]["ego_id"] == 24968346


def test_angariador_so_do_role_certo():
    outro = _payload(PropertyAgents=[{"AgentName": "X", "Roles": [{"ID": 9, "Name": "Vendedor"}]}])
    assert "angariador" not in _map_property(outro)


# ── validação CRM restrita aos despublicados ────────────────────────────────
#
# A Web API só devolve publicados: quando um imóvel sai dela, nada automático
# volta a dizer o que lhe aconteceu — se for vendido a seguir, o Supabase fica
# a dizer "Disponível" para sempre. `sync_egorealestate_api` passou a correr a
# validação CRM restrita a esses refs.
#
# O que estes testes protegem é a razão pela qual a validação CRM completa saiu
# do cron (`docs/decisoes.md`): sobrepunha, com dados desactualizados do
# backoffice, estados que a API pública já tinha confirmado — caso FH2483_A.
# Restrita, não pode tocar em nada que a API tenha devolvido.

import asyncio  # noqa: E402
from types import SimpleNamespace  # noqa: E402

import httpx  # noqa: E402

import app.integrations.imoveis_sync as sync  # noqa: E402


class _Q:
    def __init__(self, tabela, estado):
        self.tabela, self.estado, self._dados = tabela, estado, []
        self._filtro_in = None

    def select(self, *a, **k):
        if self.tabela == "imoveis":
            self._dados = list(self.estado["imoveis"])
        return self

    def update(self, dados):
        self.estado["updates"].append((self.tabela, dados))
        return self

    def insert(self, dados):
        self.estado["inserts"].append((self.tabela, dados))
        return self

    def upsert(self, dados, **k):
        self.estado.setdefault("sequencia", []).append("upsert")
        self.estado["inserts"].append((self.tabela, dados))
        return self

    def eq(self, campo, valor):
        if self.tabela == "imoveis" and campo == "disponibilidade":
            self._dados = [r for r in self._dados if r.get("disponibilidade") == valor]
        if self.tabela == "imoveis" and campo == "imovel_ref":
            self.estado["updates_refs"].append(valor)
        return self

    def in_(self, campo, valores):
        if self.tabela == "imoveis" and campo == "imovel_ref":
            self.estado["escopo_consultado"] = set(valores)
            self._dados = [r for r in self._dados if r["imovel_ref"] in set(valores)]
        if self.tabela == "agente_tarefas":
            self.estado["tarefas_fechadas"] = set(valores)
        return self

    def like(self, *a, **k):
        return self

    def not_(self, *a, **k):
        return self

    def is_(self, *a, **k):
        return self

    def limit(self, *a, **k):
        return self

    def execute(self):
        return SimpleNamespace(data=self._dados)


def _montar(monkeypatch, crm_items, detalhe):
    """Supabase e backoffice falsos. Devolve o `estado` observável."""
    estado = {
        # FH2571 saiu da API (é o escopo); FH2483_C continua publicado e nunca
        # pode ser tocado por esta chamada.
        "imoveis": [
            {"imovel_ref": "FH2571", "disponibilidade": "Disponível", "ego_id": 111, "fonte": "egorealestate"},
            {"imovel_ref": "FH2483_C", "disponibilidade": "Disponível", "ego_id": 222, "fonte": "egorealestate"},
        ],
        "updates": [], "updates_refs": [], "inserts": [],
        "escopo_consultado": None, "tarefas_fechadas": None,
    }
    fake_sb = SimpleNamespace(table=lambda nome: _Q(nome, estado))
    monkeypatch.setattr(sync, "get_supabase", lambda: fake_sb)
    monkeypatch.setattr(sync.settings, "egorealestate_crm_username", "u")
    monkeypatch.setattr(sync.settings, "egorealestate_crm_password", "p")

    class _Cliente:
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False

    async def _detalhe(client, ego_id):
        return detalhe

    monkeypatch.setattr(sync.egorealestate_crm, "authenticated_client", lambda: _Cliente())
    monkeypatch.setattr(sync.egorealestate_crm, "_login", lambda c: asyncio.sleep(0))
    monkeypatch.setattr(sync.egorealestate_crm, "fetch_all", lambda c: _async(crm_items))
    monkeypatch.setattr(sync.egorealestate_crm, "fetch_detail", _detalhe)
    return estado


async def _async(valor):
    return valor


def test_validacao_restrita_nao_toca_no_que_a_api_confirmou(monkeypatch):
    """A regressão do FH2483_A: com escopo, um imóvel que a API devolveu não
    pode ser lido nem corrigido — é a única razão pela qual isto pode voltar ao
    cron sem repetir o erro que o tirou de lá."""
    estado = _montar(monkeypatch, crm_items=[], detalhe={"disponibilidade": "Vendido"})

    corrigidos, detalhes = asyncio.run(sync.validar_disponibilidade_crm({"FH2571"}))

    assert estado["escopo_consultado"] == {"FH2571"}, "a consulta local não foi restringida"
    assert "FH2483_C" not in estado["updates_refs"], "tocou num imóvel ainda publicado"
    assert estado["updates_refs"] == ["FH2571"]
    assert corrigidos == 1
    assert detalhes[0]["alteracoes"]["disponibilidade"]["para"] == "Vendido"


def test_validacao_restrita_nao_cria_imoveis(monkeypatch):
    """O Caso 1 fica desligado com escopo: esta chamada corrige o que existe,
    não importa imóveis novos pela porta das traseiras."""
    estado = _montar(
        monkeypatch,
        crm_items=[{"imovel_ref": "NOVO_1", "crm_disponibilidade": "Disponível", "ego_id": 999}],
        detalhe={"disponibilidade": "Vendido"},
    )

    asyncio.run(sync.validar_disponibilidade_crm({"FH2571"}))

    assert not [d for t, d in estado["inserts"] if t == "imoveis"]


def test_crm_diz_disponivel_nao_altera_nada(monkeypatch):
    """Retirado da publicação mas ainda à venda: o backoffice lista-o como
    Disponível, e o estado local está certo. Não mexer."""
    estado = _montar(
        monkeypatch,
        crm_items=[{"imovel_ref": "FH2571", "crm_disponibilidade": "Disponível", "ego_id": 111}],
        detalhe={"disponibilidade": "Disponível"},
    )

    corrigidos, _ = asyncio.run(sync.validar_disponibilidade_crm({"FH2571"}))

    assert corrigidos == 0
    assert estado["updates_refs"] == []


def test_lista_vazia_do_crm_aborta_so_quando_nao_ha_escopo(monkeypatch):
    """Sem escopo, `fetch_all` vazio é sinal de o backoffice ter falhado e o
    Caso 3 marcaria tudo. Com escopo é normal — um imóvel vendido não aparece
    em `fetch_all` (`_STATUS_CODES` não inclui Vendido) e é precisamente esse o
    caso que temos de apanhar."""
    estado = _montar(monkeypatch, crm_items=[], detalhe={"disponibilidade": "Vendido"})
    assert asyncio.run(sync.validar_disponibilidade_crm()) == (0, [])
    assert estado["updates_refs"] == []

    estado = _montar(monkeypatch, crm_items=[], detalhe={"disponibilidade": "Vendido"})
    corrigidos, _ = asyncio.run(sync.validar_disponibilidade_crm({"FH2571"}))
    assert corrigidos == 1


def test_tarefas_de_despublicacao_sao_fechadas(monkeypatch):
    """Havia 20 pendentes e nenhuma fechada: a tarefa nascia automática e só se
    fechava à mão."""
    estado = _montar(monkeypatch, crm_items=[], detalhe={"disponibilidade": "Vendido"})
    asyncio.run(sync._fechar_tarefas_despublicado(["FH2571"]))
    assert estado["tarefas_fechadas"] == {"FH2571"}
    assert ("agente_tarefas", {"estado": "concluida"}) in estado["updates"]


def test_validacao_crm_corre_depois_do_upsert(monkeypatch):
    """O cron morreu dois dias por causa da ordem, não da lógica.

    A validação CRM raspa o backoffice inteiro e estourou o `--max-time 120` do
    workflow a 2026-08-16/17. Estando **antes** do upsert, o curl desligava, o
    handler era cancelado a meio e os imóveis nunca eram gravados: `agente_sync_log`
    ficou sem uma linha `egorealestate_api` de 08-15 08:08 a 08-17.

    O `try/except` à volta da validação não apanha isto — um cliente que desiste
    não levanta excepção do lado de cá. Só a ordem protege, e é ela que este
    teste tranca: primeiro gravar o que a API deu, depois o que é lento e
    opcional."""
    estado = {"imoveis": [], "updates": [], "updates_refs": [], "inserts": [], "sequencia": []}
    fake_sb = SimpleNamespace(table=lambda nome: _Q(nome, estado))
    monkeypatch.setattr(sync, "get_supabase", lambda: fake_sb)
    monkeypatch.setattr(sync.settings, "egorealestate_api_key", "k")

    async def _pagina(page, size):
        return ([{"ID": 111, "Reference": "FH2571"}], 1) if page == 1 else ([], 1)

    async def _flag(missing):
        return 0, [], ["FH2571"]

    async def _crm(refs):
        estado["sequencia"].append("crm")
        return 0, []

    async def _log(tipo, resumo, detalhes):
        estado["sequencia"].append("log")

    monkeypatch.setattr(sync.egorealestate, "get_properties_page", _pagina)
    monkeypatch.setattr(sync.egorealestate, "get_property_detail", lambda eid: _async({}))
    monkeypatch.setattr(sync, "_map_property", lambda p: {
        "imovel_ref": "FH2571", "ego_id": 111, "ego_atualizado_em": None,
    })
    monkeypatch.setattr(sync, "_map_extras", lambda p: {})
    monkeypatch.setattr(sync, "_existing_ego_ids", lambda d: _async({111}))
    monkeypatch.setattr(sync, "_flag_unpublished", _flag)
    monkeypatch.setattr(sync, "_existing_refs", lambda r: _async(set()))
    monkeypatch.setattr(sync, "validar_disponibilidade_crm", _crm)
    monkeypatch.setattr(sync, "_log_execucao", _log)

    asyncio.run(sync.sync_egorealestate_api())

    assert estado["sequencia"] == ["upsert", "crm", "log"], estado["sequencia"]


# ── visitas virtuais: só existem no endpoint de detalhe ─────────────────────
#
# `GET /v1/Properties` devolve 82 campos, `GET /v1/Properties/{ID}` devolve 104.
# `ExternalVirtualTours` está só no segundo, e foi por se olhar apenas para a
# listagem que se concluiu (mal) que o eGO não expunha visitas virtuais.
# A 2026-08-18: 7 dos 56 publicados, todas Matterport, uma por imóvel.


def test_visita_virtual_extraida_do_detalhe():
    p = {
        "ID": 26167109, "Reference": "FH2572",
        "ExternalVirtualTours": [
            {"Url": "https://my.matterport.com/show/?m=hHEhT5f4Wxw", "Description": "Visita Virtual"},
        ],
    }
    assert sync._map_property(p)["visita_virtual_url"] == "https://my.matterport.com/show/?m=hHEhT5f4Wxw"


def test_sem_visita_virtual_escreve_none():
    """A chave tem de existir mesmo vazia: é o que faz tirar a visita virtual no
    eGO apagar o link cá. Se isto fosse pelo `_map_extras`, que filtra os nulos,
    o link velho ficava para sempre."""
    record = sync._map_property({"ID": 1, "Reference": "FH0001"})
    assert "visita_virtual_url" in record
    assert record["visita_virtual_url"] is None


def test_resumo_conta_as_visitas_virtuais(monkeypatch):
    """Testemunha de que os campos do detalhe continuam a chegar: se o eGO
    renomear `ExternalVirtualTours`, o sync fica verde com `erros: 0` e os links
    vão a NULL em silêncio — e o site novo mostra-os."""
    estado = {"imoveis": [], "updates": [], "updates_refs": [], "inserts": [], "sequencia": []}
    monkeypatch.setattr(sync, "get_supabase", lambda: SimpleNamespace(table=lambda n: _Q(n, estado)))
    monkeypatch.setattr(sync.settings, "egorealestate_api_key", "k")

    async def _pagina(page, size):
        if page != 1:
            return [], 2
        return [{"ID": 1, "Reference": "COM_TOUR"}, {"ID": 2, "Reference": "SEM_TOUR"}], 2

    async def _detalhe(ego_id):
        return {"ExternalVirtualTours": [{"Url": "https://my.matterport.com/show/?m=X"}]} if ego_id == 1 else {}

    monkeypatch.setattr(sync.egorealestate, "get_properties_page", _pagina)
    monkeypatch.setattr(sync.egorealestate, "get_property_detail", _detalhe)
    monkeypatch.setattr(sync, "_existing_ego_ids", lambda d: _async(set()))
    monkeypatch.setattr(sync, "_flag_unpublished", lambda m: _async((0, [], [])))
    monkeypatch.setattr(sync, "_existing_refs", lambda r: _async(set()))
    monkeypatch.setattr(sync, "_log_execucao", lambda t, r, d: _async(None))

    resumo = asyncio.run(sync.sync_egorealestate_api())

    assert resumo["com_visita_virtual"] == 1
    assert resumo["erros"] == 0


def test_falha_do_detalhe_salta_o_imovel(monkeypatch):
    """Melhor perder um imóvel numa corrida do que gravá-lo sem os campos do
    detalhe — `visita_virtual_url` iria a NULL e apagaria um link bom por causa
    de uma falha passageira da API."""
    estado = {"imoveis": [], "updates": [], "updates_refs": [], "inserts": [], "sequencia": []}
    fake_sb = SimpleNamespace(table=lambda nome: _Q(nome, estado))
    monkeypatch.setattr(sync, "get_supabase", lambda: fake_sb)
    monkeypatch.setattr(sync.settings, "egorealestate_api_key", "k")

    async def _pagina(page, size):
        return ([{"ID": 111, "Reference": "FH2571"}], 1) if page == 1 else ([], 1)

    async def _detalhe_rebenta(ego_id):
        raise httpx.ConnectError("eGO em baixo")

    monkeypatch.setattr(sync.egorealestate, "get_properties_page", _pagina)
    monkeypatch.setattr(sync.egorealestate, "get_property_detail", _detalhe_rebenta)
    monkeypatch.setattr(sync, "_existing_ego_ids", lambda d: _async(set()))
    monkeypatch.setattr(sync, "_flag_unpublished", lambda m: _async((0, [], [])))
    monkeypatch.setattr(sync, "_existing_refs", lambda r: _async(set()))
    monkeypatch.setattr(sync, "_log_execucao", lambda t, r, d: _async(None))

    resumo = asyncio.run(sync.sync_egorealestate_api())

    assert resumo["erros"] == 1
    assert resumo["criados"] == 0 and resumo["atualizados"] == 0

    # O upsert chega a sair, mas com a lista vazia — é isso que tem de ser
    # verdade: nenhuma linha escrita. (Um upsert vazio é um no-op; não vale um
    # guarda no código só para o evitar.)
    gravados = [d for t, d in estado["inserts"] if t == "imoveis"]
    assert all(not d for d in gravados), f"gravou um imóvel sem o detalhe: {gravados}"


# ── ligação ao Supabase caída por inactividade ──────────────────────────────
#
# A validação CRM raspa o backoffice ~2,5 min sem tocar no Supabase. O outro
# lado fecha a conexão do pool, e a chamada seguinte reutiliza um socket morto.
# Visto em produção a 2026-08-17: `RemoteProtocolError: Server disconnected` no
# insert do log, com o upsert e a validação CRM já feitos, e um 502 devolvido ao
# cron por um sync que correu bem.


def test_run_repete_uma_vez_em_ligacao_caida():
    tentativas = []

    def _fn():
        tentativas.append(1)
        if len(tentativas) == 1:
            raise httpx.RemoteProtocolError("Server disconnected")
        return "ok"

    assert asyncio.run(sync._run(_fn)) == "ok"
    assert len(tentativas) == 2


def test_run_nao_repete_outros_erros():
    """A repetição só é segura porque um socket fechado falha antes de o pedido
    ser processado. Qualquer outro erro pode ter deixado a escrita aplicada —
    repetir duplicaria tarefas e linhas de log."""
    tentativas = []

    def _fn():
        tentativas.append(1)
        raise ValueError("erro de dados")

    try:
        asyncio.run(sync._run(_fn))
    except ValueError:
        pass
    else:
        raise AssertionError("engoliu um erro que não é de ligação")

    assert len(tentativas) == 1, "repetiu uma escrita que pode ter sido aplicada"


def test_log_falhado_nao_derruba_o_sync(monkeypatch):
    """O log é o registo, não o trabalho. Falhar a escrevê-lo não pode
    transformar um sync bem sucedido num 502."""
    async def _explode(fn):
        raise httpx.RemoteProtocolError("Server disconnected")

    monkeypatch.setattr(sync, "_run", _explode)
    asyncio.run(sync._log_execucao("egorealestate_api", {}, []))  # não levanta


if __name__ == "__main__":
    for nome, fn in sorted(globals().items()):
        if nome.startswith("test_"):
            fn()
            print(f"ok  {nome}")
