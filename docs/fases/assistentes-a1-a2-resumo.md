# Resumo — Reformulação dos Agentes: Fundação + A2 + A1

> Fase concluída em 2026-08-02. Plano em `assistentes-a1-a2-plano.md`.
> Requisitos em `assistentes-ia-especificacao.md` (raiz do repo).

## O que ficou a funcionar

Um motor único de assistentes, com roteamento de intenção, a servir WhatsApp
e o chat do painel. Três assistentes activos: **A1 Vendedor**, **A2 Geral** e
o **Broker** interno.

Saldo do diff: **+622 / −819 linhas** (−197 líquidas), 14 ficheiros.

## Alterações

### Consolidação
- **3 cérebros → 1.** `engine.py` substitui `broker/claude_agent.py` e
  `voice/whatsapp_intake.py` (ambos apagados, −494 linhas). O ciclo de imports
  `broker → voice → broker` morreu por remoção, não por refactor.
- **`_load_config` 3× → 1×** (`assistants.load_config`). Corrigidos dois
  defeitos que as três cópias partilhavam: `instrucoes` era descartado sempre
  que `persona` estivesse vazia, e `ativo` era editável no painel mas nunca
  lido por ninguém — agora é kill switch real (nem chega a chamar a API).
- **Prompt caching e tool forcing** só existiam no caminho do WhatsApp;
  passam a valer para todos os assistentes.
- **Dedup de clientes**: `guards.find_or_create_cliente` é a única via de
  escrita. Havia quatro upserts artesanais quase iguais — incluindo em
  `voice/save_call.py`, também religado.

### Novo
| Ficheiro | Papel |
|---|---|
| `agents/broker/engine.py` | O loop agêntico, único |
| `agents/broker/assistants.py` | Registry: prompt, tools e forcing por assistente |
| `agents/broker/router.py` | Router por keywords, com stickiness. Função pura |
| `agents/broker/guards.py` | Normalização, dedup, regra dos 80% |
| `tests/test_router.py`, `tests/test_guards.py` | Asserts simples, sem framework |
| `frontend/src/pages/AgenteConfig.jsx` | Config genérica, rota `/agentes/:agente` |
| `frontend/src/pages/Chat.jsx` | Chat com selector de assistente |
| `supabase/migrations/0014_assistentes.sql` | 1 coluna, 2 linhas de seed |

### Correcções de bugs reais
- `pesquisar_imoveis` devolvia imóveis **vendidos e retirados** — faltava
  filtro de disponibilidade. Agora `publicado = true` (coluna GENERATED da
  0008, mais forte que `disponibilidade` e indexada).
- Zona filtrava só por `concelho`; agora `concelho OR freguesia OR zona`.
- `execute_tool` devolvia `str(list)` — repr do Python com plicas. Agora JSON.
- `normalizar_telefone` falhava em `00351…` (apanhado pelo `test_guards.py`).
- **Fallback de tipologia** (apanhado no E2E): o modelo traduz "T2" para
  `natureza="Apartamento"` e perdia as moradias T2 — respondia "não temos"
  havendo uma moradia T2 a 65k. O nível 1 do fallback progressivo da spec
  (§3.2 SI-B fase 5) passou a viver **dentro da tool**: zero resultados com
  `natureza` dispara segunda pesquisa sem esse filtro, marcada como
  alternativa. Determinístico, não depende de o prompt aguentar.

### Segurança
`consultar_clientes` e `consultar_leads` expõem a base de clientes da agência.
Estavam disponíveis no mesmo endpoint que passa a servir clientes no banco de
ensaio. O subconjunto de tools por assistente restringe-as ao `broker` — é a
razão principal de o registry existir.

## Verificação feita

Contra a Supabase real e a API da Anthropic:

| Verificação | Resultado |
|---|---|
| Migration 0014 | Coluna `agente` existe; 4 linhas em `agente_config` |
| Router: "Bom dia" | → `a2_geral`, gravado na thread |
| Router: "procuro T2 na Figueira até 150 mil" (mesma thread) | → `a1_vendedor`, sticky |
| `pesquisar_imoveis` | Só `publicado=true`, ordenado por preço, máx. 3 |
| 80% — orçamento a 50% | Recusa, **zero escritas** |
| 80% — sem orçamento | Recusa, zero escritas |
| 80% — limiar exacto | Passa, 1 tarefa + 1 cliente |
| Dedup `+351 912 345-678` vs `912345678` | 1 cliente só, gravado normalizado |
| Kill switch `ativo=false` | Handoff em 0,17s, sem chamada à API |
| `test_guards.py`, `test_router.py` | Verdes |
| `npm run build` | Verde |

Linhas de teste removidas da BD no fim; estado de `agente_config` restaurado.

**Produção (2026-08-02)**: backend deployado no Fly.io (`/health` 200, v0.4.0),
frontend no Cloudflare Pages. Confirmado end-to-end pelo utilizador — **chat do
painel e WhatsApp, ambos a funcionar**.

## Adiado

A3 Recrutamento, A4 Angariador, SC (simulação de crédito), FP (propostas
completas — só a escalada está honrada), lembretes 24h / follow-up 48h das
visitas (precisam de scheduler), atribuição de consultor e agenda real
(não existe tabela de consultores), Meta Lead Ads, Email, SMS, Voz
(bloqueada por credenciais Telnyx), RGPD soft-delete e retenção.

Detalhe e justificação em `assistentes-a1-a2-plano.md` §9.

## Como testar

1. Painel → **Chat** → selector em **Auto (router)**.
2. "Bom dia" → responde o A2.
3. "procuro um T2 na Figueira até 150 mil" → passa ao A1 e mostra imóveis reais.
4. "quero visitar o FH2542" + "tenho 20 mil" → **não marca**, oferece alternativas.
5. Repetir com orçamento ≥ 80% do preço → aparece tarefa em Imóveis → Tarefas.
6. Painel → **Assistentes → A2 Geral**: horários e morada editam-se aqui, sem deploy.
7. Desligar "Assistente activo" → responde com a linha de handoff.
