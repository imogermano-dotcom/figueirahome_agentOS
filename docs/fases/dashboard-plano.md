# Plano — Reformulação do Dashboard

> Fase seguinte à dos assistentes A1/A2. Segue `planeamento-fases.md`.

## Contexto

O dashboard actual (`frontend/src/pages/Dashboard.jsx`, 88 l. + `api/dashboard.py`,
69 l.) mostra 5 cartões que lêem **as tabelas do agente**. Volumes reais hoje:

| Cartão actual | Fonte | Valor real |
|---|---|---|
| Chamadas hoje | `agente_chamadas` | **1 no total** (voz bloqueada por Telnyx) → sempre 0 |
| Leads novos | `agente_leads` | **1 no total** → ~0 |
| Conversas hoje | `agente_conversas` | **4 no total** → ~0 |
| Tarefas pendentes | `agente_tarefas` | 16 |
| Imóveis disponíveis | `imoveis` | 67 |

**Três dos cinco cartões estão permanentemente a zero.** Entretanto o negócio real
é invisível: **25.301 oportunidades, 27.833 contactos, 4.462 imóveis, 100.282 notas,
23.336 tarefas de CRM**.

Há ainda uma incoerência: o cartão conta `disponibilidade='Disponível'` (**67**),
mas só **53** têm `publicado=true` — o número mostrado não é o que está no site.
O resto da aplicação já usa `publicado` (migration 0008).

**Resultado pretendido:** um dashboard que mostre o negócio real, com números que
os dados aguentem.

### Decisões de âmbito (aprovadas)
1. **Quatro áreas**: pipeline de oportunidades, portefólio de imóveis, actividade
   dos assistentes IA, saúde das sincronizações.
2. **Expor os dados sujos** como alerta, incluindo os ~3459 `Em Prospecção` de
   origem desconhecida (bloqueador hoje só registado em notas).
3. **Uma RPC em Postgres** devolve todas as contagens — um round-trip em vez de
   ~12, agregação feita na base de dados.

## 1. O que os dados aguentam — e o que não

Levantamento feito sobre amostra real de 1000 oportunidades:

| Dimensão | Qualidade | Decisão |
|---|---|---|
| `oportunidade_estado` (Ativa 858 / Perdida 120 / Ganha 22) | ✅ limpo, 3 valores | Barra empilhada |
| `responsavel` (13 pessoas) | ✅ limpo, 11% vazios | Barras ordenadas, top 8 + "Outros" |
| `origem` (Internet 529, Loja 60, Placa 18…) | ✅ limpo, 10 valores | Barras ordenadas, top 7 + "Outros" |
| `tipo_oportunidade` (Venda 592, Angariação 119, Arrend. 23) | ✅ limpo, 27% vazios | Cartões |
| `etapa_atual` | ⚠️ 35% vazios **e duplicados sujos** ("Contacto" vs "3-Contacto") | Só no cartão de alerta, não como funil |
| `data_criacao_iso` | ❌ **45% preenchida** | **Sem série temporal** |
| `valor_negocio` | ❌ **7 em 1000** | **Sem métricas de receita** |

> Não haverá gráfico de evolução nem de facturação. Com 45% das datas em falta e
> 0,7% dos valores preenchidos, qualquer um dos dois **mentiria**. Se isto for
> requisito, o trabalho é a montante — corrigir o pipeline de importação, não
> desenhar o gráfico.

## 2. Backend — uma RPC

`supabase/migrations/0015_dashboard_metricas.sql` cria
`dashboard_metricas()` que devolve **um** `jsonb` com todas as secções.
Contar 25 mil linhas ×12 do lado do cliente não é opção; e o endpoint actual já
faz 5 queries em série.

```sql
create or replace function dashboard_metricas()
returns jsonb language sql stable as $$
  select jsonb_build_object(
    'oportunidades', (select jsonb_build_object(
        'total', count(*),
        'ativas', count(*) filter (where oportunidade_estado = 'Ativa'),
        'ganhas', count(*) filter (where oportunidade_estado = 'Ganha'),
        'perdidas', count(*) filter (where oportunidade_estado = 'Perdida'))
      from oportunidades),
    'por_responsavel', (…top 8 + Outros…),
    'por_origem',      (…top 7 + Outros…),
    'imoveis', (select jsonb_build_object(
        'publicados', count(*) filter (where publicado),
        'disponiveis', count(*) filter (where disponibilidade = 'Disponível'),
        'prospeccao', count(*) filter (where disponibilidade = 'Em Prospecção'),
        'retirados', count(*) filter (where disponibilidade = 'Retirado'))
      from imoveis),
    'assistentes', (…conversas por agente_conversas.agente, tarefas por tipo…),
    'sync',   (…última execução por tipo, de agente_sync_log…),
    'alertas',(…contagens de dados incompletos…));
$$;
```

