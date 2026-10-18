-- ════════════════════════════════════════════════
-- Migration 0051 — `lead_meta_compra`: o consentimento de WhatsApp passa a seguir a resposta
-- ════════════════════════════════════════════════
-- Achado a 18/10 (docs/fases/lead-compra-para-ego-plano.md, standby):
--
--   v_whatsapp_optin := (coalesce(p_aceita_whatsapp, '') <> '');
--
-- Qualquer resposta NÃO VAZIA contava como consentimento, incluindo «não». Resultado medido: das 12 leads de
-- compra que o RPC escreveu em `contactos` desde 13/10, as 4 que disseram «não» ficaram com
-- `whatsapp_permissao = true` (em `leads.ficha`, onde o trigger 0031 normaliza, ficaram certas: «NÃO»).
-- Não houve envio indevido (o fluxo 01 do n8n decide pela resposta crua e os follow-ups exigem
-- `template_enviado_em`), mas o dado estava errado para o painel e para qualquer leitura futura.
--
-- Regra nova = a do trigger 0031 e a do `startsWith('sim')` do n8n: `sim*` (e s/yes/y/true/1) é consentimento;
-- tudo o resto é recusa; vazio fica sem consentimento. Mais nada muda na função (corpo igual, linha a linha).
--
-- O que NÃO faz:
--   · não mexe na versão antiga da função (8 argumentos, sem anúncio): o n8n chama a de 12 e a outra está sem uso;
--   · não revoga consentimento já dado: se a pessoa já existe em `contactos` com `true` e agora responde «não»,
--     o valor fica como estava (comportamento original; revogar é decisão à parte).
--
-- A correção pontual das linhas já gravadas vai no fim e só toca nas que a `leads` diz «NÃO» e que nunca
-- receberam template.

create or replace function public.lead_meta_compra(
  p_nome text, p_telefone text, p_email text, p_aceita_whatsapp text, p_meta_lead_id text,
  p_meta_form_name text, p_meta_created_at text, p_imovel_ref text,
  p_ad_id text default null::text, p_ad_name text default null::text,
  p_adset_id text default null::text, p_adset_name text default null::text)
