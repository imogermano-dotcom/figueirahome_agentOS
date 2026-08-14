"""Onde é que os conjuntos de referências divergem: CRM eGO vs Web API vs Supabase.

Só leitura — não escreve em lado nenhum, não cria tarefas, não corrige nada.
Responde a uma pergunta e só a essa: **que referências existem de um lado e não
do outro**. Divergências de valor (preço, tipologia, campos vazios) são outro
diagnóstico.

    cd backend && python scripts/diagnostico_refs.py

Três fontes, com visibilidades diferentes de propósito:

* **CRM backoffice** — visibilidade total, mas `fetch_all` só percorre os quatro
  estados com referência real (`_STATUS_CODES`: Disponível, Reservado, Arrendado,
  Por validar). Um imóvel Vendido ou Retirado **não aparece** — ausência aqui não
  é prova de que não exista.
* **Web API pública** — só os publicados. Demora ~10 min a expor um imóvel novo.
* **Supabase** — tudo, incluindo as linhas `fonte='manual'`/`csv` de origem
  anterior a este pipeline, que nenhuma das outras duas fontes conhece.
"""

import asyncio
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.supabase_client import get_supabase  # noqa: E402
from app.integrations import egorealestate, egorealestate_crm  # noqa: E402
from app.config import settings  # noqa: E402

_PAGINA = 1000  # limite por omissão do PostgREST; sem paginar, o conjunto sai truncado


def _supabase_imoveis() -> list[dict]:
    """Tabela `imoveis` inteira. Pagina — são ~3500 linhas contra um tecto de 1000."""
    sb = get_supabase()
    linhas: list[dict] = []
    inicio = 0
    while True:
        resp = (
            sb.table("imoveis")
            .select("imovel_ref,fonte,disponibilidade,ego_id,publicado,disponivel_na_api")
            .range(inicio, inicio + _PAGINA - 1)
            .execute()
        )
        linhas.extend(resp.data)
        if len(resp.data) < _PAGINA:
            return linhas
        inicio += _PAGINA


async def _web_api_refs() -> list[dict]:
    """Todas as páginas da Web API pública."""
    props: list[dict] = []
    pagina = 1
    while True:
        lote, total = await egorealestate.get_properties_page(pagina)
        props.extend(lote)
        if not lote or len(props) >= total:
            return props
        pagina += 1


async def _crm_refs() -> list[dict]:
    if not settings.egorealestate_crm_username or not settings.egorealestate_crm_password:
        print("!! Credenciais do CRM ausentes — secção do CRM saltada.\n")
        return []
    async with egorealestate_crm.authenticated_client() as client:
        await egorealestate_crm._login(client)
        return await egorealestate_crm.fetch_all(client)


_SAIDA = Path(__file__).resolve().parent / "output" / "diagnostico_refs.txt"
_relatorio: list[str] = []


def _secao(titulo: str, refs: set[str], nota: str = "") -> None:
    """Resumo no ecrã (20 primeiras), lista completa no ficheiro."""
    print(f"\n{titulo}: {len(refs)}")
    if nota:
        print(f"  ({nota})")
    for ref in sorted(refs)[:20]:
        print(f"    {ref}")
    if len(refs) > 20:
        print(f"    … mais {len(refs) - 20} — lista completa em {_SAIDA.name}")

    _relatorio.append(f"\n{titulo}: {len(refs)}\n  ({nota})")
    _relatorio.extend(f"    {ref}" for ref in sorted(refs))


async def main() -> None:
    print("A ler as três fontes…")
    crm, api, locais = await _crm_refs(), await _web_api_refs(), _supabase_imoveis()

    refs_crm = {c["imovel_ref"] for c in crm if c.get("imovel_ref")}
    refs_api = {p.get("Reference") for p in api if p.get("Reference")}
    refs_sb = {r["imovel_ref"] for r in locais if r.get("imovel_ref")}
    refs_sb_ego = {r["imovel_ref"] for r in locais if r.get("fonte") == "egorealestate"}

    print("\n" + "═" * 62)
    print(f"CRM (4 estados)     {len(refs_crm):>6}")
    print(f"Web API (publicados){len(refs_api):>6}")
    print(f"Supabase (total)    {len(refs_sb):>6}")
    print(f"  dos quais fonte='egorealestate': {len(refs_sb_ego)}")
    print("  por fonte:", dict(Counter(r.get("fonte") for r in locais)))
    print("═" * 62)

    # Comparar só por `imovel_ref` sobrestima as faltas: as 4001 linhas `manual`
    # são anteriores a este pipeline e podem ter o mesmo imóvel com outra
    # convenção de referência. O `ego_id` é a chave estável dos dois lados.
    ego_ids_sb = {r["ego_id"] for r in locais if r.get("ego_id")}
    em_falta = refs_crm - refs_sb
    crm_por_ref = {c["imovel_ref"]: c for c in crm}
    so_ref_diferente = {
        ref for ref in em_falta
        if (crm_por_ref[ref].get("ego_id") or -1) in ego_ids_sb
    }

    _secao(
        "▸ NO CRM, AUSENTES DO SUPABASE (ref e ego_id)",
        em_falta - so_ref_diferente,
        "faltas reais: nem a referência nem o ego_id existem cá",
    )
    _secao(
        "▸ NO CRM, EM FALTA SÓ PELA REFERÊNCIA",
        so_ref_diferente,
        "o ego_id existe no Supabase — mesma linha, `imovel_ref` diferente",
    )

    # Decisivo: `imoveis_sync.py:442` só cria linha para o estado "Disponível".
    # Se as faltas forem quase todas noutros estados, a causa é essa regra e não
    # o sync não ter corrido.
    print("\n  estado no CRM das faltas reais:")
    for estado, n in Counter(
        crm_por_ref[r]["crm_disponibilidade"] for r in (em_falta - so_ref_diferente)
    ).most_common():
        print(f"    {estado:<14} {n}")
    print("  sem ego_id (o Caso 1 também os salta):",
          sum(1 for r in (em_falta - so_ref_diferente) if not crm_por_ref[r].get("ego_id")))
    _secao(
        "▸ NA WEB API, AUSENTES DO SUPABASE",
        refs_api - refs_sb,
        "publicados que o sync não apanhou — o sync diário devia ter criado estes",
    )
    _secao(
        "▸ MARCADOS 'egorealestate' NO SUPABASE, AUSENTES DO CRM",
        refs_sb_ego - refs_crm,
        "vieram do eGO mas o CRM já não os lista — Vendido/Retirado, ou ref mudada",
    )
    _secao(
        "▸ PUBLICADOS NO SUPABASE, AUSENTES DA WEB API",
        {r["imovel_ref"] for r in locais if r.get("publicado")} - refs_api,
        "o painel mostra-os como no site, o eGO não os devolve",
    )

    dup = [ref for ref, n in Counter(c["imovel_ref"] for c in crm).items() if n > 1]
    if dup:
        print(f"\n▸ REFS DUPLICADAS NO PRÓPRIO CRM: {len(dup)}")
        print("  (o sync desempata pela data de alteração — ver docs/decisoes.md)")
        for ref in sorted(dup)[:20]:
            print(f"    {ref}")

    _SAIDA.parent.mkdir(exist_ok=True)
    _SAIDA.write_text("\n".join(_relatorio), encoding="utf-8")
    print(f"\nListas completas: {_SAIDA}")


if __name__ == "__main__":
    asyncio.run(main())
