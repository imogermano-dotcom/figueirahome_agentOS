# Plano — Observabilidade dos Assistentes A1/A2

> Fase seguinte ao Dashboard. Segue `planeamento-fases.md`.

## Contexto

Pedido: ver por assistente a configuração, conversas, acções, **gastos com API**,
desempenho operacional, qualidade da interação, eficiência técnica e análise de
contexto.

**Verificação feita primeiro: nada disso está a ser gravado.** `agente_conversas.mensagens`
guarda apenas `{role, content, timestamp}` — confirmado nas 5 conversas reais em
produção. O `engine.py` recebe `usage` em cada resposta da Anthropic e **descarta-o**.

| Pedido | Existe hoje? |
|---|---|
| Configuração | ✅ `agente_config`, já editável no painel |
| Conversas | ⚠️ texto sim; sem tokens, sem latência, sem modelo |
| Acções (tools chamadas) | ❌ `tool_use`/`tool_result` são construídos para o loop e **nunca persistidos** |
| Gastos com API | ❌ nenhum token gravado — impossível calcular |
| Desempenho operacional | ❌ sem latência, sem contagem de iterações |
| Qualidade da interação | ⚠️ só por leitura manual |
| Eficiência técnica | ❌ sem taxa de acerto de cache, sem erros registados |
| Análise de contexto | ❌ sem tamanho de prompt por turno |

**Portanto a fase é: instrumentar primeiro, painel depois.** Não há atalho — um
ecrã de custos sobre dados inexistentes seria inventado.

## Achado paralelo: bug a afectar clientes agora

O agente responde em **Markdown** no WhatsApp — `**negrito**` e tabelas
(`| campo | valor |`). O WhatsApp usa asterisco simples e **não tem tabelas**.
Confirmado numa conversa real: a ficha do FH2550 foi entregue como um bloco de
`|` e `---`.

Correcção (fora do âmbito desta fase, mas trivial): instrução no prompt do A1
+ conversão `**x**` → `*x*` no `meta_api.py`, que já é o único ponto de saída
para WhatsApp. ~10 linhas. **Recomendo fazer antes** — é visível ao cliente.

---

## 1. Migration `0016_agente_interacoes.sql`

Um turno = uma linha. É o único dado desta fase sem casa: `agente_conversas`
guarda a conversa, não o custo de cada chamada à API.

```sql
create table agente_interacoes (
  id                uuid primary key default uuid_generate_v4(),
  conversa_id       uuid references agente_conversas(id) on delete cascade,
  agente            text not null,
  canal             text not null,
  modelo            text not null,

  -- Tokens, tal como a API os devolve (usage). Sem estes não há custo.
  tokens_input      integer not null default 0,
  tokens_output     integer not null default 0,
  tokens_cache_read integer not null default 0,   -- ~0,1x do preço de input
  tokens_cache_write integer not null default 0,  -- 1,25x do preço de input

  -- Custo em USD calculado no momento da chamada, com os preços vigentes.
  -- Guardado (não recalculado) de propósito: é o que foi de facto cobrado,
  -- e os preços mudam. Recalcular reescreveria o histórico.
  custo_usd         numeric(10,6) not null default 0,

  latencia_ms       integer,
  iteracoes         integer not null default 1,   -- voltas no loop de tools
  tools_usadas      text[],                       -- ['pesquisar_imoveis', ...]
  tool_forcada      boolean not null default false,
  erro              text,                         -- null = correu bem
  criado_em         timestamptz not null default now()
);

create index idx_agente_interacoes_agente_data on agente_interacoes (agente, criado_em desc);
create index idx_agente_interacoes_conversa on agente_interacoes (conversa_id);
```

**Uma tabela, nada mais.** O que não se cria:

| Tentação | Porque não |
|---|---|
| Tabela de tools chamadas | `text[]` numa coluna chega; ninguém vai fazer join por tool |
| Tabela de preços | Duas constantes em Python; o custo já fica gravado por linha |
| Guardar prompt/resposta completos | Já estão em `agente_conversas.mensagens` — duplicar é só custo de disco |

