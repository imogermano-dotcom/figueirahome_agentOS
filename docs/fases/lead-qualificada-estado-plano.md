# Lead que a Matilde qualifica fica «nova» (24/11)

Origem: ponto 4 do pedido #47 do Miguel (FH2572, leads de 20–21/11). **Plano antes de código; nada deste plano está implementado.**

## Problema
Uma lead de compra (Meta) com a conversa toda feita (tipologia, zona, orçamento e até uma proposta de compra) continua com `leads.estado = 'nova'`,
`qualificada_em` vazio e sem o aviso «lead qualificada» à consultora. A pessoa só chegou ao eGO porque o cron das 2 h/«respondeu» a apanhou (39 h depois).

## O que se sabe (leitura, 24/11)
- A promoção a `qualificada` (`guards.promover_lead_do_cliente` / `promover_se_qualificada`) **não lê a conversa**: exige `agente_clientes` com
  `tipo_interesse`, `orcamento` e `zona_preferida` preenchidos (`guards.lead_qualificada`, a regra do MQL).
- Nesta pessoa a ficha de cliente tem os 3 campos **vazios**, mas as `notas` têm o resumo da conversa de 21/11 (a proposta de compra, o imóvel, a zona).
  Logo `guardar_dados_cliente` **foi chamado** com `resumo`, e os campos estruturados ficaram por preencher.
- `tools._guardar_dados_cliente` tem uma rede para isso (`_extrair_mql_do_resumo`: uma 2.ª chamada forçada por tool que tira tipo/orçamento/zona do `resumo`),
  e só corre se o `resumo` existir e faltar algum campo. Aqui não apanhou nada (ou nem correu, ou devolveu vazio).
- `interesse_real_em` desta pessoa é de 25/10 (negociação de preço, 1.ª entrada); a conversa de 21/11 não o marcou, por isso o caminho «interesse real → lead no eGO» não disparou.
- Medido nas leads Meta com anúncio desde 01/11 (87): todas as 50 que responderam têm conversa; as 36 sem conversa nunca responderam (comportamento esperado).

## Hipóteses (por esta ordem)
1. O modelo chama `guardar_dados_cliente` só com `resumo` e a extração devolve vazio porque o resumo não diz «compra» nem o orçamento como número
   (a proposta é de um valor, não um «orçamento até»).
2. A extração devolve campos mas `find_or_create_cliente` não os grava (só grava o que não é `None`, e `tipo_interesse` pode vir fora do enum).
3. A chamada nem chegou a correr (erro silencioso: `_extrair_mql_do_resumo` devolve `{}` em qualquer exceção).

## Passos (cada um com OK próprio)
1. **Reproduzir sem escrever:** correr `_extrair_mql_do_resumo` com o resumo desta ficha (nomes e contactos retirados) e ver o que devolve. Decide a hipótese.
2. **Medir a dimensão (leitura):** nas leads de compra que responderam desde 01/11, quantas têm a ficha com MQL incompleto e `leads.estado` ainda `nova`/`contactada`,
   e quantas dessas tinham falado de orçamento/zona/visita/proposta. Sem isto não se sabe se é 1 caso ou uma fuga sistemática.
3. **Corrigir** conforme o passo 1:
   - a) se o extrator falha com «proposta de €X»: ensiná-lo (o valor de uma proposta conta como orçamento) e dar-lhe também as mensagens da pessoa, não só o `resumo` do modelo;
   - b) se o modelo não passa os campos: reforçar a descrição da tool e a regra no prompt da Matilde («passa tipo, orçamento e zona sempre que os souberes»);
   - c) rede em código no fim do turno (`promover_se_qualificada`): se houve `guardar_dados_cliente`, o MQL ainda está incompleto e a conversa já tem tipo, orçamento e zona, extrair das mensagens da pessoa e promover. Uma chamada por turno só quando faltam campos.
4. **Proposta/visita como interesse real:** uma conversa com proposta de compra deve marcar `interesse_real` (hoje só `pedir_visita`, escalada e lead qualificada). Se a 3.c a promover, isto vem de graça (a promoção chama `marcar_interesse_real`).
5. Testes (extrator com resumo de proposta, rede em código, nada a promover sem os 3 campos), commit, push, deploy; medir 1 semana.

## O que não muda
- A regra do MQL (orçamento + zona + tipo de interesse) continua em `guards.py`; só se garante que os campos chegam lá.
- Nunca inventa campos: só o que a pessoa disse. `leads.estado` só passa a `qualificada` pela promoção existente.
- A lead que a promoção cria no eGO continua a passar pelas mesmas travas (consultora, 1 aviso por pessoa em 24 h, reentrada).

