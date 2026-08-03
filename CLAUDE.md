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

Backend **obrigatoriamente** em Fly.io — WebSockets persistentes para streaming de áudio.

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
├── db/supabase_client.py  ← get_supabase() [dados, projecto unificado] + get_supabase_auth() [só login]
└── models/          ← Pydantic (imovel, cliente, lead, tarefa, ...)

frontend/src/
├── App.jsx          ← React Router v6
├── components/      ← Layout, Sidebar (dark), ProtectedRoute
├── pages/           ← Dashboard, Clientes, Imoveis (abas: Portfólio/Tarefas/Sincronização), Leads, Chat, AgenteConfig (/agentes/:agente), Config
└── lib/             ← supabase.js, api.js

scraper/             ← app Fly.io separada, dedicada a Playwright (ver Decisões)
    app.py (POST /run/oportunidades-completo) · oportunidades_completo.py (lê a
    URL directa do export, não o popup) · mapping_todas_colunas.py · upsert.py
```

---

## Estado actual — Handoff 2026-08-02

### Produção

| Componente | URL | Estado |
|---|---|---|
| Backend | `https://figueirahome-agentos.fly.dev` | ✅ deployado (2026-08-03, `85221a4`), secrets eGO API+CRM+SCRAPER_SERVICE_* postos |
| Scraper oportunidades | `https://figueirahome-scraper.fly.dev` | ✅ app Fly.io separada (org `miguel-germano`, 1 vCPU/1GB, scale-to-zero) |
| Frontend | `https://figueirahome-agentos.pages.dev` | ✅ Cloudflare Pages, auto-deploy do push |
| WhatsApp | agente responde + pesquisa imóveis reais | ✅ end-to-end funcional |
| Cron sync eGO | `.github/workflows/sync-imoveis.yml` | ✅ diário (última run 2026-08-03T09:42, 54 actualizados), só **API** (CRM manual) + `workflow_dispatch` |
| Git | `https://github.com/imogermano-dotcom/figueirahome_agentOS` | ✅ master, tudo pushed |

### Assistentes A1/A2 (2026-08-02)

Motor único (`engine.py`) no lugar de 3 cérebros duplicados; assistentes por
configuração (`assistants.py`); router com stickiness; guardas em código
(`guards.py`). Saldo **−197 linhas**; primeiros testes do projecto. **Confirmado
end-to-end em produção — chat do painel e WhatsApp.**

### Fases anteriores — o histórico vive em `docs/fases/`

Só o que uma sessão nova precisa de saber para não partir nada. Cada fase tem
plano e resumo em `docs/fases/`.

| Quando | Fase | Migrations |
|---|---|---|
| 08-02 | Assistentes A1/A2 | `0014` |
| 08-03 | Dashboard | `0015` |
| 08-03 | Observabilidade + métricas em 4 blocos | `0016`–`0019` |
| 07-28/31 | Campos extra eGO (`plantas`, `video_url`, `destaque`); sync de oportunidades via app `scraper/` | `0012`, `0013` |

Invariantes que não são óbvias no código:

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

### Base de dados unificada

Todas as tabelas vivem no projecto Supabase secundário (`zphasvfopnbzwnaidsnw`, settings `supabase_imoveis_*`). Projecto original (`supabase_url/key`) fica **só Auth**. `get_supabase()` = dados; `get_supabase_auth()` = só valida login.

### Sincronismo eGO

`backend/app/integrations/imoveis_sync.py`: `sync_egorealestate_api()` (Web API pública, full pull paginado, cron diário) e `sync_egorealestate_crm()` (CRM autenticado, visibilidade total incl. não-publicados, só via botão "Validar CRM", fora do cron — ver Decisões). Coluna `publicado` (GENERATED STORED, migration `0008`) e `disponivel_na_api` (plain boolean).

### Ambiente local

- Python: `C:\Users\joaoa\AppData\Local\Programs\Python\Python312\python.exe`
- fly CLI: `C:\Users\joaoa\.fly\bin\flyctl.exe deploy --app <nome>` (a partir de `backend/` ou `scraper/`)
- `backend/.env` / `scraper/.env` — Supabase (ambos) ✅, Anthropic ✅, OpenAI ✅, eGO API+CRM ✅, SCRAPER_SERVICE_* ✅, Telnyx ❌, Meta ❌
- Scrapers Playwright: `pip install -r <pasta>/requirements*.txt` + `playwright install chromium`

### Bloqueadores activos

| Item | Estado |
|---|---|
| Credenciais Telnyx (3 vars) | ❌ bloqueia chamadas de voz |
| Número PT +351 Telnyx | ❌ requer regulatory requirement group |
| Número WhatsApp do corretor | ⚠️ escalada já funciona via `agente_tarefas`; só a notificação por WhatsApp está bloqueada |
| ~3459 linhas `fonte='manual'`/`Em Prospecção` de origem desconhecida | ⚠️ investigação parada a pedido do utilizador — não mexer sem ser pedido de novo |

