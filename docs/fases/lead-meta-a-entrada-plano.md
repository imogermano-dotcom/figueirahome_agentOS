# Lead da Meta no eGO à entrada, e a conversa como nota (plano, pedido #17 reaberto a 26/11)

> Estado 27/11: **só plano, nada implementado.** Cada fase espera o OK do utilizador (código, commit, push, deploy, interruptor, e escritas no eGO).

## Pedido

O Miguel reabriu o #17 a 26/11 (a lead de 13:54 só chegou ao eGO às 16:00). Já tinha pedido o mesmo a 02/11, no #48 e no #22, e as respostas
foram sempre uma janela de espera (4 h, depois 2 h, depois «cron 9h–20h»). O que pede, e que aqui se aceita sem contra-proposta:

1. A lead Meta é criada no eGO **no momento em que entra** no Supabase, a qualquer hora, com o imóvel (`realestateId`) e o angariador como responsável.
2. A conversa, o interesse real, a escalada e a recusa entram **depois como nota** nessa lead (`InsertNote`, `objectName` 14) ou, se já foi promovida a
   oportunidade, na oportunidade (`objectName` 3, mesmo id). Nunca uma 2.ª lead.
3. Acaba a janela «a conversa parou» como condição para criar.
4. Se houver razão técnica para não criar à entrada, explicá-la ao Miguel.

Já testado por ele a 02/11: a OP promovida fica com o **mesmo id** da lead; `GetLead` traz `upgradeUserID` (nulo enquanto é lead); o OBS da lead passa para a OP
mas as notas da lead não; `InsertNote` com `objectName` 3 e o mesmo id funciona depois da promoção; sem `realestateId` a promoção dá erro no ecrã.

## O que existe hoje (`app/leads_para_ego.py`, cron `leads-compra-para-ego`, `*/10`)

- `_candidatas` exige **template enviado há mais de 2 h** e sem resposta (`elegivel`); `_candidatas_interesse` cria quem mostra interesse real;
  `_candidatas_paradas` cria 2 h depois da última mensagem; `tratar_respondeu_depois` avisa por email (lead na caixa) ou cria **lead nova** (se a pessoa já era OP).
- A recusa do WhatsApp cria logo (n8n → `recusou_whatsapp`).
- Já resolvido e que se mantém: deduplicação por lead na caixa / oportunidade ativa do mesmo imóvel (avisa a consultora, não cria), nunca sem consultora
  (`SemConsultora`), reentrada (`vale_para_a_entrada`), marca `ego_lead_em` gravada **com** `ego_lead_id` (pedido (d) de 02/11).

A espera não é um acaso: foi desenhada para não criar leads de quem ainda ia escrever e para a consultora não receber lixo. O Miguel pesou isso e quer a lead à
entrada na mesma (a consultora descarta o que não interessa; nada se apaga).

## Desenho

### Fase 1 — criar à entrada (muda só quando se cria)

- `elegivel` deixa de exigir template e as 2 h. Uma entrada de `contactos` com `meta_lead_id`, comprador e sem marca desta entrada é candidata **logo**.
  Mantém-se tudo o resto: dedupe, reentrada, sem email não se cria (a Web API exige-o; o `InsertLead` não), `SemConsultora`.
- **Quando corre.** Opção A: o cron de 10 em 10 min passa a 2 em 2 (a volta sai logo sem candidatas, é barata): lead no eGO em ≤2 min. Opção B: o n8n chama
  `POST /api/leads/meta/{id}/entrada` a seguir ao RPC (como já faz na recusa): segundos. **Recomendo A primeiro** (não mexe no n8n, que tem o risco de rascunhos
  antigos reporem nós); B se o Miguel precisar de «no mesmo minuto» e A não bastar. O cron fica sempre como rede.
- **Interruptor** `LEAD_ENTRADA_EGO` (vazio = comportamento de hoje), para ligar e desligar sem deploy.
- **Sem consultora / imóvel desconhecido.** Hoje não cria e regista erro. Passa a: ir buscar o imóvel ao eGO à entrada (já se faz em `_criar_lead`) e, se
  mesmo assim não houver responsável, **não criar** mas mandar email à direção com a referência após 30 min sem solução (o Miguel aceitou «avisar por email,
  nunca ficar só no Supabase», 31/10). A regra «nunca sem responsável» mantém-se: uma lead sem responsável é invisível.
- O OBS da lead à entrada leva o que se sabe então (imóvel, anúncio, campanha, «ainda sem conversa»). O resumo passa a ser nota (fase 3).

### Fase 2 — escrever notas na lead/OP (escrita no eGO)

- `ego_api.inserir_nota(objeto, id, texto)` (hoje só há a leitura de notas): `GetLead` → `upgradeUserID` preenchido ⇒ `objectName` 3 (OP, o mesmo id), senão 14 (lead).
- **Por testar antes de usar:** que o nosso utilizador pode escrever `objectName` 14 (só se viu o 3); o formato do texto e do tipo de nota. Teste com uma lead
  Meta de teste real, com OK expresso (escrita no eGO), e sem apagar nada (a consultora/Miguel descarta).