`api/dashboard.py` passa a chamar `get_supabase().rpc("dashboard_metricas").execute()`
e devolve o `jsonb` tal como vem. O ficheiro **encolhe** — as 5 queries e o
`_fetch` desaparecem.

`stable`, sem `security definer`: o backend usa `service_role_key`, não precisa.

## 3. Frontend — formas, não enfeites

Regra aplicada (skill `dataviz`): **a forma vem do trabalho que o dado tem de fazer.**

| Secção | Forma | Porquê |
|---|---|---|
| Números de topo | **KPI row** de 4 stat tiles | Valores únicos. Um gráfico de barra única seria pior |
| Pipeline (Ativa/Ganha/Perdida) | **Barra empilhada horizontal** | Parte-para-todo, 3 classes |
| Por responsável (13) | **Barras horizontais ordenadas** | Magnitude; >7 classes → top 8 + "Outros" |
| Por origem (10) | **Barras horizontais ordenadas** | Idem, top 7 + "Outros" |
| Imóveis por estado | **Barras horizontais** | Magnitude, 4 classes |
| Assistentes IA | **Stat tiles** | Números pequenos; gráfico seria ruído |
| Sync + alertas | **Linhas com ícone + rótulo** | Estado, não magnitude |

**Sem biblioteca de gráficos.** São barras horizontais — `div` com `width: %` em
Tailwind. Recharts custaria ~100 kB para desenhar rectângulos. O bundle actual é
437 kB; não vale a pena.

### Cor — validada, não escolhida a olho

Superfície real dos cartões: `zinc-900` `#18181b` (o painel é dark-only). Validado
com `scripts/validate_palette.js` contra **essa** superfície, não a default da skill.

Duas falhas reais apanhadas e corrigidas:

1. **Ganha (verde `#0ca30c`) vs Perdida (vermelho `#d03b3b`): CVD ΔE 4,1 — FAIL.**
   Um deuteranope não distinguiria "ganha" de "perdida" — a pior falha possível
   neste gráfico. **Correcção:** ordem da pilha `Perdida · Ativa · Ganha`, com o
   azul a separar os dois. Revalidado: pior par adjacente ΔE 25,7 — **todos passam**.
   Mais ícone + rótulo em cada segmento (regra das cores de estado).
2. **Ramp sequencial de 5 passos: ΔL adjacente 0,049 — FAIL.** Mas as barras estão
   **ordenadas**: o comprimento já codifica a magnitude. **Correcção:** uma cor só
   (`#3987e5`) em todas as barras. O ramp era informação repetida — removido, não
   remendado.

| Papel | Hex | Uso |
|---|---|---|
| Série / neutro | `#3987e5` | Barras de magnitude, segmento "Ativa" |
| Bom | `#0ca30c` | Ganha, sync com sucesso |
| Crítico | `#d03b3b` | Perdida, sync falhado |
| Aviso | `#fab219` | Alertas de dados sujos |

`warning` e `serious` nunca ficam adjacentes (ΔE normal 13,6 entre si).

### Acessibilidade
- Barra empilhada: rótulo directo em cada segmento (3 séries → sempre legendado).
- Estados com **ícone + texto**, nunca só cor.
- Separador de 2px entre segmentos, cantos 4px no topo da barra.
- Tooltip nativo (`title`) em cada barra — sem JS de hover.

## 4. Ficheiros

| Ficheiro | Acção |
|---|---|
| `supabase/migrations/0015_dashboard_metricas.sql` | NOVO — a RPC |
| `backend/app/api/dashboard.py` | EDIT — uma chamada RPC; encolhe |
| `frontend/src/pages/Dashboard.jsx` | REESCRITO |
| `frontend/src/components/Barras.jsx` | NOVO — barras horizontais reutilizáveis (~40 l.) |
| `backend/tests/test_dashboard.py` | NOVO — verifica forma do payload |

## 5. Verificação

- `test_dashboard.py`: a RPC devolve todas as chaves esperadas; contagens do
  pipeline somam o total; percentagens nunca dividem por zero (BD vazia).
- Confronto manual: totais da RPC vs `select count(*)` directo.
- `npm run build` verde; abrir o dashboard e confirmar que nenhuma barra
  transborda com nomes longos ("Alexsandra Ferreira") nem com valor 0.
- Confirmar que **imóveis publicados = 53**, não 67.

## 6. Fora de âmbito

Séries temporais e receita (dados não aguentam — §1), funil por `etapa_atual`
(dados sujos), filtros por data ou responsável, exportação, dashboard por
utilizador. O `agente_conversas.agente` já permite métricas por assistente, mas
com 4 conversas no total só ganha valor quando o WhatsApp tiver histórico.
