# Voz como canal do motor: plano (pedido #25)

> Estado 26/10/2026: **só plano, nada implementado.** Pedido #25 do Miguel (03/10): «avançar com o agente de voz, para todos os agentes (Inês, Maria, Bárbara e Matilde)».
> Base: `voz-telnyx-resumo.md` (a ligação Telnyx funciona de ponta a ponta desde 19/10, 13 chamadas de teste em `agente_chamadas`).

## Problema

A voz é um 2.º ciclo de conversa à parte (`agents/voice/claude_agent.py`): um prompt próprio (`agente_config['voz']`), `claude-sonnet-4-6` fixo, **sem ferramentas**,
sem router, sem guards, sem lead nem tarefa. Só recolhe nome, interesse, orçamento e zona e deixa o resto para um resumo no fim (`save_call`).
Isto viola «um motor, N assistentes» e deixa a voz de fora de tudo o que os outros canais já têm: Maria a encaminhar, Matilde/Inês/Bárbara com os seus prompts,
`guardar_dados_cliente`, `escalar_para_humano`, `encerrar_lead`, dedup de clientes, aviso por email e a lead no eGO.

## Desenho

1. **`engine.responder("voz", …)`.** Um novo canal, a par de `whatsapp`, `site` e `web`.
   - Thread **por chamada**: `participante = call_control_id` (uma chamada = uma conversa; o telefone não serve, voltaria a abrir a conversa anterior).
   - O telefone de quem liga (`from`) passa ao motor por um parâmetro novo, `telefone`, e entra no `contexto` das tools e nos guards (hoje só o WhatsApp o tem).
     `_contexto_inicial` passa a correr também para a voz (perfil do cliente conhecido, lead aberta, candidatura da Meta); o **template** não entra (é uma mensagem de WhatsApp).
2. **Instrução de canal no motor** (`_montar_system_prompt`, como o site e o WhatsApp), nunca no prompt base de cada assistente:
   frases curtas (≤25 palavras), sem markdown, listas, símbolos, emojis nem links; preços e referências ditos como se falam; o telefone já é conhecido
   (`instrucao_telefone` actual); a saudação já foi dita; despedida final com a marca `FIM_CHAMADA`. `MAX_TOKENS["voz"] = 200`.
   Tudo o que hoje vive em `_SYSTEM_BASE` e é específico de voz passa para aqui; o que é recolha de dados passa a vir do prompt de cada assistente.
3. **Router.** A Maria (A2) atende; o `router.route` decide a partir do que a pessoa disser e a thread fica colada (sticky). A voz é a mesma em todos os assistentes
   (sem trocar de nome a meio da chamada): **decisão para o Miguel** (ver abaixo).
4. **Ferramentas por canal** (fronteira de segurança, com teste): `tools_para(spec["tools"], canal)`. A voz recebe só as de **registo** (`guardar_dados_cliente`, `escalar_para_humano`,
   `encerrar_lead`, e `pedir_visita` na Matilde). Nunca as `consultar_*` do broker. Procura de imóveis por voz é a fase 2 (ver adiante).
5. **`save_call` reduzido ao registo**: continua a gravar a chamada em `agente_chamadas` (transcrição, resumo, duração) e passa a guardar o `conversa_id` e o `contacto_id`.
   A criação de cliente, lead e tarefa deixa de ser por extração no fim e passa a vir das tools durante a conversa (a extração fica como rede de segurança na fase 1).
6. **Guards do WhatsApp que não se aplicam:** fim de conversa por emoji, opt-out por texto e nudge. O nudge e a cascata ignoram o canal `voz` (não há envios proativos por voz).
7. **Interruptor `VOZ_COMO_CANAL`** (secret do Fly, vazio = comportamento actual). Desligar volta ao agente antigo sem deploy.

## Fases

