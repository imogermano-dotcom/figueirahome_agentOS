-- ════════════════════════════════════════════════
-- Migration 0041 — trigger de origem para leads da Meta
-- ════════════════════════════════════════════════
-- Achado 23/09: `leads.origem` está correcto ('meta') só até 17/08. A partir
-- de 18/08 (a data exacta em que a migration 0029 correu) toda a lead nova
-- da Meta nasce com 'manual' — o DEFAULT da coluna, nunca corrigido.
--
-- Causa: a `0029` fez um UPDATE de uma vez só (`where meta_lead_id is not
-- null`), que acertou as 119 leads que existiam nesse momento. Mas o Make
-- escreve `leads` directamente por PostgREST (`docs/n8n/README.md`) e nunca
-- manda `origem` no corpo do insert — cada lead nova desde então cai
-- silenciosamente no DEFAULT `'manual'`, mesmo trazendo `meta_lead_id`
-- preenchido. Confirmado: 187 de 196 leads com `meta_lead_id` desde 18/08
-- estão marcadas `'manual'` no painel (as 9 restantes vieram por outro
-- caminho, já correctas).
--
-- Mesmo padrão do `tgr_normaliza_aceita_whatsapp` (`0031`) — um escritor
-- externo (Make) não pode ser corrigido do nosso lado, a regra vive na base.
-- `origem='assistente'` (escrita por `tools.py`, nunca traz `meta_lead_id`)
-- fica intacta: a condição só dispara quando `meta_lead_id is not null`.

create or replace function public.fn_normaliza_origem_leads()
returns trigger
language plpgsql
as $$
begin
  if new.meta_lead_id is not null then
    new.origem := 'meta';
  end if;

  return new;
end;
$$;

drop trigger if exists tgr_normaliza_origem_leads on public.leads;

create trigger tgr_normaliza_origem_leads
  before insert or update on public.leads
  for each row
  execute function public.fn_normaliza_origem_leads();

-- Backfill das leads já afectadas (18/08 em diante) — o trigger só apanha
-- escritas futuras.
update leads set origem = 'meta' where meta_lead_id is not null and origem <> 'meta';

-- VERIFICAÇÃO
-- select origem, count(*) from leads where meta_lead_id is not null group by 1;
-- -- só deve aparecer 'meta'
