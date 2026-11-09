# Telefone da ficha antiga no 1.º envio — plano (#58, 06/11/2026)

> Plano, nada implementado. Pedido #58 do registo do Miguel (urgência alta). A migration corre o utilizador; o n8n edita-se ao vivo (ver riscos).
> Versão 2 (06/11): a 1.ª versão lia o formulário da `leads` no fluxo do envio. Contrariava a decisão de 15/10 (o fluxo lê só `contactos`) e acrescentava uma segunda fonte para o mesmo dado. Esta corrige na origem.

## Princípio

O que está na `leads` (o formulário da Meta) deve estar igual na `contactos` da mesma `meta_lead_id`. Desde o espelho em `contactos` (21/09) isto cumpre-se, **exceto num sítio**: quando o RPC junta a lead a uma ficha que já existia.

## O caso

Lead Meta de compra de 06/11, 09:26, anúncio FH2588. O formulário trazia o nome e o telefone da pessoa; a `leads` ficou certa. O RPC `lead_meta_compra` juntou a lead a uma ficha de 2021 (mesmo email, `telemovel` igual ao do formulário). A ficha tinha outro nome e o `telefone` com o número de 9 dígitos escrito duas vezes (18 dígitos). O sub-fluxo do n8n leu a `contactos` e enviou «Olá <nome da ficha>» para 18 dígitos. A Meta aceitou (`200`) e a entrega falhou um segundo depois (131026). A pessoa tem WhatsApp e escreveu diretamente à agência; a Matilde nunca lhe respondeu.

## Causa (verificada)

1. **RPC `lead_meta_compra` (`0057`), ramo «ficha existente»**: encontra a ficha por `normalize_phone(telefone)` ou `normalize_phone(telemovel)` e, se falhar, pelo email. Ao juntar, só preenche `telefone`/`telemovel`/`email` se estiverem **vazios** e nunca toca no nome. No ramo «ficha nova» grava os mesmos dados da `leads`, por isso lá não há divergência.
2. **Sub-fluxo n8n «enviar template à lead da Meta» (`4rDc9amm6HpO5F4j`)**: lê `contactos` (nó «Ler lead no Supabase»). O nó «Preparar texto e número» calcula `telefone_e164`: só dígitos, tira `00`, junta `351` se tiver 9 dígitos, **senão deixa como está**. Não valida o comprimento e 18 dígitos seguem para a Meta.
3. **Dados estragados já na tabela**: 417 contactos têm >12 dígitos no telefone, mas só **23** são o mesmo número repetido (19 de 9+9). Dos restantes, 207 têm 14 dígitos (`00351`+9, válido e escrito pelo scraper) e 99 têm 18 dígitos (dois números colados). Dos 23 repetidos, 20 vêm de linhas sem `ego_link` nem `meta_lead_id`, ou seja do pipeline do Miguel, não do nosso scraper.
4. **Origem dos 18 dígitos (verificada 06/11): um único evento.** Os 99 têm o mesmo `ego_atualizado_em`, **03/05/2026 10h**, num lote de 15 590 linhas sem `ego_link` (uma carga em massa; 73 são dois números diferentes colados, 19 o mesmo duas vezes). Nenhuma linha de 18 dígitos existe fora desse lote: não é um escritor ativo. Mas:
5. **Latente, no nosso scraper:** o eGO guarda por vezes vários números no mesmo campo, separados por vírgula (498 `telemovel` assim, ex. `"00351…, 00351…"`). `mapping_todas_colunas.py:329` faz `telefone = telemovel` sem tratar listas. Hoje 485 dessas fichas têm o `telefone` vazio (não foram reeditadas desde 28/09); na próxima edição no eGO, o scraper copia a lista para `telefone` e o n8n, ao tirar o que não é dígito, cola os números: é o mesmo estrago. **Há que fechar isto antes de qualquer restrição na BD.**

## Dimensão (auditoria de 06/11, `leads` × `contactos` por `meta_lead_id`)

