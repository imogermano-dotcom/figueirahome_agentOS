# Handoff — 13/09/2026

Sessão com 3 fases + 1 incidente crítico + 1 ligação de ferramenta.

## 1. Novo assistente — Bárbara (A4, angariação)

WhatsApp/painel, para leads de proprietário/vendedor (angariação de imóvel),
seguindo "um motor, N assistentes".

- `backend/app/agents/broker/assistants.py` — `A4 = "a4_angariador"`, `NOME_A4 = "Bárbara"`,
  prompt: qualifica imóvel/zona, propõe 2 horários concretos de visita, nunca
  fala de comissão (remete sempre para o consultor), usa `guardar_dados_cliente`
  / `escalar_para_humano` / `encerrar_lead`.
- `router.py` — `_A4_RE` (angariação) e `_A3_RE` (recrutamento, continua adiado);
  ordem de match: A3 → A4 → A1.
- `guards.agente_de_lead()` — lead `tipo='angariacao'` fixa a thread em `a4_angariador`
  (sticky), como as outras.
- `tools.py` — nome de agente para notificações.
- `supabase/migrations/0036_assistente_a4_angariador.sql` — seed em `agente_config`.
- Frontend: entradas aditivas em `Sidebar.jsx`, `pt.js`, `AgenteConfig.jsx`, `Chat.jsx`.
- Testado ao vivo no chat do painel; dados de teste (`agente_tarefas`, `agente_clientes`,
  `leads`) apagados depois de confirmar com o utilizador.
- Decisões (AskUserQuestion): comissão sempre remetida ao consultor; sem
  diferenciação de tom no prompt por agora; rollout só painel nesta fase.
- Deployado: commit + push confirmado em produção.

## 2. Bug de datas alucinadas — fix transversal

Achado ao testar a Bárbara: o modelo inventava datas de visita ("amanhã" a
calhar errado). Root cause era **do motor**, não do prompt de um assistente —
afectava A1/A2/Broker também.

- `engine.py` — `_data_de_hoje()` (dia da semana PT + `dd/mm/aaaa` UTC) anexado
  a **todo** `system_prompt` em `_montar_system_prompt`, antes da instrução de
  canal.
- Testes actualizados: `test_identidade_site.py` (3 asserts), novo
  `test_engine_prompt.py` (funções puras).
- Deployado junto com a Bárbara (confirmado via AskUserQuestion "commit + deploy").

## 3. Uptime monitor — figueirahome.pt

GitHub Actions cron (não APScheduler — Fly já dorme/acorda, cron externo é
mais simples e não gasta RAM da app).

- `backend/app/site_uptime.py` — `verificar_site()`: GET a `SITE_URL`, timeout 10s,
  alerta só à **3ª falha seguida** (evita blip de rede), alerta de recuperação
  quando volta. Log em `agente_sync_log` (`tipo='site_uptime'`, reaproveitado,
  sem tabela nova).
- `backend/app/api/site_uptime.py` — `POST /api/site/uptime-check`, protegido por
  `X-Automacao-Secret` (mesmo padrão do resto).
- `.github/workflows/site-uptime.yml` — `cron: */5 * * * *`, curl com `--max-time 30`.
- Alerta por Resend (canal já existente, não SendGrid — corrigido um engano
  meu a meio da conversa).
- `docs/fases/uptime-figueirahome-plano.md` — plano completo, incl. comparação
  honesta com UptimeRobot (grátis, 5 min, mais simples de operar; o nosso
  reaproveita infra e log já existentes mas exige manutenção própria).
- ⚠️ **Cron de GitHub Actions só disparou 1x em ~3h17 no primeiro dia** —
  atraso conhecido de "arranque a frio" de crons novos no GitHub. Por
  reconfirmar se estabilizou nos 5 min.

## 4. Incidente crítico — chaves novas do Supabase

Ver `docs/fases/migracao-supabase-chaves-novas-plano.md` (detalhe completo).
Resumo:

- Supabase desactivou chaves legacy (`anon`/`service_role`) a nível de
  projecto, 2026-09-12T18:26 UTC → toda a escrita/leitura do backend em
  produção falhava em silêncio (erros engolidos por desenho).
