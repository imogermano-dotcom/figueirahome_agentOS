# Plano — `contacto_id` nas tabelas do eGO (01/10)

> Pedido: poder relacionar `oportunidades`, `tarefas`, `notas`, `visitas` pelo ID do contacto
> (urgente). Estado: **código + SQL escritos, migration por correr** (corre-a o utilizador à mão).

## Problema
Nenhuma destas tabelas se liga a `contactos` por ID — só têm nome (`cliente_nome`,
`visita_cliente`). Por nome é ambíguo em **17 268 das 26 049** oportunidades (10 319 nomes
repetidos em `contactos`).

## O que se mediu (só leitura)
- `contactos`: 28 483 linhas, todas com `id uuid` (UNIQUE). **Duas populações sobrepostas**:
  12 631 com `ego_link` (nosso scraper, 2025-26) e 15 852 sem (pipeline do Miguel, 2019-25);
  ~10 000 das segundas casam por telefone/email com uma das primeiras (mesma pessoa, 2+ linhas).
- O relatório diário de Oportunidades **já traz a pessoa** (`Link (2)` = `/egocore/person/<id>` =
  `contactos.ego_link`): 25/25 oportunidades com contacto ligado e um com nome == `cliente_nome`.
  `group()` já construía `contactos_por_oportunidade` mas nunca persistia o elo.
- Backfill do histórico por SQL (regra canónica): telefone ~11 900 · email ~700 · só nome ~8 700
  (baixa confiança) · sem resolução ~4 800 → **82% resolvíveis; 48% de alta confiança**.

## Decisões (utilizador, 01/10)
1. **Alvo = linha com `ego_link`** (identidade real do eGO); só onde não há, a linha do pipeline do Miguel.
   Limpeza de duplicados fica para fase seguinte.
2. **Histórico = daqui para a frente + heurística SQL** (sem backfill completo pelo eGO).
3. **Avançar sem consultar o Miguel** — mitigação: colunas nullable, `ADD COLUMN IF NOT EXISTS`,
   inspecção de triggers antes, e `COUNT(contacto_id)` 24 h depois.

## Desenho
- `oportunidades.contacto_id` (+ `contacto_match`) é a **fonte de verdade**; `tarefas`/`notas`/`visitas`
  herdam por `oportunidade_ref` (denormalizado para juntar directamente a `contactos`).
- FK para `contactos(id)` e **não** para `(nome, criado_em)`: o scraper muda `criado_em` a cada
  edição e a FK composta de `leads_angariacao` já partiu (23503).
- Escrita **só por RPC** (`set_contacto_oportunidades`, `propagar_contacto_id`), nunca no upsert em
  lote: a armadilha do PostgREST (chave só em alguns registos escreve NULL nos outros) apagaria o backfill.
- Scraper: `group()` devolve `contacto_por_oportunidade` (ego_link do contacto com nome == cliente);
  `upsert.run()` grava `contactos` **primeiro**, lê `ego_link -> id` e chama a RPC; `tarefas.py`
  chama `propagar_contacto_id()` no fim. Tudo best-effort: sem a migration, regista e segue.

## Ficheiros
`supabase/migrations/0046_contacto_id.sql` · `docs/fases/contacto-id-backfill.sql` ·
`scraper/mapping_todas_colunas.py` (`group`) · `scraper/upsert.py` (`_ligar_contactos`, `run`) ·
`scraper/tarefas.py` (`run`).

## Ordem de execução
1. **Inspecção** no editor SQL (antes de qualquer coisa):
   ```sql
   select conrelid::regclass, conname, pg_get_constraintdef(oid) from pg_constraint
    where conrelid in ('contactos'::regclass,'oportunidades'::regclass,'tarefas'::regclass,'notas'::regclass,'visitas'::regclass);
   select event_object_table, trigger_name, action_statement from information_schema.triggers
    where event_object_table in ('contactos','oportunidades','tarefas','notas','visitas');
   ```
   Confirmar que não há trigger a reescrever linhas nem constraint a conflituar.
2. Correr `0046_contacto_id.sql` (colunas + 2 RPCs; o SELECT final deve dar `com_contacto = 0`).
3. **Só depois** deployar o scraper (`flyctl deploy` de `scraper/`) — antes, a RPC não existe.
4. Correr `contacto-id-backfill.sql` passo a passo; olhar a amostra do passo 3 (nome).
5. Disparar `sync-oportunidades` à mão (`cm jobs trigger 3`) e ver `contacto_match='ego_link'`.
6. 24 h depois: `COUNT(contacto_id)` não desce (prova de que o pipeline do Miguel não o apaga).

## Limites conhecidos
- 33% do histórico fica ligado só por nome (`contacto_match='nome'`): filtrável/anulável, nunca
  usar para acções automáticas.
- Só as oportunidades editadas passam pelo relatório de 48 h; o histórico não editado fica na heurística.
- Mesma pessoa continua com 2+ linhas em `contactos`; ligar à canónica (com `ego_link`) é o que torna
  o JOIN fiável. Fundir duplicados + repointing é a fase seguinte.
- `leads`/`agente_clientes`/`leads_angariacao` têm ligações próprias — fora de âmbito (2.ª fase).
