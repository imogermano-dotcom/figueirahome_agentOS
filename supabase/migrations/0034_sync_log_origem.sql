-- Distingue no agente_sync_log se a execução veio do cron (GitHub Actions,
-- X-Sync-Secret) ou de um clique manual no painel (JWT via require_sync_access).
-- Sem isto não se sabia se um FH2571 preso 1 dia era falta de cron ou uso do botão.
alter table agente_sync_log add column if not exists origem text;
