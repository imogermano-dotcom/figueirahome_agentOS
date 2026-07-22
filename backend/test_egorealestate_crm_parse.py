"""Teste isolado do parsing de `egorealestate_crm._parse_page`/`_parse_detail`
contra fragmentos HTML reais capturados do backoffice eGO (sessão 2026-07-21)
— sem rede, sem credenciais."""
from app.integrations.egorealestate_crm import _parse_detail, _parse_page

FIXTURE_HTML = """
<div class="listItem propertyItem">
  <div class="listItemHeader">
    <div class="listActionsCheck">
      <input type="checkbox" class="ObjectChecker ListItemCheckbox" data-object-id="30117399">
    </div>
    <div class="listItemStatus evaluation"><span class="dot"></span>Por validar</div>
    <div class="ListItemTitle">
      <a href="/egocore/realestate/30117399" title="Apartamento T3 FH2569">Apartamento T3 <span>FH2569</span></a>
    </div>
  </div>
</div>
"""

# Imóvel que é fracção de um empreendimento: span extra "Fração"/"Empreendimento"
# antes do span com a referência real — bug real encontrado ao correr contra
# produção (imovel_ref era lido como "Fração" para ~50 imóveis distintos).
FIXTURE_HTML_FRACAO = """
<div class="listItem propertyItem">
  <div class="listItemHeader">
    <div class="listActionsCheck">
      <input type="checkbox" class="ObjectChecker ListItemCheckbox" data-object-id="24265052">
    </div>
    <div class="listItemStatus available"><span class="dot"></span>Disponível</div>
    <div class="ListItemTitle">
      <a href="/egocore/realestate/24265052" title="Loja FH2283DN"><span class="developmentTitle">Fração </span>Loja <span>FH2283DN</span></a>
    </div>
  </div>
</div>
"""


# Página de detalhe (GET /egocore/realestate/{id}) — trecho real de FH2569,
# reduzido aos blocos que _parse_detail lê (título, subtítulo, preço,
# "Detalhes", "Descrição", fotos).
FIXTURE_DETAIL_HTML = """
<p class="listHeaderTitle">Apartamento T3 <span>FH2569</span></p>
<p class="listHeaderSubTitle">São Pedro, Figueira da Foz</p>
<span class="listItemPricingSection">Venda&nbsp;<strong><span>215 000 €</span></strong></span>
<div class="detailPropertyContentTitle">Descrição</div>
<div class="listItemDescription">E se a sua próxima casa estivesse a poucos minutos do mar?</div>
<div class="detailPropertyContentTitle">Características</div>
<div class="listItemDescription"><div class="listItemFeaturesGroup"><strong>Infraestruturas</strong>: Garagem</div></div>
<div class="listItemData">
    <span class="listItemDataSection">Estado<strong> Usado</strong></span>
    <span class="listItemDataSection">Disponibilidade<strong> Por validar</strong></span>
    <span class="listItemDataSection">Quartos<strong> 3</strong></span>
    <span class="listItemDataSection">Casas de banho<strong> 2</strong></span>
    <span class="listItemDataSection">Área útil<strong>&nbsp;113 m²</strong></span>
    <span class="listItemDataSection">Área bruta<strong>&nbsp;166 m²</strong></span>
</div>
<img src="https://images.egorealestate.com/Z640x480/W6429/S5/C6429/P30117399/Tphoto/ID1.jpg" alt="FH2569 (1)">
<img src="https://images.egorealestate.com/Z640x480/W6429/S5/C6429/P30117399/Tphoto/ID2.jpg" alt="FH2569 (2)">
"""


def main():
    items = _parse_page(FIXTURE_HTML)
    assert len(items) == 1, items
    item = items[0]
    assert item["imovel_ref"] == "FH2569", item
    assert item["crm_disponibilidade"] == "Por validar", item
    assert item["ego_id"] == 30117399, item

    items_fracao = _parse_page(FIXTURE_HTML_FRACAO)
    assert len(items_fracao) == 1, items_fracao
    item_fracao = items_fracao[0]
    assert item_fracao["imovel_ref"] == "FH2283DN", item_fracao
    assert item_fracao["crm_disponibilidade"] == "Disponível", item_fracao
    assert item_fracao["ego_id"] == 24265052, item_fracao

    assert _parse_page("<div>sem imoveis</div>") == []

    detail = _parse_detail(FIXTURE_DETAIL_HTML, ego_id=30117399)
    assert detail["imovel_ref"] == "FH2569", detail
    assert detail["titulo"] == "Apartamento T3", detail
    assert detail["freguesia"] == "São Pedro", detail
    assert detail["concelho"] == "Figueira da Foz", detail
    assert detail["venda_preco"] == 215000.0, detail
    assert detail["disponibilidade"] == "Por validar", detail
    assert detail["estado"] == "Usado", detail
    assert detail["quartos"] == 3, detail
    assert detail["casas_banho"] == 2, detail
    assert detail["area_util"] == 113.0, detail
    assert detail["area_bruta"] == 166.0, detail
    # descrição real (não a das "Características", que também usa .listItemDescription)
    assert detail["descricao"] == "E se a sua próxima casa estivesse a poucos minutos do mar?", detail
    assert len(detail["fotos"]) == 2, detail
    assert detail["foto_principal"] == detail["fotos"][0], detail
    assert detail["ego_id"] == 30117399, detail
    assert detail["fonte"] == "egorealestate", detail

    assert _parse_detail("<div>sem imovel</div>", ego_id=1) is None

    print("OK — parsing do backoffice eGO confirmado contra fixtures reais.")


if __name__ == "__main__":
    main()