returns jsonb
language plpgsql
security definer
as $function$
  declare
    v_meta_ts timestamptz;
    v_lead_id uuid;
    v_tel_norm text;
    v_contact_nome text;
    v_contact_criado date;
    v_found boolean := false;
    v_whatsapp_optin boolean;
  begin
    if p_meta_created_at is not null and p_meta_created_at != '' then
      v_meta_ts := p_meta_created_at::timestamptz;
    else
      v_meta_ts := null;
    end if;

    -- Mesma regra do trigger 0031 (`fn_normaliza_aceita_whatsapp`): só `sim*` e os sinónimos curtos.
    v_whatsapp_optin := (
      lower(trim(coalesce(p_aceita_whatsapp, ''))) like 'sim%'
      or lower(trim(coalesce(p_aceita_whatsapp, ''))) in ('s', 'yes', 'y', 'true', '1')
    );

    if p_meta_lead_id is not null then
      select id into v_lead_id
      from leads
      where meta_lead_id = p_meta_lead_id;

      if v_lead_id is not null then
        return jsonb_build_object(
          'status', 'duplicate',
          'lead_id', v_lead_id,
          'message', 'Lead já importada anteriormente'
        );
      end if;
    end if;

    insert into leads (
      meta_lead_id, meta_form_name, meta_created_at,
      nome, telefone, email, imovel_ref, ficha
    ) values (
      p_meta_lead_id, p_meta_form_name, v_meta_ts,
      p_nome, p_telefone, p_email, p_imovel_ref,
      jsonb_build_object('aceita_whatsapp', p_aceita_whatsapp)
    )
    returning id into v_lead_id;

    v_tel_norm := normalize_phone(p_telefone);

    if v_tel_norm is not null then
      select nome, criado_em into v_contact_nome, v_contact_criado
      from contactos
      where normalize_phone(telefone) = v_tel_norm
         or normalize_phone(telemovel) = v_tel_norm
      limit 1;

      if v_contact_nome is not null then
        v_found := true;
      end if;
    end if;

    if not v_found and p_email is not null and p_email != '' then
      select nome, criado_em into v_contact_nome, v_contact_criado
      from contactos
      where lower(email) = lower(p_email)
      limit 1;

      if v_contact_nome is not null then
        v_found := true;
      end if;
    end if;

    if v_found then
      update contactos set
        telefone = case when (telefone is null or telefone = '') and p_telefone is not null then p_telefone else telefone end,
        telemovel = case when (telemovel is null or telemovel = '') and p_telefone is not null then p_telefone else telemovel end,
        email = case when (email is null or email = '') and p_email is not null then p_email else email end,
        whatsapp_permissao = case when v_whatsapp_optin then true else whatsapp_permissao end,
        whatsapp_data = case when v_whatsapp_optin then current_date else whatsapp_data end,
        meta_lead_id = p_meta_lead_id,
        meta_form_name = p_meta_form_name,
        meta_created_at = v_meta_ts,
        ad_id = p_ad_id,
        ad_name = p_ad_name,
        adset_id = p_adset_id,
        adset_name = p_adset_name,
        agente = 'a1_vendedor',
        tipo_contacto = case
          when 'comprador' = any(coalesce(tipo_contacto, '{}'::text[])) then tipo_contacto
          else array_append(coalesce(tipo_contacto, '{}'::text[]), 'comprador')
        end
      where nome = v_contact_nome and criado_em = v_contact_criado;
    else
      insert into contactos (
        nome, criado_em, telefone, telemovel, email,
        whatsapp_permissao, whatsapp_data, tipos, tipo_contacto,
        estado, meta_lead_id, meta_form_name, meta_created_at, agente,
        ad_id, ad_name, adset_id, adset_name
      ) values (
        p_nome, current_date, p_telefone, p_telefone, p_email,
        v_whatsapp_optin, case when v_whatsapp_optin then current_date else null end,
        array['Lead Meta']::text[], array['comprador']::text[],
        'nova', p_meta_lead_id, p_meta_form_name, v_meta_ts, 'a1_vendedor',
        p_ad_id, p_ad_name, p_adset_id, p_adset_name
      );
    end if;

    return jsonb_build_object(
      'status', 'ok',
      'action', 'created',
      'lead_id', v_lead_id
    );

  exception when others then
    return jsonb_build_object(
      'status', 'error',
      'message', sqlerrm
    );
  end;
  $function$;

notify pgrst, 'reload schema';

-- ── CORREÇÃO PONTUAL das linhas já gravadas ─────────────────────────────
-- Só as de compra cuja `leads` diz «NÃO» e que nunca receberam template (4 esperadas a 18/10).
update public.contactos c
   set whatsapp_permissao = false,
       whatsapp_data = null
 where c.template_enviado_em is null
   and c.whatsapp_permissao is true
   and 'comprador' = any(coalesce(c.tipo_contacto, '{}'::text[]))
   and c.meta_lead_id in (select l.meta_lead_id from public.leads l
                           where l.tipo = 'compra' and l.ficha->>'aceita_whatsapp' = 'NÃO');

-- ── VERIFICAÇÃO ──────────────────────────────────────────────────────────
-- Antes de correr, a mesma contagem mostra o que o UPDATE vai tocar:
--   select count(*) from public.contactos c
--    where c.template_enviado_em is null and c.whatsapp_permissao is true
--      and 'comprador' = any(coalesce(c.tipo_contacto,'{}'::text[]))
--      and c.meta_lead_id in (select l.meta_lead_id from public.leads l
--                              where l.tipo='compra' and l.ficha->>'aceita_whatsapp'='NÃO');   -- esperado: 4
-- Depois de correr, a regra nova (sem escrever nada):
--   select (lower(trim('não')) like 'sim%' or lower(trim('não')) in ('s','yes','y','true','1')) as nao,
--          (lower(trim('Sim, aceito')) like 'sim%') as sim;                                    -- false, true

-- Desfazer (volta ao comportamento antigo; repõe a linha `v_whatsapp_optin := (coalesce(p_aceita_whatsapp,'') <> '');`):
--   recriar a função com essa linha. As 4 linhas corrigidas: `update public.contactos set whatsapp_permissao=true
--   where meta_lead_id in (...)` só se for mesmo preciso.
