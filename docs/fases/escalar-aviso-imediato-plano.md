# Pedido #20, etapa de 21/11: aviso imediato quando a mensagem precisa de uma pessoa

## Problema
A 19/11 às 21:04 o proprietário de um imóvel em angariação (OP `CAP_21715`, imóvel `APA_5444`, consultora Sandra) escreveu ao
WhatsApp da Matilde: «Amanhã pelas 18:30 poderá visitar o apartamento…». A Matilde respondeu que as visitas são tratadas
pela consultora (sem escalar), às 09:12 do dia seguinte saiu o nudge «Ainda está interessado?» e **ninguém foi avisado**.

O Miguel pede (3 pontos): (1) quando a mensagem precisa de uma pessoa, `escalar_para_humano` e email imediato ao Miguel e ao
consultor responsável (o da OP ligada ao telefone, ou o do imóvel), com a mensagem, o telefone, a ref da OP/imóvel e o link da
conversa; (2) sem consultor identificado, só ao Miguel; (3) depois de escalar, não sai o nudge.

## O que já existe (medido, 23/11)
- **Ponto 3 já cumpre:** `nudge._conversas_escaladas` salta conversas com tarefa `escalar` ou `visita` (07/10 e 10/11).
  Os follow-ups 24 h/72 h do n8n são de leads Meta em `contactos` (template): este telefone não é uma (3 contactos `fsbo`
  do eGO, sem `meta_lead_id`).
- **Regra no prompt da Matilde** (`e7a17d8`, 21/11, no código): «MENSAGEM QUE NÃO É PARA TI» manda escalar com motivo
  «mensagem para a equipa» e cita este caso. **Não há ensaio nem código que a garanta**, e é ao modelo que cabe cumpri-la.
- **O telefone liga à OP:** `oportunidades.cliente_telefone` devolve 3 OPs ativas deste proprietário (`CAP_21715`,
  `CAP_20756`, `CAP_20416`), com `responsavel` (2 consultoras diferentes). A ligação funciona.

## O que falta
1. **Destinatários.** `notificar(..., imovel_ref)` só junta a consultora do imóvel. A escalada de «mensagem para a equipa»
   não traz `imovel_ref` (o modelo não o sabe), por isso o email iria só ao Miguel: a consultora da OP não sabe de nada.
2. **Conteúdo.** O email não leva a ref da OP nem o link/identificação da conversa. O painel não tem rota por conversa.
3. **Tarefa sem `responsavel`** quando não há imóvel (`_angariador_do_imovel`): pede o Miguel «a tarefa fica com responsável».
4. **Garantia.** Só o prompt manda escalar. Pelas regras do projeto («o que não pode falhar vive em `guards.py`») falta uma
   rede em código.

## Decisão
1. **Destinatários pelo telefone** (função em `notificacoes.py`, usada por `_escalar_para_humano` para qualquer escalada):
   além do diretor/Miguel e da consultora do `imovel_ref`, entram os `responsavel` de **todas as oportunidades ativas** ligadas
   ao telefone (`oportunidades.cliente_telefone`, não apagadas), resolvidos para email por `profiles.ego_responsavel`. Com
   várias consultoras avisam-se todas (a mensagem não diz de que imóvel fala: é preferível um email a mais do que perder a
   visita). Sem ninguém identificado: só o Miguel (já é o comportamento).
2. **Corpo do email:** a mensagem **tal como a pessoa a escreveu** (o resumo que o modelo escreve já vai literal pela regra),
   o telefone, as refs das OPs ativas (`CAP_…`/`VEN_…`) e do imóvel, e a identificação da conversa (agente, data/hora de
   Lisboa e id curto, com a indicação de onde a ler no painel). **Sem rota nova no painel agora** (ponytail: um link por
   conversa exige frontend + deploy no Cloudflare; propõe-se só se o Miguel o quiser mesmo).
3. **`responsavel` da tarefa** sem imóvel: o da OP ligada ao telefone (a 1.ª se forem várias; as outras na descrição).
4. **Rede em código (contingente):** primeiro um **ensaio com o modelo real** (≈12 mensagens: confirmar/desmarcar/mudar
   visita, proprietário a falar de um imóvel, «quero falar com a consultora», proposta, reclamação, e contra-exemplos de
   comprador normal). Se alguma não escalar, junta-se a `guards.py` um detetor por regex e, **só se o modelo não chamou
   nenhuma tool de registo naquele turno**, o motor regista a escalada ele próprio (mesmo caminho de `_escalar_para_humano`,
   com a mensagem tal e qual). Se o ensaio der 12/12, não se acrescenta código.
5. **Nunca duplicar:** o dedup de `_tarefa_ja_registada` (conversa + motivo) já cobre a escalada repetida; informação nova
   continua a acrescentar à tarefa.

## O que não muda
- `pedir_visita` (comprador que quer visitar) e todo o fluxo de leads Meta; o nudge e as marcas `nao_contactar_em`.
- Nada escreve no eGO. Nenhuma migration.

## Fora do âmbito
- Link clicável por conversa no painel; email ao proprietário; mudar o roteamento do 928 (quem escreve de fora do funil
  continua a cair na Matilde, que passa a escalar em vez de responder «não me compete»).

## Prova
`tests/test_escalar_aviso.py` (novo) e `tests/test_interesse_real.py`:
- telefone com 2 OPs de 2 consultoras → o email leva as duas (e o diretor); sem OP nem imóvel → só o diretor;
- `responsavel` da tarefa vem da OP quando não há imóvel; com imóvel mantém o do imóvel;
- o corpo tem a mensagem literal, o telefone, as refs e a identificação da conversa;
- falha a resolver a OP ou o email nunca impede a escalada (o aviso ao Miguel sai sempre);
- repetição da mesma escalada não duplica; informação nova acrescenta;
- (se houver rede em código) mensagem de visita sem tool de registo → escalada registada; com `pedir_visita` ou
  `escalar` já chamados → não duplica; comprador a pedir visita → não dispara.
Por ver com um proprietário real; o teste do Miguel («telefone ligado a uma OP CAP_ escreve ao 928») é com o número dele
ligado a uma OP, ou com o ensaio de uma conversa gravada.

## Passos (cada um com OK próprio)
1. Código + testes dos pontos 1–3 (destinatários, corpo, `responsavel`), sem tocar em produção.
2. Ensaio com o modelo real (chamadas à API da Anthropic, sem escrever em produção) → decide o ponto 4.
3. (Se preciso) rede em código + testes.
4. Commit, push e deploy.
5. Verificar com a próxima escalada real e pedir ao Miguel que feche o #20.
