-- ════════════════════════════════════════════════
-- Migration 0007 — histórico de execuções de sync (eGO API + CRM)
-- ════════════════════════════════════════════════
-- Guarda 1 linha por execução de sync_egorealestate(): quando correu, o
-- resumo (contagens) e o detalhe de cada alteração feita (imovel_ref +
-- campo + valor anterior/novo), para o botão "Sincronizar agora" e o cron
-- diário deixarem rasto visível em /imoveis mesmo quando ninguém está a
-- ver a resposta do POST (o cron corre sem UI).

create table agente_sync_log (
  id            uuid primary key default uuid_generate_v4(),
  tipo          text not null default 'egorealestate',
  executado_em  timestamptz default now(),
  resumo        jsonb,   -- {criados, atualizados, erros, nao_publicados, corrigidos}
  detalhes      jsonb    -- [{imovel_ref, campo, de, para}, ...]
);

create index idx_agente_sync_log_tipo_data on agente_sync_log(tipo, executado_em desc);

alter table agente_sync_log enable row level security;
create policy auth_full_access on agente_sync_log for all to authenticated using (true) with check (true);
