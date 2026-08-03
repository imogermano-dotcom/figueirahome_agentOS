# CLAUDE.md — Figueirahome Agent Call

> Contexto principal do projecto. Lido automaticamente em cada sessão.

---

## O que é

Plataforma de IA para agência imobiliária em Portugal:
1. **Assistentes de atendimento** — **A1 Vendedor** (compradores e arrendatários) e
   **A2 Geral** (recepção e encaminhamento), em WhatsApp e no chat do painel.
2. **Agente de Voz** — atendimento telefónico (Telnyx). Bloqueado por credenciais.
3. **Assistente Broker** — chat interno do corretor, com acesso de leitura à BD.
4. **Painel de gestão** — React: clientes, imóveis, leads, métricas dos assistentes.

---

## Stack

| Camada | Tecnologia |
|---|---|
| Frontend | React + Tailwind v4 (Vite) → Cloudflare Pages |
| Backend | FastAPI (Python, async) → Fly.io |
| Base de dados | Supabase (PostgreSQL + Auth) — 2 projectos |
| Telefonia | Telnyx (Call Control + Media Streaming) |
| STT | OpenAI Whisper (PT) |
| IA | Claude API — Sonnet 4.6 (httpx directo, não SDK) |
| TTS | Telnyx `speak()` — voz `Polly.Ines-Neural` |

---

## Estrutura

```
backend/app/
├── main.py          ← FastAPI + CORS + routers
├── config.py        ← pydantic-settings (SUPABASE_*, SUPABASE_IMOVEIS_*, EGOREALESTATE_*, SCRAPER_SERVICE_*)
├── api/             ← clientes, imoveis, imoveis_sync, oportunidades_sync, leads,
│                      tarefas, config, dashboard, broker, agentes (métricas)
├── agents/
│   ├── voice/       ← webhook Telnyx, audio_ws, save_call, claude_agent (só voz)
│   └── broker/      ← engine (motor único), assistants (registry), router, guards
│                      (dedup + 80%), custos, tools, conversation, channels/whatsapp/
├── integrations/    ← egorealestate.py (cliente API), imoveis_sync.py (upsert)
├── db/supabase_client.py  ← get_supabase() [dados] + get_supabase_auth() [só login]
└── models/          ← Pydantic (imovel, cliente, lead, tarefa, ...)

frontend/src/    App.jsx · lib/ (supabase.js, api.js)
├── components/  ← Layout, Sidebar, ProtectedRoute, AgenteMetricas, AgenteConversas, Barras
└── pages/       ← Dashboard, Clientes, Imoveis (Portfólio/Tarefas/Sincronização),
                   Leads, Chat, AgenteConfig (/agentes/:agente), Config

scraper/             ← app Fly.io separada, dedicada a Playwright (ver docs/decisoes.md)
    app.py (POST /run/oportunidades-completo) · oportunidades_completo.py (lê a
    URL directa do export, não o popup) · mapping_todas_colunas.py · upsert.py
```

---

## Estado actual — Handoff 2026-08-03

### Produção

| Componente | URL | Estado |
|---|---|---|
| Backend | `figueirahome-agentos.fly.dev` | ✅ deployado (`85221a4`), secrets eGO API+CRM+SCRAPER_SERVICE_* postos |
| Scraper oportunidades | `figueirahome-scraper.fly.dev` | ✅ app Fly.io separada (1 vCPU/1GB, scale-to-zero) |
| Frontend | `figueirahome-agentos.pages.dev` | ✅ Cloudflare Pages, auto-deploy do push |
| Assistentes A1/A2 | WhatsApp + chat do painel | ✅ end-to-end, com pesquisa de imóveis reais |
| Cron sync eGO | `.github/workflows/sync-imoveis.yml` | ✅ diário (última run 08-03T09:42, 54 actualizados), só **API** (CRM manual) |
| Git | `github.com/imogermano-dotcom/figueirahome_agentOS` | ✅ master, tudo pushed |

### Fases concluídas — o histórico vive em `docs/fases/`

| Quando | Fase | Migrations |
|---|---|---|
| 07-28/31 | Campos extra eGO (`plantas`, `video_url`, `destaque`); sync de oportunidades via app `scraper/` | `0012`, `0013` |
| 08-02 | **Assistentes A1/A2** — motor único (`engine.py`) no lugar de 3 cérebros duplicados, assistentes por configuração, router sticky, guardas em código. Saldo −197 linhas; primeiros testes do projecto | `0014` |
| 08-03 | **Dashboard** — RPC única, cartões mortos removidos, dados sujos expostos como alertas | `0015` |
| 08-03 | **Observabilidade** — `agente_interacoes` (1 linha por turno): custo, latência, tokens, tools | `0016`, `0017` |
| 08-03 | **Métricas do A1 em 4 blocos de negócio** — funil, atendimento, preferências, operacional | `0018`, `0019` |

