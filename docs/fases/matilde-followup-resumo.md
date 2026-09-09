# Resumo — Frente A implementada (nudge dentro da janela de 24h)

> Plano completo em `matilde-followup-plano.md`. Esta fase implementou só a
> Frente A (lembrete de conversa). A Frente B (template 01/02/03) continua
> por importar — trabalho já conhecido, sem código novo desta análise.

## O que foi feito

- `backend/app/agents/broker/nudge.py` — `_candidatos()` (query
  `agente_conversas`: `agente='a1_vendedor'`, `canal='whatsapp'`, `nudge_em`
  vazio, `atualizado_em` entre 6h e 20h atrás; filtra despedidas e leads
  fechadas/com `contacto_humano_em`) e `enviar_nudges()` (envia, grava no
  histórico via `save_conversation`, marca `nudge_em`, regista em
  `agente_sync_log` tipo `nudge_matilde`).
- `backend/app/api/nudge.py` — `POST /api/matilde/nudge`, protegido por
  `require_automacao_access` (reaproveitado o `X-Automacao-Secret` já
  existente para Make/n8n, em vez de criar um terceiro segredo).
- `backend/app/main.py` — router registado.
- `.github/workflows/nudge-matilde.yml` — cron de hora a hora,
  `workflow_dispatch` para correr à mão.
- `supabase/migrations/0035_agente_conversas_nudge.sql` — coluna
  `agente_conversas.nudge_em`. **Por correr à mão** no editor SQL, como as
  restantes.
- `backend/tests/test_nudge.py` — 7 testes. Suite completa: 244 a passar
  (era 237).

## Correcção pós-teste ao vivo (2026-09-09)

O teste ao vivo com o número do utilizador revelou um buraco: `_candidatos()`
usava `guards.lead_aberta`, que devolve `None` tanto para "nunca houve lead"
como para "lead fechada" — **indistinguíveis**. Isso excluía precisamente o
caso que motivou a Frente A (proposta de 110 000€ ao FH2571, nome/telefone
nunca recolhidos com sucesso — sem `cliente_id`, sem `leads`, ficaria sempre
de fora).

Corrigido com `nudge._pode_enviar(telefone)`: consulta a `leads` mais
recente **sem filtrar por estado aberto**, e só recusa quando há mesmo lead
`ESTADOS_FECHADOS` ou `contacto_humano_em`. Sem lead nenhuma → elegível. A
mudança em `guards.lead_aberta` (seleccionar `contacto_humano_em`) foi
revertida — deixou de ser necessária, `guards.py` fica sem alterações
nesta fase.

## Decisões já tomadas (ver plano)

- Janela: 6h–20h desde a última mensagem da Matilde.
- Texto: *"Ainda está interessado? Fico a postos para continuar, ou diga-me
  só que não para eu não voltar a incomodar."*
- Despedidas detectadas por marcadores na mensagem da própria Matilde (👋,
  "cuide-se", "boa continuação", "muita força", "boa sorte") — lista em
  `nudge._MARCAS_FECHO`, fácil de estender.
- Threads sem lead associada (site/web) já ficam fora só pelo filtro
  `canal='whatsapp'`, sem mecanismo extra.

## Por fazer antes de ligar em produção

1. ~~Correr a migration `0035` à mão no Supabase~~ — **feito (2026-09-09)**,
   confirmado.
2. ~~Confirmar `AUTOMACAO_SECRET`~~ — **feito (2026-09-09)**: gerado, posto no
   Fly (`fly secrets set`) e no GitHub Actions (secret do repositório).
3. ~~Deploy do backend~~ — **feito (2026-09-09)**, `flyctl deploy` a partir de
   `backend/` (o Dockerfile/`fly.toml` vivem lá, não na raiz). Confirmado ao
   vivo: `/docs` a 200, `/api/matilde/nudge` sem segredo a 401, com o
   segredo certo a 200 (`{"candidatos":0,"enviados":0,"erros":0}` — sem
   candidatos elegíveis no momento do teste).
4. ~~Commitar e dar `git push`~~ — **feito (2026-09-09)**, `093e414` em
   `master`. Cron activo a partir de agora, dispara de hora a hora.

## Testado ao vivo (2026-09-09)

Janela encurtada temporariamente (6h→3min) para não esperar horas, testada
com um número real do utilizador: mensagem enviada, resposta chegou. Janela
revertida para 6h/20h e reposta em produção depois do teste — confirmado
saudável (`/docs` 200).

## Não implementado nesta fase

- A resposta da lead a um nudge que diga "não" **não** está ligada a
  `encerrar_lead` — o nudge manda o texto e grava-o no histórico, mas quem
  responde entra pelo caminho normal do webhook/engine, que já trata
  desfechos. Não confirmado ao vivo que o "diga-me só que não" dispara
  `encerrar_lead` correctamente a partir desta mensagem em concreto — a
  lógica de desfecho já existe no motor, isto só a invoca indirectamente.
