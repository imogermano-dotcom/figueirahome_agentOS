# Decisões arquitecturais

> Arquivo das decisões tomadas e o **porquê** de cada uma. Saiu do `CLAUDE.md`
> em 2026-08-03 por limite de linhas; o `CLAUDE.md` mantém só o resumo de uma
> linha por decisão e aponta para aqui.
>
> Regra: se uma decisão for revertida, não apagar — escrever a nova por baixo
> com a data. O valor deste ficheiro é impedir que alguém repita uma tentativa
> que já falhou ao vivo.

---

## Assistentes (A1 / A2 / broker)

- **Um motor, N assistentes — nunca N cópias do loop**: assistentes distinguem-se por 3 coisas em `assistants.ASSISTENTES` (prompt base, subconjunto de tools, tool forcing), não por código próprio. Antes havia 3 loops agênticos duplicados que divergiam em silêncio: só um tinha prompt caching, só um tinha tool forcing. Acrescentar A3/A4 é uma entrada no dict + uma linha em `agente_config`, não um ficheiro novo.
- **Subconjunto de tools por assistente é uma fronteira de segurança, não organização**: `consultar_clientes`/`consultar_leads` expõem a base de clientes da agência e o mesmo endpoint (`/api/broker/chat`) serve agora clientes no banco de ensaio. Restritas ao assistente `broker`. Não alargar sem pensar em quem fala com o endpoint.
- **Router por regex, não por LLM**: o nível 1 da spec é uma tabela de keywords que escolhe entre dois baldes, um dos quais é "não classificado". Falhas são baratas nos dois sentidos (keyword falhada cai no A2, que encaminha). Upgrade só se os logs mostrarem má taxa de acerto — e mesmo aí, classificação forçada só na 1ª mensagem da thread, nunca uma chamada por mensagem.
- **Routing sticky em `agente_conversas.agente`** (migration `0014`): a thread fica com o assistente decidido, em vez de ser re-classificada a cada mensagem. Sentido único — A2→A1 com sinal de compra, nunca A1→A2 (uma thread de comprador não volta atrás e perde o contexto de qualificação).
- **`agente_config` é a tabela de assistentes; não há lista em código**: `AGENTES_VALIDOS` foi removido de `api/config.py`. A validação é "a linha existe". Acrescentar assistente = INSERT, não deploy. `instrucoes` do A2 faz de base de conhecimento editável (horários, morada, serviços) — foi por isso que a tabela `agency_knowledge` da spec foi rejeitada.
- **Agente unificado**: `agente_config[agente='voz']` é a persona da voz telefónica. Atendimento ao cliente (WhatsApp, web) passou para `a1_vendedor`/`a2_geral`. `agente_config[agente='broker']` continua exclusivo do corretor.
- **Tool forcing**: quando o utilizador menciona critérios de pesquisa (regex `_SEARCH_RE`, em `assistants.py`), `tool_choice: {"type":"tool","name":"pesquisar_imoveis"}` é forçado na iteração 0. Sem este mecanismo Claude ignorava as tools e prometia callbacks. Hoje é declarado por assistente (`spec["force"]`), não hardcoded — mas o regex e o comportamento são os mesmos, provados em produção. Não remover sem reconfirmar ao vivo.
- **Prompt caching**: system prompt como lista com `cache_control: ephemeral` + beta header. Cache hits custam 10% do preço normal.
- **Aging de conversas**: `load_conversation` verifica `atualizado_em`; se > 48h retorna `None, []` e `save_conversation` cria nova linha.
- **`agente_config[a1_vendedor].instrucoes` carregado a 2026-08-06** com o ficheiro que o Miguel entregou (`kb-a1-vendedor.md`, raiz do repo). Até aqui tinha só o texto placeholder da seed da migration `0014` (112 caracteres) — o agente respondia no WhatsApp a partir do prompt base, nunca da base de conhecimento real. Valor anterior fez backup fora do repo antes de sobrescrever.

