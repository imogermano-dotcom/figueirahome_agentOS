# Pedido #20: resumo no email de «lead qualificada» e dados do imóvel na angariação (25/11)

**Plano antes de código; nada deste plano está implementado.** Sem nomes nem telefones de clientes.
Continua `escalar-aviso-imediato-plano.md` (21/11) e `escalar-urgente-plano.md` (25/11): são os 2 pontos que ficaram por fazer.

## Estado medido (25/11, só leitura do código)
- **«Lead qualificada» (`guards._promover_lead`, `guards.py:472-490`):** o email traz nome, telefone, email, interesse, orçamento, zona e imóvel do anúncio. **Não traz nada do que a pessoa disse**, nem a tarefa `lead_ego` (`descricao`, `guards.py:457-464`).
- **O resumo já existe noutro sítio:** o `resumo` do `escalar_para_humano` chega a `find_or_create_cliente(notas=…)` (`tools.py:926`) e a `marcar_interesse_real` (`contactos.interesse_real_resumo`, `guards.py:422`, só contactos Meta de comprador). A `_promover_lead` não lê nenhum.
- **Angariação:** a Bárbara não tem email próprio, usa `escalar_para_humano` («visita de avaliação»). O email traz contacto, motivo, consultoras e o `resumo` livre. O imóvel a angariar só aparece se o modelo o escrever no `resumo`; o `imovel_ref` quase nunca vem, porque o imóvel ainda não está no eGO.
- `_promover_lead` ignora tipos fora de compra/arrendamento (`_TIPOS_QUE_PROMOVEM`): uma angariação nunca gera o email «Lead qualificada». O email da escalada é, por isso, o único aviso dela.

## Desenho

### Ponto 1: resumo no email e na tarefa de «lead qualificada»
1. `_promover_lead` obtém o resumo da conversa e acrescenta-o ao email («O que a pessoa disse:») e à `descricao` da tarefa `lead_ego`.
2. **Fonte:** `cliente["notas"]` (o que `find_or_create_cliente` recebeu do `resumo`); se vazio, `contactos.interesse_real_resumo` do telefone. A confirmar na implementação qual das duas vem preenchida em cada via (escalada, fim de turno, site).
3. Limite de 600 caracteres, cortado no fim de frase quando possível. Sem resumo, o email sai como hoje (nenhuma linha vazia).
4. **Sem mudança de gatilho nem de destinatários.** O dedup de 24 h por pessoa fica igual.
5. **Duplicação a vigiar:** uma conversa que escala e qualifica no mesmo turno gera o email da escalada e o da qualificada, com o mesmo texto. O resumo no segundo ajuda quem só lê esse, e o custo é uma repetição. Se incomodar, o email da qualificada diz só «ver também o aviso da escalada» quando houve escalada nas últimas 24 h (fica de fora desta etapa).

### Ponto 2: bloco «Imóvel a angariar» no email da escalada da angariação (opção 2)
1. **Esquema de `escalar_para_humano` (`tools.py:164`):** 3 campos opcionais novos, preenchidos só na angariação:
   - `tipo_imovel` (texto curto: apartamento T2, moradia, terreno…);
   - `zona_imovel` (morada ou zona que a pessoa deu);
   - `outra_agencia` (texto curto: «não», «só particular», «com outra agência»).
2. **Email e tarefa:** quando algum vier preenchido, o email e a `descricao` da tarefa ganham um bloco fixo antes do `resumo`:
   ```
   Imóvel a angariar:
     Tipo:           …
     Zona/morada:    …
     Outra agência:  …
   ```
   Só entram as linhas com valor. Sem nenhum campo, o email sai como hoje.
3. **Prompt da Bárbara (`_PROMPT_A4`, passo 5):** mandar passar os 3 campos no `escalar_para_humano`, além do `resumo`. As instruções adicionais em `agente_config` não se tocam.
4. **O email de atualização da escalada** não repete o bloco (já foi enviado no 1.º aviso).
5. **Sem preço nem comissão no bloco:** o prompt proíbe estimar valor e a comissão é do consultor na visita.
6. Os outros assistentes não recebem o bloco: os campos só se preenchem se o modelo os passar, e só a Bárbara é instruída a fazê-lo.

## O que não muda
Nada se escreve no eGO. Destinatários, urgência («URGENTE — » em todas as escaladas) e a regra de o follow-up parar depois de escalar ficam iguais. A allowlist `_TOOLS_INPUT_SEGURO` não inclui `escalar_para_humano`, por isso os campos novos (que são dados do cliente) não vão para o registo de métricas. Sem migration.

## Riscos
- **Campo novo só preenchido se o modelo o passar:** a opção 2 é mais fiável do que texto livre, mas não é garantida. Se a Bárbara os omitir, o email sai como hoje, sem erro. Medir nas primeiras angariações reais.
- **Resumo com dados pessoais no email:** já acontece nas escaladas, vai só a destinatários internos.
- **Esquema da tool maior:** custa alguns tokens por turno nos assistentes que têm a tool (cache a 67%, sem impacto relevante).

## Testes
- `_promover_lead`: email e tarefa levam o resumo quando existe; sem resumo, sem linha vazia; resumo longo é cortado a 600.
- `escalar_para_humano` da angariação: com os 3 campos, o email e a tarefa trazem o bloco; com 1 campo só essa linha; sem campos, igual a hoje.
- Esquema da tool: os 3 campos existem e não são obrigatórios.
- Atualização da escalada: não repete o bloco.

## Passos (cada um com OK próprio)
1. Código e testes (pontos 1 e 2), sem commit.
2. Commit e push.
3. Deploy do `figueirahome-agentos`.
4. Nota ao Miguel no registo (#20) e CLAUDE.md.
5. Ver a 1.ª angariação real e a 1.ª lead qualificada depois do deploy: se o resumo e o bloco vêm preenchidos.
