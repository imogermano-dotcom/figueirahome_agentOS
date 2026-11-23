# Lead Meta de uma pessoa que já tinha lead no eGO: a segunda entrada não pode ficar bloqueada (22/11)

## Problema
Caso de 21/11 (comprador, FH2584 em 26/10, FH2572 em 21/11). A pessoa entrou pela Meta, conversou 17 mensagens com a
Matilde, propôs um preço e a Matilde escalou: saíram a tarefa `escalar` e um email, mas **nenhuma lead no eGO**.

Causa: a pessoa reaproveita a linha de `contactos` (o RPC `lead_meta_compra` atualiza `meta_lead_id` e `meta_created_at`) e
`contactos.ego_lead_em` ficou da primeira lead (26/10). Tudo o que decide «falta criar a lead» pergunta `ego_lead_em IS NULL`
e conclui que a pessoa já está tratada:

| Onde | Efeito em 21/11 |
|---|---|
| `leads_para_ego._candidatas`, `_candidatas_interesse`, `_candidatas_paradas`, `elegivel` | a 2.ª entrada nunca é candidata |
| `leads_para_ego.recusou_whatsapp` (`ja_tratada`) | uma recusa da 2.ª entrada não criava lead |
| `guards.marcar_interesse_real` (`ego_lead_em IS NULL`) | o interesse da conversa nova não se regista (ficou o de 25/10) |
| `guards._contacto_ja_no_ego` | a promoção disse «lead já no eGO voltou a responder»: o email foi esse, com a lead **do outro imóvel** |

`contactos.imovel_ref` também fica no imóvel antigo (o RPC só grava o novo em `leads`): a lead seria criada com o imóvel errado.

Os campos da conversa da 1.ª entrada (`respondeu_em`, `contacto_humano_em`, `interesse_real_em`, `template_enviado_em`) também
ficam e bloqueiam a 2.ª: `elegivel` recusa quem tem `respondeu_em`; a porta «conversa parada» trata a pessoa como «respondeu»
e lê a conversa antiga (de outro imóvel); o `Guardas` do sub-fluxo do template não reenvia (`template_enviado_em` antigo).

## Medição (só leitura, 22/11)
180 compradores Meta desde 20/10. **4** têm a entrada nova bloqueada por campos da entrada anterior:
- **A**: o caso de 21/11 (a corrigir): `ego_lead_em`, `interesse_real_em` e `respondeu_em` antigos.
- **B**: entrada de 21/10, marca de 19/10, sem conversa. Com 1 mês: **não se deve criar agora**.
- **C**: número de teste do utilizador, sem imóvel nem consultora (nunca se cria sem responsável).
- **D**: entrada de 07/11, `respondeu_em` de 08/10 (sem marca no eGO): a conversa antiga acabou numa despedida e saltou a
  porta «conversa parada». Entrada com 15 dias: fica **fora da janela**, nada se cria.

## Decisão
1. **Um campo só vale para a entrada a que pertence.** Função única `vale_para_a_entrada(linha, campo)` em
   `leads_para_ego.py`: verdadeiro se o campo existe e é `>= meta_created_at`; anterior = pertence a uma entrada passada e
   conta como vazio. Aplica-se a:
   - `ego_lead_em`: três listas de candidatas, `elegivel`, `recusou_whatsapp` e `guards._contacto_ja_no_ego`;
   - `respondeu_em` e `contacto_humano_em`: `elegivel` e `_candidatas_paradas`;
   - `interesse_real_em`: `_candidatas_interesse` e `guards.marcar_interesse_real`.
2. **Janela de 7 dias para a reentrada**: só conta se `meta_created_at` for dos últimos 7 dias (o caso B, de 1 mês, e qualquer
   histórico ficam de fora; o cron não passa a «recuperar» o passado). `IDADE_MAX_REENTRADA_DIAS = 7`.
3. **Consulta com filtro no servidor e verificação em Python** (o PostgREST não compara duas colunas):
   `.or_("ego_lead_em.is.null,meta_created_at.gte.<agora-7d>")` e depois `not marca_cobre_a_entrada(l)`. Volume: ~1 reentrada
   em 176; o `limit(200)` chega.
4. **Imóvel da entrada**: nas candidatas vindas de reentrada, `imovel_ref` = o da linha de `leads` com o `meta_lead_id` atual
   (cai para `contactos.imovel_ref` se não houver).
