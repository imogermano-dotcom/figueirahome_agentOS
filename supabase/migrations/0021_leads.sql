-- ════════════════════════════════════════════════
-- Migration 0021 — Tabela `leads` (projecto UNIFICADO, supabase_imoveis)
-- ════════════════════════════════════════════════
-- Leads NÃO qualificadas, de qualquer origem. Nasce a servir o fluxo Meta Lead
-- Ads (formulário de venda), mas o esquema é genérico de propósito: é para aqui
-- que `agente_leads` e `leads_angariacao` vão convergir mais tarde.
--
-- O ciclo de vida é: entra `nova` -> o n8n manda o template e marca `contactada`
-- -> o A1 conversa e qualifica -> `qualificada`, e daí o corretor passa ao eGO.
--
-- NÃO escrever em `contactos` a partir daqui. `contactos` é espelho do eGO
-- (upsert por `ego_link`, que só o eGO atribui) e um insert nosso fica órfão ou
-- colide com a PK real `(nome, criado_em)` — ver `docs/decisoes.md`. A passagem
-- ao eGO é manual nesta fase.

create table if not exists leads (
  id              uuid primary key default gen_random_uuid(),

  -- Quem trata a lead depende disto: 'compra' vai para o A1, 'angariacao'
  -- continua com a consultora ao telefone (o A4 está adiado).
  tipo            text not null default 'compra',
  estado          text not null default 'nova',   -- nova | contactada | qualificada | sem_interesse | perdida

  -- Contacto directo na própria linha, de propósito: `leads_angariacao` depende
  -- de um join a `contactos` por (nome, data) que resolve 74/79 mas parte-se
  -- assim que dois leads com o mesmo nome cheguem no mesmo dia.
  nome            text,
  telefone        text,                            -- normalizado a 9 dígitos (guards.normalizar_telefone)
  email           text,

  -- Origem Meta. `meta_lead_id` unique dá idempotência ao Make: reenviar o
  -- mesmo lead não cria linha nova.
  meta_lead_id    text unique,
  meta_form_name  text,
  meta_created_at timestamptz,

  imovel_ref      text,                            -- sem FK: a lead pode citar um imóvel que ainda não sincronizou
  ficha           jsonb not null default '{}'::jsonb,  -- respostas do formulário + notas de quem trabalhou a lead

  responsavel     text,
  notas           text,

  -- Ligações criadas quando a conversa é semeada (api/leads_meta.py).
  cliente_id      uuid references agente_clientes(id) on delete set null,
  conversa_id     uuid references agente_conversas(id) on delete set null,

  qualificada_em  timestamptz,
  criado_em       timestamptz not null default now(),
  atualizado_em   timestamptz not null default now()
);

-- O webhook do WhatsApp procura a lead pelo telefone a cada mensagem que chega
-- sem conversa viva; sem este índice é full scan no caminho quente.
create index if not exists idx_leads_telefone on leads(telefone);
create index if not exists idx_leads_estado on leads(estado);
create index if not exists idx_leads_tipo on leads(tipo);

alter table leads enable row level security;

-- Backend usa service_role (bypass). Esta política é para o painel autenticado.
-- `anon` fica bloqueado: `leads` tem nome, telefone e email de pessoas reais.
drop policy if exists "auth_full_access" on leads;
create policy "auth_full_access" on leads
  for all to authenticated using (true) with check (true);

-- VERIFICAÇÃO (executar após aplicar):
-- select column_name, data_type from information_schema.columns
--   where table_name = 'leads' order by ordinal_position;
-- select indexname from pg_indexes where tablename = 'leads';
