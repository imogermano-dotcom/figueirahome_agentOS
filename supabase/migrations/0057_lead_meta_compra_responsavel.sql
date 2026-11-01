-- ════════════════════════════════════════════════
-- Migration 0057 — `lead_meta_compra`: o responsável da lead é o angariador do imóvel do anúncio
-- ════════════════════════════════════════════════
-- Pedido #17 (etapa de 01/11, docs/fases/responsavel-leads-meta-plano.md). Hoje `leads.responsavel` está vazio em 430 de 430
-- leads Meta e `contactos.responsavel` em 303 de 325. A regra: numa lead Meta de compra, o responsável é o angariador do imóvel
-- (`imoveis.angariador`, o nome tal como o eGO o escreve).
--
-- Decisão E1 (01/11): `leads.responsavel` leva sempre o angariador (a linha é nova); `contactos.responsavel` só onde está vazio
-- (um contacto que já existia no eGO mantém a consultora que tem).
--
-- A função é a de produção lida com `pg_get_functiondef` a 01/11 (igual à da `0051`): só mudam as linhas marcadas «0057».
-- Sem imóvel em `imoveis` ou sem angariador, `v_resp` fica nulo e nada se grava (uma rede no cron preenche depois).
--
-- Corre por partes (1 a 4), vendo o resultado de cada uma. As partes 2 e 3 só preenchem vazios.

-- 0. Só leitura: triggers que um UPDATE em massa de `leads` e `contactos` vai disparar.
select c.relname, t.tgname, t.tgenabled, pg_get_triggerdef(t.oid) as definicao
  from pg_trigger t join pg_class c on c.oid = t.tgrelid
 where c.relname in ('leads', 'contactos') and not t.tgisinternal
 order by c.relname, t.tgname;

-- 1. A função.
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
    v_resp text;  -- 0057
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

    -- 0057: angariador do imóvel do anúncio (ref exata; senão a ref curta, p.ex. «FH2584_V1» → «FH2584»).
    select angariador into v_resp from imoveis
     where imovel_ref in (p_imovel_ref, upper(substring(coalesce(p_imovel_ref, '') from '^[A-Za-z]*[0-9]+')))
       and coalesce(angariador, '') <> ''
     order by (imovel_ref = p_imovel_ref) desc
     limit 1;

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
      nome, telefone, email, imovel_ref, ficha, responsavel  -- 0057
    ) values (
      p_meta_lead_id, p_meta_form_name, v_meta_ts,
      p_nome, p_telefone, p_email, p_imovel_ref,
      jsonb_build_object('aceita_whatsapp', p_aceita_whatsapp), v_resp  -- 0057
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
        end,
        responsavel = case when (responsavel is null or responsavel = '') and v_resp is not null then v_resp else responsavel end  -- 0057
      where nome = v_contact_nome and criado_em = v_contact_criado;
    else
      insert into contactos (
        nome, criado_em, telefone, telemovel, email,
        whatsapp_permissao, whatsapp_data, tipos, tipo_contacto,
        estado, meta_lead_id, meta_form_name, meta_created_at, agente,
        ad_id, ad_name, adset_id, adset_name, responsavel  -- 0057
      ) values (
        p_nome, current_date, p_telefone, p_telefone, p_email,
        v_whatsapp_optin, case when v_whatsapp_optin then current_date else null end,
        array['Lead Meta']::text[], array['comprador']::text[],
        'nova', p_meta_lead_id, p_meta_form_name, v_meta_ts, 'a1_vendedor',
        p_ad_id, p_ad_name, p_adset_id, p_adset_name, v_resp  -- 0057
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

-- 2. Backfill de `leads`: só as Meta sem responsável (esperado: 430).
update leads l
   set responsavel = i.angariador
  from imoveis i
 where l.meta_lead_id is not null
   and coalesce(l.responsavel, '') = ''
   and i.imovel_ref = l.imovel_ref
   and coalesce(i.angariador, '') <> '';

-- 3. Backfill de `contactos`: só compradores Meta sem responsável, pelo imóvel da lead do mesmo `meta_lead_id`.
--    Quem já tem responsável (vindo do eGO) não se toca.
update contactos c
   set responsavel = i.angariador
  from leads l
  join imoveis i on i.imovel_ref = l.imovel_ref
 where c.meta_lead_id = l.meta_lead_id
   and 'comprador' = any(coalesce(c.tipo_contacto, '{}'::text[]))
   and coalesce(c.responsavel, '') = ''
   and coalesce(i.angariador, '') <> '';

-- 4. Verificação. Esperado: leads Meta sem responsável ≈ 0; compradores Meta com responsável ≈ 114+ de 119.
select count(*) filter (where meta_lead_id is not null) as leads_meta,
       count(*) filter (where meta_lead_id is not null and coalesce(responsavel, '') <> '') as com_responsavel
  from leads;
select count(*) as compradores_meta,
       count(*) filter (where coalesce(responsavel, '') <> '') as com_responsavel
  from public.contactos
 where meta_lead_id is not null and 'comprador' = any(coalesce(tipo_contacto, '{}'::text[]));
