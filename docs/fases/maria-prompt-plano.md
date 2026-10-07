# Prompt da Maria (A2) — plano

> Fase pequena. **Plano antes de código** (CLAUDE.md, regra 2). Origem: conversa
> `465be710` (07/10) e medições do mesmo dia, só leitura.

## O que se viu na conversa de 07/10
Candidata a "trabalhar" ficou na A2 (router corrigido entretanto, `router-menu-maria-plano.md`).
Três comportamentos da Maria por rever:
1. **Pediu o telefone no WhatsApp**, onde já é conhecido.
2. **Voltou a chamar `guardar_dados_cliente` + `escalar_para_humano`** no turno seguinte
   ("Não"), depois de já ter dito "Tudo registado".
3. Tratamento "recebê-lo/a", "ajudá-lo/a" (não sabe o género).

## Medições (read-only, `agente_interacoes`/`agente_conversas`, 411 interacções)

| Comportamento | Maria (A2) | Outros |
|---|---|---|
| Pede telefone/contacto no WhatsApp (regex heurística) | 2 de 4 conversas | A1 3/39, **A3 3/27 — apesar de o prompt da Inês o proibir** |
| Repete a escalada (2+ turnos a chamar `escalar_para_humano`) | 2 de 5 | **A3: 11 de 12 — apesar da regra do passo 7**; A1 1 de 4 |
| Custo extra desses turnos repetidos | ≈ 0,03 USD | A3 ≈ 0,63; A1 ≈ 0,08 (≈ 0,75 USD no total) |
| Tarefas `escalar` duplicadas | 0 | 0 (o dedup de `_tarefa_ja_registada` funciona) |
| Mensagens com "o/a" | 3 de 21 | A3 5/202, A1 1/244 |

**Conclusão que muda o plano:** uma regra no prompt **não impede** a repetição (a Inês
tem-na escrita e repete em 11 de 12). A causa é de motor: `tool_use`/`tool_result` não
ficam persistidos entre turnos (`tools._tarefa_ja_registada`, bug de 20/09), por isso no
turno seguinte o modelo só vê o que *disse*, não que a tool correu. Copiar a regra para
a Maria seria inútil.

## Proposta (por ordem de valor)

### 1. Telefone no WhatsApp — instrução de canal no motor, não no prompt
Segue o princípio já registado (`engine._INSTRUCAO_IDENTIDADE_SITE`: o site ganha
"pergunta nome e telefone"). Acrescentar o par para o WhatsApp: *"o número já o tens
(vem do canal): nunca o peças; pede só o nome"*, aplicado a **todos** os assistentes
virados para o público. As tools já fazem fallback ao telefone do canal
(`contexto.get("telefone")` em `guardar_dados_cliente`, `pedir_visita`, `escalar_para_humano`),
por isso não pedir é seguro.
- Reverte uma decisão testada: `test_identidade_site.py::test_whatsapp_nao_ganha_a_instrucao`
  assume "WhatsApp sem instrução". Esse teste passa a afirmar o contrário (a instrução existe
  e não pede o telefone).
- A1 diz hoje "Precisas de nome e telefone" (`pedir_visita`): conflito aparente; a instrução
  de canal prevalece (acrescentar "no WhatsApp, só o nome").

### 2. Prompt da A2 (`_PROMPT_A2`), mudanças pequenas
- **Vender / avaliação / recrutamento**: manter a escalada para humano como **fallback**
  (a A2 não tem mecanismo para passar à Bárbara/Inês), mas sem prometer "a conversa passa"
  e pedindo só o **nome**. Usar nos `motivo` as palavras `recrutamento`, `angariação`,
  `avaliação` ou `venda`: o script `monitorizar_encaminhamento.py` conta as escaladas da
  Maria por esse padrão.
- **Tratamento neutro** até saber o nome: sem "o/a", frases como "Em que posso ajudar?".
- **Não mexer na linha do menu** (`apresenta as opções: Comprar / Vender / Arrendar /
  Trabalhar connosco / Outro.`): `test_router.py::test_menu_da_a2_encaminha_cada_opcao` lê-a
  do prompt e falha se uma opção nova não tiver destino.

### 3. Repetição de tools depois de escalar — **separado, decisão tua**
Não é do prompt. Opção de motor: quando `_tarefa_ja_registada(conversa_id, 'escalar')`
é verdadeira, o motor acrescenta ao system prompt uma **nota de estado** ("o pedido
desta pessoa já foi entregue a um humano; não voltes a chamar `guardar_dados_cliente` nem
`escalar_para_humano`, salvo assunto novo; despede-te") — baseada no facto, não numa regra
abstracta. Não retira as tools (um 2.º assunto legítimo, ex. reclamação depois de proposta,
tem de poder escalar). Reduz custo e o risco de `guardar_dados_cliente` repetido
escrever por cima de telefone/email (bug A4 da auditoria de 06/09). Não é garantia.
**Valor pequeno (cêntimos) e mexe no motor único** → só se quiseres.

## Fora do código: dados em falta nas instruções da Maria
`agente_config[a2_geral].instrucoes` (235 caracteres) tem dois campos **por preencher**:
`Morada: (preencher no painel).` e `Parceiros de crédito habitação: (preencher no painel).`
Se alguém perguntar a morada à recepcionista, ela ou repete o placeholder ou inventa
(o prompt proíbe inventar, mas o dado não existe). **Preenche-se no painel
(Agente → Config), sem deploy.** Confirmar também o horário ("segunda a sexta, 9h30–18h30,
sábado por marcação").

## Testes
- `test_identidade_site.py`: reescrever o caso do WhatsApp (instrução presente, sem
  "pede o telefone"); site e painel inalterados.
- Um teste do prompt da A2: não contém "o/a"; menu intacto (já coberto pelo do router);
  menciona os `motivo` esperados.
- Regressão: suite completa (`pytest backend/tests/`, hoje 292).

## Risco
- Prompt/instrução de canal: o modelo continua a poder ignorá-los (a Inês é a prova).
  Mede-se depois com a mesma consulta: % de conversas WhatsApp em que se pede o telefone.
- A instrução de WhatsApp toca em todos os assistentes públicos, incluindo a Inês (o
  único com tráfego). Mitigado: ela já tem a mesma regra no prompt.
- Reversível com `git revert`; sem migration. Deploy só do backend.

## Decisões (07/10) e estado
1. **Instrução de canal para todos os assistentes** (no motor): feito. `_INSTRUCAO_TELEFONE_WHATSAPP`
   em `engine.py`; fala do número de quem escreve (o telefone da agência continua a poder
   ser dado). A Matilde ganhou um parêntesis no passo das visitas (WhatsApp: só o nome).
2. **Nota de estado no motor (repetição de tools): adiada.** Valor pequeno (≈ 0,75 USD em
   sete semanas, quase tudo da Inês) e mexe no motor único. Reabrir se a Inês passar a ter
   tráfego a sério.
3. **Morada e parceiros de crédito: por preencher no painel** (Agente → Config,
   `a2_geral`). Escrita na base de produção feita por quem tem os dados; sem deploy.

Implementado nesta fase: instrução de WhatsApp no motor, prompt da A2 (motivos
`venda`/`avaliação`/`recrutamento`, só o nome, tratamento neutro), uma linha no A1, e
testes (294). Menu da A2 intacto.

**Como medir depois:** repetir a consulta de 07/10 — % de conversas de WhatsApp em que o
assistente pede telefone/contacto (hoje A2 2/4, A1 3/39, A3 3/27). Não é garantia: o
modelo pode ignorar a instrução (a Inês é a prova).