Invariantes que não são óbvias a ler o código:

- **Prompt caching a 67%** — o cartão "Servido de cache" fica vermelho se cair a
  zero havendo turnos. Sem esse alarme, uma quebra multiplica por 10 o custo dos
  tokens de entrada sem nada dar sinal.
- **PII nunca entra em `tools_detalhe`** — allowlist `_TOOLS_INPUT_SEGURO`: só
  `pesquisar_imoveis` e `ficha_imovel` guardam argumentos. Tool nova entra no
  lado seguro por omissão; um teste falha se a allowlist crescer sem revisão.
- **Preços em `custos.py`** ($3/$15 por MTok, cache read 0,1×, write 1,25×). O
  custo é **gravado**, não recalculado.
- **Imóveis contam-se por `publicado` (53), não `disponibilidade` (67)**.
- **Sem gráficos de evolução nem de receita, e sem uptime** — `data_criacao_iso`
  falta em 8432 registos, `valor_negocio` está em 7 de 1000, e não há sonda de
  disponibilidade. Mentiriam; os ecrãs dizem-no em vez de os desenhar.
- **Percentagens com < 20 turnos mostram a fracção** ("33% (1 de 3)").
- **WhatsApp não lê Markdown** — `channels/whatsapp/formatacao.py` converte no
  único ponto de saída. 14 das 17 respostas reais estavam afectadas.
- **MQL = orçamento + zona + tipo de interesse.** O "timing" não é recolhido.

### Base de dados unificada

Todas as tabelas vivem no projecto Supabase secundário (`zphasvfopnbzwnaidsnw`,
settings `supabase_imoveis_*`). Projecto original (`supabase_url/key`) fica **só
Auth**. `get_supabase()` = dados; `get_supabase_auth()` = só valida login.
**Migrations são corridas à mão pelo utilizador** no editor SQL do Supabase — não
há psql nem ligação directa; explicar o SQL antes de pedir que o corra.

### Sincronismo eGO

`backend/app/integrations/imoveis_sync.py`: `sync_egorealestate_api()` (Web API
pública, full pull paginado, cron diário) e `sync_egorealestate_crm()` (CRM
autenticado, visibilidade total incl. não-publicados, só via botão "Validar CRM",
fora do cron). Coluna `publicado` (GENERATED STORED, `0008`) e `disponivel_na_api`.

### Ambiente local

- Python: `C:\Users\joaoa\AppData\Local\Programs\Python\Python312\python.exe`
- fly CLI: `C:\Users\joaoa\.fly\bin\flyctl.exe deploy --app <nome>` (de `backend/` ou `scraper/`)
- `backend/.env` / `scraper/.env` — Supabase (ambos) ✅, Anthropic ✅, OpenAI ✅,
  eGO API+CRM ✅, SCRAPER_SERVICE_* ✅, Telnyx ❌, Meta ❌
- Testes: `pytest backend/tests/` **a partir de `backend/`** (fora daí o `.env` não é encontrado)
- Scrapers Playwright: `pip install -r <pasta>/requirements*.txt` + `playwright install chromium`

### Bloqueadores activos

| Item | Estado |
|---|---|
| Credenciais Telnyx (3 vars) | ❌ bloqueia chamadas de voz |
| Número PT +351 Telnyx | ❌ requer regulatory requirement group |
| Número WhatsApp do corretor | ⚠️ escalada já funciona via `agente_tarefas`; só a notificação por WhatsApp está bloqueada |
| ~3459 linhas `fonte='manual'`/`Em Prospecção` de origem desconhecida | ⚠️ investigação parada a pedido do utilizador — não mexer sem ser pedido de novo |

### Próximos passos

