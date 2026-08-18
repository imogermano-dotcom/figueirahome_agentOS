-- ════════════════════════════════════════════════
-- Migration 0029 — `origem` em leads
-- ════════════════════════════════════════════════
-- `leads` passa a ser a tabela única de leads não qualificadas, como o `0021`
-- previa ("é para aqui que `agente_leads` e `leads_angariacao` vão convergir").
-- `agente_leads` deixa de ser escrita nesta fase; fica de pé, vazia de uso, e
-- cai numa migration à parte depois de isto correr uns dias em produção.
--
-- Sem `origem` a proveniência só se inferia de `meta_lead_id is not null`, o que
-- separa a Meta de tudo o resto mas não distingue o assistente da voz nem da
-- landing page — e é essa distinção que a página de Leads precisa de filtrar.
--
-- `tipo` continua a ser o INTERESSE ('compra' | 'angariacao'), não a origem.
-- São eixos diferentes: uma lead de compra pode vir da Meta ou do WhatsApp.

alter table leads add column origem text not null default 'manual';

comment on column leads.origem is
  'De onde veio a lead: meta | assistente | voz | landing | manual. Eixo distinto de `tipo`, que é o interesse.';

create index if not exists idx_leads_origem on leads(origem);

-- As 119 existentes são todas do Meta Lead Ads.
update leads set origem = 'meta' where meta_lead_id is not null;
