# Resumo — Reformulação do Dashboard

> Fase concluída em 2026-08-03. Plano em `dashboard-plano.md`.

## O que mudou

O dashboard mostrava 5 cartões que liam as tabelas do agente. **Três estavam
permanentemente a zero** (chamadas, leads, conversas — tabelas com 1 a 5 linhas),
enquanto o negócio real era invisível.

| | Antes | Depois |
|---|---|---|
| `api/dashboard.py` | 69 l., 5 queries em série | 33 l., 1 RPC |
| Cartões sempre a zero | 3 de 5 | 0 |
| Registos representados | ~20 | 25.301 oportunidades · 4.462 imóveis · 27.836 contactos |
| Bundle | 437 kB | 442 kB (+5,6 kB) |

## Secções

1. **KPI row** — oportunidades activas, imóveis publicados, contactos, tarefas pendentes.
2. **Pipeline** — barra empilhada Perdidas · Activas · Ganhas, com percentagens.
3. **Por responsável** (top 8) e **por origem** (top 7), barras ordenadas.
4. **Portefólio** — publicados vs disponíveis vs prospecção vs por validar vs retirados.
5. **Assistentes IA** — conversas por assistente, visitas e escaladas pendentes.
6. **Sincronizações** — última execução de cada pipeline, vermelho se houver erros
   **ou** se um sync diário estiver calado há mais de 48h (o modo de falha real:
   pipeline partido em silêncio).
7. **A precisar de atenção** — registos incompletos, expostos de propósito.

## Decisões

**`publicado`, não `disponibilidade`.** O cartão antigo contava
`disponibilidade='Disponível'` (67); o novo conta `publicado` (53) — o que está
mesmo no site. `publicado` é GENERATED (migration 0008) e exige disponibilidade +
ref + preço > 0 + `disponivel_na_api`. Um teste garante que publicados nunca
excede disponíveis.

**Sem biblioteca de gráficos.** São barras horizontais: `div` com `width: %`.
Recharts custaria ~100 kB para desenhar rectângulos. Custo real do dashboard
inteiro: **+5,6 kB**.

**Agregação no Postgres.** `dashboard_metricas()` (migration 0015) devolve um
`jsonb` com tudo. `stable`, só leitura — `oportunidades` e `contactos` são o
espelho externo do eGO e nunca são escritas.

### Cor — validada, não escolhida a olho

Corrido `validate_palette.js` contra a superfície real dos cartões
(`zinc-900` `#18181b`), não a default da skill. **Duas falhas apanhadas:**

1. **Ganha (verde) vs Perdida (vermelho): CVD ΔE 4,1 — FAIL.** Um deuteranope não
   distinguiria ganho de perda. Corrigido pela ordem da pilha
   `Perdida · Activa · Ganha`, com o azul a separar: pior par adjacente passa a
   ΔE 25,7. Cada segmento leva ícone + rótulo — a cor nunca decide sozinha.
2. **Ramp sequencial de 5 azuis: ΔL adjacente 0,049 — FAIL.** As barras são
   ordenadas, logo o comprimento já codifica a magnitude. O ramp era informação
   repetida: **removido**, não remendado. Uma cor só.

## O que NÃO foi construído, e porquê

Levantamento sobre os dados reais antes de desenhar:

| Pedido natural | Porque não |
|---|---|
| Gráfico de evolução | `data_criacao_iso` **em falta em 8.432 registos** (33%) |
| Métricas de receita | `valor_negocio` preenchido em **7 de 1000** |
| Funil por etapa | 8.124 sem etapa + duplicados sujos ("Contacto" vs "3-Contacto") |

Qualquer um dos três mentiria. O trabalho é a montante, no pipeline de importação.
É por isso que esses números aparecem no cartão "A precisar de atenção" em vez de
gráficos: o problema fica visível em vez de disfarçado.

## Bug apanhado na verificação

**Duas linhas "Outros" em `por_origem".** Existe uma origem real chamada "Outros"
(2222) nos dados, que colidia com o balde da cauda (343) — chave duplicada no
React e barra a duplicar. Corrigido com `group by` depois do `union`: somam-se as
duas (2565). Teste `test_dashboard.py` passou a exigir nomes únicos.

Também ficou à vista que **a coluna `responsavel` tem lixo**: "Internet" aparece
como responsável em 892 registos — um valor de origem no campo errado. Não foi
mascarado: é dado a corrigir a montante.

## Verificação

- `test_dashboard.py` — 5 testes: secções presentes, pipeline soma o total,
  publicados ≤ disponíveis, listas ordenadas e sem nomes repetidos, sem divisão
  por zero.
- Confronto RPC vs `count()` directo em 10 métricas: **todas batem certo**.
- Ambas as listas somam 25.301 — nada se perde no agrupamento da cauda.
- `test_guards.py`, `test_router.py`, `npm run build` verdes.
