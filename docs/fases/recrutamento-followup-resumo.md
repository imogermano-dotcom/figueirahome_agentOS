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

## Por fazer

- **Correr a `0039`** no editor SQL.
- **Deploy do backend.**
- Teste de routing ao vivo: candidato com `contactos` aberto responde no
  WhatsApp → confirmar `a3_recrutamento`, não A2.
- Corrida manual do fluxo novo (`Limit=5`, já no ficheiro) sobre um
  candidato de teste → confirmar WhatsApp entregue e `follow_up_em` gravado.
- Só depois: activar o `Schedule Trigger`.

## Como testar

1. `pytest backend/tests/` a partir de `backend/` — 269 verdes (4 novos em `test_guards.py`).
2. `select respondeu_em, follow_up_em from contactos limit 1;` depois da `0039`.
3. Fluxo n8n `3pKTcPNSU850s0ha`, execução manual, `Limit=5`.