### Próximos passos

1. **Decidir promoção `teste_imoveis`/`teste_oportunidades` → produção** — ou manter só como consulta manual pontual.
2. **Monitorizar sync de oportunidades completo** em paralelo ao `sync_excel_supabase.py` externo (confirmar que não duplicam/conflituam).
3. **Assistentes A3 (Recrutamento) e A4 (Angariador)** — adiados da fase A1/A2. Router já os reconhece e encaminha para o A2; falta criar as linhas em `agente_config` e os prompts.
4. **A1 — sub-fluxos SC (simulação de crédito) e FP (propostas)** — adiados. A *escalada* do FP já está honrada via `escalar_para_humano`.
5. **Confirmar a latência com tráfego real** — 10,1s num turno com pesquisa (só 3 turnos medidos). Ver a p95 em Assistentes → A1 → Métricas antes de mexer em `_MAX_TOOL_ITERATIONS`.
6. **Investigar o dedup sob carga** — um teste falhou e voltou a passar com o mesmo código; hipótese não confirmada de atraso leitura-após-escrita no PostgREST. Se aparecerem clientes duplicados em produção, é por aqui.
7. **`agente_clientes` sem coluna `agente`** — impede atribuir leads por assistente; o bloco Funil mostra o mesmo no A1 e no A2.
8. **Lembretes de visita 24h / follow-up 48h** — precisam de scheduler (cron GitHub Actions é o hospedeiro óbvio). É a condição para criar `agente_visitas`; até lá as visitas vivem em `agente_tarefas`.
9. **Corrigir dados a montante** — `responsavel` das oportunidades tem valores de origem ("Internet" em 892 registos); 8432 sem `data_criacao_iso`; `valor_negocio` quase vazio. Enquanto assim for, não há gráficos de evolução nem de receita.
10. **`escalar_para_broker` via WhatsApp** — hoje escala para `agente_tarefas` (visível no painel). Enviar mensagem ao corretor ainda depende do número dele.
11. **Telnyx PT** — regulatory requirement, comprar +351, configurar secrets Fly.io.
12. Reavaliar se/quando voltar a incluir a validação CRM no cron diário.

---

## Decisões arquitecturais

