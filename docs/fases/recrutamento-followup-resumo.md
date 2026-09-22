# Resumo — follow-up de recrutamento + routing sem semeadura (22/09)

Plano: `recrutamento-followup-plano.md`. Pedido: fluxo n8n para candidatos que
não respondem ao 1º template de recrutamento.

## Achado antes de desenhar

Ia repetir o padrão antigo de semeadura (`api/leads_meta.py`,
`/conversa-semeada`) — investigar mostrou que esse endpoint está **inerte
desde 15/08** (`docs/fases/leads-meta-sem-semeadura-resumo.md`). O
mecanismo real em produção para A1/A4 é `guards.agente_de_lead`, chamado
pelo webhook do WhatsApp **antes** do router: se há uma lead aberta,
força o assistente dono, sem depender de regex nem de thread semeada.
Recrutamento não tinha equivalente — candidatos só existem em `contactos`
(`lead_meta_recrutamento`), nunca em `leads`, logo `agente_de_lead` nunca os
via. Efeito real: uma resposta tipo "Sim" ao 1º template de recrutamento
podia cair na Maria (A2) em vez da Inês — bug já activo, independente do
follow-up.

## O que mudou

| Ficheiro | O quê |
|---|---|
| `supabase/migrations/0039_contactos_respondeu_followup.sql` | `contactos.respondeu_em` + `follow_up_em` (aditivo) |
| `backend/app/agents/broker/guards.py` | `contacto_recrutamento_aberto()`, `marcar_contacto_respondeu()`, `agente_de_lead()` ganha fallback para `contactos` |
| `backend/app/agents/broker/engine.py` | `responder()` marca `contactos.respondeu_em` quando o agente é A3, espelhando o bloco já existente para `leads` |
| `backend/tests/test_guards.py` | 4 testes novos |
| n8n `3pKTcPNSU850s0ha` | novo fluxo "FigueiraHome — follow-up recrutamento (diário)", 9 nós, validado, **inactivo** |

**Zero mudanças ao fluxo de envio do 1º template** — o routing resolve-se
sozinho via `agente_de_lead`, tal como já acontecia para A1/A4.

Template aprovado usado: `figueirahome_recrutamento_followup|pt_PT`, 1
variável (nome): *"Olá {{1}}, Ainda estamos disponíveis para falar sobre a
sua candidatura à FigueiraHome. Responda quando puder."*

## Testado 22/09 — tudo confirmado

Migration `0039` corrida, deploy feito, routing testado ao vivo ("Sim" a um
candidato com `contactos` aberto caiu em `a3_recrutamento`, não A2;
`respondeu_em` gravado). Fluxo n8n corrido à mão (`Limit=5`): mensagem
entregue, `follow_up_em` gravado. Dados de teste limpos a seguir.

Janela alterada de 48h para **24h** a 22/09 (`template_enviado_em=lt.{{
$now.minus(24, 'hours')... }}` no nó `Ler candidatos sem resposta`) — decisão
do utilizador, para abrir espaço a um 3º fluxo a 72h.

## 3º fluxo — "última tentativa" a 72h (22/09)

Pedido a seguir: um 2º follow-up a quem continua sem responder 72h depois
do **1º template** (âncora independente do follow-up de 24h — confirmado
com o utilizador). Isto obrigou a corrigir um bug antes de construir: o nó
`Supabase: marcar follow-up` do fluxo de 24h reescrevia
`contactos.template_enviado_em` para a hora do follow-up — a âncora dos 72h
deixava de ser o 1º template e passava a ser o de 24h, sem ninguém dar por
isso. Corrigido (deixou de tocar em `template_enviado_em`, só grava
`follow_up_em` + o texto).

| Ficheiro | O quê |
|---|---|
| `supabase/migrations/0040_contactos_follow_up_2.sql` | `contactos.follow_up_2_em` (aditivo) |
| n8n `3pKTcPNSU850s0ha` | fluxo de 24h corrigido — não reescreve mais `template_enviado_em` |
| n8n `RuBg6gDOjUmRXZ2U` | novo fluxo "FigueiraHome — follow-up recrutamento 2, última tentativa (72h)", 9 nós, validado, **inactivo** |

Template: `figueirahome_recrutamento_followup_2|pt_PT`, 1 variável (nome):
*"Olá {{1}}, Continuamos disponíveis para falar sobre a sua candidatura à
FigueiraHome. Esta será a última tentativa de contacto. Se ainda tiver
interesse, é só responder."*

Guarda do novo fluxo **não olha a `follow_up_em`** (o de 24h) — as duas
janelas medem-se independentemente a partir do `template_enviado_em`
original; quem nunca recebeu o de 24h (por exemplo, se aquele fluxo falhou
nesse dia) ainda assim recebe este a 72h.

## Por fazer

- Correr a `0040`.
- Testar o fluxo de 72h ao vivo (mesmo processo do de 24h — candidato de
  teste com `template_enviado_em` > 72h).
- Activar os dois `Schedule Trigger` (confirmação explícita, por decidir
  quando).

## Como testar

1. `pytest backend/tests/` a partir de `backend/` — 269 verdes (4 novos em `test_guards.py`).
2. `select respondeu_em, follow_up_em, follow_up_2_em from contactos limit 1;` depois da `0039`+`0040`.
3. Fluxo n8n `3pKTcPNSU850s0ha` (24h) e `RuBg6gDOjUmRXZ2U` (72h), execução manual, `Limit=5`.