1. **A3 (Recrutamento) e A4 (Angariador)** — adiados. Router já os reconhece e manda para o A2; falta a linha em `agente_config` e os prompts.
2. **A1 — sub-fluxos SC (simulação de crédito) e FP (propostas)** — adiados; a *escalada* do FP já vai via `escalar_para_humano`.
3. **Confirmar latência com tráfego real** — 10,1s num turno com pesquisa, só 3 medidos. Ver a p95 antes de mexer em `_MAX_TOOL_ITERATIONS`.
4. **Investigar o dedup sob carga** — teste falhou e voltou a passar com o mesmo código. Se aparecerem clientes duplicados em produção, é por aqui.
5. **`agente_clientes` sem coluna `agente`** — impede atribuir leads por assistente; o bloco Funil mostra o mesmo no A1 e no A2.
6. **Lembretes de visita 24h / follow-up 48h** — precisam de scheduler (cron GitHub Actions). É a condição para criar `agente_visitas`.
7. **`escalar_para_broker` via WhatsApp** — hoje só cria tarefa no painel; enviar mensagem depende do número do corretor.
8. **Corrigir dados a montante** — `responsavel` com valores de origem ("Internet", 892 registos); 8432 sem `data_criacao_iso`; `valor_negocio` quase vazio.
9. **Monitorizar o sync de oportunidades** contra o `sync_excel_supabase.py` externo (não devem duplicar) e decidir `teste_*` → produção.
10. **Telnyx PT** — regulatory requirement, comprar +351, secrets Fly.io.
11. Reavaliar se/quando voltar a incluir a validação CRM no cron diário.

---

## Decisões arquitecturais

**Texto completo e o porquê de cada uma: `docs/decisoes.md`.** Ler antes de mexer
na área respectiva — quase todas registam uma tentativa que já falhou ao vivo.

- **Um motor, N assistentes** — nunca N cópias do loop. A3/A4 = entrada no dict + linha em `agente_config`.
- **Subconjunto de tools por assistente é fronteira de segurança**, não organização (`consultar_*` só no `broker`).
- **Router por regex, não por LLM**; routing **sticky** em `agente_conversas.agente`, sentido único A2→A1.
- **`agente_config` é a tabela de assistentes** — não há lista em código; acrescentar = INSERT, não deploy.
- **Regras que não podem falhar vivem em `guards.py`** (dedup + 80%), nunca no prompt.
- **Dedup: o nome é sempre tentado**, aceite só quando nada contradiz (`_compativel`).
- **Fallback de tipologia dentro da tool** — o modelo perdia moradias T2 ao traduzir "T2"→`natureza`.
- **Tool forcing** na iteração 0 quando `_SEARCH_RE` bate; sem ele Claude prometia callbacks.
- **Assistentes nunca escrevem em `oportunidades`/`contactos`** — espelho do eGO, pipeline externo.
- **`publicado` é coluna GENERATED**; `disponivel_na_api` é a excepção escrita pela app.
- **Sync eGO sempre full, nunca incremental** — `?Since=` confirmado avariado.
- **CRM é a fonte com visibilidade total, mas só manual** — sobrepunha estados desactualizados no cron.
- **Playwright nunca na app principal** — RAM; o `scraper/` tem app Fly.io própria.
- **O eGO devolve a URL do export no JSON** — o popup nunca navega em datacenter.

## Bugs conhecidos

- **Timeout esporádico no sync de oportunidades** (`scraper/oportunidades_completo.py:217`,
  30s): confirmado 2026-07-30 — falha transiente do CRM eGO a responder a
  `POST /report/export`, não bug de código (retry manual resolveu). Se repetir com
  frequência, subir 30s→60s.
- **Dedup sob carga**: ver Próximos passos 4 — não reproduzido, não explicado.
- **Agente de voz** (bloqueado por Telnyx, nenhum destes se manifesta hoje): sem
  barge-in; sessões em memória, perdidas em restart; race condition (`is_speaking`
  vs `call.speak.ended`); janelas fixas de 2s sem VAD, podem cortar frases.

---

## Convenções

- **Python:** PEP 8, type hints, async. **React:** funcionais + hooks, sem classes.
- **Nomes:** código em inglês; UI em PT-PT. **DB:** português, snake_case.
- **Segredos:** nunca hardcoded. Só em `.env` / Fly.io secrets.

## Regras para o Claude Code

1. Ler `docs/PRD.md` antes de feature nova; `docs/database-schema.md` antes de
   tocar na DB; `docs/api-spec.md` antes de criar/alterar endpoints;
   `docs/decisoes.md` antes de contrariar uma decisão.
2. **Fase nova → seguir `planeamento-fases.md`. Plano antes de código. Sempre.**
   Uma fase de cada vez; primeira resposta = plano, nunca código directo.
3. Manter este ficheiro actualizado após cada fase. **Limite: 200 linhas** — o
   histórico vai para `docs/fases/`, as decisões para `docs/decisoes.md`.
4. Nunca inventar credenciais.
