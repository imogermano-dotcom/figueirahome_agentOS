# Lead de compra → eGO (plano)

> ## Estado 20/10 — leitura obrigatória antes do resto (o desenho abaixo é de 16–17/10 e foi em parte superado)
> - **Criação pela Web API, não pela API nova.** A API nova (`InsertLead`, `api.egocrm.com`) exige `internetlead/insert`, que a nossa conta não tem (standby até o Miguel criar um utilizador de serviço). Entretanto cria-se por `PUT http://websiteapi.egorealestate.com/v1/Lead` (o contrato do antigo Make: cabeçalhos `AuthorizationToken`+`Language`; query `CTY=4`, `RID`, `NAM`, `EML`, `PHO`, `OBS`), em `egorealestate.inserir_lead_webapi`. Testado a 20/10: **200 `{"Success":true}`, sem id** na resposta; **sem `EML` dá 400**; a lead aparece na caixa em segundos e o eGO atribui-a em ~2,5 min.
> - **`RID` = `imoveis.ego_id`.** O imóvel só ficou ligado quando publicado (o teste com o FH2564, despublicado, entrou sem imóvel): **por confirmar com um publicado**.
> - **A atribuição é do eGO, não do `angariador`** (teste: Lidia Sousa; as de Setembro do FH2573: Sandra Silva). O email do n8n vai ao Miguel e à consultora do imóvel; quem recebe a lead no eGO pode ser outra pessoa (decisão A, mantida).
> - **Recusa do WhatsApp = criação imediata, no n8n**, a par do email: `POST /api/leads/meta/{meta_lead_id}/recusou-whatsapp` (segredo `X-N8N-Secret`, `require_n8n_access`; abre só este endpoint). Quatro casos: oportunidade ativa com consultor (não cria, devolve o consultor), já na caixa de leads, contacto antigo / sem histórico (cria). Sem email → `sem_email`. Decide-se pelo espelho (`oportunidades`) e por `ListLeadByPage`; se a API nova falhar, cria na mesma e diz `verificado_no_ego: false`. Idempotente por `contactos.ego_lead_em`.
> - **Sem resposta em 2 h** continua no cron `leads-compra-para-ego` (`enabled: false`), agora também pela Web API.
> - **Travas:** `LEAD_COMPRA_EGO_DESDE` vazio = tudo desligado (o endpoint devolve `desligado`; compara por **dia**, porque `contactos.criado_em` é `date`) e o nó n8n «Criar lead no eGO (recusou WhatsApp)» no fluxo `4rDc9amm6HpO5F4j` está **desativado**. Ligar: definir a data no Fly, ativar o nó, ver a 1.ª recusa real.
> - ⚠️ **O n8n publica ao gravar um fluxo ativo**: editar uma ramificação nova liga-a logo. Desativar o nó *antes* de gravar.
> - **Todas as leads de compra da Meta têm email** (o formulário obriga). Medido: 8 de 15 leads de 10/10 em diante já tinham oportunidade ativa com consultora, daí a regra dos 4 casos.

> Pedido do Miguel (16/10): se a lead de um anúncio de compra não responder à Matilde em 2 h, criá-la no eGO para um consultor lhe ligar.
> Estado (17/10): **código escrito e testado (403 testes), nada deployado, migration `0050` por correr, nada escrito no eGO.** Defaults do plano: lead tipo 7, sub-origem 4001, 2 h seguidas, pessoa com oportunidade ativa não é criada, número sem WhatsApp vai logo. Desligado: `LEAD_COMPRA_EGO_DESDE` vazio + cron `enabled: false`.

## O que as leituras mostraram (16/10, só `GET`/`List*`)

| Tema | Achado |
|---|---|
| Problema real | As 5 leads de compra de 13–16/10 não têm oportunidade ligada por `contacto_id`; 2 já eram conhecidas pelo telefone (oportunidade antiga). A Meta não chega ao eGO por outra via. |
| Volume | Histórico: 155 leads de compra com template, **127 (82%) nunca responderam**; das 28 que responderam, 25 foram em ≤ 2 h. Com a regra, ~8 em 10 leads vão para o eGO. |
| Endpoint | `POST /lead/Lead/InsertLead?applicationId=6429`. `externalId` é int32 e o `meta_lead_id` da Meta não cabe (400): a idempotência é só `contactos.ego_lead_em`. |
| Atribuição | **O eGO distribui sozinho**: nas 75 leads ativas, 100% têm consultor atribuído, 109 s de mediana (máx. 206 s) depois de criada. Há regra de entrega (`ListApplicationLeadDelivery`, tipo 2, localização 620). Não precisamos de escolher consultor. |
| Convenções das leads atuais | Todas `originId=1` (Internet), `masterLeadType=2` (Venda), `leadTypeId` 4 (Pedido de Informação, 35), 3 (Pedido de Visita, 27), 1 (Procura, 10), 7 (Pedido de Contacto, 3). Sem `subOriginId`. Com imóvel: `realestateId` + `realestateReference`. |
| Sub-origem Meta | Existe a global **4001 «Facebook/Instagram»** (origem Internet) e a da agência **34798477 «Facebook campanha»** (origem 11 Outros). Não é preciso criar nenhuma. |
| Utilizador da API | `securityUserId` 92411, agência 6429 `FIGUEIRAHOME` (a outra, 8484, não se toca). |
| **Permissões (bloqueio possível)** | `lead/insert` = 1, mas **`internetlead/insert` = 0**; `lead/delete` = 0 (`internetlead/delete` = 1); `lead/edit` = 0. Só uma chamada real diz qual vale para `InsertLead`. |
| Motivos de eliminação | Existe o 4 «Testes internos» (útil para limpar o teste). |

