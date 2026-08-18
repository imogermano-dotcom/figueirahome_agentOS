-- ════════════════════════════════════════════════
-- Migration 0028 — visita virtual em imoveis
-- ════════════════════════════════════════════════
-- URL da visita virtual externa do imóvel ("Visitas virtuais externas" no
-- backoffice do eGO). A 2026-08-18: 7 dos 56 publicados, todas Matterport,
-- todas exactamente uma por imóvel — daí ser uma coluna de texto e não um
-- array. `FH2318A` e `FH2318B` partilham URL (mesmo edifício, duas fracções).
--
-- O dado vem de `GET /v1/Properties/{ID}` (campo `ExternalVirtualTours`), não
-- da listagem: a listagem devolve 82 campos e o detalhe 104. Ver a docstring de
-- `app/integrations/egorealestate.py`.
--
-- Escrita pelo `_map_property` (upsert em lote), como o `video_url`, e não pelo
-- `_map_extras` — este filtra os nulos e por isso nunca conseguiria apagar um
-- link quando o imóvel deixasse de ter visita virtual.

alter table imoveis add column visita_virtual_url text;

comment on column imoveis.visita_virtual_url is
  'URL da visita virtual externa (eGO: ExternalVirtualTours[0].Url). Só vem do endpoint de detalhe da Web API.';