- Cada nota leva um marcador no fim e fica registada (coluna nova em `contactos`, `ego_nota_em`, ou `agente_sync_log`) para não repetir.

### Fase 3 — a conversa passa a notas (substitui o resumo no OBS e a lead «parada»)

Eventos que geram nota, no máximo **1 por evento e por entrada**, com resumo curto (mesmas regras de privacidade do OBS atual, 600 caracteres):
1. A pessoa respondeu à Matilde (1.ª resposta): o que perguntou, e o pedido inicial.
2. Interesse real / pedido de visita / lead qualificada (`marcar_interesse_real`).
3. Escalada para humano.
4. Recusa («já não tenho interesse», `nao_contactar_em`): a nota diz-o; a consultora descarta. Nada se apaga no eGO.
5. Sem resposta ao lembrete: a nota diz «sem resposta ao lembrete».
Os emails atuais à consultora (lead na caixa que voltou a responder, escalada urgente) **mantêm-se**: a nota é o registo, o email é o aviso.

### Fase 4 — retirar o que deixa de fazer sentido (com o interruptor ligado há dias)

`_candidatas_paradas`, `_candidatas_interesse` e o ramo «lead nova depois» deixam de decidir se a lead existe. `LEAD_RESPONDEU_EGO` e
`LEAD_INTERESSE_EGO` passam a controlar só as notas. Atualizar `CLAUDE.md` (o texto de 20–25/10 e 23/11 descreve a espera de 2 h) e o registo do Miguel.

## Opção B escolhida a 27/11: o n8n cria a lead à entrada

Decisão do utilizador: em vez do cron a 2 min, o fluxo `Meta leads to supabase` chama o backend logo a seguir ao nó `Supabase: criar lead venda`. O cron de 10 em 10 min fica como rede.

**Backend** (variante de `recusou_whatsapp`, mesmo `require_n8n_access`):
- `POST /api/leads/meta/{meta_lead_id}/entrada?imovel_ref=` → `leads_para_ego.entrada_meta`. Interruptor `LEAD_ENTRADA_EGO` (vazio = devolve `{"resultado":"desligado"}` e não faz nada) e, como na recusa, só para entradas desde `LEAD_COMPRA_EGO_DESDE`.
- Mesma verificação da recusa: `vale_para_a_entrada(ego_lead_em)` → `ja_tratada`; oportunidade ativa do mesmo imóvel → não cria e avisa o consultor; já na caixa → só marca; sem email → não cria; `SemConsultora` → não marca. Falha do eGO ao ler a caixa → cria na mesma (`verificado_no_ego:false`).
- **Reserva antes de criar** (o que o cron não tinha): `UPDATE contactos SET ego_lead_em=now WHERE id=… AND ego_lead_em <é a que lemos>` e só quem consegue a reserva chama o eGO; se a criação falhar, repõe o valor anterior (o cron apanha 2 h depois). Isto evita 2 leads por reenvio do webhook da Meta ou por n8n em repetição.
- **Quem recusa o WhatsApp não é tratado aqui (verificado a 27/11):** o fluxo do template (`4rDc9amm6HpO5F4j`) já tem o ramo `Guardas` (falso) → `Recusou o WhatsApp?` → `Criar lead no eGO (recusou WhatsApp)` (`POST …/recusou-whatsapp`) → email ao Miguel e à consultora. Cria a lead segundos depois da entrada, com OBS «recusou o WhatsApp». O `/entrada` recebe `?whatsapp_optin=` (a resposta crua do formulário) e **só cria se começar por «sim»** (a regra do `Guardas`; nunca `whatsapp_permissao`, que o RPC pode calcular laxa); senão devolve `{"resultado":"recusa"}` (200) sem fazer nada. Se não, o `/entrada` (que corre primeiro) criava a lead com OBS genérico e a recusa recebia `ja_tratada`, e o email dizia «já tratada antes». A decisão 4 do plano fica resolvida por aquilo que já existe.
- OBS à entrada: «Lead Meta Ads (anúncio X) entrou agora; ainda sem conversa com a Matilde.» + imóvel + aviso de arrendar se o formulário o disser. Sem resumo de conversa (ainda não há).

**O que continua a funcionar sem nota** (até à F2/F3): lead marcada à entrada → `tratar_respondeu_depois` já avisa a consultora por email se a pessoa responder à Matilde e a conversa parar (1 por entrada); escaladas e interesse real mantêm os emails atuais. O que se perde até haver notas: o resumo da conversa no próprio eGO.

