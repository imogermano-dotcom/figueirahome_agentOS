# Router × menu da Maria — plano

> Fase mínima, só backend. Achado ao vivo a 07/10: uma candidata respondeu
> "Trabalhar" ao menu da Maria e ficou na A2, escalada como `recrutamento` em vez de
> ir para a Inês. Plano antes de código (CLAUDE.md, regra 2).

## Problema
O menu que a Maria apresenta (`_PROMPT_A2`: *Comprar / Vender / Arrendar / Trabalhar
connosco / Outro*) é a **interface com o utilizador**; o router (`router.py`) é regex.
Duas das cinco opções não encaminham:

| Opção | Regex actual | Resultado |
|---|---|---|
| Vender | `_A4_RE` exige "quero vender", "vender a minha/o meu"… | A2 (devia ser A4) |
| Trabalhar connosco / Trabalhar | `_A3_RE` tem "trabalhar **convosco**" (2.ª pessoa) | A2 (devia ser A3) |

O desenho assume que o que o router falha, a A2 "percebe e encaminha"; mas a A2 não
tem tool de encaminhamento (só `guardar_dados_cliente` e `escalar_para_humano`).

## Proposta
1. **`_A3_RE`**: aceitar *connosco* e variantes de 2.ª pessoa (`trabalhar com vocês/vós`,
   `na agência`, `fazer parte da equipa`), `procuro/oferta de/vaga de emprego` (nunca
   "emprego" solto: "tenho emprego estável e quero comprar" não pode ir para a Inês), e
   a mensagem **inteira** "Trabalhar".
2. **`_A4_RE`**: `vender um/uma/o/a …`, `vender imóvel/casa/apartamento/moradia/terreno`,
   e a mensagem **inteira** "Vender". As frases com "comprar" continuam a ir para o A1
   (ordem A3 → A4 → A1 inalterada).
3. **Teste que lê o menu do próprio prompt** da Maria e verifica o destino de cada
   opção: se o menu mudar sem o router acompanhar, o teste falha.
4. Negativos: frases de compra com as palavras vizinhas ("trabalhar de casa", "emprego
   estável") não mudam de destino.

## Fora desta fase
- Tool `passar_para(agente)` na A2 (encaminhamento pelo modelo): só se os logs mostrarem
  mais desvios que o regex não apanha (2 em 10 conversas da A2 até hoje).
- Prompt da Maria: não pedir telefone no WhatsApp; não repetir as tools depois de
  escalar (regra do passo 7 da Inês). Fase própria, para não misturar com o router.
- "Arrendar" (menu) vai para o A1, que atende quem procura; um senhorio que queira
  arrendar o seu imóvel também cai aí. Não observado; por decidir.

## Risco
Baixo: função pura, sem DB. Um regex mais largo pode mandar para a Inês/Bárbara quem
não devia: mitigado com frases específicas (não palavras soltas) e os testes negativos.
Reversível com `git revert`.
