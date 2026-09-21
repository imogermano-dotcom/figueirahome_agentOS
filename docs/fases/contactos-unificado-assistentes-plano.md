# Plano — `leads`/`agente_clientes` → `contactos` como registo único (assistentes)

> **Opção B aplicada em 21/09** (parcial — só a captação inicial, não a
> migração completa): `find_or_create_cliente` (`guards.py`) passou a
> espelhar em `contactos` via `_espelhar_em_contactos`, aditivo, nunca mexe
> em linha que não seja sua (`agente is not null`). `contactos` ganhou coluna
> `agente` (ALTER à mão, sem migration própria no repo — como sempre).
> `agente_metricas` (migration 0038) passou a contar `leads_captados` daqui,
> por assistente. `leads`/`agente_clientes` continuam a ser a fonte de
> verdade operacional (MQL, estados, painel, notificações) — nada disso
> mudou. Detalhe: `docs/decisoes.md`. Opções A/C abaixo continuam por decidir
> se um dia se quiser ir mais longe.

## Objectivo

Pedido do utilizador (18/09): leads dos assistentes (A1/A2, e no futuro
A4/Bárbara) devem parar de nascer em `leads`+`agente_clientes` e passar a
nascer em `contactos` — a mesma tabela que já recebe as leads da Meta desde a
migração de 14–17/09 (`leads-meta-n8n-resumo.md`). Origem diferente, mesma
tabela, campos a identificar a origem.

## Estado actual (facto, não opinião)

Três tabelas de lead/contacto, cada uma com dono e forma diferentes:

| | `contactos` | `leads` | `agente_clientes` |
|---|---|---|---|
| Dono | scraper (upsert por `ego_link`) **+** pipeline externo do Miguel | assistentes (A1/A2), painel | assistentes (A1/A2) |
| PK | **nenhuma** — soft `(nome, criado_em)` | `id` uuid | `id` uuid |
| Liga a quem | nada (tabela achatada) | `cliente_id` → `agente_clientes.id` | — |
| Estado | `estado` texto livre, sem máquina de estados (só visto `'nova'`) | `estado` com ciclo definido (`nova→qualificada→contactada→...`, `ESTADOS_FECHADOS`) | — |
| MQL (orçamento/zona/tipo) | **não tem** | não tem (fica no cliente) | tem (`tipo_interesse`, `orcamento`, `zona_preferida`) |
| Telefone | `telefone` **e** `telemovel`, nenhum normalizado (invariante conhecida: por isso o telefone só acha 54/281 contactos, o email 232) | `telefone` normalizado | `telefone` normalizado |
| Tipo/origem | `tipos` (livre, heterogéneo) **e** `tipo_contacto` (array novo, `comprador`/`vendedor`/`recrutamento`) — dois campos sobrepostos, ainda por resolver com o Miguel | `origem`, `tipo` | `origem` |
| Colunas de negócio dos assistentes | não tem | `qualificada_em`, `follow_up_em`, `contacto_humano_em`, `conversa_id` | — |

`_criar_lead_se_preciso`/`find_or_create_cliente` (`guards.py`, `tools.py`)
são o único caminho de escrita dos assistentes — dedup por
telefone→email→nome, sempre contra `agente_clientes`.

## Bloqueadores reais para "uniformizar já"

Não são detalhes de implementação — decidem a abordagem:

1. **`contactos` não tem `id`.** `leads.cliente_id`, `agente_tarefas` (via
   `conversa_id`), e o embed do painel (`agente_clientes(nome, telefone)`,
   `api/leads.py`) dependem de FK para uuid. Sem `id` em `contactos`, ligar
   uma tarefa/conversa a um contacto concreto fica dependente do soft PK
   `(nome, criado_em)` — já demonstrado frágil ao vivo (5 linhas para
   "Miguel Germano", ver `leads-meta-n8n-resumo.md`).
2. **`contactos` não tem MQL** (`orcamento`, `zona_preferida`,
   `tipo_interesse`) nem máquina de estados equivalente a `leads.estado`.
   `lead_qualificada`/`promover_se_qualificada` (`guards.py`) ficam sem onde
   escrever.
3. **`telefone`/`telemovel` de `contactos` não são normalizados** — dedup por
   telefone (`_procurar_cliente`, `variantes_telefone`) rebentaria ou
   duplicaria em silêncio contra dados já sujos.
4. **`contactos` tem dois escritores externos a nós** (scraper + Miguel).
   CLAUDE.md já regista a invariante: não mexer na estrutura sem a query R2
   e sem falar com ele — isto inclui adicionar um terceiro escritor
   (assistentes) à mesma tabela.
5. **`tipos` vs `tipo_contacto`** já sobrepostos e por resolver — juntar mais
   um caminho de escrita (assistentes) agrava, não simplifica, enquanto isto
   não estiver decidido.

Nenhum destes é ficção — todos vêm de trabalho já feito nesta sessão ou
documentado no `CLAUDE.md`.

## Opções (para decidir, não decidido)

**A. Falar primeiro com o Miguel.** Pedir `id` (ou UUID gerado por nós,
imutável) em `contactos`, e acordar como `tipos`/`tipo_contacto` coexistem
antes de mexer no código dos assistentes. Mais lento, mas evita escrever
lógica de dedup contra uma tabela que ainda vai mudar de forma.

**B. Espelho aditivo, sem tocar no que já existe.** Os assistentes passam a
escrever *também* em `contactos` (como o RPC `lead_meta_compra` já faz —
grava em `leads` **e** em `contactos`), mantendo `leads`/`agente_clientes`
como fonte de verdade operacional (MQL, estados, painel). `contactos` fica
espelho de leitura para quem precisa de ver tudo num sítio. Não resolve
"uma tabela só", mas não bloqueia em nada externo.

**C. Migração a sério** (`leads`+`agente_clientes` desaparecem,
`contactos` ganha `id`+MQL+máquina de estados, painel e `api/leads.py`
reescritos para ler de lá). É o pedido literal do utilizador, mas exige (1)
resolvido, e toca `engine.py`, `guards.py`, `tools.py`, `assistants.py`,
`api/leads.py`, `Leads.jsx` — fase grande, várias sessões.

## Por decidir com o utilizador

- Qual das três opções (ou faseamento A→B→C)?
- Se B ou C: quem faz a pergunta ao Miguel sobre `id`/`tipos` — e quando?
- Scope da 1.ª fatia: só A1, ou já A2/futura Bárbara também?
