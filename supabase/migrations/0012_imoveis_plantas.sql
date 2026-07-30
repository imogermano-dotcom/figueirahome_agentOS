-- ════════════════════════════════════════════════
-- Migration 0012 — imoveis: coluna plantas (projecto SECUNDÁRIO, supabase_imoveis)
-- ════════════════════════════════════════════════
-- A Web API do eGO devolve `BluePrints` (plantas) no mesmo formato de
-- `Images` (array de objectos com Thumbnail/Original/várias resoluções),
-- confirmado ao vivo em 2026-07-30 — até agora ignorado por
-- `_map_property()`. Mesmo padrão de `fotos`: array de URLs (Thumbnail).

alter table imoveis add column if not exists plantas jsonb default '[]'::jsonb;
