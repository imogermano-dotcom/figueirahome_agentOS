# Leads criadas pelos assistentes — plano

> Mexe em `tools.py` e `guards.py` (caminho de escrita de todos os canais).
> **Plano antes de código** (CLAUDE.md, regra 2). Origem: pergunta sobre o chat do site
> (07/10) e a conversa da candidata de 07/10; medições do mesmo dia, só leitura.

## Problema (medido a 07/10, tabela `leads`, 333 linhas)

| Origem / tipo | Leads |
|---|---|
| `meta` / `compra` | 308 |
| `assistente` / `compra` | 15 |
| `assistente` / `recrutamento` | 10 |

**As 25 leads criadas por assistentes** (`origem = assistente`):
- **Todas em `estado = nova`**: nenhuma foi alguma vez qualificada, contactada ou fechada.
- **Nenhuma tem telefone nem nome na própria linha** (25/25): só `cliente_id`.
- **Tipo mal etiquetado**: das 15 `compra`, só **1** é compra de facto. 8 são candidatos
  (o `tipo_interesse` do cliente é `recrutamento`, de antes do arranjo de 29/09), 2 são
  `outro` e 4 não têm `tipo_interesse`.
- **MQL completo e nunca promovida**: a única lead assistida com tipo+orçamento+zona (chat do
  site, 17/09) continua `nova`, `qualificada_em` vazio. Logo, nunca houve a tarefa
  "Lead qualificada — passar ao eGO" nem o email ao corretor.

### Causas (no código)
1. **`tools._criar_lead_se_preciso` insere só `{cliente_id, estado, origem, notas}`** (e `tipo`
   só para recrutamento). Tudo o que procura leads **por telefone ou email** não as vê:
   `guards.lead_aberta` (router e contexto), `encerrar_lead_do_telefone`, o guarda do nudge
   (`_pode_enviar_a1`) e `guards._promover_lead`.
2. **A promoção chega antes da lead existir.** `_promover_lead` corre dentro de
   `find_or_create_cliente`, **antes** de `_criar_lead_se_preciso` criar a lead no mesmo
   `guardar_dados_cliente`; e só actualiza leads em `contactada` (as da Meta).
3. **No site, nunca há segunda hipótese.** `promover_se_qualificada` (fim do turno) só corre
   `if telefone`, e o chat do site não tem telefone de canal.
4. **`leads.tipo` tem por omissão `compra`** e só o recrutamento é distinguido. Um vendedor
   (Bárbara) ficaria `compra`; `agente_de_lead` mandaria esse número para a Matilde.
5. O texto da tarefa diz "Lead da **Meta** qualificada", mesmo vinda de um assistente.

## Proposta

### P1. Lead criada com contacto e tipo certo (`_criar_lead_se_preciso`)
- Copiar `nome`, `telefone` e `email` do cliente para a lead.
- `tipo` a partir do `tipo_interesse`: `compra`→`compra`, `arrendamento`→`arrendamento`,
  `venda`→`angariacao`, `recrutamento`→`recrutamento` (vocabulário que `agente_de_lead` já
  entende). Para `outro`/vazio: **não criar lead** (decisão 1).
- Efeito lateral desejado: `lead_aberta`, `encerrar_lead` e o nudge passam a ver estas leads, e
  `agente_de_lead` devolve a Inês a uma candidata que a Maria registou (hoje volta ao router).

### P2. Promover quando a lead já existe (`tools._guardar_dados_cliente`)
- Depois de `_criar_lead_se_preciso`, se `lead_qualificada(cliente)` e o tipo for compra ou
  arrendamento (decisão 2), chamar `_promover_lead` sobre as leads abertas (`nova`+`contactada`+…).
- `_promover_lead` passa a procurar também **por `cliente_id`** (além de telefone/email), para
  apanhar as leads antigas e as do site (sem telefone de canal).
- Idempotente: depois de `qualificada` já não bate no filtro, por isso a tarefa e o email saem
  **uma vez**. Cobre WhatsApp e site com o mesmo código, sem depender de `promover_se_qualificada`.

### P3. Texto neutro na tarefa
- "Lead da Meta qualificada…" → origem real (`meta`/`assistente`) e canal.

