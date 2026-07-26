-- ════════════════════════════════════════════════
-- Migration 0010 — teste_imoveis: 2 colunas em falta
-- ════════════════════════════════════════════════
-- `imoveis` tem `panoramic_url`/`video_url` (adicionadas directamente em
-- produção, sem migration registada — não constavam em docs/database-schema.md
-- nem na migration 0009 quando esta foi escrita). `teste_imoveis` devia ter
-- os mesmos nomes de coluna que `imoveis` (pedido original) — a acrescentar.

alter table teste_imoveis add column panoramic_url text;
alter table teste_imoveis add column video_url text;