- **Um motor, N assistentes — nunca N cópias do loop**: assistentes distinguem-se por 3 coisas em `assistants.ASSISTENTES` (prompt base, subconjunto de tools, tool forcing), não por código próprio. Antes havia 3 loops agênticos duplicados que divergiam em silêncio: só um tinha prompt caching, só um tinha tool forcing. Acrescentar A3/A4 é uma entrada no dict + uma linha em `agente_config`, não um ficheiro novo.
- **Subconjunto de tools por assistente é uma fronteira de segurança, não organização**: `consultar_clientes`/`consultar_leads` expõem a base de clientes da agência e o mesmo endpoint (`/api/broker/chat`) serve agora clientes no banco de ensaio. Restritas ao assistente `broker`. Não alargar sem pensar em quem fala com o endpoint.
- **Router por regex, não por LLM**: o nível 1 da spec é uma tabela de keywords que escolhe entre dois baldes, um dos quais é "não classificado". Falhas são baratas nos dois sentidos (keyword falhada cai no A2, que encaminha). Upgrade só se os logs mostrarem má taxa de acerto — e mesmo aí, classificação forçada só na 1ª mensagem da thread, nunca uma chamada por mensagem.
- **Routing sticky em `agente_conversas.agente`** (migration `0014`): a thread fica com o assistente decidido, em vez de ser re-classificada a cada mensagem. Sentido único — A2→A1 com sinal de compra, nunca A1→A2 (uma thread de comprador não volta atrás e perde o contexto de qualificação).
- **`agente_config` é a tabela de assistentes; não há lista em código**: `AGENTES_VALIDOS` foi removido de `api/config.py`. A validação é "a linha existe". Acrescentar assistente = INSERT, não deploy. `instrucoes` do A2 faz de base de conhecimento editável (horários, morada, serviços) — foi por isso que a tabela `agency_knowledge` da spec foi rejeitada.
- **Regras que não podem falhar vivem em `guards.py`, não no prompt**: dedup de clientes (única via de escrita — havia 4 upserts artesanais que duplicavam entre canais) e regra dos 80% dentro de `agendar_visita`, antes de qualquer escrita. Um LLM esquece uma regra; um `if` não.
- **Dedup: o nome é sempre tentado, mesmo com telefone presente**. A ordem é telefone → email → nome, mas a procura por nome corre *também* quando telefone/email não deram correspondência — antes era saltada (`if nome and not telefone`), e isso duplicava a pessoa no padrão mais comum de uma conversa: `guardar_dados_cliente` grava o nome sem telefone (o modelo nem sempre o passa) e `agendar_visita` traz o telefone no turno seguinte. A correspondência por nome só é aceite quando nada contradiz (`_compativel`): telefone/email vazios ou iguais. Dois homónimos com telefones diferentes continuam a ser duas pessoas — a spec proíbe fundir por nome sozinho.
- **Fallback de tipologia dentro da tool, não no prompt**: o modelo traduz "T2" para `natureza="Apartamento"` e perde as moradias T2 — observado ao vivo a responder "não temos" havendo uma moradia T2 a 65k. Zero resultados com `natureza` dispara segunda pesquisa sem esse filtro. O nível 1 do fallback da spec (§3.2 SI-B fase 5) é determinístico; os níveis 2 e 3 continuam no prompt.
- **Tabelas da spec dos assistentes rejeitadas por duplicação**: `ai_conversations`→`agente_conversas`, `ai_messages`→`mensagens` jsonb, `ai_visit_bookings`→`agente_tarefas` (já indexada e já no painel), `agency_knowledge`→`agente_config.instrucoes`. `consultants`/`agency_info`/`properties`/`feedback_queries` não existem — a spec inventou-as. Migration `0014` = 1 coluna e 2 linhas de seed, mais nada.
- **Assistentes nunca escrevem em `oportunidades`/`contactos`**: são espelho do eGO, escritos por pipeline externo. `pref_*` só via RPC `bulk_update_prefs` com `pref_extraido_em IS NULL`; `contactos` tem PK `(nome, criado_em)` mas o sync usa `ego_link` — insert nosso colide ou fica órfão. Leitura sim, escrita não. A spec §2.5 pede o contrário; ignorar.
- **Agente unificado**: `agente_config[agente='voz']` é a persona da voz telefónica. Atendimento ao cliente (WhatsApp, web) passou para `a1_vendedor`/`a2_geral`. `agente_config[agente='broker']` continua exclusivo do corretor.
- **Dois projectos Supabase, papéis divididos**: `get_supabase()` = todos os dados (projecto `zphasvfopnbzwnaidsnw`, dados unificados desde 2026-07-21); `get_supabase_auth()` = só validação de login (projecto original, onde vivem as contas reais). Backend usa sempre `service_role_key` para dados — nunca passa o JWT ao Postgres — por isso um token emitido pelo projecto de Auth valida-se normalmente mesmo com os dados noutro projecto (RLS nunca chega a ser avaliado). Lazy singletons em `db/supabase_client.py`.
- **Tool forcing**: quando o utilizador menciona critérios de pesquisa (regex `_SEARCH_RE`, em `assistants.py`), `tool_choice: {"type":"tool","name":"pesquisar_imoveis"}` é forçado na iteração 0. Sem este mecanismo Claude ignorava as tools e prometia callbacks. Hoje é declarado por assistente (`spec["force"]`), não hardcoded — mas o regex e o comportamento são os mesmos, provados em produção. Não remover sem reconfirmar ao vivo.
- **Prompt caching**: system prompt como lista com `cache_control: ephemeral` + beta header. Cache hits custam 10% do preço normal.
- **Aging de conversas**: `load_conversation` verifica `atualizado_em`; se > 48h retorna `None, []` e `save_conversation` cria nova linha.
- **Tailwind v4** via `@tailwindcss/vite` — sem `tailwind.config.js`
- **Auth backend**: `require_auth` FastAPI Depends por router; RLS activo (service_role_key no backend = bypass automático)
- **Supabase backend**: sync via `asyncio.run_in_executor()` (supabase-py é síncrono)
- **TTS** via `speak()` REST, não via WebSocket; **µ-law decode** manual (sem `audioop`, removido no Python 3.13)
- **Extracção de dados voz**: só no hangup (Claude tool use sobre transcrição completa)
- **CORS**: `frontend_url` + regex `*.figueirahome-agentos.pages.dev` para preview deploys
- **Sync eGO sempre full, nunca incremental**: `/v1/Properties/Latest?Since=` confirmado avariado (ignora `Since`, devolve sempre 1 imóvel) — não tentar reintroduzir cursor incremental nesta API sem reconfirmar que o eGO corrigiu o bug.
- **CRM backoffice como fonte de verdade de `disponibilidade`, mas não no cron automático**: Web API pública só vê publicados; o CRM autenticado (`egorealestate_crm.py`) é a única fonte com visibilidade total, usado para criar/corrigir linhas fora do alcance da API pública — mas por sobrepor às vezes um estado "Disponível" que a API pública já confirmava (dados desactualizados do lado do CRM), passou a correr só manual, não no cron diário.
- **"Sem acesso" no CRM ≠ permissão negada por defeito**: uma ficha que devolve "Você não pode consultar este imóvel" é, mais frequentemente, um `ego_id` desactualizado (imóvel recriado com novo ID) do que uma restrição real de permissão — `find_by_ref()` (campo `FreeText`, não `searchText`) resolve isto automaticamente antes de sinalizar tarefa.
- **`publicado` como coluna GENERATED, não campo escrito pela app**: critério de publicação no site é puramente função de outras colunas da mesma linha (`disponibilidade`, `imovel_ref`, preços, `disponivel_na_api`) — Postgres recalcula sempre, nunca dessincroniza. `disponivel_na_api` é a excepção (plain boolean): só a app sabe, a cada pull da API, se um ref ainda foi devolvido.
- **Scrapers de relatório eGO em `backend/scripts/` (imóveis, oportunidades 48h/notas) correm só local**: Chromium headless excede a RAM da app principal (256MB). O scraper de oportunidades completo (`scraper/`) é a excepção — tem app Fly.io própria e dedicada (`figueirahome-scraper`, 1GB, scale-to-zero) só para isto, para não subir a RAM da app principal 24/7. Não juntar Playwright à app principal.
- **Staging antes de produção para dados de scraping — excepto onde já confirmado com o utilizador**: regra por defeito continua a ser `teste_*` primeiro (`imoveis`, `oportunidades` via `backend/scripts/`). O sync de oportunidades completo (`scraper/`) é uma excepção explicitamente aprovada pelo utilizador — escreve direto em produção, validado ao vivo antes de activar.
- **Popup de download do eGO não funciona em Fly.io/browser headless em datacenter**: confirmado ao vivo — `POST /egocore/report/export` responde 200 e abre popup, mas o popup nunca navega (fica em branco para sempre), nunca reproduzido em dev local. A resposta JSON de `/report/export` já traz a URL directa do ficheiro no campo `data` (domínio `media.egorealestate.com`, assinada) — usar essa URL directamente via httpx em vez de esperar pelo popup/evento `download` do browser. Os scrapers antigos (`backend/scripts/`) ainda usam o mecanismo de popup porque só correm local (nunca expostos a este problema) — se algum dia forem para Fly.io, aplicar a mesma técnica.
- **Formato PT do eGO precisa de conversão antes de upsert em produção**: preços vêm com vírgula decimal ("240000,0" — Postgres `numeric` rejeita), datas em "dd/mm/aaaa" (Postgres `date`/`timestamptz` com datestyle ISO rejeita). `scraper/mapping_todas_colunas.py` converte antes de qualquer upsert — confirmado por erros reais em produção antes do fix.
- **`contactos` tem chave primária real `(nome, criado_em)`, não `ego_link`**: ao contrário do que a doc do pipeline externo recomendava. Duas pessoas reais podem partilhar nome+data (visto ao vivo). `scraper/upsert.py` faz upsert registo-a-registo por `ego_link` e ignora (loga, não aborta o lote) colisões de `(nome, criado_em)` — não tentar "resolver" fundindo os dois registos.

