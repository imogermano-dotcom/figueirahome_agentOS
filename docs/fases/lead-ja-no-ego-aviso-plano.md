# Lead já no eGO que volta a responder — aviso à consultora (12/11)

## Problema
O cron das 2 h cria a lead no eGO «sem resposta ao WhatsApp da Matilde» (OBS de ~90 caracteres). Se a pessoa responde depois
(dias mais tarde) e qualifica, `marcar_interesse_real` não faz nada (só marca quando `ego_lead_em` é nulo) e `_promover_lead`
criava uma tarefa `lead_ego` que nunca fecha (o cron só a fecha quando grava `ego_lead_em`, e já estava gravado). A consultora
ficava com o texto «sem resposta» e sem saber que a pessoa respondeu, nem que quer arrendar (caso C1, 11/11, imóvel à venda).

## Decisão
Em `guards._promover_lead`, antes de criar a tarefa: se o contacto Meta deste telefone já tem `ego_lead_em`, **não** se cria
`lead_ego`. Cria-se `lead_ego_aviso` já `concluida` (só serve de chave de dedup, 1 aviso por pessoa em 24 h, a mesma do aviso
normal) e manda-se email à consultora do imóvel e ao diretor com o que a pessoa disse. Se quer arrendar, leva o mesmo aviso
do OBS («Atenção: quer ARRENDAR …»).

## Fora do âmbito
- Não escreve no eGO (nada de `UpdateLead` nem nota): só email. Acrescentar o texto ao OBS precisa de ordem expressa.
- Só corre quando a lead é promovida a `qualificada` (MQL completo). Quem responde sem qualificar não avisa.

## Prova
`tests/test_lead_ja_no_ego.py`: já no eGO → `lead_ego_aviso` concluída + 1 email com imóvel e aviso de arrendar; fora do eGO →
tarefa `lead_ego` como antes. Por ver com uma lead real.