| Fase | O quê | Critério |
|---|---|---|
| F0 | **Medir antes de mexer**: latência por turno (STT, Claude, TTS) das 13 chamadas e o custo do motor por turno (leituras da base antes de cada resposta) | Números no plano; o motor deve acrescentar < 300 ms |
| F1 | Canal `voz` no motor, instrução de canal, ferramentas de registo, router, `save_call` ligado à conversa, interruptor | 12 chamadas de ensaio (3 por assistente: engano, sem interesse, interesse real) com o estado certo no Supabase |
| F2 | Procura de imóveis por voz: resultados compactos (1–2 imóveis, ditos), ficha curta, sem links; oferta de enviar a ficha por WhatsApp (mensagem à parte, só com consentimento) | A Matilde responde a «tem T2 na Figueira?» com dados reais |
| F3 | Barge-in, STT em tempo real, passar a chamada a um consultor, chamadas de saída (cascata, #21) | Por decidir |

**Latência (risco principal).** O motor faz 5 leituras à base antes de chamar o modelo (conversa, configuração, perfil, motivos escalados, ferramentas já usadas).
Numa conversa de texto é irrelevante; numa chamada soma-se ao STT e ao TTS. Mitigação: carregar tudo **uma vez no início da chamada** e manter em memória durante a chamada;
só a gravação do turno vai à base, fora do caminho da resposta.

## Resultados da F0 (26/10/2026, só leitura)

- **Logs das chamadas de teste:** o Fly guarda ~100 linhas e nenhuma é de chamadas; os tempos de STT e de Claude por frase **não se recuperam**. Medem-se na F1.
- **Leituras do motor antes de cada resposta** (Supabase real, mediana de 7 corridas): `load_conversation` 79 ms, `load_config` 78 ms, `_contexto_inicial` 156 ms, `motivos_escalados` + `tools_ja_usadas` em paralelo ~80 ms (estimado: com `conversa_id` vazio devolvem 0). Total ~390 ms por turno; a 1.ª ligação fria custou 1 578 ms.
- **Tempo do modelo** (`agente_interacoes.latencia_ms`, turnos de 1 iteração sem erro, WhatsApp, n=264): p50 2,8 s, p90 5,4 s, com `max_tokens` 1024 e respostas longas. Não é a latência da voz (frase curta, `max_tokens` 200), mas mostra que o motor sozinho não cabe em <1 s. Na voz antiga ainda não há medida.
- **Conclusão:** 390 ms ultrapassa o limite de 300 ms, por isso a regra do plano aplica-se. A chamada abre com a saudação da Telnyx (alguns segundos de fala): **carregar conversa, configuração, perfil e estado durante a saudação**, e em cada turno só a chamada ao modelo e a gravação (fora do caminho da resposta). Numa conversa nova (a chamada) `load_conversation` e `motivos_escalados` nem são precisos.

## Testes

- Unitários: a instrução de voz entra só no canal `voz`; a de WhatsApp não; `tools_para` filtra por canal (a voz nunca tem `consultar_*`); o `telefone` passa ao contexto das tools.
- Webhook/áudio com o `responder` simulado: uma frase completa devolve texto, `FIM_CHAMADA` desliga, texto vazio pede repetição.
- Ensaio contra o modelo (padrão `eval_ines_zona`): guiões curtos por assistente; verifica as tools chamadas e o estado final. Sem rede nos testes de CI.

## Decisões para o Miguel (reunião de 28/10)

1. **Uma voz ou uma por assistente?** Recomendo uma só (Maria atende e encaminha sem mudar de nome), para a chamada não parecer uma transferência.
2. **Gravação do áudio:** hoje só se guarda a transcrição (avisada na saudação). Gravar exige consentimento explícito e um prazo de retenção. Recomendo não gravar.
3. **Fora de horas e passagem a um consultor:** a Maria diz que um consultor liga (como hoje), ou passa a chamada ao telemóvel do consultor de serviço (fase 3, precisa de número).
4. **Chamadas de saída** (cascata do #21, 3.º ou 4.º passo): só depois do consentimento por telefone e do RGPD; fora desta fase.
5. **Procura de imóveis por voz** (F2): queres que a Matilde diga preços e zonas ao telefone, ou só recolha e passe a um consultor?

## Fora de âmbito

Barge-in e STT em tempo real (F3), chamadas de saída, gravação do áudio, mudança do STT (`gpt-transcribe`) e do TTS (`VOZ_TTS`).