## Decisões por tomar

1. **Entidade**: lead (`InsertLead`, recomendado: entra como as do portal e o eGO distribui) ou oportunidade direta (`InsertOpportunity`, sem distribuição automática provável).
2. **Tipo da lead**: 7 «Pedido de Contacto» (recomendado, é o pedido do Miguel) ou 1 «Procura».
3. **Sub-origem**: 4001 (recomendado) ou 34798477.
4. **Horário**: 2 h seguidas ou só em horário de expediente (lead às 23h dispara à 01h e o consultor só liga de manhã).
5. **Já existe no eGO** (oportunidade ativa pelo telefone): não criar; nota/tarefa na existente, ou nada?
6. **Número que falhou** (`whatsapp_falhou_em`, 131026): enviar logo, sem esperar 2 h (recomendado: é quem mais precisa de telefonema).
7. **Permissão**: pedir ao Miguel `internetlead/insert` (ou `lead/delete`) para o utilizador da API, se o teste falhar com 403.
8. **Rodar a password do eGO** antes de pôr uma escrita automática a usá-la (exposta a 15/10).

## Desenho proposto (lazy)

- **Cliente**: `backend/app/integrations/ego_api.py` (login em 2 passos, User-Agent de browser, token em memória 24 h). Só `inserir_lead` e uma leitura de apoio. Isto adianta o mínimo da F0 do `ego-api-plano.md` para o backend (o plano punha-o no `scraper/`).
- **Gatilho**: cron de ~10 min em `figueirahome-crons` → `POST /api/leads/meta/para-ego` (`X-Automacao-Secret`). Condições, em `contactos`:
  `tipo_contacto` contém `comprador` · `meta_lead_id` não nulo · `template_enviado_em` ≤ agora − 2 h · `respondeu_em` e `contacto_humano_em` nulos · `ego_lead_id` nulo · `criado_em` ≥ data de ativação (**nunca o histórico**: 150+ leads antigas inundavam o eGO) · ou `whatsapp_falhou_em` preenchido.
- **Migration `0050`** (corres tu): `contactos.ego_lead_id bigint`, `contactos.ego_lead_em timestamptz`. Aditiva, nullable.
- **Corpo**: `name`, `phone`, `email`, `originId=1`, `subOriginId=4001`, `typeId=7`, `masterLeadTypeId=2`, `title` («Lead Meta compra — sem resposta ao WhatsApp»), `observation` (anúncio, imóvel de interesse como texto, horas desde o template; **sem a conversa**). `realestateId` só quando houver `imoveis.ego_backoffice_id` (F5); até lá, a referência vai na observação.
- **Segurança**: lê o telefone da própria lead; log só com 3 últimos dígitos; falha da API nunca marca `ego_lead_id`; sem retry em loop (próxima volta do cron).
- **Testes**: condições do gatilho (puras), idempotência, corpo sem PII em log, falha da API não marca.

## Teste real (só com ordem expressa)

1. Uma lead «TESTE — não ligar» com o meu telemóvel de teste, na agência real.
2. Ver: devolve id? 403? o eGO atribui consultor? notifica o consultor ou envia email/SMS à lead?
3. Apagar com `DeleteLead` (motivo 4 «Testes internos»). Se der 403 por `lead/delete`=0, o Miguel apaga na interface.
4. Avisar o Miguel antes, porque o consultor atribuído vê a lead durante uns minutos.

## Fora de âmbito

Recrutamento e angariação (pedido só para compra), notas/tarefas no eGO, `UpgradeLeadToOpportunity`, sincronizar o estado de volta. Contraria a decisão «assistentes nunca escrevem em `oportunidades`»: regista-se a exceção em `docs/decisoes.md` ao implementar.

## Ordem

1. Respostas às decisões 1–6 (Miguel).
2. Teste real do `InsertLead` (ordem tua).
3. Migration `0050` → cliente + endpoint + testes → cron `enabled: false` → ligar com tua ordem.