- Projecto de Auth (`fykbogojkcqokvopnmkz`) tinha sido **eliminado** pelo
  utilizador, dados (`profiles`) fundidos no projecto de dados
  (`zphasvfopnbzwnaidsnw`) — confirmado pelo utilizador. **Um projecto
  Supabase agora, não dois.**
- Migrado para chaves novas (`sb_secret_...`/`sb_publishable_...`) em 3 sítios:
  - **Backend** — `config.py` colapsado a `supabase_url`+`supabase_secret_key`;
    `supabase_client.py` só `get_supabase()` (removido `get_supabase_auth()`);
    `deps.py`/`notificacoes.py` actualizados. `supabase` SDK `2.10.0→2.31.0`
    (a 2.10.0 tem regex client-side que rejeita o formato novo de chave antes
    de qualquer pedido de rede). Deployado, confirmado com escrita real.
  - **Scraper** — mesmo padrão (`config.py`, `oportunidades_completo.py`,
    `dry_run.py`, `requirements.txt`). Deployado, `/health` 200, ligação às
    3 tabelas confirmada. Pipeline completo (Playwright+upsert) por confirmar
    no próximo cron (06:00/13:00 UTC).
  - **Frontend/login** — achado à parte: `VITE_SUPABASE_URL`/`_ANON_KEY`
    (Cloudflare Pages, build-time do Vite) ainda apontavam para o projecto
    eliminado → login novo partido em produção (sessões antigas sobreviviam
    por token em cache). `.env` local corrigido; utilizador actualizou a
    variável no Cloudflare e fez retry do deployment (mudar só a variável não
    rebuilda). Confirmado no bundle novo: zero refs ao projecto antigo.
- ⚠️ **Chave partilhada, temporária**: backend e scraper usam a mesma
  `sb_secret_...` do site (`sitefigueirahome`) — utilizador sem acesso para
  criar uma dedicada no momento do incidente. **Trocar assim que possível.**
- ⚠️ Segredos antigos no Fly (`SUPABASE_SERVICE_ROLE_KEY`,
  `SUPABASE_IMOVEIS_URL`, `SUPABASE_IMOVEIS_KEY`) **não removidos** em nenhuma
  das 2 apps — por decisão do utilizador.
- ⚠️ Fora do repo, ainda bloqueados pelas chaves legacy desactivadas: portal
  do Miguel, Make, bundle das landing pages. Reactivar chaves legacy como
  stopgap é decisão do utilizador, ainda não tomada.

## 5. n8n-mcp — ligação ao n8n self-hosted

Utilizador pediu acesso do Claude Code aos fluxos do n8n
(`n8n.figueirahome.cloud`).

- Registado como MCP server **scope local** (`~/.claude.json`, nunca
  `--scope project` — evita meter a API key no `.mcp.json` deste repo público):
  `claude mcp add n8n-mcp -e MCP_MODE=stdio -e LOG_LEVEL=error -e
  DISABLE_CONSOLE_OUTPUT=true -e N8N_API_URL=... -e N8N_API_KEY=... -- npx n8n-mcp`.
- Confirmado `Status: ✔ Connected` (após pré-aquecer a cache do npm com
  `npx -y n8n-mcp --version` — a 1ª tentativa tinha dado timeout de 30s por
  causa do download).
- Dá acesso a docs de nodes sempre, e gestão completa de workflows
  (listar/criar/actualizar/executar) por a API key estar definida.
- Utilizador perguntou sobre o n8n CLI como alternativa — precisa de acesso
  SSH ao host, que não há; ficou decidido manter o MCP/REST API.
- **Falta reiniciar o Claude Code** para a sessão actual carregar as tools
  novas (ainda não confirmado pelo utilizador).

## Estado no fim da sessão

Tudo o que foi deployado está confirmado em produção. Itens em aberto:
troca da chave partilhada, remoção dos segredos antigos do Fly, decisão sobre
chaves legacy, confirmação do pipeline do scraper no próximo cron,
estabilização do cron do uptime, restart do Claude Code para as tools n8n.
