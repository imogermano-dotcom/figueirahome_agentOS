-- ──────────────────────────────────────────────────────────────────────────
-- 0046 — `contacto_id`: relacionar oportunidades/tarefas/notas/visitas por ID do contacto
--
-- Antes: nenhuma destas tabelas se liga a `contactos` por ID. Só têm o nome do
-- cliente (`cliente_nome`, `visita_cliente`), e por nome é ambíguo em 17 268 das
-- 26 049 oportunidades (10 319 nomes repetidos em `contactos`).
--
-- Desenho (docs/fases/contacto-id-plano.md):
--   * `oportunidades.contacto_id` é a FONTE DE VERDADE (+ `contacto_match`, que diz
--     com que confiança se ligou: 'ego_link' | 'telefone' | 'email' | 'nome').
--   * `tarefas`/`notas`/`visitas` herdam-no por `oportunidade_ref` (FK que já
--     existe), denormalizado para se poderem juntar directamente a `contactos`.
--   * FK para `public.contactos(id)` (uuid, UNIQUE, não muda num UPSERT) e NÃO para a PK
--     `(nome, criado_em)`: o scraper regrava `criado_em` a cada edição e a FK
--     composta de `leads_angariacao` já partiu por isso (23503, docs/decisoes.md).
--   * Tudo NULLABLE e `IF NOT EXISTS`: não parte nenhuma leitura (portal do Miguel,
--     `social_imovel_stats`). `ON DELETE SET NULL`: apagar um contacto nunca apaga
--     nem bloqueia uma oportunidade.
--   * Escrita só pela RPC (nunca no upsert em lote): uma chave presente só em
--     alguns registos escreveria NULL nos outros e apagaria o que o backfill pôs.
--
-- ATENÇÃO: existe também um schema `prospeccao` com outra tabela `contactos` (PK `id`).
-- Tudo aqui está qualificado como `public.` de propósito.
--
-- Idempotente. Corre-se à mão no editor SQL (db push proibido). Antes: ver a query
-- de inspecção no plano (triggers/constraints das 5 tabelas). Depois: backfill em
-- docs/fases/contacto-id-backfill.sql.
-- ──────────────────────────────────────────────────────────────────────────

alter table oportunidades add column if not exists contacto_id    uuid references public.contactos(id) on delete set null;
alter table oportunidades add column if not exists contacto_match text;
alter table tarefas       add column if not exists contacto_id    uuid references public.contactos(id) on delete set null;
alter table notas         add column if not exists contacto_id    uuid references public.contactos(id) on delete set null;
alter table visitas       add column if not exists contacto_id    uuid references public.contactos(id) on delete set null;

create index if not exists idx_oportunidades_contacto_id on oportunidades(contacto_id);
create index if not exists idx_tarefas_contacto_id       on tarefas(contacto_id);
create index if not exists idx_notas_contacto_id         on notas(contacto_id);
create index if not exists idx_visitas_contacto_id       on visitas(contacto_id);

comment on column oportunidades.contacto_id    is 'Pessoa da oportunidade (contactos.id). Fonte de verdade; tarefas/notas/visitas herdam-no.';
comment on column oportunidades.contacto_match is 'Como se ligou: ego_link (certo, vem do eGO) | telefone | email | nome (baixa confiança, homónimos).';

-- Copia `contacto_id` das oportunidades para tarefas/notas/visitas. Só toca no que
-- difere e só quando a oportunidade já tem contacto. Devolve quantas linhas mudou.
create or replace function propagar_contacto_id() returns jsonb
language plpgsql
set statement_timeout = '300s'
set search_path = public
as $$
declare
  n_tarefas int; n_notas int; n_visitas int;
begin
  update tarefas x set contacto_id = o.contacto_id
    from oportunidades o
   where x.oportunidade_ref = o.oportunidade_ref
     and o.contacto_id is not null
     and x.contacto_id is distinct from o.contacto_id;
  get diagnostics n_tarefas = row_count;

  update notas x set contacto_id = o.contacto_id
    from oportunidades o
   where x.oportunidade_ref = o.oportunidade_ref
     and o.contacto_id is not null
     and x.contacto_id is distinct from o.contacto_id;
  get diagnostics n_notas = row_count;

  update visitas x set contacto_id = o.contacto_id
    from oportunidades o
   where x.oportunidade_ref = o.oportunidade_ref
     and o.contacto_id is not null
     and x.contacto_id is distinct from o.contacto_id;
  get diagnostics n_visitas = row_count;

  return jsonb_build_object('tarefas', n_tarefas, 'notas', n_notas, 'visitas', n_visitas);
end;
$$;

-- Chamada pelo scraper com as oportunidades do relatório do eGO, cujo contacto vem
-- por `ego_link` (a ligação certa, por isso sobrepõe qualquer heurística do backfill).
-- pares = [{"oportunidade_ref": "VEN_1", "contacto_id": "<uuid>", "contacto_match": "ego_link"}, ...]
create or replace function set_contacto_oportunidades(pares jsonb) returns jsonb
language plpgsql
set statement_timeout = '300s'
set search_path = public
as $$
declare
  n_oport int;
begin
  update oportunidades o
     set contacto_id = p.contacto_id, contacto_match = p.contacto_match
    from jsonb_to_recordset(pares) as p(oportunidade_ref text, contacto_id uuid, contacto_match text)
   where o.oportunidade_ref = p.oportunidade_ref
     and (o.contacto_id is distinct from p.contacto_id or o.contacto_match is distinct from p.contacto_match);
  get diagnostics n_oport = row_count;

  return jsonb_build_object('oportunidades', n_oport) || propagar_contacto_id();
end;
$$;

-- Como na 0025: funções que escrevem não são para anónimos (o PostgREST expõe-nas).
revoke execute on function propagar_contacto_id()            from public, anon, authenticated;
revoke execute on function set_contacto_oportunidades(jsonb) from public, anon, authenticated;
grant  execute on function propagar_contacto_id()            to service_role;
grant  execute on function set_contacto_oportunidades(jsonb) to service_role;

-- Verificação: as 4 colunas existem e estão todas a NULL (nada foi ligado ainda).
select 'oportunidades' as tabela, count(*) as linhas, count(contacto_id) as com_contacto from oportunidades
union all select 'tarefas',  count(*), count(contacto_id) from tarefas
union all select 'notas',    count(*), count(contacto_id) from notas
union all select 'visitas',  count(*), count(contacto_id) from visitas;
