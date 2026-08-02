# Plano — Reformulação dos Agentes: Fundação + A2 + A1

> Destino final: `docs/fases/assistentes-a1-a2-plano.md` (passo 0 da implementação, conforme `planeamento-fases.md`).

## Contexto

`assistentes-ia-especificacao.md` (raiz do repo, convertido do docx) especifica 4 assistentes: **A1 Vendedor**, **A2 Geral**, **A3 Recrutamento**, **A4 Angariador**. Hoje o backend tem **3 cérebros duplicados** e nenhum roteamento:

| Ficheiro | O que é | Problema |
|---|---|---|
| `agents/voice/whatsapp_intake.py` (374 l.) | O **verdadeiro** agente WhatsApp | Vive em `voice/`, não é voz |
| `agents/broker/claude_agent.py` (120 l.) | Chat web interno | Mesmo loop, sem caching, sem tool forcing |
| `agents/voice/claude_agent.py` (69 l.) | Voz telefónica | SDK em vez de httpx; bloqueado (sem Telnyx) |

Import circular real: `broker/channels/whatsapp/webhook.py:8` → `voice/whatsapp_intake.py:9` → `broker/conversation.py`. `_load_config()` duplicado 3×, com o mesmo bug: `extra = ... if persona else ""` descarta `instrucoes` sempre que `persona` está vazia. `agente_config.ativo` é gravado e editável no painel mas **nunca lido** — não há kill switch.

**Resultado pretendido:** um motor único, assistentes definidos por configuração (prompt + subconjunto de tools), router de intenção, A2 e A1 (SI-A/SI-B/SV) a funcionar em WhatsApp e no chat web do painel.

### Decisões de âmbito (aprovadas)
1. **FastAPI nativo — sem Make/n8n.** O backend já faz webhook → router → Claude → Supabase.
2. **Esta fase = Fundação + A2 + A1 (SI-A, SI-B, SV).** A3, A4, SC (crédito) e FP (propostas) ficam para depois.
3. **Canais = WhatsApp (Meta, já vivo) + chat web** (`/api/broker/chat` como banco de ensaio).
4. **Regras:** prompt trata tom/fluxo; **código** garante o que não pode falhar — dedup de contactos e regra dos 80%.

### Conflitos spec ↔ realidade (resolvidos)
- **Fictícias, não existem:** `ai_conversations`, `ai_messages`, `ai_visit_bookings`, `agency_knowledge`, `consultants`, `agency_info`, `properties`, `feedback_queries`. Mapeadas para tabelas reais em §3. O aviso RLS sobre `feedback_queries` descreve tabela inexistente — nada a fazer.
- **Escrever em `oportunidades`/`contactos` (spec §2.5) — rejeitado.** São espelho do eGO, escritos por pipeline externo. `oportunidades.pref_*` só via RPC `bulk_update_prefs` quando `pref_extraido_em IS NULL`; `contactos` tem PK `(nome, criado_em)` mas o sync usa `ego_link` — insert nosso colide ou fica órfão. **Leitura sim, escrita não.**
- Modelo: repo usa `claude-sonnet-4-6` (spec diz 4-5). Mantém-se o do repo.
- `disponibilidade='Disponível'` da spec → usar `publicado` (coluna GENERATED da migration 0008, mais forte e indexada).
- Spec §2.2 usa "hora do contacto" no router, mas §3.4 diz "24/7" — contraditório. Horário fica no prompt, fora do router.

---

## 1. Estrutura alvo

```
backend/app/agents/broker/
├── engine.py        NOVO   o único loop agêntico (extraído de whatsapp_intake.py)
├── assistants.py    NOVO   registry: prompt base + tools + max_tokens + load_config()
├── router.py        NOVO   router por keywords + stickiness (puro, sem I/O)
├── guards.py        NOVO   normalização, find_or_create_cliente, visita_permitida
├── tools.py         EDIT   passa a registry de tools de todos os assistentes
├── conversation.py  EDIT   load/save transportam `agente`
├── claude_agent.py  APAGA
└── channels/whatsapp/webhook.py  EDIT (1 linha de import)

backend/app/agents/voice/
├── whatsapp_intake.py  APAGA          ← mata o ciclo de imports
├── claude_agent.py     EDIT (~5 l.)   _load_config → assistants.load_config
└── save_call.py        EDIT (~20 l. a menos) → guards.find_or_create_cliente
```

