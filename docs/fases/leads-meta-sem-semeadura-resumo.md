# Resumo — A1 assume a lead da Meta sem semeadura (2026-08-15)

Plano: `docs/fases/leads-meta-sem-semeadura-plano.md`. Decisões:
`docs/decisoes.md`, secção "Leads da Meta".

## O que ficou a funcionar

A lead responde ao template e o A1 assume **já com contexto**, sem que ninguém
chame um endpoint nosso — portanto sem `AUTOMACAO_SECRET`.

Fluxo real: Meta → Make (escreve a lead em `leads`) → webhook → n8n (envia o
template e grava-o em `leads.template_enviado`) → a lead responde → o A1 entra.

## Alterações

| Ficheiro | O quê |
|---|---|
| `supabase/migrations/0024_leads_template.sql` | `template_enviado` + `template_enviado_em` |
| `guards.py` | `_ALIAS_FICHA` + `campos_mql_da_ficha()` (vindos de `api/leads_meta.py`), e `lead_aberta()` extraída de `agente_de_lead` |
| `engine.py` | `_texto_perfil()` e `_contexto_inicial()`; `responder` passou a usá-la |
| `api/leads_meta.py` | importa o mapa partilhado; resto igual, fica inerte |
| `tests/test_leads_meta.py` | 6 testes novos — **75 verdes** |

`_contexto_inicial` faz duas coisas num só sítio:

1. **Perfil** — de `agente_clientes` como sempre e, **só se não houver linha**,
   dos campos MQL de `leads.ficha`. `agente_clientes` ganha sempre: é escrita
   durante a conversa, logo mais recente que o formulário. Deixar a ficha
   sobrepor-se ressuscitaria um orçamento que o cliente já tinha corrigido ao A1.
2. **Template** — entra como mensagem do assistente **só no primeiro turno**
   (`thread_nova`), para o A1 não voltar a cumprimentar. Nos turnos seguintes já
   está no histórico gravado.

Nada mudou na qualificação: `promover_se_qualificada` já aceitava leads `nova`
(2026-08-14), e é isso que torna este fluxo viável sem semeadura.

## Por fazer

- **Correr a `0024`.**
- **Deployar o backend** — nada disto está em produção (`9838377`).
- **Confirmar os campos reais do formulário de venda.** `_ALIAS_FICHA` continua
  a ser palpite tirado do formulário de angariação. Se os nomes não baterem, o
  A1 fica cego na mesma e a lead nunca é qualificada: o código está pronto, a
  fase só entrega valor depois disto.
- **Confirmar que é o n8n** a escrever `template_enviado`, e não o Make.

## Como testar

1. `pytest backend/tests/` a partir de `backend/` — 75 verdes.
2. Correr a `0024` e confirmar as duas colunas.
3. Fim a fim, com o backend deployado: inserir lead de teste com `ficha` e
   `template_enviado`, responder "Sim" desse número no WhatsApp, e confirmar que
   o A1 **não** pergunta orçamento/zona/tipo, não cumprimenta de novo, e que ao
   fim do turno a lead fica `qualificada` com tarefa criada.
4. Regressão: uma conversa de quem **não** tem lead aberta comporta-se como hoje.
