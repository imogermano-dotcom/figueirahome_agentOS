-- ════════════════════════════════════════════════
-- Migration 0013 — imoveis: coluna destaque (projecto SECUNDÁRIO, supabase_imoveis)
-- ════════════════════════════════════════════════
-- A Web API do eGO devolve `Tags` (array de objectos com ID/Name), incl. a
-- tag de sistema {"ID": 1, "Name": "Destaque"} — confirmado ao vivo em
-- 2026-07-30 (1 de 55 imóveis actuais tinha, FH2450). Até agora ignorada
-- por `_map_property()`.

alter table imoveis add column if not exists destaque boolean default false;
