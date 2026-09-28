# Resumo — `telefone`/`telemovel` em `contactos` unificados (28/09)

Achado ao analisar contactos sem email: `contactos` tem 2 colunas para o
mesmo número, escritas de forma inconsistente por 3 pipelines —
- scraper (`ego_link`): só `telemovel`.
- `_espelhar_em_contactos` (conversas A1/A3/A4): só `telefone`.
- RPCs `lead_meta_*` (leads Meta): as duas.

## Bug real encontrado

`guards.contacto_meta_aberto` (routing de resposta a template Meta) só
procurava por `telefone` — um contacto só com `telemovel` (scraper) ficaria
invisível. Confirmado em produção que **ainda não tinha acontecido** (RPCs
sempre preenchem os dois ao ligar um contacto existente), mas era a mesma
suposição frágil que já rebentou a 25/09 (Sandra Pinto, `criado_em`).

## Fix

- `contacto_meta_aberto`: passa a procurar por `telefone` OU `telemovel`
  (`.or_()`, mesmo padrão já usado noutros sítios do ficheiro).
- Scraper (`mapping_todas_colunas.py`, `classify()`): grava `telefone` igual
  a `telemovel` sempre que houver valor.
- `_espelhar_em_contactos` (`guards.py`): grava `telemovel` igual a
  `telefone`, no insert e no update.

Não faz backfill das linhas antigas só numa coluna — só corrige gravações
daqui para a frente. Um backfill retroactivo fica fora de âmbito (mesma
lógica dos duplicados por resolver, `contactos-unificado-assistentes-plano.md`).

## Testes

`test_guards.py::test_contacto_meta_aberto_filtra_por_tipo_e_template`,
`test_espelhar_contactos.py` (2 testes existentes ganharam assert de
`telemovel`), `mapping_todas_colunas.py::demo()` — novo assert. Suite: 281
(sem alteração de contagem, testes existentes estendidos).
