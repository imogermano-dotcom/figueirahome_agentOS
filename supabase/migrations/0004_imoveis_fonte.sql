-- ════════════════════════════════════════════════
-- Migration 0004 — imoveis: coluna fonte (projecto SECUNDÁRIO, supabase_imoveis)
-- ════════════════════════════════════════════════
-- A tabela `imoveis` já existe com dados reais (eGO export) e já tem
-- ego_id, ego_atualizado_em, fotos, foto_principal, portais, etc.
-- O único gap real é uma coluna para distinguir a origem de cada linha
-- (eGO API, scraper, entrada manual) — usada pelo pipeline de sync (Fase B/C).
--
-- Aditiva apenas. Não tocar nas colunas existentes.

alter table imoveis add column if not exists fonte text not null default 'manual';

-- Backfill: linhas com ego_id preenchido já vieram do eGO (import inicial).
update imoveis set fonte = 'egorealestate' where ego_id is not null and fonte = 'manual';

-- Dedup/upsert do sync eGO usa ego_id; imovel_ref é a chave de negócio usada
-- em todo o resto do sistema (CSV import, WhatsApp, broker) — ambas ficam
-- únicas para suportar upsert sem duplicados.
-- Índice plano (não parcial): Postgres já permite múltiplos NULL num unique
-- index normal, e um índice parcial não é elegível como alvo de ON CONFLICT
-- a menos que o INSERT declare o mesmo WHERE — o upsert do Supabase não o faz.
create unique index if not exists idx_imoveis_ego_id on imoveis(ego_id);
create unique index if not exists idx_imoveis_imovel_ref on imoveis(imovel_ref) where imovel_ref is not null;
create index if not exists idx_imoveis_fonte on imoveis(fonte);
create index if not exists idx_imoveis_disponibilidade on imoveis(disponibilidade);
