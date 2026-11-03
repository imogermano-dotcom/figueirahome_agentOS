---
name: verificacao-diaria
description: Verificação diária da plataforma Figueirahome — crons, scraper e API (Fly + agente_sync_log), runs dos fluxos n8n e entradas no Supabase, e leitura das conversas dos agentes. Usar quando o utilizador pedir "verificação diária", "verifica as runs", "como correu hoje" ou "analisa as conversas dos agentes". Só leitura; relatório no fim.
---

# Verificação diária

Só leitura. Nunca corrigir, fazer deploy, escrever em produção, tocar no eGO ou correr fluxos n8n sem autorização expressa do utilizador. Propor a correção e esperar. PT-PT, terso.

**Antes de começar:** ver a hora (Lisboa = UTC no inverno, UTC+1 no verão) e a data. Já errei a ver "madrugada" quando eram 10:00: confirmar sempre contra o relógio e não assumir que os syncs ainda não correram.

Todos os comandos Python correm de `backend/` com o Python do projeto (`C:\Users\joaoa\AppData\Local\Programs\Python\Python312\python.exe`). O repo é **público**: nada do que sair daqui (nomes, telefones, emails de pessoas) vai para ficheiros do repo, commits ou docs; no relatório usar iniciais ou ids curtos.

## Passo 1 — Crons, scraper e API

1. **Registos dos syncs:** `python scripts/verificacao_diaria.py syncs 26`. Mostra o último registo por `tipo` em `agente_sync_log`. Comparar com o `crons/schedules.json` (horas UTC):

   | Cron | Hora UTC | `tipo` no log |
   |---|---|---|
   | sync-oportunidades | 03:37 | `egorealestate_oportunidades_completo` |
   | sync-propostas | 04:17 | `egorealestate_propostas` |
   | sync-tarefas | 05:07 | `egorealestate_tarefas` |
   | sync-imoveis-manha / tarde | 06:17 / 13:23 | `egorealestate_api` |
   | sync-imoveis-todos | 06:47 | `egorealestate_imoveis_todos` (ligado a 02/11; ver o 1.º ciclo sozinho a 03/11: tempo contra o limite de 300 s) |
   | nudge-matilde | de hora a hora, :12 | `nudge_matilde`, `nudge_ines`, `nudge_barbara` |
   | leads-compra-para-ego | de 10 em 10 min, só cria 9h–20h Lisboa | (sem registo próprio: ver `ego_lead_em` no passo 2) |

   `resumo-falhas-whatsapp` e `site-uptime` estão `enabled: false` de propósito.
2. **Falhas:** qualquer `tipo` terminado em `_erro` é falha de cron (também gera email ao diretor). Um sync que devia ter corrido e não aparece é pior: o aviso não apanha um cron que nem arranca.
3. **Números a ler no `resumo`:** `erros` > 0; `a_inserir` ≠ `inseridos`; `fechadas`/`apagadas` anormais; contagens de oportunidades e tarefas a cair. Compara com o dia anterior quando houver dúvida.
4. **Fly** (`C:\Users\joaoa\.fly\bin\flyctl.exe`): `status --app figueirahome-agentos`, `--app figueirahome-scraper` e `--app figueirahome-crons`; se algo falhar, `logs --app <nome> --no-tail`. A agentos faz auto-stop por inatividade: **"health check failed" é arranque a frio, não é erro.**

## Passo 2 — Fluxos n8n e entradas no Supabase

**n8n.** O Traefik à frente do n8n pede Basic auth e o MCP não a faz sozinho, por isso o acesso é por um proxy local:
- O utilizador arranca, numa janela PowerShell própria e deixada aberta: `node backend/scripts/n8n_proxy.mjs` (pede a palavra-passe escondida; utilizador `miguelgermano`). Nunca pedir nem receber a palavra-passe no chat.
- O `~/.claude.json` do `n8n-mcp` tem `N8N_API_URL=http://127.0.0.1:5679` e `WEBHOOK_SECURITY_MODE=moderate`. Teste: `n8n_health_check`. Se der 401/502, o proxy não está a correr ou a palavra-passe está errada.
- Se o n8n continuar inacessível: **dizer "n8n por ver"** no relatório, fazer só o lado Supabase e não inventar.
- Sem proxy: `python scripts/n8n_execucoes.py 24` faz o mesmo por API REST com `N8N_API_KEY`, `N8N_BASIC_USER` e `N8N_BASIC_PASS` no `backend/.env`.