## Bugs conhecidos

- **Timeout esporádico no sync de oportunidades** (`scraper/oportunidades_completo.py:217`, 30s): confirmado 2026-07-30 — falha transiente do CRM eGO em responder a `POST /report/export`, não bug de código (retry manual resolveu de imediato). Teoria do comentário no código (eGO envia por email se resultado grande) não confirmada. Se repetir com frequência, subir timeout 30s→60s.
- **Agente de voz** (bloqueado por Telnyx, nenhum destes se manifesta hoje): sem barge-in; sessões em memória, perdidas em restart; race condition (`is_speaking` vs `call.speak.ended`); janelas fixas de 2s sem VAD, podem cortar frases.

---

## Convenções

- **Python:** PEP 8, type hints, async.
- **React:** componentes funcionais + hooks. Sem class components.
- **Nomes:** código em inglês; UI em PT-PT.
- **DB:** tabelas e colunas em português, snake_case.
- **Segredos:** nunca hardcoded. Só em `.env` / Fly.io secrets.

---

## Regras para o Claude Code

1. Ler `docs/PRD.md` antes de feature nova.
2. Consultar `docs/database-schema.md` antes de tocar na DB.
3. Consultar `docs/api-spec.md` antes de criar/alterar endpoints.
4. **Fase nova → seguir `planeamento-fases.md`. Plano antes de código. Sempre.**
5. Uma fase de cada vez. Primeira resposta a fase nova = plano (nunca código directo).
6. Manter este ficheiro actualizado após cada fase. Limite: 200 linhas.
7. Nunca inventar credenciais.
