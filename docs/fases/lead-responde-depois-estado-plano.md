# A lead que responde depois de criada: ver o estado no eGO e criar lead nova se já não está na caixa (23/11)

## Problema
Três falhas vistas no caso HD (FH2572, 22–23/11) e no caso R (20–22/11):
1. **A mensagem pré-preenchida do formulário conta como interesse.** A pessoa abre o WhatsApp e envia «Olá! Preenchi o teu
   formulário e gostaria de saber mais sobre o teu negócio…» 6–13 s depois do template. `guards.e_pedido_de_informacao` apanha
   «gostaria de saber mais» e marca `interesse_real`: a lead vai para o eGO em ~9 min, e o OBS leva esse texto padrão como
   «Resumo» e «Pediu:» (2 de 9 leads, HD e RS).
2. **O aviso de «lead já no eGO voltou a responder» não vê o estado no eGO.** Decide só por `contactos.ego_lead_em` (a marca
   que nós gravámos). O HD tinha sido trabalhado pela consultora às 15:33 (a lead virou a oportunidade VEN_22523) e o email das
   19:12 mandava «acrescenta uma nota na lead do eGO» e dizia que o texto «ainda diz sem resposta».
3. **A porta nova de 23/11 (`avisar_respondeu_depois`) só avisa por email e usa a mesma chave de dedup do aviso da qualificação**
   (`lead_ego_aviso` do título): quem foi avisado pela qualificação, como o HD, nunca chega a ela.

## Regra nova (decisão do utilizador, 23/11)
**Se a lead já não existe ou já foi convertida em oportunidade, cria-se uma lead nova.** Uma lead que continua na caixa de leads
abertas fica como está (email à consultora). Assim a pessoa que volta a falar reaparece na caixa da consultora em vez de ficar
enterrada numa oportunidade que ninguém está a ver.

Isto abre uma **exceção deliberada** à regra de 10/11 («oportunidade ativa do mesmo imóvel: não cria, avisa»), que continua a
valer para a **1.ª criação** da lead. A exceção só vale para quem já tinha lead nossa (`ego_lead_em` desta entrada) e responde
depois dela.

## Decisão
1. **Ignorar a mensagem pré-preenchida** (começa por «Olá! Preenchi o teu formulário») em `e_pedido_de_informacao` e no
   `respostas_da_pessoa`/`resumo_da_conversa` do OBS. A lead passa pela porta normal: «conversa parada» 4 h depois da última
   mensagem real, com o resumo do que a pessoa disse.
2. **Estado da lead no eGO**, lido na volta do cron (`avisar_respondeu_depois`, que passa a decidir):
   - **na caixa** (`ego_api.leads_abertas()` tem o `ego_lead_id`, ou a mesma pessoa e imóvel): email à consultora, como hoje,
     com o texto certo («lead aberta, acrescenta uma nota»); **sem** frases sobre o OBS se este já tem as respostas;
   - **fora da caixa** (convertida, arquivada ou apagada): **cria lead nova** pelo caminho do cron (`InsertLead`, mesma
     atribuição à consultora do imóvel, `SemConsultora` não cria), grava a marca nova (`ego_lead_em`, `ego_lead_id`), e manda
     email à consultora a dizer que a lead anterior já estava em tratamento (com a ref da oportunidade, `VEN_…`, procurada em
     `oportunidades_ativas()` por telefone/email e imóvel; sem ela, «lead anterior já fora da caixa»).
3. **OBS da lead nova** = «Lead Meta Ads (anúncio …) voltou a responder à Matilde depois de a lead anterior ser tratada
   (oportunidade VEN_…)» + `Disse:`/`Respostas da pessoa` das mensagens **depois** da lead anterior (a mensagem pré-preenchida
   fora) + aviso de arrendar.
4. **Dedup próprio da porta:** deixa de usar o aviso da qualificação. Para o email, marca-se com uma tarefa `lead_ego_aviso`
   com descrição própria («respondeu depois…», criada **depois** de `respondeu_em`); para a lead nova, a própria marca
   `ego_lead_em` (a porta só atua se `respondeu_em` > `ego_lead_em`). Assim o aviso imediato da qualificação e a lead nova
   convivem.
5. **Travão contra lead em série:** no máximo **1 lead nova por pessoa e por 24 h** (a pessoa pode continuar a falar horas e
   a consultora voltar a converter). Passado esse prazo, nova resposta + lead convertida → outra lead.
6. **Aviso imediato da qualificação** (`guards._avisar_lead_ja_no_ego`): o texto deixa de afirmar que o OBS «diz sem resposta»
   nem manda «acrescentar nota à lead»; diz só que a lead já está no eGO e que, se já estiver em tratamento, abre-se lead nova
   quando a conversa assentar. A conversa continua sem falar com o eGO.

## O que não muda
- 1.ª criação da lead e as suas portas, a atribuição à consultora, `SemConsultora`, e nunca criar sem responsável.
- O eGO só é escrito pelo `InsertLead` do cron (já existente). Nenhuma migration.

## Fora do âmbito
- O caso HD já passou pelo aviso da qualificação (19:12); não se cria retroativamente a lead dele sem ordem expressa.
- Resposta de outro número (H) e o texto do template («sobe o imóvel»): à parte.
- Fundir ou apagar oportunidades duplicadas no eGO: é decisão da consultora.

## Prova
`tests/test_lead_respondeu_depois.py` e `tests/test_leads_para_ego.py`:
- mensagem pré-preenchida não marca interesse nem entra no OBS; uma mensagem real igual sim;
- lead na caixa → só email (texto de lead aberta); fora da caixa → lead nova criada, marca atualizada, email com a ref VEN_;
- sem consultora → não cria, erro à vista; falha da API do eGO → não cria nem marca (repete na volta seguinte);
- 2.ª resposta nas 24 h seguintes à lead nova → não cria outra; passado o dia e lead de novo fora da caixa → cria;
- o aviso da qualificação já enviado **não** bloqueia a porta; o email da porta não repete a cada volta;
- OBS da lead nova só leva mensagens depois da lead anterior.
Por ver com um caso real (próxima pessoa que responda depois de a consultora tratar a lead).

## Passos (cada um com OK próprio)
1. Código + testes, sem tocar em produção.
2. Dry-run em leitura: listar o que a porta faria hoje (esperado: nada novo; o HD está avisado e a RA também).
3. Commit, push e deploy.
4. Verificar com o próximo caso real; avisar o Miguel de que as leads podem reaparecer na caixa.