| | |
|---|---|
| Leads Meta | 480 (310 sem `contactos` com o mesmo id: 278 de agosto, 30 de setembro, **2 de outubro**, 0 de novembro) |
| Com `contactos` | 170 |
| Telefone do formulário em nenhuma coluna | 0 |
| Telefone do formulário ≠ `contactos.telefone` | **1** (o caso do #58) |
| Nome ≠ (texto exato) | 8: 3 acentos, **2 realmente diferentes**, 3 só escrita |
| Email ≠ | 3 |
| Telefones «inválidos» | 8, mas 7 são números estrangeiros legítimos (10 a 13 dígitos, iguais nos dois lados) |

O erro é raro, mas custa a lead inteira. E a validação **tem de aceitar números internacionais**.

## Impacto além do primeiro envio

Tudo o que usa `contactos.telefone` ficaria apontado ao número errado: os follow-ups de 24 h e 72 h (n8n), a deteção de resposta (`leads_para_ego._conversa_do` procura a conversa pelo telefone do contacto) e a lead criada no eGO (que exige email). Corrigir só o envio deixava isto por resolver; por isso a correção principal é na origem (F1).

## Plano

### F1 — O RPC garante que o número do formulário fica numa das duas colunas (migration `0059`, corrida por ti)

**Decisão (06/11): só acrescentar, nunca substituir.** Substituir o `telefone` apagava o número de um cliente do eGO quando duas pessoas partilham o email (a junção por email não distingue). Em 170 leads Meta com ficha nunca faltou o número do formulário nas duas colunas; o caso do #58 era o número certo no `telemovel` e o estragado no `telefone`. A F1 fecha o buraco teórico.

Ler primeiro a função em produção com `pg_get_functiondef` (como na `0057`) e alterar só o ramo `v_found`. Se `normalize_phone(p_telefone)` não coincidir com nenhuma das duas colunas:
- `telefone` vazio → `telefone` := número do formulário;
- senão `telemovel` vazio → `telemovel` := número do formulário;
- senão (as duas ocupadas com outros números) → **acrescentar ao `telemovel`** como o eGO guarda listas: `telemovel || ', ' || p_telefone`.
- Nada se apaga nem se substitui. `email` continua a só preencher quando estiver vazio; o **nome** não se altera (faz parte da chave `(nome, criado_em)` e a ficha é do eGO).

Reverter: guardar a função anterior (`pg_get_functiondef`) antes de substituir.

**Limite assumido:** numa ficha com `ego_link` o scraper reescreve `telemovel` com o valor do eGO na próxima edição, e o número do formulário pode perder-se. A F2 lê as duas colunas e não depende da `leads`; a solução definitiva é a sincronização dos dados do contacto entre o Supabase e o eGO (ver abaixo).

**Mais tarde (decisão do utilizador, 06/11):** garantir que o Supabase e o eGO estão em sincronia nos dados do contacto (telefone, email, nome). Hoje o número que a pessoa dá numa lead Meta não chega ao eGO se a ficha já existir, e o scraper repõe o do eGO. Fica fora do #58; precisa de plano próprio.

### F2 — O envio valida o número (n8n, sem tocar na BD)

No sub-fluxo `4rDc9amm6HpO5F4j`, que continua a ler só `contactos`:
1. Novo nó «Validar telefone» (antes de «Preparar texto e número») escolhe `telefone_e164`:
   - tira não dígitos e o prefixo `00`;
   - 9 dígitos a começar por 2, 3 ou 9 → `351`+9;
   - 12 dígitos a começar por `351` → ok;
   - 10 a 15 dígitos (limite E.164) e que **não** sejam um bloco repetido duas vezes → internacional, ok;
   - o `telemovel` do eGO pode ser uma lista (`"a, b"`) e o `telefone` também: separa-se por `, ; /` e fica o **primeiro** número válido, entre `telefone` e `telemovel`;
   - tudo o resto → **inválido**.
2. Novo nó **«Número válido?»** (`IF`) antes de «Send template». Inválido: não envia; grava `whatsapp_falhou_em` com código `0` (os follow-ups já filtram `whatsapp_falhou_em is null`) e **avisa por email** a consultora do imóvel e o Miguel, no estilo do aviso de recusa do WhatsApp (o desenho já existe: «Ler angariador» → «Ler email da consultora» → Resend).
3. Os follow-ups de 24 h e 72 h (`TK8moXEAjYgvrY1A`, `HRSMT5PRZYRZ7Oc1`) têm a mesma normalização; aplicar a mesma validação.

Verificação: lead sintética cujo email coincide com uma ficha antiga de outro telefone, **com o teu número** no formulário: o template tem de chegar a ti. Nova execução com 18 dígitos: não envia e avisa. Atualizar a caixa do `docs/n8n/README.md` (o JSON do `01` no repo é snapshot antigo).

### F3 — Limpar os 23 repetidos (escrita em produção, só com OK)

- Corrida em seco: listar os 23 com `telefone`, `telemovel` e origem. Corrige-se **só** quando o bloco repetido é válido (9 dígitos PT ou E.164): `telefone` := um só bloco. Os 4 de blocos de 10 a 14 dígitos mostram-se à parte.
- Os 80 de 18 dígitos que **não** são repetidos (dois números colados?) ficam por rever à mão: não se adivinha.

### F4 — Backend: escolher o telefone válido (Python)

`normalizar_telefone` devolve 18 dígitos sem reclamar (confirmado). Em `leads_para_ego` e em quem usa `telefone or telemovel`, escolher o **primeiro válido** entre os dois, em vez de deixar um inválido «ganhar» a um válido. Teste com um contacto de telefone repetido e `telemovel` certo.

### F5 — Scraper: nunca copiar uma lista de números para `telefone` (código, `scraper/`)

`mapping_todas_colunas.py:329`: `telefone` := o **primeiro** número da lista de `telemovel` (separada por vírgula, ponto e vírgula ou barra); `telemovel` fica como vem do eGO. Teste no `demo()` com `"00351912345678, 00351913345678"` → `telefone == "00351912345678"`. Deploy do `figueirahome-scraper` (app à parte).

### F6 — Restrição na BD (migration `0058`, **já escrita**, corrida por ti e só no fim)

`supabase/migrations/0058_contactos_telefone_max_15_digitos.sql`: `check` em `contactos.telefone`: no máximo 15 dígitos (limite E.164) e sem `, ; /`. O bloco 1 **recusa-se a correr** enquanto houver linhas fora da regra. Só `telefone`: o `telemovel` fica de fora de propósito (guarda a lista do eGO tal como vem; uma restrição ali partia o sync do scraper nas 498 fichas).

Porque tem de ser a última:
- **Antes da F5**, o primeiro upsert do scraper de um contacto com vários números violava a restrição e **o lote inteiro era rejeitado** (um `upsert` em lote falha todo por uma linha).
- **Antes da F3**, qualquer `UPDATE` a uma das 168 fichas fora da regra falhava (o n8n a marcar «enviado», o nudge, os recibos de entrega…), mesmo sem mexer no telefone.
- O pipeline do Miguel também passa a ser rejeitado se escrever mais de um número em `telefone`. É a intenção, mas **avisá-lo antes**.
- Reverter: `alter table public.contactos drop constraint contactos_telefone_um_numero;`.

## O nome (limite assumido)

A `contactos` continua com o nome da ficha antiga; o template pode saudar com o nome errado (2 casos em 170). O número, esse, vai certo. Para o nome certo no template faltava uma coluna nova (`contactos.nome_formulario`) ou ler a `leads` no fluxo. **Decisão adiada**: o ganho é pequeno e a coluna cria uma segunda fonte. Quando o primeiro nome do formulário for diferente, convém o Miguel ver o caso à mão (a auditoria acima volta a correr-se quando quiserem).

## Decisões a tomar

1. **F1:** a regra («`telefone` = formulário, o antigo válido vai para `telemovel` se estiver vazio») serve?
2. **F2:** o aviso do número inválido vai para a consultora do imóvel e o Miguel, como a recusa do WhatsApp?
3. **Recrutamento e angariação** têm RPCs com a mesma estrutura (`lead_meta_recrutamento`, `lead_meta_angariacao`). Aplicar lá também, ou só à compra, como o #58 pede?
4. **Os 2 leads de outubro sem `contactos`:** ver porquê (fora do #58).
5. **F3:** quando autorizares, faço primeiro a corrida em seco.

## Ordem proposta e riscos

F2 (já protege o envio, sem tocar na BD) → F4 (backend) → F5 (scraper, fecha a fonte) → F1 (migration `0059`, tua) → F3 (limpeza das 168 fichas, só com OK, depois de uma corrida em seco) → F6 (migration `0058`, a restrição, no fim). Cada passo é independente, exceto a F6, que só corre depois da F5 e da F3. A F2 evita a perda da lead enquanto o resto não corre.

**F3 alargada:** são 168 fichas com `telefone` fora da regra (99 de 18 dígitos da carga de 03/05, mais 69 de 15 a 28 dígitos). Dos 99, 19 são o mesmo número duas vezes (um só bloco) e 73 são dois números diferentes colados (9+9: o primeiro fica em `telefone`, o segundo em `telemovel` se estiver vazio). Os restantes listam-se à mão.

- **n8n ao vivo:** editar pela API e pela UI ao mesmo tempo repõe o rascunho antigo (um separador aberto regrava). Fechar o fluxo no editor, ou ler a versão publicada antes de gravar e guardar a versão anterior (`n8n_workflow_versions`) para reverter. O n8n publica ao gravar.
- **Teste que envia WhatsApp a sério:** só com o teu número.
