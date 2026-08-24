-- ════════════════════════════════════════════════
-- Migration 0031 — trigger de consentimento em `leads` (projecto UNIFICADO)
-- ════════════════════════════════════════════════
-- **NÃO É UMA ALTERAÇÃO. Isto já está em produção desde 2026-08-20 11:34:07.**
--
-- Foi aplicado pela interface do Supabase, fora deste repositório, e por isso não
-- estava em lado nenhum do código. Encontrado a 2026-08-24 ao ligar o CLI ao
-- projecto de dados: `supabase_migrations.schema_migrations` tinha-o registado
-- como `normaliza_aceita_whatsapp_leads`.
--
-- O ficheiro é cópia literal do que lá está, e é todo idempotente
-- (`create or replace` + `drop trigger if exists`). Corrê-lo não muda nada; serve
-- para a regra ser legível a quem lê o repositório.
--
-- ── PORQUE É QUE ISTO IMPORTA ───────────────────────────────────────────────
--
-- `ficha.aceita_whatsapp` é o **gate do consentimento de WhatsApp**: decide quem
-- recebe template (fluxos n8n 01, 02 e 03) e o distintivo no painel. Havia três
-- allowlists documentadas como fronteiras de segurança; esta é a quarta, e a
-- única que não se vê a ler o código Python.
--
-- Resolve também um mistério que o `docs/n8n/README.md` dava como impossível de
-- datar. O valor passou de `sim,_aceito_receber_informações_pelo_whatsapp` para
-- `SIM` "por volta de 20/08" e o histórico foi normalizado junto, portanto
-- parecia que a base não guardava memória do momento. Guardava: foi este
-- trigger, e a data é exacta.
--
-- **Não é um UPDATE de uma vez — é uma regra viva.** Normaliza a cada escrita,
-- portanto as leads novas do Make entram já em forma. A 2026-08-24 a tabela
-- tinha exactamente dois valores: `SIM` (194) e `NÃO` (29).
--
-- ── A REGRA ─────────────────────────────────────────────────────────────────
--
-- Lista branca por prefixo, igual à do `startsWith('sim')` do n8n e do painel:
-- só `sim*` (e os sinónimos curtos) dá `SIM`; **tudo o resto dá `NÃO`**. Chave
-- ausente ou valor vazio ficam intactos — nunca inventa consentimento onde não
-- houve resposta.
--
-- ── O QUE NÃO DISPARA ───────────────────────────────────────────────────────
--
-- `update OF ficha`: só corre quando `ficha` está na lista de colunas do UPDATE.
-- `guards.encerrar_lead_do_telefone` (estado, notas) e o fluxo 03 (estado,
-- follow_up_em, template_enviado) não lhe tocam.
--
-- ⚠️ Quem mexer nesta função está a mexer num gate de consentimento. Alargar a
-- condição do `case` faz sair template a quem disse que não.

-- Normaliza ficha->>'aceita_whatsapp' para 'SIM' / 'NÃO'.
-- A Meta envia o texto integral da opção do formulário, que varia por campanha
-- (ex.: 'sim,_aceito_receber_informações_pelo_whatsapp'). Este trigger torna o
-- valor estável independentemente do label usado em cada form.

create or replace function public.fn_normaliza_aceita_whatsapp()
returns trigger
language plpgsql
as $$
declare
  v text;
begin
  if new.ficha is null or not (new.ficha ? 'aceita_whatsapp') then
    return new;
  end if;

  v := lower(trim(new.ficha->>'aceita_whatsapp'));

  if v is null or v = '' then
    return new;
  end if;

  new.ficha := jsonb_set(
    new.ficha,
    '{aceita_whatsapp}',
    to_jsonb(case when v like 'sim%' or v in ('s','yes','y','true','1') then 'SIM' else 'NÃO' end)
  );

  return new;
end;
$$;

drop trigger if exists tgr_normaliza_aceita_whatsapp on public.leads;

create trigger tgr_normaliza_aceita_whatsapp
  before insert or update of ficha on public.leads
  for each row
  execute function public.fn_normaliza_aceita_whatsapp();

-- VERIFICAÇÃO
-- select tgname, tgenabled from pg_trigger
--  where tgrelid = 'public.leads'::regclass and not tgisinternal;
--
-- Só pode haver dois valores (e o trigger é o que o garante):
-- select ficha->>'aceita_whatsapp' as v, count(*) from leads group by 1 order by 2 desc;
