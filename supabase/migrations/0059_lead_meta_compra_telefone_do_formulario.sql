-- ════════════════════════════════════════════════
-- Migration 0059 — `lead_meta_compra`: o número do formulário fica sempre numa das duas colunas da ficha
-- ════════════════════════════════════════════════
-- Pedido #58, F1 (docs/fases/telefone-ficha-antiga-plano.md). Decisão de 06/11: só acrescentar, nunca substituir.
--
-- No ramo «ficha já existe» a função só preenchia `telefone`/`telemovel` quando estavam VAZIOS. Com as duas ocupadas por
-- outros números (ficha antiga achada pelo email), o número do formulário perdia-se. Agora, nesse caso, acrescenta-se ao
-- `telemovel` como o eGO guarda listas: `telemovel || ', ' || número`. Só se os 9 últimos dígitos do número não estiverem
-- já em nenhuma das duas colunas (robusto a listas e ao prefixo 00351) e se o número tiver 9+ dígitos.
-- Nada se apaga nem se substitui; email, nome e o resto ficam como na 0057.
--
-- Base: a função de produção lida com `pg_get_functiondef` a 09/11 (12 argumentos) — igual à da 0057; só mudam as
-- linhas marcadas «0059». REVERTER: voltar a correr a parte 1 da `0057_lead_meta_compra_responsavel.sql` (é a mesma função).
--
-- ⚠️ Em produção existe TAMBÉM uma sobrecarga antiga de 8 argumentos (sem `p_ad_*`, regra de opt-in `<> ''` da pré-0051).
-- Esta migration NÃO lhe toca; ver nota no fim.
--
-- Corre por partes (1 e 2).

-- 1. A função (12 argumentos).
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
    v_digitos text;  -- 0059: dígitos do número do formulário
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

    v_digitos := regexp_replace(coalesce(p_telefone, ''), '\D', '', 'g');  -- 0059

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
        telemovel = case
          when (telemovel is null or telemovel = '') and p_telefone is not null then p_telefone
          -- 0059: as duas colunas ocupadas por outros números → acrescenta à lista (nada se apaga)
          when length(v_digitos) >= 9
               and regexp_replace(coalesce(telefone, ''), '\D', '', 'g') not like '%' || right(v_digitos, 9) || '%'
               and regexp_replace(coalesce(telemovel, ''), '\D', '', 'g') not like '%' || right(v_digitos, 9) || '%'
            then telemovel || ', ' || p_telefone
          else telemovel
        end,
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

-- 2. Verificação com dados sintéticos. O bloco desfaz tudo (o `raise exception` final faz rollback): o resultado é a
--    MENSAGEM DE ERRO, que deve ser «OK 0059 …». Qualquer outra («FALHOU …») = não confiar na função.
do $$
declare
  r1 jsonb; r2 jsonb; v_tf text; v_tm text;
begin
  insert into public.contactos (nome, criado_em, telefone, telemovel, email, tipo_contacto)
  values ('ZZ Teste 0059', current_date, '912345678', '913456789', 'teste0059@example.com', array['comprador']::text[]);

  -- a) email igual, número novo, duas colunas ocupadas → acrescenta ao telemovel
  r1 := public.lead_meta_compra('ZZ Form', '961234567', 'teste0059@example.com', 'Sim', 'teste0059a', 'f', null, 'FH0000', null, null, null, null);
  select telefone, telemovel into v_tf, v_tm from public.contactos where nome = 'ZZ Teste 0059';
  if r1->>'status' <> 'ok' or v_tf <> '912345678' or v_tm <> '913456789, 961234567' then
    raise exception 'FALHOU a): % | % | %', r1, v_tf, v_tm;
  end if;

  -- b) mesma lead outra vez com o mesmo número (já na lista) → não duplica
  r2 := public.lead_meta_compra('ZZ Form', '961234567', 'teste0059@example.com', 'Sim', 'teste0059b', 'f', null, 'FH0000', null, null, null, null);
  select telemovel into v_tm from public.contactos where nome = 'ZZ Teste 0059';
  if r2->>'status' <> 'ok' or v_tm <> '913456789, 961234567' then
    raise exception 'FALHOU b): % | %', r2, v_tm;
  end if;

  raise exception 'OK 0059 (rollback feito): a) telemovel=%  b) sem duplicar', v_tm;
end $$;

-- NOTA — sobrecarga antiga de 8 argumentos de `lead_meta_compra` (sem `p_ad_*`):
--   (p_nome, p_telefone, p_email, p_aceita_whatsapp, p_meta_lead_id, p_meta_form_name, p_meta_created_at, p_imovel_ref)
-- ainda existe, com o opt-in antigo (`<> ''`: qualquer resposta conta como «sim») e sem o responsável. O PostgREST escolhe
-- a sobrecarga pelos NOMES dos argumentos recebidos: se algum chamador mandar só os 8, cai nesta. Por decidir (com o teu OK):
-- ver quem a chama e, se ninguém, `drop function public.lead_meta_compra(text,text,text,text,text,text,text,text);`.