## Regras de negócio em código

- **Regras que não podem falhar vivem em `guards.py`, não no prompt**: dedup de clientes (única via de escrita — havia 4 upserts artesanais que duplicavam entre canais) e regra dos 80% dentro de `agendar_visita`, antes de qualquer escrita. Um LLM esquece uma regra; um `if` não.
- **Dedup: o nome é sempre tentado, mesmo com telefone presente**. A ordem é telefone → email → nome, mas a procura por nome corre *também* quando telefone/email não deram correspondência — antes era saltada (`if nome and not telefone`), e isso duplicava a pessoa no padrão mais comum de uma conversa: `guardar_dados_cliente` grava o nome sem telefone (o modelo nem sempre o passa) e `agendar_visita` traz o telefone no turno seguinte. A correspondência por nome só é aceite quando nada contradiz (`_compativel`): telefone/email vazios ou iguais. Dois homónimos com telefones diferentes continuam a ser duas pessoas — a spec proíbe fundir por nome sozinho.
- **Fallback de tipologia dentro da tool, não no prompt**: o modelo traduz "T2" para `natureza="Apartamento"` e perde as moradias T2 — observado ao vivo a responder "não temos" havendo uma moradia T2 a 65k. Zero resultados com `natureza` dispara segunda pesquisa sem esse filtro. O nível 1 do fallback da spec (§3.2 SI-B fase 5) é determinístico; os níveis 2 e 3 continuam no prompt.

## Dados e esquema

- **Tabelas da spec dos assistentes rejeitadas por duplicação**: `ai_conversations`→`agente_conversas`, `ai_messages`→`mensagens` jsonb, `ai_visit_bookings`→`agente_tarefas` (já indexada e já no painel), `agency_knowledge`→`agente_config.instrucoes`. `consultants`/`agency_info`/`properties`/`feedback_queries` não existem — a spec inventou-as. Migration `0014` = 1 coluna e 2 linhas de seed, mais nada.
- **Assistentes nunca escrevem em `oportunidades`/`contactos`**: são espelho do eGO, escritos por pipeline externo. `pref_*` só via RPC `bulk_update_prefs` com `pref_extraido_em IS NULL`; `contactos` tem PK `(nome, criado_em)` mas o sync usa `ego_link` — insert nosso colide ou fica órfão. Leitura sim, escrita não. A spec §2.5 pede o contrário; ignorar.
- **`contactos` tem chave primária real `(nome, criado_em)`, não `ego_link`**: ao contrário do que a doc do pipeline externo recomendava. Duas pessoas reais podem partilhar nome+data (visto ao vivo). `scraper/upsert.py` faz upsert registo-a-registo por `ego_link` e ignora (loga, não aborta o lote) colisões de `(nome, criado_em)` — não tentar "resolver" fundindo os dois registos.
- **`publicado` como coluna GENERATED, não campo escrito pela app**: critério de publicação no site é puramente função de outras colunas da mesma linha (`disponibilidade`, `imovel_ref`, preços, `disponivel_na_api`) — Postgres recalcula sempre, nunca dessincroniza. `disponivel_na_api` é a excepção (plain boolean): só a app sabe, a cada pull da API, se um ref ainda foi devolvido.
- **Dois projectos Supabase, papéis divididos**: `get_supabase()` = todos os dados (projecto `zphasvfopnbzwnaidsnw`, dados unificados desde 2026-07-21); `get_supabase_auth()` = só validação de login (projecto original, onde vivem as contas reais). Backend usa sempre `service_role_key` para dados — nunca passa o JWT ao Postgres — por isso um token emitido pelo projecto de Auth valida-se normalmente mesmo com os dados noutro projecto (RLS nunca chega a ser avaliado). Lazy singletons em `db/supabase_client.py`.

## Integração eGO

