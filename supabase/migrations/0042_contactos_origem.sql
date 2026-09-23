-- ════════════════════════════════════════════════
-- Migration 0042 — `origem` em `contactos`
-- ════════════════════════════════════════════════
-- Mesmo problema que a `0041` encontrou em `leads`: `contactos` não tinha
-- coluna nenhuma para dizer de onde veio um contacto — só se inferia por
-- `meta_lead_id is not null` (Meta) ou `agente is not null` (assistentes,
-- desde a 21/09). Aditivo, não mexe em `tipos`/`tipo_contacto` (esses ficam
-- por decidir com o Miguel, ver docs/decisoes.md).
--
-- Trigger em vez de confiar em cada escritor lembrar-se de preencher —
-- lição directa da `0041`: a RPC `lead_meta_compra` nunca mandou `origem`
-- em `leads`, e ficou 5 semanas em silêncio a gravar errado. `contactos`
-- tem ainda mais escritores (scraper, pipeline do Miguel, 3 RPCs `lead_meta_*`,
-- os assistentes) — mais sítios para o mesmo esquecimento acontecer.
--
-- Prioridade quando mais do que um sinal está presente (não deviam
-- coexistir na prática, mas a ordem importa se algum dia coexistirem):
-- meta_lead_id > agente > ego_link. Sem nenhum dos três, fica `NULL` —
-- não se inventa "scraper" vs "pipeline do Miguel" só por ausência de
-- ego_link, os dois escritores externos partilham esse padrão e não há
-- como distinguir sem falar com ele (mesma cautela da invariante já
-- registada em CLAUDE.md).

alter table contactos add column origem text;

comment on column contactos.origem is
  'De onde veio o contacto: meta | assistente | scraper. NULL = escritor externo sem ego_link (scraper antigo ou pipeline do Miguel, indistinguíveis) ou anterior a esta coluna.';

create or replace function public.fn_normaliza_origem_contactos()
returns trigger
language plpgsql
as $$
begin
  if new.meta_lead_id is not null then
    new.origem := 'meta';
  elsif new.agente is not null then
    new.origem := 'assistente';
  elsif new.ego_link is not null then
    new.origem := 'scraper';
  end if;

  return new;
end;
$$;

drop trigger if exists tgr_normaliza_origem_contactos on public.contactos;

create trigger tgr_normaliza_origem_contactos
  before insert or update on public.contactos
  for each row
  execute function public.fn_normaliza_origem_contactos();

-- Backfill do que já existe e já tem sinal.
update contactos set origem = 'meta' where meta_lead_id is not null and (origem is distinct from 'meta');
update contactos set origem = 'assistente' where agente is not null and (origem is distinct from 'assistente');
update contactos set origem = 'scraper' where ego_link is not null and origem is null;

-- VERIFICAÇÃO
-- select origem, count(*) from contactos group by 1 order by 2 desc;
