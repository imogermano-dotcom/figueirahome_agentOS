# Resumo — Métricas do A1 em 4 blocos de negócio

> Fase concluída em 2026-08-03. Plano aprovado na mesma sessão.
> Sucede à fase de observabilidade (`assistentes-observabilidade-resumo.md`).

## O ponto de partida

A aba Métricas mostrava o que a instrumentação capta — custos, latência, cache,
tokens. Informação **técnica**. O pedido era reorganizá-la em quatro blocos de
**negócio**: funil, saúde do atendimento, preferências de mercado, estado
operacional.

**Verificação antes de planear: metade das métricas não era calculável.**

| Lacuna | Causa |
|---|---|
| Zonas, tipologias, preço pedido | `engine.py` guardava `bloco["name"]` e descartava `bloco["input"]` |
| Taxa de conversão por assistente | `agente_tarefas` sem `conversa_id` nem `agente` |
| Motivos de transbordo | Enterrados no texto do `titulo`, só acessíveis por ILIKE |
| Uptime | Não é medido em lado nenhum |

## O que ficou

| Camada | Entrega |
|---|---|
| Dados | `0018` — `tools_detalhe` (jsonb) + `tipo`/`agente`/`conversa_id`/`motivo` nas tarefas |
| Captura | `engine.py` guarda argumentos das tools de pesquisa; `tools.py` atribui as tarefas |
| Agregação | `0019` — `agente_metricas` v2 em 4 blocos |
| Painel | `AgenteMetricas.jsx` reescrito; detalhe técnico recolhível |

### Os quatro blocos

- **🌟 Funil** — leads captados, MQLs, taxa de qualificação, visitas, taxa de conversão
- **💬 Atendimento** — resposta p50/p95, transbordos e taxa, **motivos agregáveis**,
  mensagens por conversa, conversas longas, clientes recorrentes
- **🏠 Preferências** — zonas, tipologias, preço médio/mediano pedido, orçamento
  declarado, intenção (compra/arrendamento/venda)
- **⚙️ Operacional** — custo total e por interação, taxa de sucesso, última
  interação, cache, canais, tools; tokens e contexto num bloco recolhível

## Decisões

**MQL = orçamento + zona + tipo de interesse.** O "timing" não é recolhido pelo
A1 e acrescentá-lo obrigava a mais uma pergunta na conversa — decisão do
utilizador foi usar só o que já existe.

**PII nunca entra no `tools_detalhe`.** `pesquisar_imoveis` e `ficha_imovel`
guardam os argumentos; `guardar_dados_cliente`, `agendar_visita` e
`escalar_para_humano` recebem nome, telefone e email e guardam **só o nome da
tool**. Copiá-los espalharia dados pessoais por uma segunda tabela sem ganho —
o bloco de preferências só precisa dos critérios de pesquisa.

É uma **allowlist, não uma blocklist**: uma tool nova entra por omissão no lado
seguro. Um teste falha de propósito se alguém alargar a allowlist sem reparar.

**Porque os argumentos das pesquisas valem mais que `agente_clientes`:** captam
toda a gente que procurou, incluindo quem nunca deixou contacto. `agente_clientes`
só tem quem chegou a registar-se.

**Sem uptime inventado.** O ecrã diz explicitamente que não o mede e aponta para
o painel do Fly.io. Mostra taxa de sucesso e última interação, que são o que os
dados suportam.

**Percentagens com denominador visível.** Abaixo de 20 turnos, a taxa aparece
como "33% (1 de 3)". Com 5 conversas em produção, uma percentagem isolada seria
ruído apresentado como sinal.

## Bug de deduplicação apanhado na verificação

Não estava no plano. `guardar_dados_cliente` grava o nome **sem telefone** (o
modelo nem sempre o passa); no turno seguinte `agendar_visita` traz o telefone.
A procura por telefone falha e a procura por nome era **saltada** — a condição
era `if nome and not telefone and not email`. Resultado: duas linhas para a
mesma pessoa. É o padrão normal de uma conversa — dados parciais primeiro,
completos depois.

**Correcção:** tentar o nome sempre, aceitando a correspondência só quando nada
contradiz (`_compativel`). Telefone/email vazios ou iguais → é a mesma pessoa e
os campos em falta são preenchidos. Telefones diferentes → dois homónimos, duas
linhas. Reproduzido contra a BD real: 1 linha no cenário do bug, 2 no cenário
dos homónimos.

## Verificação

- `test_metricas_negocio.py` — 7 asserts no filtro de PII, incluindo uma trava
  que falha se a allowlist crescer sem revisão.
- `test_guards.py` — 3 asserts novos em `_compativel`.
- **Ao vivo**: `tools_detalhe` traz `{"zona": "Figueira da Foz", "quartos": 2,
  "preco_max": 150000}`; auditoria confirmou **zero** ocorrências de nome,
  apelido, telefone ou `@`. Visita gravada com `tipo`, `agente`, `conversa_id`.
- **RPC contra contagens directas**: 8 métricas, todas batem.

## Ressalvas registadas

⚠️ **A primeira execução do teste de dedup falhou com o mesmo código que depois
passou.** Sem explicação confirmada. Hipótese: atraso de leitura-após-escrita no
PostgREST (o insert ainda não visível ao SELECT seguinte). A ser isso, o dedup
pode falhar esporadicamente sob carga e a correcção não cobre esse caso.

⚠️ **Leads não são atribuíveis por assistente.** `agente_clientes` não tem coluna
`agente`, por isso o bloco Funil mostra os mesmos números no A1 e no A2. Não foi
inventada uma atribuição.

## Fora de âmbito

Recolher "timing" do cliente, sonda externa de uptime, alertas de orçamento,
exportação, séries temporais (com 5 conversas não há série para desenhar).