5. **Interesse novo = recomeçar**: em `marcar_interesse_real`, se a linha tem `interesse_real_em` anterior a `meta_created_at`,
   sobrescreve motivo/resumo e data em vez de acrescentar ao resumo antigo (hoje só o 1.º sinal grava).
6. **«Já no eGO» só se a marca cobre a entrada** (`_contacto_ja_no_ego`): sem isso a consultora continua a ouvir «já está
   no eGO» sobre a lead do imóvel anterior. A pessoa volta ao caminho normal (tarefa `lead_ego` + email) e o cron cria a lead.
7. A marca nova (`ego_lead_em = agora`) é posterior à entrada: a mesma entrada nunca se cria duas vezes (idempotente).
8. **Espera das 2 h contada desde a entrada.** `elegivel` mede desde `template_enviado_em`, que numa reentrada é o antigo: a
   candidata apareceria na volta seguinte, antes de a pessoa poder responder. Passa a medir desde
   `max(template_enviado_em, meta_created_at)`. Como a reentrada não recebe template novo, a espera é só tempo para a pessoa
   escrever (e a Matilde, se escrever, tratar do resto). Número sem WhatsApp continua imediato.
9. **Resumo da conversa só da entrada atual.** `_com_conversa` e `_conversa_do` leem hoje a conversa inteira do número; numa
   reentrada o OBS levava o que a pessoa disse sobre o imóvel anterior. As mensagens **não têm hora**, por isso a unidade é a
   conversa: se a última atividade (`agente_conversas.atualizado_em`) é anterior a `meta_created_at`, a conversa é toda da entrada
   anterior e não conta (OBS sem resumo; a despedida/recusa dela não trava a porta «conversa parada»). Uma conversa que atravessa
   a entrada (reaproveitada em <48 h) conta inteira: limite conhecido.

## O que não muda
- Criação, atribuição à consultora do imóvel, `SemConsultora`, aviso de oportunidade ativa e «já na caixa» (`_lead_da_caixa` já
  compara por imóvel, 13/11): a reentrada passa pelas mesmas regras e pode terminar em «já existia» + aviso, sem duplicar.
- Nunca se escreve no eGO fora do `InsertLead` do cron, que já existe.

## Fora do âmbito (ficam como limitação)
- **`template_enviado_em` fica da 1.ª entrada** (o RPC não o repõe e o `Guardas` não reenvia): a reentrada **não recebe template
  novo**; a Matilde só arranca se a pessoa escrever primeiro. Reenviar o template é decisão do utilizador (lembra o consentimento
  e o horário: nenhum envio sem confirmar a hora) e mexe no n8n/RPC, em separado.
- **Caso C (teste)**: com a correção, é candidata nas 2 h seguintes à entrada e dá `SemConsultora` (erro à vista, sem criar). Se
  incomodar, marcar o contacto como teste (decisão do utilizador).
- A lead do caso A no eGO: criação à mão pela consultora ou por ordem expressa; esta correção só vale daqui em diante.

## Prova
`tests/test_leads_para_ego.py` e `tests/test_lead_ja_no_ego.py`:
- marca anterior à entrada e entrada recente → candidata, com o imóvel de `leads`; marca posterior → não;
- entrada com mais de 7 dias e marca anterior → não;
- `respondeu_em` e `contacto_humano_em` anteriores à entrada → não bloqueiam `elegivel`; da mesma entrada → bloqueiam;
- reentrada: `elegivel` só 2 h depois de `meta_created_at` (não de `template_enviado_em`); número sem WhatsApp, imediato;
- reentrada com conversa antiga acabada em despedida → não trava; o OBS só leva mensagens depois de `meta_created_at`
  (sem nenhuma, sem «Respostas da pessoa» nem resumo);
- recusa da 2.ª entrada cria lead; recusa repetida da mesma → `ja_tratada`;
- `marcar_interesse_real` com interesse antigo recomeça o resumo; com interesse da mesma entrada acrescenta;
- `_contacto_ja_no_ego` falso se a marca é anterior à entrada;
- idempotência: depois da criação, a volta seguinte não cria.
Por ver com uma reentrada real.

## Passos (cada um com OK próprio)
1. Código + testes, sem tocar em produção.
2. Dry-run em leitura: listar as candidatas que o cron passaria a ver (esperado: o caso A e o C; B fora pela janela).
3. Commit, push e deploy (o cron age na volta seguinte de 10 em 10 min).
4. Verificar a volta seguinte e o caso A (a criar sem a consultora ter já a lead à mão).