O ciclo de imports desaparece por **apagar**, não por refactor. Restam imports só num sentido (`voice → broker`).

---

## 2. Motor e registry

```python
# engine.py
async def responder(canal: str, participante: str, mensagem: str,
                    agente: str | None = None) -> str
```

Ordem de resolução:
1. `conversa_id, mensagens, agente_atual = await load_conversation(canal, participante)`
2. `agente = agente or route(mensagem, agente_atual)`
3. `spec = ASSISTENTES[agente]` — dict simples em `assistants.py`:
   ```python
   ASSISTENTES = {
     "a1_vendedor": {"prompt": PROMPT_A1, "force": ("pesquisar_imoveis", _SEARCH_RE),
        "tools": ["pesquisar_imoveis","ficha_imovel","guardar_dados_cliente",
                  "agendar_visita","escalar_para_humano"]},
     "a2_geral":    {"prompt": PROMPT_A2, "force": None,
        "tools": ["guardar_dados_cliente","escalar_para_humano"]},
     "broker":      {"prompt": PROMPT_BROKER, "force": None,
        "tools": ["consultar_clientes","consultar_imoveis","consultar_leads"]},
   }
   MAX_TOKENS = {"whatsapp": 512, "web": 1024}
   ```
4. `extra, ativo = await load_config(agente)` — **se `ativo is False`: devolve linha de handoff e não chama a Anthropic** (kill switch, zero tokens). Corrige também o bug do `persona` vazia: junta as partes não-vazias em vez de gatilhar em `persona`.
5. System prompt = `spec["prompt"] + perfil_cliente + extra`. `perfil_cliente` só quando `canal == "whatsapp"` (no web, `participante` não é telefone).
6. **Preservar verbatim de `whatsapp_intake.py:289-292`:** header `anthropic-beta: prompt-caching-2024-07-31` + system como lista com `cache_control: ephemeral`. Adicionar `temperature: 0.4` (spec §2.3; hoje não está definido → default 1.0).
7. **Preservar verbatim de `whatsapp_intake.py:296,307`:** tool forcing na iteração 0 quando o regex casa — agora parametrizado por `spec["force"]`. CLAUDE.md regista que sem isto o Claude ignorava tools e prometia callbacks.
8. `_MAX_TOOL_ITERATIONS = 4` (era 3 WhatsApp / 5 broker; A1 encadeia lookup→save→agendar).

O subconjunto de tools por assistente é **a razão principal do registry**: hoje `consultar_clientes` está exposto no mesmo endpoint que vai servir clientes no banco de ensaio — um cliente podia pedir a lista de clientes da agência.

---

## 3. Router

`router.py` — uma função pura, sem DB, sem rede:

```python
def route(mensagem: str, agente_atual: str | None) -> str
```

| # | Sinal | Resultado |
|---|---|---|
| 1 | argumento `agente=` explícito | esse (não passa por aqui) |
| 2 | `agente_atual` definido **e** sem sinal forte de A1 | `agente_atual` — sticky |
| 3 | keyword A1 | `a1_vendedor` |
| 4 | resto | `a2_geral` — fallback por design |

Stickiness num sentido só: A2→A1 com sinal forte, nunca A1→A2. **Sem keywords para A3/A4** — encaminhar para assistente inexistente é pior que o A2 tratar; o prompt do A2 já recolhe contacto e promete follow-up. Marcar com `# ponytail:` a via de upgrade.

**Regex, não LLM.** Um router LLM custa ~700ms e uma chamada em *cada* mensagem para escolher entre dois baldes, um dos quais é, por definição da spec, "não classificado". Falhas são baratas nos dois sentidos: keyword falhada cai no A2, cujo trabalho é perceber e passar; falso A1 custa uma pergunta de qualificação. Além disso o `_SEARCH_RE` já apanha intenção de imóvel *dentro* do A1 via tool forcing. Se os logs mostrarem má taxa de acerto, o upgrade é uma tool de classificação forçada **só na primeira mensagem da thread**.

**Banco de ensaio web.** `Agente2.jsx` envia `participante: "painel_<agente>"` + `agente` explícito, dando thread isolada a cada assistente. O selector inclui **"Auto (router)"** (`agente: null`) — é assim que se testa o router pelo painel. Threads web saltam o lookup por telefone, e `find_or_create_cliente` recusa criar cliente sem telefone nem email, por isso o ensaio não polui `agente_clientes`.

---

## 4. Migration `0014_assistentes.sql`