---

## 2. Instrumentação — `engine.py`

O motor já tem tudo à mão; só está a deitar fora. Alterações:

1. **Capturar `usage`** de cada resposta (`data["usage"]`), somando ao longo das
   iterações do loop de tools — um turno com 3 tools são 4 chamadas à API.
2. **Cronometrar** com `time.monotonic()` à volta do bloco `async with httpx`.
3. **Registar tools chamadas** (já se itera sobre os blocos `tool_use`) e se
   houve tool forcing.
4. **Registar erros** — hoje o `except` faz `logger.exception` e devolve texto
   genérico; o erro não fica em lado nenhum consultável.
5. **Gravar a linha** no fim, ao lado do `save_conversation` — no mesmo
   `try/except`, para nunca partir a resposta ao cliente se o registo falhar.

Preços em `assistants.py`, ao lado do modelo (confirmados na doc oficial da
Anthropic, não de memória):

```python
# claude-sonnet-4-6, USD por milhão de tokens.
# Cache: leitura ~0,1x do input, escrita 1,25x.
PRECOS = {"claude-sonnet-4-6": {"input": 3.00, "output": 15.00}}
```

`# ponytail: preços hardcoded — um dict, não uma tabela. Mover para a BD só
quando houver mais de um modelo em uso.`

---

## 3. RPC `agente_metricas(dias int default 30)`

Mesmo padrão da `dashboard_metricas` (migration 0015), que já provou funcionar:
agregação no Postgres, um round-trip. Devolve por assistente:

| Grupo | Métricas |
|---|---|
| **Custos** | total USD, por assistente, por canal, média por conversa, média por turno |
| **Volume** | turnos, conversas, mensagens |
| **Desempenho** | latência p50/p95, iterações médias, taxa de erro |
| **Eficiência** | % tokens servidos de cache (o indicador que diz se o prompt caching está mesmo a funcionar), tokens in/out |
| **Acções** | contagem por tool, quantas visitas e escaladas foram criadas |
| **Contexto** | tokens de input médios e máximos por turno, comprimento das conversas |

---

## 4. Frontend

Nova aba na página de cada assistente (`/agentes/:agente`), sem página nova:

- **Configuração** — o que já existe (persona, instruções, activo)
- **Métricas** — KPI row (custo, turnos, latência p95, taxa de cache) + barras
  por tool e por canal, reutilizando `components/Barras.jsx`
- **Conversas** — lista das recentes com custo e nº de turnos; clicar abre a
  transcrição com as tools chamadas em cada turno

Sem biblioteca de gráficos, como no Dashboard.

---

## 5. Verificação

- `test_custos.py` — função pura `calcular_custo(usage, modelo)`: valores
  conhecidos batem certo à sexta casa decimal; cache read é 0,1× do input;
  cache write é 1,25×; modelo desconhecido não rebenta (devolve 0 e loga).
- Confronto ao vivo: mandar uma mensagem no banco de ensaio e conferir os
  tokens gravados contra o `usage` cru devolvido pela API.
- Confirmar que `tokens_cache_read > 0` a partir do 2.º turno — se for sempre 0,
  o prompt caching está partido e ninguém sabia.
- Uma falha propositada (chave errada) deve gravar linha com `erro` preenchido
  e **não** partir a resposta ao cliente.

---

## 6. Fora de âmbito

Alertas de orçamento, exportação, comparação A/B de prompts, avaliação
automática de qualidade (precisaria de um LLM juiz — fase própria), e retenção
de dados (a tabela cresce ~1 linha por mensagem; a 5 conversas por dia é
irrelevante durante anos).

**Qualidade da interação fica semi-manual**: dá para ver conversas com muitas
iterações, com erro, ou que acabaram em escalada — sinais de fricção. Pontuar
qualidade automaticamente é outra coisa, e não a proponho às cegas.
