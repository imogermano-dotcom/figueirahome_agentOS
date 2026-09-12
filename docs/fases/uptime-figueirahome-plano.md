# Plano — Uptime check do figueirahome.pt

> Fase nova, pedida pelo utilizador (11/09). Decisões já tomadas por
> pergunta directa: Resend (não SendGrid — este projecto não usa SendGrid,
> ver abaixo), 3 falhas seguidas, cron de 5 em 5 min, alerta de queda E de
> recuperação.

## Correcção ao pedido original

O pedido mencionava "SendGrid" e um "AGENTS.md" com MX+SendGrid — não
existem neste repositório. `notificacoes.py` já usa **Resend**
(`docs/decisoes.md:30`, trocou de `smtplib` a 31/08). Reaproveita-se essa
função (`notificar()`), sem conta nem credencial nova.

Também: em vez de APScheduler dentro do FastAPI (dependência nova, mais uma
coisa a correr num processo com RAM já apertada — CLAUDE.md), segue-se o
padrão já estabelecido no projecto para tudo o que é periódico: **GitHub
Actions cron** a chamar um endpoint protegido por `X-Automacao-Secret`
(mesmo de `sync-imoveis.yml`/`nudge-matilde.yml`).

## Desenho

**Sem tabela nova.** `agente_sync_log` (migration `0007`) já é log genérico
por `tipo` — usa-se `tipo='site_uptime'`, mesmo padrão do `nudge_matilde`.

1. `backend/app/site_uptime.py` — `verificar_site()`:
   - `GET https://www.figueirahome.pt`, timeout 10s.
   - Grava uma linha em `agente_sync_log` (`resumo`: `ok`, `status`,
     `latencia_ms`, `erro`).
   - Lê as últimas 4 linhas (`_LIMIAR_FALHAS + 1`) desse tipo e conta falhas
     seguidas a partir do topo (função pura, testável sem DB).
   - Falha e a contagem **atinge exactamente 3** → `notificar()` "site em
     baixo" (só dispara uma vez ao cruzar o limiar, não a cada execução
     seguinte que continue em baixo).
   - Sucesso e a execução anterior já tinha 3+ falhas seguidas →
     `notificar()` "site recuperado".
2. `backend/app/api/site_uptime.py` — `POST /api/site/uptime-check`,
   `require_automacao_access` (mesmo segredo `AUTOMACAO_SECRET` já usado
   pelo nudge e pelos syncs — não cria um segredo novo).
3. `.github/workflows/site-uptime.yml` — cron `*/5 * * * *`, `curl` com o
   segredo, `workflow_dispatch` pra correr à mão.
4. `backend/tests/test_site_uptime.py` — a lógica de contagem de falhas é
   pura (`_contar_falhas_no_topo`), testa-se sem DB nem rede.

## Fora do âmbito

- Só a raiz (`https://www.figueirahome.pt`), não `/imoveis` — um único
  endpoint já testa DNS, TLS, servidor e app; adicionar um segundo só
  compensa se algum dia a raiz responder e uma rota específica não. Fácil de
  acrescentar depois se for preciso.
- Sem painel/dashboard para o histórico — fica só no `agente_sync_log`,
  consultável à mão se for preciso (mesmo nível do `nudge_matilde` hoje).

## Verificação

- `pytest backend/tests/` — suite completa.
- Correr o endpoint à mão (`workflow_dispatch` ou `curl` directo) antes de
  confiar no cron, mesmo padrão de cautela já seguido nos outros crons.
