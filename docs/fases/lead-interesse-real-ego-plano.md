# Lead no eGO quando a pessoa responde com interesse real (plano, pedido #17)

> Estado 25/10: **só plano, nada implementado.** Decisões 1–4 tomadas a 25/10 (as propostas do plano, ver fim).

## Problema

A lead de compra da Meta só chega ao eGO por dois caminhos (`lead-compra-para-ego-plano.md`): recusa do WhatsApp (logo) e
sem resposta em 2 h (cron, 9h–20h). **Quem responde à Matilde com interesse real não chega ao eGO**: fica uma tarefa em
`agente_tarefas` e um email, e a consultora tem de criar o contacto à mão. Casos de 24/10 (campanha FH2584): pedido de negociação
de preço (tarefa de escalada), pedido de visita, "quero comprar", e uma lead qualificada de arrendamento (tarefa «criar o contacto
no eGO e associar a oportunidade», ainda pendente). Pedido #17 do Miguel: *criar a lead no eGO só quando o agente confirma interesse
real, com nome, telefone, email, imóvel, resumo da conversa e origem*.

## Desenho

**A conversa não fala com o eGO.** Quando há interesse real, o assistente só **marca** o contacto; o cron que já existe
(`leads-compra-para-ego`, de 10 em 10 min, 9h–20h) cria a lead. Assim a conversa não depende da API do eGO, uma falha repete-se na volta
seguinte e a janela da consultora é a mesma das outras leads. Custo: até ~10 min de atraso.

### O sinal de interesse real (escrito em código, nunca decidido pelo modelo)

Três pontos, todos já existentes, que passam a chamar `marcar_interesse_real(telefone, motivo, resumo)`:

1. `pedir_visita` com sucesso (passou a regra dos 80 %).
2. `escalar_para_humano` com motivo de compra (regex no `motivo`: `proposta|negoci|visita|oferta|compra`; fora: recrutamento, angariação,
   reclamação, legal). Só marca se o contacto for comprador.
3. `_promover_lead` (MQL: tipo + orçamento + zona; compra e arrendamento).

Responder, perguntar o preço ou pedir fotografias **não** é interesse real.

### Dados (migration `0051`, corres tu; aditiva e nullable)

`contactos.interesse_real_em timestamptz`, `interesse_real_motivo text`, `interesse_real_resumo text`.
`marcar_interesse_real` procura o contacto Meta do comprador por variantes do telefone; o 1.º sinal grava, os seguintes (antes de a lead
ser criada) acrescentam ao resumo. Nunca levanta: um erro aqui não pode estragar a resposta ao cliente.

### O cron

`processar()` ganha uma 2.ª consulta: contactos com `interesse_real_em` e `ego_lead_em` nulos, **mesmo com `respondeu_em`**.
Mesmas regras de hoje: janela 9h–20h, só depois de `LEAD_COMPRA_EGO_DESDE`, `leads_abertas()` para não duplicar, oportunidade ativa não
cria, email obrigatório, **nunca sem consultora** (`SemConsultora`), idempotência por `ego_lead_em`/`ego_lead_id`. O OBS da lead passa
a dizer «respondeu à Matilde com interesse real: <motivo>. Resumo: <≤ 600 caracteres>. Contactar por telefone ou WhatsApp.» (função
`observacao_da_lead` com parâmetro novo; sem email extra: o da escalada/visita já foi).

### Contacto que já tem lead no eGO

Se a lead foi criada pelo caminho das 2 h e a pessoa responde depois, **não se cria outra**. Fase 2 (opcional): acrescentar o resumo ao
OBS com `ego_api.atualizar_lead` (corpo completo, confirmado a ler; ver CLAUDE.md). Fase 1 deixa só o email que já existe.

## Fora de âmbito

Contactos que não são leads Meta (chat do site, WhatsApp sem campanha), recrutamento e angariação, notas em oportunidades existentes
(o #46 do Miguel), tarefas no eGO, sincronizar o estado de volta.

## Interruptor e reversão

Segredo `LEAD_INTERESSE_EGO` no Fly (vazio = desligado, o código só marca e o cron ignora). Entra desligado; liga-se com ordem expressa.
Desligar: apagar o segredo. As marcas ficam em `contactos` sem efeito.

## Testes

Sinal: regex do motivo (compra sim; recrutamento, angariação, reclamação não); `marcar_interesse_real` (contacto Meta comprador marca; sem
contacto, sem telefone, ou vendedor/recrutamento não marca; segundo sinal acrescenta; erro da BD não levanta). Cron: marcada e com
`respondeu_em` cria; fora do horário espera; já na caixa ou com oportunidade ativa não cria; sem email conta como erro; sem consultora
não marca; `ego_lead_em` impede a segunda; interruptor desligado ignora. OBS com resumo cortado e sem emails.

## Passos (cada escrita em produção só com ordem expressa)

1. Decisões abaixo.
2. Migration `0051` (a correres tu).
3. Código + testes; deploy do `figueirahome-agentos` com o interruptor desligado.
4. Retroativo (opcional, com lista aprovada): marcar os casos dos últimos dias.
5. Ligar `LEAD_INTERESSE_EGO` e verificar a próxima lead real (contacto marcado, lead na caixa, consultora certa).
6. Docs: CLAUDE.md e este plano.

## Decisões (25/10, as propostas do plano)

1. **Arrendamento num anúncio de venda:** a lead qualificada (MQL) que procura arrendar vai para o eGO, com o OBS a dizer «procura arrendamento».
2. **Janela das 9h–20h** também aqui, como as outras leads.
3. **Retroativo:** só daqui em diante. Os casos de 22–25/10 (uma escalada por negociação de preço e uma lead qualificada de arrendamento) ficam com as tarefas que já existem.
4. **Fase 2** (acrescentar o resumo a uma lead que o cron das 2 h já criou): só depois de ver a fase 1 a funcionar. Isto retira o passo 4 («retroativo») da lista acima.