```sql
-- 1 coluna: routing sticky. agente_conversas só tem `canal` hoje.
alter table agente_conversas add column if not exists agente text;
comment on column agente_conversas.agente is
  'a1_vendedor | a2_geral | broker — assistente que detém a thread (routing sticky)';

-- 2 linhas: agente_config JÁ É a tabela de assistentes.
-- Semear evita ter de transformar o PUT /api/config/{agente} em upsert.
insert into agente_config (agente, persona, instrucoes) values
  ('a1_vendedor', '...', '...'),
  ('a2_geral',    '...', '...')
on conflict (agente) do nothing;
```

É a migration **inteira**. O que **não** se cria e porquê:

| Spec pede | Decisão |
|---|---|
| `ai_conversations` | `agente_conversas` + nova coluna `agente` já cobre canal/assistente/participante |
| `ai_messages` | Já é o jsonb `mensagens`. Segunda tabela não compra nada neste volume |
| `ai_visit_bookings` | `agente_tarefas` — ver §5 |
| `agency_knowledge` | `agente_config[a2_geral].instrucoes`, editável no painel sem deploy — exactamente o propósito declarado |
| `consultants` / `agency_info` | Não existem, sem dados e sem dono. Fluxos ajustados em §8 |
| índice único em `agente_clientes.telefone` | **Não.** Produção tem formatos mistos (`912…`, `351912…`) — o índice falhava a criar. Dedup trata disto em código (§6) |

---

## 5. Tools

**Reutilizadas tal como estão:** `consultar_clientes`, `consultar_imoveis`, `consultar_leads` — mas **restritas ao assistente `broker`** pelo registry.

**Corrigidas:**
- `pesquisar_imoveis` (`whatsapp_intake.py:120-171`), três bugs reais:
  1. **Sem filtro de disponibilidade** — devolve vendidos/retirados. → `.eq("publicado", True)`.
  2. `.limit(5)` → `.limit(3)` + `.order("venda_preco")` (spec §3.2 SI-B: até 3, ascendente).
  3. Zona só por `concelho`; spec quer `concelho OR freguesia OR zona`. → `.or_()`.
  Acrescentar `preco_min`.
- `execute_tool` (`tools.py:143`) devolve `str(result)` — repr Python com plicas, não JSON. → `json.dumps(..., ensure_ascii=False, default=str)`. Uma linha, menos tokens.

**Novas (4, pequenas):**

| Tool | Assistente | Para quê |
|---|---|---|
| `ficha_imovel(imovel_ref \| morada)` | A1 | SI-A precisa de lookup de imóvel único; `pesquisar_imoveis` não faz |
| `agendar_visita(imovel_ref, nome, telefone, data_hora_texto, orcamento)` | A1 | SV. **Aplica a regra dos 80% antes de escrever** |
| `escalar_para_humano(motivo, resumo)` | A1 + A2 | Ramos de reclamação/legal do A2; e "quero fazer proposta" no A1 — FP está fora de âmbito mas a regra 6 da spec (*FP escala sempre*) não pode falhar em silêncio. Escreve `agente_tarefas`, não depende do número do corretor (bloqueador activo) |
| `guardar_dados_cliente` | A1 + A2 | Reutilizada, mas `_save_to_db` é apagado e religado a `guards.find_or_create_cliente`. Schema ganha `email` |

**Onde fica a marcação de visita** (`ai_visit_bookings` não existe):

| Candidato | Veredicto |
|---|---|
| `oportunidades.visita_*` | **Rejeitado.** Espelho externo do eGO. Não temos `oportunidade_ref`, logo seria *insert* num espelho — corrompe para o scraper e para o `sync_excel_supabase.py` externo. Colunas `text`, sobrescritas no próximo full sync |
| Nova `agente_visitas` | **Rejeitado por agora.** Ref, nome, telefone, data, estado, notas — tudo já tem casa. Justifica-se quando existirem lembretes 24h/follow-up 48h, que precisam de scheduler (fora de âmbito) |
| **`agente_tarefas`** | **Escolhido.** `titulo="Visita FH2233 — João Silva 912345678 — 14/08 15h00"`, `descricao=` contexto completo, `imovel_ref`, `prazo=` data, `estado='pendente'`. Já indexada em `estado`/`imovel_ref` e **já visível no painel** (Imóveis → aba Tarefas) — zero trabalho de frontend |

`# ponytail: hora da visita vive no titulo — prazo é date. Criar agente_visitas quando os lembretes 24h entrarem.` Deliberadamente **não** se acrescenta `data_hora` ao lado do `prazo` existente.

