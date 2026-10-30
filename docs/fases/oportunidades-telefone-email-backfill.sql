-- Pedido #4, etapa 2 (30/10/2026): telefone e email nas oportunidades, de forma permanente.
-- Corre-se UMA vez, no editor SQL do Supabase, por esta ordem. O sync (scraper/upsert.py) passa a manter o resultado:
-- já não grava texto vazio nem escreve NULL por cima, e completa o que faltar a partir do contacto ligado.
--
-- Antes de correr, vê quantas linhas vão mudar (só leitura):
--   select count(*) filter (where cliente_telefone = '') as tel_vazio,
--          count(*) filter (where cliente_email = '')    as email_vazio,
--          count(*) filter (where cliente_telefone is null and cliente_email is null) as sem_nada
--   from public.oportunidades;
--
-- Efeito lateral: `oportunidades` tem um BEFORE UPDATE que carimba `atualizado_em`; as linhas tocadas ficam com a data de hoje.

-- 1) Texto vazio passa a NULL (o relatório do eGO dá '' quando não há valor).
update public.oportunidades set cliente_telefone = null where cliente_telefone = '';
update public.oportunidades set cliente_email    = null where cliente_email = '';

-- 2) Onde está vazio, usa o contacto ligado por contacto_id. Nunca mexe num valor que já exista.
update public.oportunidades o
set cliente_telefone = coalesce(nullif(c.telemovel, ''), nullif(c.telefone, ''))
from public.contactos c
where o.contacto_id = c.id
  and o.cliente_telefone is null
  and coalesce(nullif(c.telemovel, ''), nullif(c.telefone, '')) is not null;

update public.oportunidades o
set cliente_email = nullif(c.email, '')
from public.contactos c
where o.contacto_id = c.id
  and o.cliente_email is null
  and nullif(c.email, '') is not null;
