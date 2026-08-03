# Resumo — Observabilidade dos Assistentes A1/A2

> Fase concluída em 2026-08-03. Plano em `assistentes-observabilidade-plano.md`.

## O ponto de partida

Foi pedido ver por assistente: configuração, conversas, acções, gastos com API,
desempenho, qualidade, eficiência técnica e contexto.

**Verificação feita antes de planear: nada disso estava a ser gravado.** O
`engine.py` recebia o `usage` em cada resposta da API e deitava-o fora;
`agente_conversas.mensagens` guardava só `{role, content, timestamp}`. Um ecrã
de custos sobre esses dados seria inventado — daí a fase ter sido
**instrumentar primeiro, painel depois**.

## O que ficou

| Camada | Entrega |
|---|---|
| Dados | `agente_interacoes` (migration `0016`) — um turno = uma linha |
| Cálculo | `custos.py` — `somar_usage()` + `calcular_custo()` |
| Captura | `engine.py` — tokens, latência, tools, iterações, tool forcing, erros |
| Agregação | RPC `agente_metricas(agente, dias)` (migration `0017`) |
| API | `/api/agentes/metricas`, `/conversas`, `/conversas/{id}` |
| Painel | Três abas: Configuração · Métricas · Conversas (+10 kB) |

**Custo total do painel: +10 kB.** Sem biblioteca de gráficos — reutiliza
`components/Barras.jsx` do Dashboard.

## Decisões

**Uma tabela nova, justificada.** `agente_conversas` guarda a conversa, não o
custo de cada chamada. Tokens, latência, tools e erros não tinham casa. O que
se recusou criar: tabela de tools (`text[]` chega), tabela de preços (duas
constantes em Python), cópia do prompt/resposta (já estão em `mensagens`).

**Custo gravado, não recalculado.** `custo_usd` é calculado no momento da
chamada com os preços então vigentes. Recalcular a partir dos tokens
reescreveria o histórico sempre que a Anthropic mudasse a tabela de preços —
o que lá está é o que foi de facto cobrado.

**Duas guardas defensivas.** `_registar_interacao` engole a excepção e
`calcular_custo` devolve 0 num modelo desconhecido. Ambas correm no caminho de
resposta ao cliente: observabilidade nunca pode derrubar uma conversa. Foi isto
que permitiu correr o código em produção antes de a migration estar aplicada,
sem partir o WhatsApp.

**Preços confirmados na fonte**, não de memória: `claude-sonnet-4-6` a
$3,00/$15,00 por MTok; cache read 0,1×, cache write 1,25× (TTL 5 min).

## O achado principal

**O prompt caching está a funcionar — taxa de 67%.** Dois terços dos tokens de
entrada são servidos do cache a 10% do preço. Era a incógnita que motivou a
fase: se viesse zero, estaríamos a pagar preço cheio em cada mensagem desde
sempre e nada no sistema daria sinal. O cartão "Servido de cache" fica
**vermelho** se a taxa cair a zero havendo turnos — é o alarme dessa falha.

## Números medidos (3 turnos — indicativo, não conclusivo)

| Métrica | Valor |
|---|---|
| Custo por turno | $0,0025 (saudação) a $0,018 (com pesquisa) |
| Latência | 3,2s sem tools · **10,1s com pesquisa** |
| Taxa de cache | 67% |
| Iterações médias | 1,33 |

⚠️ **10,1s é lento para WhatsApp.** Com 3 turnos não é uma conclusão — é o que
a p95 no painel serve para responder com tráfego real. Se confirmar, os
suspeitos são `_MAX_TOOL_ITERATIONS` e a segunda chamada à API que a pesquisa
obriga.

## Verificação

- `test_custos.py` — 7 asserts: factores de cache contra valores exactos (1M
  cache read = $0,30; cache write = $3,75), acumulação entre iterações, modelo
  desconhecido a não rebentar.
- **Ao vivo contra a API real**: caching confirmado (turno 1 escreve 1234
  tokens, turno 2 lê-os); aritmética conferida à mão ($0,002512 num turno,
  exacto); turno com tool regista `iteracoes=2` e `tools=['pesquisar_imoveis']`;
  chave inválida → cliente recebe fallback, erro gravado, nada parte.
- **RPC contra soma directa**: 8 métricas confrontadas, todas batem; `taxa_cache`
  confirmada; filtro por agente correcto; agente inexistente devolve zeros sem
  divisão por zero.
- Dados de teste removidos no fim; as 5 conversas reais intactas.

## O que NÃO faz

**Não pontua qualidade automaticamente.** Precisaria de um LLM juiz e é uma
fase própria. O que o painel mostra é *fricção observável*: conversas com
muitas iterações, com erro, ou que acabaram em escalada.

**Não inventa retroactivos.** Conversas anteriores à instrumentação aparecem
sem custo, e o ecrã di-lo — esses tokens nunca foram gravados.

Também fora: alertas de orçamento, exportação, comparação A/B de prompts,
retenção de dados (a tabela cresce ~1 linha por mensagem).
