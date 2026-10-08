-- ──────────────────────────────────────────────────────────────────────────
-- Backfill das leads criadas por assistentes (P4 de `leads-do-assistente-plano.md`).
-- Corre-se à mão no editor SQL, PASSO A PASSO, DEPOIS do deploy do código novo.
-- Medido a 08/10 (só leitura): 25 leads com origem = 'assistente'.
--
-- ORDEM IMPORTA: primeiro o `tipo`, depois o telefone. Se se copiasse o telefone antes,
-- `guards.agente_de_lead` passava a ver as 8 candidatas ainda marcadas `compra` e mandava-as
-- para a Matilde. Idempotente: pode voltar a correr-se.
--
-- Decisões (08/10): as 6 leads duvidosas (cliente com tipo_interesse 'outro' ou vazio) NÃO se
-- tocam; a lead do chat do site de 17/09 ganha contacto mas NÃO é promovida; leads cujo telefone
-- já está noutra lead ABERTA ficam de fora (routing ambíguo: A1 vs A3/A4).
--
-- Desfazer: restaurar a partir da cópia do passo 0 (ver o fim do ficheiro).
-- ──────────────────────────────────────────────────────────────────────────

-- ══ PASSO 0 — cópia de segurança (mesmo padrão de oportunidade_preferencias_bak_20260909) ══
create table if not exists leads_assistente_bak_20261008 as
  select * from leads where origem = 'assistente';
select count(*) from leads_assistente_bak_20261008;                       -- esperado: 25

-- ══ PASSO 1 — tipo certo (as candidatas que nasceram `compra`) ═══════════════════════════
update leads l
   set tipo = 'recrutamento'
  from agente_clientes c
 where l.cliente_id = c.id
   and l.origem = 'assistente'
   and l.tipo = 'compra'
   and c.tipo_interesse = 'recrutamento';                                   -- esperado: 8

select tipo, count(*) from leads where origem = 'assistente' group by 1 order by 1;
-- esperado: compra 7 (1 real + 6 duvidosas) · recrutamento 18

-- ══ PASSO 2 — nome/telefone/email na própria lead ════════════════════════════════════════
-- Só clientes com tipo_interesse recrutamento/compra e telefone; e só se esse telefone NÃO estiver
-- já noutra lead aberta (nova/contactada/sem_resposta/pausa): evita duas leads abertas com o
-- mesmo número, que tornam `lead_aberta` (limit 1) ambíguo.
update leads l
   set nome = c.nome, telefone = c.telefone, email = c.email
  from agente_clientes c
 where l.cliente_id = c.id
   and l.origem = 'assistente'
   and l.telefone is null
   and c.tipo_interesse in ('recrutamento', 'compra')
   and c.telefone is not null
   and not exists (
         select 1 from leads o
          where o.id <> l.id
            and o.estado in ('nova', 'contactada', 'sem_resposta', 'pausa')
            and o.telefone is not null
            and right(regexp_replace(o.telefone, '\D', '', 'g'), 9)
              = right(regexp_replace(c.telefone, '\D', '', 'g'), 9)
       );                                                                   -- esperado: 18

select tipo, (telefone is not null) as com_telefone, count(*)
  from leads where origem = 'assistente' group by 1, 2 order by 1, 2;
-- esperado: compra/false 6 · compra/true 1 · recrutamento/false 1 · recrutamento/true 17
-- (a recrutamento sem telefone é a que colide com 2 leads abertas da Meta — fica de fora de propósito)

-- ══ Verificação do efeito no routing (sem dados pessoais) ═══════════════════════════════
-- Nenhum telefone pode ter agora duas leads abertas de tipos diferentes:
select right(regexp_replace(telefone, '\D', '', 'g'), 9) as tel9, count(*) as abertas, count(distinct tipo) as tipos
  from leads
 where telefone is not null and estado in ('nova', 'contactada', 'sem_resposta', 'pausa')
 group by 1 having count(distinct tipo) > 1;                                -- esperado: 0 linhas

-- ══ DESFAZER (só se preciso): repor tipo, nome, telefone e email a partir da cópia ═════════
-- update leads l set tipo = b.tipo, nome = b.nome, telefone = b.telefone, email = b.email
--   from leads_assistente_bak_20261008 b where l.id = b.id;
