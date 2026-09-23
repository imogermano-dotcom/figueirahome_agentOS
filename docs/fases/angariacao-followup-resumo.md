# Resumo — follow-up de angariação (Bárbara) + routing sem semeadura (23/09)

Plano: `docs/fases/recrutamento-followup-plano.md` (mesmo desenho, referido
antes de ser sobrescrito — ver `cron-manager-fly-resumo.md` e
`recrutamento-followup-resumo.md` para o padrão original). Pedido:
follow-ups para os assistentes que faltavam, a começar pela Bárbara (A4).

## Achado antes de construir

A suposição registada a 22/09 ("routing já cobre A1/A4") estava errada.
`lead_meta_angariacao` (RPC da Meta) só escreve em `contactos`
(`tipo_contacto=['vendedor']`), nunca em `leads`/`leads_angariacao` —
confirmado por dados reais (zero linhas). Mesmo bug que a Inês tinha:
resposta a um template caía na Maria (A2). A Matilde (A1) não tinha este
problema — `lead_meta_compra` escreve em `leads` **e** `contactos`.

## O que mudou

| Ficheiro | O quê |
|---|---|
| `backend/app/agents/broker/guards.py` | `contacto_recrutamento_aberto` generalizada → `contacto_meta_aberto(telefone, tipo_contacto)`; `agente_de_lead` ganha fallback para `'vendedor'` além de `'recrutamento'` |
| `backend/app/agents/broker/engine.py` | `responder()` marca `respondeu_em` para A4 no mesmo ponto que já marcava A3 |
| `backend/tests/test_guards.py` | testes actualizados + 1 novo (fallback angariação) — 274 verdes |
| n8n `3NduMpeikAoCaqcA` | "follow-up angariação (diário)", 24h, testado |
| n8n `lkx0cnWdpWWgKzCE` | "follow-up angariação 2, última tentativa (72h)", testado |

Sem migration nova — `contactos.respondeu_em`/`follow_up_em`/`follow_up_2_em`
já existiam (0039/0040), genéricas.

## Templates

- `figueirahome_angaria_follow|pt_PT` (24h), 1 variável: *"Olá {{1}}, Sou a
  Bárbara, assistente virtual da Figueira Home. Ainda estamos disponíveis
  para ajudar no seu pedido de contacto, para vender o seu imóvel. Responda
  quando puder."*
- `figueirahome_angaria_follow_2|pt_PT` (72h), 1 variável: *"Olá {{1}}, Sou
  a Bárbara, assistente virtual da Figueira Home. Recebemos o seu pedido de
  contacto sobre um imóvel na Figueira da Foz que pretende vender esta será
  a nossa última tentativa de contacto. Se ainda quiser avançar, é só
  responder."*

## Testado 23/09 — tudo confirmado

Deploy feito. Routing testado ao vivo ("sim" a um contacto `vendedor` aberto
caiu em `a4_angariador`, não A2; `respondeu_em` gravado). Os 2 fluxos n8n
corridos à mão (via editor, não Cron Manager — vivem no n8n, não no Fly):
WhatsApp entregue nos dois, `follow_up_em`/`follow_up_2_em` gravados,
`template_enviado_em` intacto nos dois casos. Dados de teste limpos.

## Por fazer

- Activar os `Schedule Trigger` dos 2 fluxos (confirmação explícita).
- Matilde (A1): decidir se também merece 2º/3º follow-up — não pedido ainda,
  routing já funciona sem mudanças.

## Como testar

1. `pytest backend/tests/` — 274 verdes.
2. Fluxos n8n `3NduMpeikAoCaqcA` (24h) e `lkx0cnWdpWWgKzCE` (72h), "Test
   workflow" no editor.
