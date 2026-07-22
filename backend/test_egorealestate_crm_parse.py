"""Teste isolado do parsing de `egorealestate_crm._parse_page` contra
fragmentos HTML reais capturados do backoffice eGO (sessão 2026-07-21) —
sem rede, sem credenciais."""
from app.integrations.egorealestate_crm import _parse_page

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

    print("OK — parsing do backoffice eGO confirmado contra fixtures reais.")


if __name__ == "__main__":
    main()