### P4. Backfill das 25 leads (SQL, corres tu; **a ordem importa**)
1. **Primeiro o `tipo`**: as 8 `compra` com cliente `recrutamento` passam a `recrutamento`.
   Se copiássemos o telefone antes, `agente_de_lead` mandava essas candidatas para a Matilde.
2. Depois nome/telefone/email a partir de `agente_clientes` (por `cliente_id`).
3. As 6 duvidosas (`outro` ou sem tipo) e a 1 com MQL completo: ver decisões 3 e 4.
4. **Colisões** (achado ao simular, 08/10): uma candidata (registada como `compra` a 21/09) partilha o
   telefone com **2 leads abertas da Meta**. Copiar-lhe o telefone tornava `lead_aberta` (limit 1)
   ambíguo entre a Matilde e a Inês; o SQL **exclui** as leads cujo telefone já está noutra lead aberta
   (resultado esperado: 18 das 19 candidatas a contacto).

SQL pronto e com contagens esperadas em `leads-do-assistente-backfill.sql` (passo 0: cópia de
segurança; passos 1–2; verificação; como desfazer). Corre-se **depois** do deploy.
Regra do projecto: dados corridos à mão pelo utilizador, explicados antes.

## Fora desta fase
- Fusão de duplicados em `contactos`, `origem = site`, nudge/horas de silêncio.
- Nudge e follow-up no site (não há telefone nem consentimento WhatsApp).
- `lead_aberta` por `cliente_id` para o router (o chat do site continua sem identidade até dar o
  telefone; não se mexe no routing).
- Tool de encaminhamento pelo modelo (`encaminhamento-pelo-modelo-plano.md`).

## Testes (`backend/tests/`, hoje 294)
1. `_criar_lead_se_preciso`: copia contacto; mapeia os 4 tipos; `outro` não cria; idempotente.
2. `_promover_lead`: encontra por `cliente_id` quando a lead não tem telefone/email.
3. `guardar_dados_cliente` com MQL completo, **sem telefone no contexto** (site): lead
   `qualificada`, 1 tarefa e 1 email; chamada repetida não duplica.
4. Recrutamento/venda com campos de MQL não são promovidos.
5. `agente_de_lead` devolve `a3_recrutamento` para o telefone de uma lead `recrutamento` criada por
   assistente (regressão do routing).
6. Regressão da Meta: lead `contactada` com telefone continua a ser promovida como antes.

## Risco
- **Routing**: leads que passam a ser visíveis por telefone alteram `agente_de_lead`. É o objectivo,
  mas só é seguro com o `tipo` já corrigido (daí a ordem do P4) e com o P1 a gravar o tipo certo.
- **Volume de emails**: passa a haver email por lead qualificada do site e do WhatsApp orgânico.
  Hoje seria 0–1 por mês; confirmar que o corretor os quer (decisão 4).
- Backend único, sem migration. Reversível com `git revert`; o backfill desfaz-se com os valores
  antigos (guardar os 25 `id` e `tipo` antes).

## Decisões por confirmar
1. ~~`tipo_interesse = outro` ou vazio~~ — **decidido (08/10): não criar lead.** Continua a gravar em
   `agente_clientes`; sem lead não há etiqueta falsa de "compra".
2. ~~Promover só `compra`/`arrendamento`~~ — **decidido (08/10): opção A, só compra e arrendamento.**
   O MQL (orçamento + zona + tipo) é de comprador; recrutamento e venda já têm o seu aviso
   (`escalar_para_humano`: tarefa + email), e promovê-los duplicaria notificações. Alargar à venda só
   se aparecerem casos reais de vendedores com perfil completo e sem aviso (mudar uma constante + teste).
3. ~~As 6 leads duvidosas (`outro`/sem tipo, hoje `compra`)~~ — **decidido (08/10): ficam como estão
   e sem telefone** (invisíveis ao router e ao nudge; não vão para a Matilde). Fechá-las como
   `sem_interesse` seria assumir algo que não sabemos. O backfill (P4) **não lhes toca**.
4. ~~A lead do chat do site (17/09) com MQL completo~~ — **decidido (08/10): não promover agora**
   (tarefa e email sobre algo com três semanas); fica `nova` até um humano a ver. **Emails de
   qualificação do site e do WhatsApp orgânico: activos** (volume previsto 0–1 por mês).

**Estado: plano fechado a 08/10. Por implementar** (P1–P3 com testes; P4 é SQL a correr pelo utilizador,
explicado antes).
