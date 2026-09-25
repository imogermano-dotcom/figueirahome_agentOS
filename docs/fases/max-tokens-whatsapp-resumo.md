# Resumo — `MAX_TOKENS["whatsapp"]` 512→1024 + log de stop_reason (25/09)

Achado ao analisar a conversa da Inês com a Carla Pato hoje: candidatura
toda recolhida (nome, situação, motivação, zona, telefone), a Inês disse
"Vou já registar os seus dados e agendar o contacto com o responsável de
recrutamento" — mas nem `guardar_dados_cliente` nem `escalar_para_humano`
correram. `agente_clientes`/`agente_tarefas` ficaram vazios. Candidatura
real perdida — registada manualmente (cliente + tarefa + email via Resend,
marcado no registo como manual).

## Causa

`MAX_TOKENS["whatsapp"]` (`assistants.py`) estava em **512**. No fim de uma
conversa de recrutamento, a Inês tenta escrever a frase de fecho **e**
chamar tool(s) com `resumo` livre na mesma resposta — se isso ultrapassar
512 tokens, a API corta a meio e devolve `stop_reason: "max_tokens"` em vez
de `"tool_use"`. `engine.py` só trata tools quando `stop_reason ==
"tool_use"` (linha 427); qualquer outro motivo cai direto no texto parcial
já gerado — **o `tool_use` cortado é descartado em silêncio, sem erro**.

Bate certo com os dados: a Maysa (mesmo dia, candidatura completa com
sucesso) teve a tool numa iteração curta, separada, e só depois o texto de
fecho — nunca competiu por tokens na mesma resposta.

## Fix

- `MAX_TOKENS["whatsapp"]`: 512 → 1024 (mesmo tecto do `web`). Não aumenta
  custo dos turnos normais (é só o tecto, gasta-se o que o modelo gerar) —
  só dá margem aos turnos de fecho que hoje ficavam cortados.
- `engine.py`: `logger.warning` quando `stop_reason` não é `tool_use` nem
  `end_turn`/`stop_sequence` — antes disto era 100% invisível.

## Por fazer

- Deploy (confirmação explícita).
- Sem forma de confirmar ao vivo sem esperar por outra conversa real que
  chegue perto do tecto — o log novo é a rede de segurança daqui pra frente.
