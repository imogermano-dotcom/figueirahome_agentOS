# Nudge: não lembrar quem já entregou o caso — plano

> Fase pequena, só backend. **Plano antes de código** (CLAUDE.md, regra 2).
> Continuação de `nudge-todos-agentes-resumo.md`.

## Problema (achado ao vivo, 05–06/10)

A Inês (A3) fechou bem uma candidatura: qualificou, escalou
(`agente_tarefas.tipo='escalar'`, 21:35 UTC) e despediu-se com
*"Tudo registado! Boa semana! 🌟"*. Às 00:12 UTC (01:12 em Lisboa) o nudge
enviou *"Ainda tem interesse em avançar com a candidatura? … diga-me só que não
para eu não voltar a incomodar."* — contradiz a mensagem anterior, e a uma
candidata que já tinha concluído.

## Causa

`nudge._candidatos` só trava por duas coisas:

1. `_e_despedida(ultima)` — lista de substrings (`_MARCAS_FECHO`, `nudge.py:47`).
   "Boa semana" e "🌟" não estão lá. Lista fechada sobre a voz do modelo:
   cada despedida nova que o modelo invente volta a furar.
2. `guarda` por agente — `None` para A3 e A4 (`nudge.py:103-104`), porque `contactos`
   não tem estado fechado. O A1 trava por `leads.estado`/`contacto_humano_em`.

O sinal fiável de "caso entregue a um humano" já existe e é gravado em código,
não pelo modelo: **uma linha `agente_tarefas` com `tipo='escalar'` e
`conversa_id` da conversa** (`tools.py:850-852`; é também o que
`_tarefa_ja_registada` usa para o dedup).

## Proposta

Em `_candidatos`, depois do filtro da janela e antes das guardas por agente,
**uma única query em lote** às tarefas:

```python
ids = [r["id"] for r in resp.data]
escaladas = {t["conversa_id"] for t in
             get_supabase().table("agente_tarefas").select("conversa_id")
             .in_("conversa_id", ids).eq("tipo", "escalar").execute().data}
```

e saltar as conversas em `escaladas`. Regra para os **três** agentes (uma só
regra, não três cópias): escalar = há um humano com o caso, o lembrete de texto
livre já não faz sentido.

- Uma query por execução (horária), não uma por conversa. Se `ids` vazio, não se consulta.
- `_MARCAS_FECHO` fica como está, **sem** acrescentar "boa semana": remendo
  frágil, e a guarda real torna-o desnecessário neste caso. (Acrescentar é
  gratuito se o quiseres; fica fora por decisão.)
- Falha da query: não enviar (falhar fechado) e `logger.exception`; um nudge a
  menos custa menos do que um nudge indevido.

## Fora desta fase (decidir à parte)

- **Horas de silêncio** — o nudge saiu à 01:12 de Lisboa e o cron corre de hora
  a hora sem noção de horário. Mexe em `_JANELA_*`/cron e em quem responde na
  1.ª hora; merece decisão própria (janela proposta, ex. 22:00–08:00 Lisboa, que
  adia em vez de descartar, porque a janela de 24h da Cloud API é de 20h úteis).
- **Visita do A1** (`tipo='visita'`) — não é `escalar`; o A1 já trava por `leads`.
- **Retroactivo** — a conversa `2cbffc68…` já recebeu o nudge (`nudge_em` gravado);
  nada a corrigir.
- **Lead de recrutamento em `leads`** — não foi criada nesta conversa (só existe uma
  antiga, `compra`/`sem_interesse`). Investigar à parte se `guardar_dados_cliente`
  correu (as tools não ficam persistidas em `mensagens`).

## Testes (`backend/tests/test_nudge.py`)

O `_FakeTable.execute` devolve `conversas` para qualquer tabela que não `leads`;
tem de passar a devolver `estado["tarefas"]` para `agente_tarefas`. Novos casos:

1. **Caso real**: A3, última mensagem "Tudo registado! Boa semana! 🌟", tarefa
   `escalar` para a conversa → 0 nudges.
2. A3 sem tarefa → recebe (regressão: não travar tudo).
3. A4 com tarefa `escalar` → 0 nudges.
4. Duas conversas, só uma escalada → só a outra recebe.
5. Tarefa de outro `tipo` (`visita`) na mesma conversa → não trava.
6. Query às tarefas a falhar → 0 nudges, sem excepção.

Corre-se `pytest backend/tests/` (hoje 283) de `backend/`.

## Deploy e risco

Só `figueirahome-agentos` (backend). Sem migration, sem alteração de dados,
sem tocar no n8n. Risco: uma escalada sem seguimento humano deixa de receber
lembrete — é intencional (o humano é o próximo passo, não a IA). Reversível com
`git revert`.

## Decisões por confirmar

1. Regra para os 3 agentes ou só A3/A4? (recomendado: os 3)
2. Horas de silêncio: fase própria depois, ou já aqui?
3. Acrescentar "boa semana" a `_MARCAS_FECHO` como segunda rede? (recomendado: não)