---

## 6. As duas guardas em código — `guards.py`

```python
def normalizar_telefone(raw: str | None) -> str | None   # dígitos; 351/00351/+351 → 9 dígitos
def normalizar_email(raw: str | None) -> str | None      # strip + lower
async def find_or_create_cliente(nome=None, telefone=None, email=None, **campos) -> dict
def visita_permitida(orcamento: float | None, preco: float | None) -> bool
```

**Dedup — a função partilhada (spec §2.7).** Ordem telefone → email → nome, como na tabela de prioridade da spec. **Todos** os caminhos de escrita passam por aqui: `guardar_dados_cliente`, `agendar_visita`, `escalar_para_humano`, **e `voice/save_call.py:59-81`** — quarta cópia artesanal do mesmo upsert por telefone. Trocá-la é remoção líquida de código, e é a razão de a guarda viver em módulo partilhado: corrigir só o caminho desta fase deixava o irmão a duplicar clientes para sempre.

Dois detalhes que mordem se ignorados:
- **Formatos legados.** As linhas existentes têm o que a Meta enviou (`351912345678`). Normalizar só para a frente faz os lookups novos falharem e duplicarem. Sem migração de dados: procurar com `.in_("telefone", [n, "351"+n, "+351"+n, "00351"+n])` e gravar já normalizado.
- **`contactos` do CRM é leitura.** Pode ser lida para enriquecer o prompt ("cliente já conhecido do CRM"); nunca escrita (PK `(nome, criado_em)` vs conflict key `ego_link`).

**Regra dos 80%.** `visita_permitida` é chamada *dentro* de `agendar_visita`, antes de qualquer escrita — não no prompt, não no chamador. O modelo fica fisicamente impedido de marcar abaixo do limiar; a tool devolve a recusa em texto e não escreve nada. Limite é `>=` (spec §3.2: €240k sobre €300k avança com ressalva). `orcamento is None` → recusa. `preco` nulo → recusa (sem divisão por zero). **Arrendamento fica isento** — 80% de uma renda mensal não significa nada; a guarda aplica-se a `venda_preco`. A spec é omissa neste caso.

---

## 7. Config API + Frontend

Ambos os bloqueios caem sem introduzir upsert:
- `api/config.py` — **apagar `AGENTES_VALIDOS`** (linhas 15, 28, 43). A validação passa a ser "a linha existe": o GET já dá 404 via `.single()`, o PUT já dá 404 em `not resp.data`. A migration semeia as linhas novas, logo o PUT nunca precisa de inserir. Saldo: −6 linhas.
- Novo `GET /api/config` (lista todas as linhas, ~8 linhas) para o painel deixar de ter lista hardcoded.

Frontend:
- `pages/Agente1.jsx` → `pages/AgenteConfig.jsx`, rota `/agentes/:agente`. Já é genérico excepto título, subtítulo e o banner Telnyx — passam para um `const META = { a1_vendedor: {...}, a2_geral: {...}, voz: {...} }` no topo do mesmo ficheiro. Sem componente novo, sem dependência nova.
- `components/Sidebar.jsx` — grupo "Assistentes" construído a partir desse mapa.
- `pages/Agente2.jsx` — ganha `<select>`: **A1 Vendedor / A2 Geral / Broker (interno) / Auto (router)**. Envia `{mensagem, participante: 'painel_'+sel, agente: sel || null}`.
- `api/broker.py` — `BrokerChatRequest` ganha `agente: str | None = None`, passado a `responder`.

Dashboard: intocado nesta fase.

---

## 8. Verificação

O projecto não tem testes. Dois ficheiros de asserts simples, sem framework nem fixtures — correm sob `pytest` e sob `python ficheiro.py`:

**`backend/tests/test_router.py`** (puro, sem DB nem rede):
```
("quero comprar casa",        None)          -> "a1_vendedor"
("bom dia",                   None)          -> "a2_geral"
("obrigado!",                 "a1_vendedor") -> "a1_vendedor"   # sticky
("procuro um T2",             "a2_geral")    -> "a1_vendedor"   # re-route A2→A1
("quero vender a minha casa", None)          -> "a2_geral"      # A4 adiado: não inventa agente
route(m, a) in ASSISTENTES  em todos os casos                    # nunca devolve chave inexistente
```