## Riscos
- Mais uma chamada ao modelo por turno nas conversas em que falta o MQL: custo pequeno, só depois de `guardar_dados_cliente` e com campos em falta.
- Promover cedo demais (o orçamento citado é de outra pessoa ou de outro imóvel): o extrator só devolve o explícito; a consultora vê o resumo no aviso.
- Reentrada: a ficha do cliente é por telefone e mantém os campos da entrada anterior; uma ficha antiga completa promove a lead nova logo ao 1.º turno (já acontece hoje; a decidir se é o que se quer).

## Fora deste plano
- «4 contactos repetidos com o telefone»: encontrei 2 em `contactos` (a da Meta e a do scraper do eGO, ambas com `ego_link`), 1 cliente e 2 conversas; a fusão de duplicados é à parte, com o Miguel.
- O atraso de 31 h das duas leads de 20/11 (a Meta não chamou o n8n): tratado com o texto novo do Vigia e os ids por formulário (`docs/n8n/README.md`).

## Resultados dos passos 1 e 2 (24/11, só leitura)
**Passo 1: o extrator não é o problema.** Com o resumo desta ficha (nomes e contactos retirados) `_extrair_mql_do_resumo` devolve os três campos
(`compra`, 240000, «Figueira da Foz»). As hipóteses 1 e 3 caem. Existe desde 31/08 (`8e72c4c`).

**Causa mais provável:** `tools._escalar_para_humano` grava o `resumo` nas `notas` da ficha através de `find_or_create_cliente(nome, telefone, notas=…)`,
**sem tipo, orçamento nem zona e sem passar pelo extrator** (a extração só existe em `_guardar_dados_cliente`). Uma conversa que acaba numa escalada
(proposta de compra, pedido de visita, reclamação) deixa a ficha com notas e sem MQL, e a promoção nunca dispara. Das 10 fichas incompletas, pelo menos 5 têm tarefa de escalada
(a procura por telefone no título/descrição é grosseira: é um mínimo).

**Passo 2: a dimensão (50 leads Meta com anúncio que responderam desde 01/11):**
- 33 não têm ficha de cliente: a Matilde nunca chamou `guardar_dados_cliente` (conversa curta ou sem dados).
- 7 têm o MQL completo e **todas foram promovidas** (0 ficaram «nova»): a regra funciona quando os campos chegam.
- 10 têm ficha com notas e MQL incompleto, **5 delas com conversa em que a pessoa falou de orçamento, zona, visita ou proposta**. As 5 estão «nova» e no eGO (pelo cron «respondeu»); 2 têm `interesse_real`.
- Ou seja: não é um caso isolado, é uma fuga nas conversas que acabam em escalada, e hoje só a apanha o cron das 2 h.

## Correção proposta (passo 3, refinado)
1. **Extrair também na escalada:** em `_escalar_para_humano`, antes do `find_or_create_cliente`, o mesmo passo de `_guardar_dados_cliente` (extrair do `resumo` se faltar algum campo).
   Factorizar numa função (`_completar_mql(inputs)`) usada pelas duas tools, sem duplicar.
2. **Só A1/A2 e só `compra`/`arrendamento`:** a escalada serve também a Inês e a Bárbara, e um `tipo_interesse` de recrutamento ou venda mexeria em `contactos.tipo_contacto`
   (o espelho em `_espelhar_em_contactos` usa o tipo). Fora do alcance, não se grava nada novo.
3. **Promover logo:** com os 3 campos, `find_or_create_cliente` já chama `_promover_lead` (a lead `nova` existe: vem da Meta). O aviso à consultora sai por aqui,
   com a trava de 1 por pessoa em 24 h, e sem duplicar a escalada (que já avisou as consultoras do telefone, pedido #20).
4. **Teste:** escalada com resumo «proposta de €X para T4 em Y» deixa ficha completa e lead `qualificada`; escalada de recrutamento não toca em `tipo_interesse`; extrator vazio não derruba a escalada.
5. **Backfill:** as 5 fichas do passo 2 ficam completas se se correr o extrator sobre as `notas` (um script, `--dry` por omissão, com OK à parte). Não promove retroativamente leads já no eGO.

## Estado (24/11)
Código dos pontos 1–4 feito e testado (`tools._completar_mql`, usado por `_guardar_dados_cliente` e `_escalar_para_humano`; `tests/test_escalar_mql.py`, 997 testes a passar;
`conftest` nunca chama o modelo a sério). Por commit/push/deploy (OK do utilizador). Depois: medir 1 semana (fichas incompletas com conversa de dados, leads «nova» com MQL dito) e o backfill das 5 fichas (script `--dry`).
**Limite aceite:** na escalada o extrator pode sobrepor um orçamento já gravado pelo valor de uma proposta (como já faz `guardar_dados_cliente`).