**n8n** (editado ao vivo; só um nó novo, nada mexido nos existentes):
- `HTTP Request` «Lead para o eGO» **logo a seguir a `Supabase: criar lead venda`, antes do template** (decisão do utilizador, 27/11): sai do mesmo nó que `Enviar template (01)` e fica acima dele no ecrã (o n8n v1 corre os ramos de cima para baixo), com `onError: continueErrorOutput` para uma falha dele não impedir o template. Só no ramo da compra (angariação e recrutamento nunca vão ao eGO). Sem IF de `status === 'ok'`: se o RPC falhou (erro com HTTP 200) o backend responde 404 e isso também avisa.
- **Aviso de erro (o utilizador é notificado):** a saída de erro liga a um 2.º nó «Avisar falha» = `POST /api/n8n/falhou` com a credencial `N8N agentos` e o corpo `{workflow, no, erro, execucao}`, o mesmo que o `Error Workflow` usa (o backend manda o email aos destinatários dos alertas). É preciso porque com `continueErrorOutput` o n8n não conta a falha como erro da execução e o `Error Workflow` não dispara. O endpoint `/entrada` responde **HTTP 502** (e não 200) quando não cria por `sem_consultora` ou `sem_email`, para o mesmo caminho avisar. `desligado`, `ja_tratada`, `ja_na_caixa` e `oportunidade_ativa` são respostas normais (200).
- Cabeçalho `X-N8N-Secret` com a credencial que a recusa já usa; `meta_lead_id` e `imovel_ref` de `DADOS FB FORM Venda` (`lead_id`, `ref_imovel`); timeout 30 s (o template espera por este nó; arranque a frio do agentos + `leads_abertas` + PUT).
- Rascunhos: recarregar o fluxo antes de gravar e dizer ao utilizador para não ter o fluxo aberto na interface.

**Ordem e OKs (cada um à parte):** (1) código + testes locais, sem produção; (2) commit + push; (3) deploy com `LEAD_ENTRADA_EGO` vazio; (4) nó no n8n com o interruptor ainda vazio (a chamada devolve `desligado`); (5) lead de teste real de ponta a ponta (a Meta «test lead» é descartada pelo filtro: tem de ser um formulário preenchido à mão com telefone/email de teste; escrita no eGO, o Miguel ou a consultora descarta); (6) ligar `LEAD_ENTRADA_EGO`; (7) ver 1–2 leads reais.

## Decisões para o utilizador

1. ~~Opção A ou B~~ **B** (27/11). O cron mantém-se a `*/10`; as proteções de reserva e de repetição entram só no endpoint novo.
2. **«Lead nova depois» (memória do pedido do Miguel):** hoje, quando a pessoa já foi promovida a OP e volta a escrever, cria-se **lead nova**
   (`LEAD_NOVA_DEPOIS_DESDE`). O #17 diz «nunca segunda lead; nota na OP». Para a **mesma entrada** passa a nota na OP. Uma **entrada nova** (reentrada, outro
   anúncio) continua a criar lead nova. Confirmo isto com o Miguel antes da fase 4?
3. **Sem consultora:** aviso por email à direção após 30 min (proposta acima), em vez de só registar.
4. **Quem recusa à entrada** (aceita receber «Não» no formulário): também se cria a lead (o Miguel quer o registo e que a consultora descarte). Confirmo?

## Riscos

- Mais leads no eGO, incluindo as que não vão responder (14 % voltam depois de 2 h, medido a 24/11): carga para as consultoras; é a escolha do Miguel.
- Escrita de notas no eGO é nova para o nosso utilizador: testar com uma lead de teste antes de ligar, e só com ordem expressa.
- Duplicados: a lead criada pelo cron e a criada à mão pelo Miguel (ou pela rede `meta-leads-rede` do portal, que ele ainda tem de desligar): manter a verificação
  `_lead_da_caixa` antes de criar.

## Ordem e OKs

F1 (código + testes, sem produção) → commit/push → deploy com `LEAD_ENTRADA_EGO` vazio → ligar → ver 1–2 leads reais. F2 (cliente de notas + teste com lead de teste, OK expresso). F3, F4 por fases, cada uma com o seu OK.

## Unificação aceita/recusa (28/11)

Duas vias para o mesmo resultado (nó novo para quem aceita, ramo do fluxo do template para quem recusa) davam a recusa a passar
2 vezes pela criação. Decisão: **`/entrada` é o único ponto de criação**, para quem aceita e para quem recusa.

- Backend: `entrada_meta` deixa de devolver `recusa`; quem não aceita (`aceitou_whatsapp` falso) cria com o OBS «recusou o WhatsApp:
  contactar por telefone, nunca por WhatsApp» e a marca `via=recusa`. `/recusou-whatsapp` fica só como reversão.
- n8n, por esta ordem, sem perder leads (quem recusa nunca recebe template, o cron das 2 h não o apanha):
  1. deploy com `LEAD_ENTRADA_EGO` ainda vazio;
  2. ligar a flag: a recusa passa a ser criada pelo nó do fluxo-pai; o nó antigo responde `ja_tratada` (o email da recusa diz
     «já tratada», só texto);
  3. fluxo do template: o email da recusa lê o resultado do `Lead para o eGO` (fluxo-pai, passado ao `Enviar template (01)`) e
     sai o nó `Criar lead no eGO (recusou WhatsApp)`.
- Opção 2 (mais tarde, se se quiser): o backend envia também o email de recusa e o ramo todo sai do n8n.
