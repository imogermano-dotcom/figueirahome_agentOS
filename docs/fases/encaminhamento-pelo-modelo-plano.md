# Encaminhamento entre assistentes decidido pelo modelo — plano

> Mexe em `engine.py` (o motor único). **Plano antes de código** (CLAUDE.md, regra 2).
> Continuação de `router-menu-maria-plano.md`: aquele corrigiu o menu; este trata do
> que o regex não consegue decidir.

## Problema

Quem decide o assistente é uma função pura de regex (`router.route`), uma vez por
mensagem, e depois a thread fica colada (sticky). O desenho assume que, quando o regex
não acerta, "cai na A2, cujo trabalho é perceber e encaminhar" — mas a A2 só tem
`guardar_dados_cliente` e `escalar_para_humano`: **não tem como encaminhar**. Na
prática, o que o regex não apanha acaba numa escalada para um humano (07/10: candidata
a "trabalhar connosco" ficou na Maria).

Medido a 07/10 com `route(frase, A2)` (frases minhas, não tráfego real):

| Frase | Destino | Quem devia ser |
|---|---|---|
| "queria ser consultor", "têm vagas?" | A2 | A3 |
| "quero colocar o meu apartamento à venda" | **A1** | A4 |
| "tenho uma casa para vender", "tenho um imóvel para arrendar" | **A1** | A4 |
| "procuro trabalho", "estou à procura de trabalho na área imobiliária" | **A1** | A3 |

**Dois sub-problemas diferentes**, e só um é da A2:
- **(a) Fica na A2** sem sinal: a A2 podia encaminhar. Corrigível dando-lhe uma tool.
- **(b) O regex manda para a A1** ("casa", "apartamento", "procuro" disparam `_A1_RE`):
  a A2 nunca vê a mensagem. E a A1 não sai da thread (sticky). **Uma tool só na A2 não
  resolve isto.** Exige que a A1 também possa devolver a conversa.

Tráfego real: 87 conversas (48 na A1). O único vendedor real encontrado na A1 é de
03/08, antes da Bárbara existir; depois de 13/09 (A4) e 20/09 (A3) **nenhum caso**. O
volume é baixo (campanha de compra parada), por isso a ausência de casos pode ser só
falta de tráfego. O risco é real, mas não está medido.

## Proposta

Uma tool `passar_para(destino, motivo)`: o **modelo decide**, o **código executa**.

- `destino` é um **enum fechado** (não o nome de um agente): `comprar_arrendar` → A1,
  `vender_ou_avaliar` → A4, `trabalhar` → A3. O mapeamento para o agente vive em código.
  Nunca aparece `broker` nem `a2_geral` como destino possível.
- **Quem a tem:** a **A2** (os três destinos) e a **A1** (só `vender_ou_avaliar` e
  `trabalhar`, e só se a thread ainda for jovem e não vier de uma lead da Meta — ver
  decisões). A3 e A4 não a têm: continuam coladas (sentido único mantido).
