# Lead já no eGO que responde depois de criada: avisar a consultora (23/11)

## Problema
O cron `leads-compra-para-ego` cria a lead 2 h depois do template se a pessoa não respondeu; o OBS fica «sem resposta ao
WhatsApp da Matilde». Se a pessoa responde **depois**, a consultora continua a ver «sem resposta»: não sabe que a pessoa
escreveu, o que pediu nem o que a Matilde já lhe disse.

Hoje só há aviso se a conversa **qualifica** (`guards._avisar_lead_ja_no_ego`, 12/11: orçamento + zona + tipo de interesse).
Interesse sem MQL completo (pedir fotos, garagem, «Sim, estou interessada») não avisa ninguém, e `marcar_interesse_real`
nem o regista (filtra a lead já marcada no eGO). Visita e escalada têm os seus próprios emails.

Caso de 23/11 (**R**, FH2572): lead criada 22/11 02:10 «sem resposta»; respondeu às 10:19 (6 mensagens: fotos, garagem,
«Sim, estou interessada»); a consultora nunca soube. Medição das 8 leads criadas desde 20/11: 1 caso (R), mais 1 de outro
tipo (**H**, respondeu de **outro número**, fora do âmbito: ver abaixo).

## Decisão
1. **Aviso por email quando uma lead já no eGO responde e a conversa assenta.** Nova porta no cron
   `leads-compra-para-ego` (corre de 10 em 10 min, já tem a infraestrutura de email): compradores Meta com
   `ego_lead_em` desta entrada (`vale_para_a_entrada`), `respondeu_em` **posterior** à marca e a última atividade da
   conversa há ≥ `JANELA_PARADA_HORAS` (4 h; o mesmo critério da porta «conversa parada»). Esperar a conversa assentar evita um
   email por mensagem e dá à consultora o resumo completo.
2. **Conteúdo:** email à consultora do imóvel (`_consultor_do_imovel`/`profiles`, como `_avisar_lead_na_caixa`) e ao diretor:
   «Lead já no eGO respondeu à Matilde», telefone/email, imóvel, id da lead no eGO e o resumo da conversa **só da entrada
   atual** (`respostas_da_pessoa` + aviso de arrendar, o mesmo bloco do OBS). Diz que o texto da lead no eGO ainda diz «sem
   resposta». **Não escreve no eGO.**
3. **Sem duplicar:** não avisa se já há `lead_ego_aviso` ou a tarefa `lead_ego` desta pessoa nas últimas 24 h (o aviso da
   qualificação tem a mesma chave: título `_TAREFA_QUALIFICADA — pessoa`). O aviso grava `lead_ego_aviso` `concluida`, igual ao
   da qualificação, e fica como dedup (uma vez por pessoa por entrada: a verificação também olha `criado_em` ≥
   `meta_created_at`).
4. **Só entradas recentes:** `meta_created_at` dos últimos `IDADE_MAX_PARADA_DIAS` (14), como as outras portas.
5. **Quem recusou ou se despediu:** não avisa (`e_recusa`/`e_fecho_da_pessoa` nas últimas mensagens, `nao_contactar_em`). A
   consultora fica sem aviso, mas a pessoa disse que não quer: o OBS «sem resposta» não engana.
6. **Interruptor:** reutiliza `LEAD_RESPONDEU_EGO` (vazio = desligado; lista = piloto).

## O que não muda
- Criação e atribuição das leads, marcas de `contactos`, `marcar_interesse_real` e os avisos de qualificação, visita e
  escalada.
- Nunca se escreve no eGO. Atualizar o OBS da lead (`atualizar_lead`, que substitui o corpo) fica como fase própria, só com
  ordem expressa.

## Fora do âmbito
- **Resposta de outro número (H)**: a conversa não fica ligada ao contacto (a mensagem pré-preenchida do WhatsApp chegou de
  um número que não é o do formulário). Ligar por email ou nome tem o risco de ligar a pessoa errada (`nome` nunca é
  identificador sozinho): decisão com o Miguel, plano à parte.
- Reenviar template, reentrada: ver `lead-meta-reentrada-plano.md`.

## Prova
`tests/test_leads_para_ego.py` (ou ficheiro novo `tests/test_lead_respondeu_depois.py`):
- lead marcada às 02:10, resposta às 10:19, conversa parada há ≥ 4 h → 1 aviso à consultora, com resumo e id da lead;
- resposta há menos de 4 h → nada (espera);
- sem resposta, ou resposta anterior à marca → nada;
- já avisada (`lead_ego_aviso` ou `lead_ego` em 24 h) → nada; volta seguinte não repete;
- recusa ou despedida nas últimas mensagens → nada;
- marca de entrada anterior (reentrada) não conta;
- falha do email não levanta nem apaga a dedup; sem consultora conhecida, só o diretor.
Por ver com uma lead real.

## Passos (cada um com OK próprio)
1. Código + testes, sem tocar em produção (ver onde `contactos.respondeu_em` é espelhado; o caso R mostra que está preenchido).
2. Dry-run em leitura: listar quem seria avisado (esperado: R).
3. Commit, push e deploy.
4. Verificar a volta seguinte e o email recebido.
