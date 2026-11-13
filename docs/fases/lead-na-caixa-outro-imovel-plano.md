# Lead Meta que já existe no eGO: não ficar parada nem em silêncio (13/11)

## Problema
Reclamação do Miguel (13/11): de 15 leads Meta cujo telefone já existia no eGO (desde 22/10), 6 ficaram «sem conversa e sem
seguimento no eGO», todas do FH2588. Análise (só leitura, na BD e nos registos):
- A Matilde arrancou em 4 de 5 casos reportados: o template saiu (3 entregues 3–4 dias depois, 1 sem WhatsApp, erro 131026).
  O quinto recusou o consentimento (sem template, por desenho). Conversa só nasce quando a pessoa responde.
- O que falhou foi o eGO, em dois sítios:
  1. **Match na caixa de leads sem olhar ao imóvel** (`_lead_da_caixa`, cron e recusa): qualquer lead aberta com o mesmo
     telefone ou email contava como «já existe», mesmo de outro imóvel ou de outra pessoa com o mesmo contacto. O cron
     marcava e não criava (`criadas: 0, ja_existiam: 1` a 06/11 e 07/11), sem avisar ninguém.
  2. **Recusa com oportunidade ativa de OUTRO imóvel** (`recusou_whatsapp`): não criava a lead do FH2588 (o pedido #17, de
     10/11, só corrigiu o cron).

## Decisão
- `_lead_da_caixa` só dá match se a lead for **do mesmo imóvel** (`realestateReference`, comparando a base «FH2588_V1» →
  «FH2588») ou se não der para provar que é de outro (sem ref de um dos lados, como hoje). Lead aberta de outro imóvel =
  interesse novo: cria-se a lead deste imóvel, marcada como «já conhecido» no OBS.
- Cron e recusa usam a mesma regra. Na recusa, a oportunidade ativa só trava se for **deste imóvel** (`_responsavel_do_mesmo_imovel`).
- Quando há match legítimo (mesma lead já na caixa) o cron **avisa por email a consultora do imóvel e o diretor**, com o id da lead
  que fez match. Antes marcava em silêncio. Volume medido: 6 em 6 dias (~1 por dia).

## Fora do âmbito
- Não escreve nada no eGO para os 5 casos antigos: primeiro vê-se no eGO quais têm lead do FH2588 e só depois se decide,
  com ordem expressa.
- O match continua a ser por telefone/email: uma lead de **outra pessoa** com o mesmo contacto e o mesmo imóvel ainda conta
  como existente (a consultora vê-a no email e decide).

## Prova
`tests/test_leads_para_ego.py`: lead da caixa de outro imóvel → cria; do mesmo imóvel ou sem ref → marca e avisa; recusa com
oportunidade de outro imóvel → cria. Por ver com uma lead real.