Passos:
1. `n8n_executions action=list status=error limit=30`: todas as runs com erro. Para cada uma nova, `action=get mode=error id=<id>`. Distinguir **falha pontual** (DNS `EAI_AGAIN`, timeout) de **falha de lógica** (400/500 sempre igual).
2. `n8n_executions action=list limit=100`: ver se os fluxos ativos correram à hora devida (follow-ups às 12:00 UTC; `Meta leads to supabase` por webhook; envio do template; LinkedIn de 10 em 10 min; respostas do Outlook).
3. Ruído conhecido, não reportar como novo: `Faturas 2026 — Miguel Gmail` (6vBgYZ…) falha todas as noites às 01:00 e não é do projeto.
4. Os nós do n8n sem retry param o lote ao 1.º erro: se um follow-up falhou, contar quantos contactos ficaram por processar.

**Supabase.** `python scripts/verificacao_diaria.py leads 48`: funil das leads Meta (opt-in → template → entregue; `falhou`, `recusou`, `eGO`, `sem_resp`). Alarmes:
- `optin_sem_template>1h` > 0: o template não saiu (ver a faturação da WABA antes de culpar o conteúdo: `200 accepted` não é entrega).
- `falhou` com `whatsapp_erro_codigo` 131026: número sem WhatsApp, não é erro nosso.
- `eGO` muito abaixo de `n`: ver se são leads fora das 9h–20h (a rede `meta-leads-rede` cria-as depois) ou sem consultora (nunca se cria sem responsável).
- `sem_resp` > 0: lead sem consultora, não aparece no eGO.
- **Vigia das leads da Meta:** o fluxo n8n «Vigia leads Meta» (`v03lokXyOY0r7JWO`) tem de ter corrido há menos de 45 min e estar ativo. Em `agente_sync_log`, `vigia_leads_meta` (cada verificação) e `vigia_leads_alerta` (avisos enviados). Se a Meta tem mais leads do que o Supabase num dia (`diferencas`), ver o Make (cenário ligado?) e as execuções do webhook; **um cenário do Make desligado não deixa rasto no n8n**.
- Cruzar com o n8n: leads a entrar e execuções do webhook devem bater.

## Passo 3 — Conversas dos agentes

1. **Métricas:** `python scripts/verificacao_diaria.py turnos`. Ver `erros` (incluindo `sem_texto`), latência p95, `cache` (abaixo de ~67% multiplica o custo), `iter>3` e custo.
2. **Ler as conversas:** `python scripts/verificacao_diaria.py conversas` (texto com telefones ocultados). Ler cada uma até ao fim e procurar:
   - **Recusa tratada como interesse** ("já não estou interessado" → lead criada no eGO). O sinal é `interesse_real_em` numa pessoa que recusou. Nunca eliminar no eGO: propor ao utilizador pedir ao Miguel que descarte a lead.
   - **Promessas que não se cumprem** ("já enviei", "o consultor liga hoje", prazos) e afirmar que há imóveis sem ter pesquisado.
   - **Afirmações legais ou de preços** que o prompt não suporta (ex.: regras de arrendamento): reportar a frase exata ao utilizador para rever o prompt.
   - **Escaladas** indevidas, repetidas ou sem tarefa; despedidas respondidas com mais texto; resposta enlatada ("Ocorreu um erro").
   - **Zona:** a Inês só no concelho da Figueira da Foz; a Matilde nunca pede telefone no WhatsApp.
   - Mensagens que não são texto (áudio, imagem): têm de ter recebido o aviso «escreva, por favor».
3. Citar problemas pela conversa (C1, C2…) e pelo agente, nunca com nome ou telefone.

## Relatório final

Uma secção por passo, por esta ordem, com o estado em 1 linha cada (✅ / ⚠️ / ❌ / "por ver"):
1. **Crons/scraper/API:** o que correu, o que falhou, o que falta.
2. **n8n + Supabase:** erros novos com causa provável, impacto em contactos concretos (quantos), ruído conhecido à parte.
3. **Conversas:** problemas por gravidade, com a frase exata quando for erro do agente.
4. **Decisões para o utilizador:** lista curta de ações propostas (corrigir, avisar o Miguel, rever prompt). Quem fizer deploy ou correr algo em produção só o faz depois de autorizado.

Terminar com o que **não** foi coberto (janela vista, n8n por ver, etc.).