**`backend/tests/test_guards.py`** (só funções puras):
```
normalizar_telefone("+351 912 345-678") == "912345678"
normalizar_telefone("00351912345678")   == "912345678"
normalizar_email("  A@B.COM ")          == "a@b.com"
visita_permitida(240000, 300000) is True    # limiar exacto — spec diz avança
visita_permitida(239999, 300000) is False
visita_permitida(None,   300000) is False
visita_permitida(100000, None)   is False   # sem preço, sem divisão por zero
```

**E2E manual** (tudo pelo chat web excepto o último):
1. Painel → Assistentes → A2 → **deixar persona vazia, preencher só instruções** → guardar → confirmar efeito na resposta. *(Regressão do bug do `persona` vazia.)*
2. Chat em **Auto**: "Bom dia" → responde A2; linha em `agente_conversas` fica com `agente='a2_geral'`.
3. Mesma thread: "procuro um T2 na Figueira até 150 mil" → passa a A1, `pesquisar_imoveis` dispara (log mostra `tool_choice` forçado na iteração 0), ≤3 resultados, todos com `publicado = true`.
4. "quero visitar o FH____" + "tenho 50 mil" → **não marca**, oferece alternativas, **zero linhas novas** em `agente_tarefas`.
5. Repetir com orçamento ≥ 80% → exactamente **uma** linha em `agente_tarefas` e **uma** em `agente_clientes`.
6. Thread nova, mesmo nome e telefone noutro formato (`+351 …`) → continua **uma só** linha em `agente_clientes`.
7. `ativo = false` no A1 → chat devolve linha de handoff **e a Anthropic não é chamada** (sem gasto de tokens nos logs).
8. Uma mensagem real no WhatsApp em produção → mesmo comportamento. É a única verificação de que o refactor não partiu o que já está vivo.

---

## 9. Adiado — e porquê

| Adiado | Razão |
|---|---|
| A3 Recrutamento, A4 Angariador | Fora do âmbito aprovado. Router sem keywords para eles; A2 recolhe contacto e escala |
| SC (simulação de crédito), FP (propostas) | Fora do âmbito. A *escalada* do FP fica honrada via `escalar_para_humano` |
| SV fases 6 e 7 — lembrete 24h, follow-up 48h | Precisam de scheduler. Já existe cron GitHub Actions para imóveis — hospedeiro óbvio, mais tarde |
| Atribuição de consultor e agenda real | Não existe `consultants` nem calendário. A1 propõe horários como *pedido*; visita fica `pendente`, `responsavel` nulo |
| Cross-sell angariação + "registo duplo" | Precisa de A4 e de escritas no CRM, ambos rejeitados. O prompt do A1 continua a *fazer* a pergunta de fecho e guarda em `agente_clientes.notas` |
| Meta Lead Ads, Email, SMS, Voz | Fora de âmbito / bloqueado (Telnyx). O argumento `agente=` é o encaixe para mapear número→assistente mais tarde |
| RGPD soft-delete, RLS write-once, retenção 12/24m | Não há `deleted_at` e `save_conversation` faz UPDATE in-place — a regra 10 da spec contradiz o design actual. Precisa de decisão própria |
| Botões/media/templates WhatsApp | Só texto, como hoje |

---

## 10. Ordem de execução

1. Copiar este plano para `docs/fases/assistentes-a1-a2-plano.md`; commit de `assistentes-ia-especificacao.md`.
2. Migration `0014` + aplicar em produção.
3. `guards.py` + `test_guards.py` (verde antes de seguir).
4. `router.py` + `test_router.py` (verde antes de seguir).
5. `assistants.py` + `engine.py` (levantar de `whatsapp_intake.py`, preservando caching e tool forcing).
6. `conversation.py` — `agente` no load/save.
7. `tools.py` — registry, correcções ao `pesquisar_imoveis`, `json.dumps`, 4 tools novas.
8. Religar `webhook.py` (1 linha) → **apagar `voice/whatsapp_intake.py` e `broker/claude_agent.py`**; religar `voice/save_call.py` e `voice/claude_agent.py`.
9. `api/config.py` (apagar `AGENTES_VALIDOS`, novo `GET /api/config`) + `api/broker.py` (campo `agente`).
10. Frontend: `AgenteConfig.jsx`, `Sidebar.jsx`, `Agente2.jsx`, `App.jsx`.
11. Deploy Fly.io + E2E manual §8 + fechar (`CLAUDE.md` e `docs/fases/assistentes-a1-a2-resumo.md`).