- **Sync eGO sempre full, nunca incremental**: `/v1/Properties/Latest?Since=` confirmado avariado (ignora `Since`, devolve sempre 1 imóvel) — não tentar reintroduzir cursor incremental nesta API sem reconfirmar que o eGO corrigiu o bug.
- **CRM backoffice como fonte de verdade de `disponibilidade`, mas não no cron automático**: Web API pública só vê publicados; o CRM autenticado (`egorealestate_crm.py`) é a única fonte com visibilidade total, usado para criar/corrigir linhas fora do alcance da API pública — mas por sobrepor às vezes um estado "Disponível" que a API pública já confirmava (dados desactualizados do lado do CRM), passou a correr só manual, não no cron diário.
- **"Sem acesso" no CRM ≠ permissão negada por defeito**: uma ficha que devolve "Você não pode consultar este imóvel" é, mais frequentemente, um `ego_id` desactualizado (imóvel recriado com novo ID) do que uma restrição real de permissão — `find_by_ref()` (campo `FreeText`, não `searchText`) resolve isto automaticamente antes de sinalizar tarefa.
- **Popup de download do eGO não funciona em Fly.io/browser headless em datacenter**: confirmado ao vivo — `POST /egocore/report/export` responde 200 e abre popup, mas o popup nunca navega (fica em branco para sempre), nunca reproduzido em dev local. A resposta JSON de `/report/export` já traz a URL directa do ficheiro no campo `data` (domínio `media.egorealestate.com`, assinada) — usar essa URL directamente via httpx em vez de esperar pelo popup/evento `download` do browser. Os scrapers antigos (`backend/scripts/`) ainda usam o mecanismo de popup porque só correm local (nunca expostos a este problema) — se algum dia forem para Fly.io, aplicar a mesma técnica.
- **Formato PT do eGO precisa de conversão antes de upsert em produção**: preços vêm com vírgula decimal ("240000,0" — Postgres `numeric` rejeita), datas em "dd/mm/aaaa" (Postgres `date`/`timestamptz` com datestyle ISO rejeita). `scraper/mapping_todas_colunas.py` converte antes de qualquer upsert — confirmado por erros reais em produção antes do fix.

## Infra e scrapers

- **Scrapers de relatório eGO em `backend/scripts/` (imóveis, oportunidades 48h/notas) correm só local**: Chromium headless excede a RAM da app principal (256MB). O scraper de oportunidades completo (`scraper/`) é a excepção — tem app Fly.io própria e dedicada (`figueirahome-scraper`, 1GB, scale-to-zero) só para isto, para não subir a RAM da app principal 24/7. Não juntar Playwright à app principal.
- **Staging antes de produção para dados de scraping — excepto onde já confirmado com o utilizador**: regra por defeito continua a ser `teste_*` primeiro (`imoveis`, `oportunidades` via `backend/scripts/`). O sync de oportunidades completo (`scraper/`) é uma excepção explicitamente aprovada pelo utilizador — escreve direto em produção, validado ao vivo antes de activar.
- **Backend obrigatoriamente em Fly.io**: WebSockets persistentes para streaming de áudio do agente de voz. Cloudflare Workers e serverless em geral não servem.

## Frontend e API

- **Tailwind v4** via `@tailwindcss/vite` — sem `tailwind.config.js`.
- **Auth backend**: `require_auth` FastAPI Depends por router; RLS activo (service_role_key no backend = bypass automático).
- **Supabase backend**: sync via `asyncio.run_in_executor()` (supabase-py é síncrono).
- **CORS**: `frontend_url` + regex `*.figueirahome-agentos.pages.dev` para preview deploys.

## Voz (Telnyx)

- **TTS** via `speak()` REST, não via WebSocket; **µ-law decode** manual (sem `audioop`, removido no Python 3.13).
- **Extracção de dados de voz**: só no hangup (Claude tool use sobre a transcrição completa), não turno a turno.