- **Execução no motor** (`_responder_sem_lock`): se uma iteração devolver `passar_para`
  (e a regra do código a aceitar), o motor **repete o turno do zero com o novo
  assistente**, sobre o histórico original + a mensagem do utilizador:
  novo `spec`, novo `system_prompt` (`_contexto_inicial` + `load_config` do destino, mais
  uma nota "esta conversa passou de outra assistente: apresenta-te e não repitas
  perguntas já respondidas"), tools do destino. A chamada do assistente antigo fica como
  uma classificação barata; o novo responde de imediato. Grava `agente=destino`.
- **Porquê repetir e não continuar a mesma lista de mensagens:** `tool_use` de uma tool
  que o novo assistente não declara no `tools` pode ser rejeitado pela API (por
  verificar), e as tools não ficam persistidas entre turnos (`engine.py`, bug de 20/09).
- **Regex continua primeiro:** é grátis e determinístico. O modelo só entra quando o
  regex não decide (A2) ou quando o assistente actual é a A1 e acha que errou.

## Regras que vivem em código (não no prompt)
- Só os assistentes com a tool, só os destinos do enum, **uma única transferência por
  turno**, nunca para o mesmo assistente, nunca para trás (A3/A4 → qualquer coisa).
- O `agente` continua a nunca vir do pedido (endpoint público). O argumento da tool vem
  do modelo, mas só alcança assistentes públicos, por construção do enum.
- A A1 só pode transferir se: `thread_nova` ou ≤ 3 mensagens do utilizador, e sem lead
  aberta (as leads da Meta são sempre compradores).
- Falha ao aplicar a transferência (destino inactivo em `agente_config`, erro): o
  assistente actual responde normalmente e regista-se o motivo. Nunca fica sem resposta.

## Observabilidade
- `agente_interacoes`: a chamada de classificação regista `tools_usadas=['passar_para']`
  e, em `tools_detalhe`, só o **destino** (enum, sem PII). **Não** se acrescenta
  `passar_para` a `_TOOLS_INPUT_SEGURO`: o `motivo` é texto livre e o modelo pode escrever
  nomes lá (o teste `test_metricas_negocio` trava a allowlist em `{pesquisar_imoveis,
  ficha_imovel}`).
- Um turno com transferência gera **duas** linhas em `agente_interacoes` (A2 e destino).
  A verificar se `agente_metricas` conta "interações" ou "conversas", para não duplicar.

## Prompts
- A2: trocar o parágrafo "VENDER / AVALIAÇÃO / RECRUTAMENTO → escalar" por "usa
  `passar_para`". `escalar_para_humano` fica para reclamações, jurídico, imprensa. Só
  transfere quando a intenção é clara; na dúvida, pergunta (menu).
- A1: uma frase curta a dizer que, se a pessoa quer vender o seu imóvel ou candidatar-se,
  usa `passar_para`. Cuidado com "à venda": um comprador também a diz.
- Fora desta fase: não pedir telefone no WhatsApp e não repetir tools depois de escalar
  (fase própria, para não misturar).

## Testes
Em `backend/tests/` (a confirmar o padrão dos testes de `responder` já existentes):
1. Unidade: `destino` fora do enum → rejeitado; `broker`/`a2_geral` inalcançáveis.
2. A2 + `passar_para(trabalhar)` → resposta vem do prompt/ferramentas da A3, `agente` gravado
   = A3, duas interacções registadas.
3. A1 + lead da Meta → transferência recusada (fica na A1).
4. A1 com thread antiga (> 3 mensagens) → recusada.
5. Falha no destino → o assistente actual responde.
6. Regressão: conversas sem transferência passam exactamente como antes (mesmo nº de
   chamadas à API).
`pytest backend/tests/` de `backend/` (hoje 292).

## Custo e risco
- Custo: só nos turnos que transferem, +1 chamada (≈ 0,003–0,007 USD, medido em turnos
  A2); latência +1–2 s nesses turnos.
- Risco principal: **transferir mal** e ficar preso (sticky). Mitigação: enum curto,
  "na dúvida, pergunta", regras de código acima, e **medição** antes de alargar.
- Mexe no motor único usado por todos os assistentes: por isso o teste 6 (regressão).
- Reversão: `git revert`. Sem migration, sem dados, sem n8n.

## Decisão (07/10): medir primeiro, sem tocar no motor

Dado o volume (10 conversas da A2 desde 15/08, campanha de compra parada), **não se
implementa a tool nem o modo sombra**. Fica um script de leitura,
`backend/scripts/monitorizar_encaminhamento.py` (`--dias N`, `--texto` só local), que
lista vendedores/candidatos na Matilde depois de a Bárbara/Inês existirem e conversas da
Maria escaladas por recrutamento/angariação, e calcula **"POR RESOLVER"** = o que o
router de hoje continuaria a falhar. Primeira corrida (120 dias, 87 conversas): **0 por
resolver**; os 2 casos da Maria já os resolve o router corrigido a 07/10.

**Quando reabrir este plano:** correr o script ao reactivar a campanha de compra e de
vez em quando; se "POR RESOLVER" passar de 0 com tráfego real, voltar às decisões 1–4.

## Decisões por confirmar (só se o script reabrir o plano)
1. **A1 também pode transferir** (recomendado, é a única forma de resolver o sub-problema
   (b)) ou só a A2 (cobre só (a), a minoria dos casos medidos)?
2. Limite da A1: ≤ 3 mensagens e sem lead (proposta) — certo?
3. Alternativa mais barata ao sub-problema (b) **sem** modelo: apertar `_A1_RE` (palavras
   fracas como "casa"/"procuro" deixam de bastar sozinhas e a mensagem fica na A2).
   Mais simples, mas volta a ser regex; pode misturar-se com esta fase.
4. Medir primeiro? Registar durante umas semanas (sem transferir) o que o modelo teria
   decidido, e só então activar. Mais seguro, mais lento.
