# Resumo — lock de `responder()` por (canal, participante) (25/09)

Achado ao analisar as leads/conversas de hoje: Margarida Lopes (lead
dormente de FH2581, 03/09) respondeu ao WhatsApp e ficou com **2 linhas**
`agente_conversas` separadas, criadas com 3 segundos de diferença, cada uma
com a sua própria leitura da ficha do imóvel e uma resposta diferente da
Matilde — cliente viu duas respostas desencontradas para o mesmo assunto.

## Causa

`conversation.load_conversation`/`save_conversation` é um clássico
check-then-act sem lock: lê se existe conversa, decide, grava. A Margarida
mandou 2 mensagens quase juntas (bubbles separados do WhatsApp, cada um o
seu webhook + `background_tasks`); os dois `_handle_message` correram em
paralelo, nenhum viu a conversa que o outro ainda não tinha gravado (era a
primeira mensagem dela de sempre, sem thread semeada) — cada um inseriu a
sua própria linha.

## Fix

`engine.responder()` ganhou lock em memória por `(canal, participante)`
(`_lock_conversa`, dict de `asyncio.Lock`) — serializa
load→responder→save para a mesma pessoa. Segunda mensagem espera a primeira
terminar (incluindo a escrita), depois encontra a conversa já gravada e
continua-a, em vez de duplicar.

**ponytail**: lock nunca é libertado do dict — cresce 1 `Lock` por número
visto, ao longo da vida do processo. Trivial ao volume actual. Só serve
com **1 máquina** Fly (confirmado, `figueirahome-agentos` corre numa só,
`d896090c747078`) — com 2+ réplicas cada uma teria o seu próprio dict de
locks e a corrida voltava. Se um dia escalar horizontalmente, precisa de
lock a nível de BD (advisory lock do Postgres, por exemplo).

## Testes

`backend/tests/test_engine_lock.py` — novo, 2 testes: mesma conversa
serializa (ordem estrita start/end/start/end), participantes diferentes não
se bloqueiam entre si. Suite: 278 verdes (era 276).

## Por fazer

- Deploy (confirmação explícita).
- Confirmar ao vivo — não há forma directa de reproduzir 2 mensagens
  simultâneas sem esperar por um caso real; os testes cobrem a lógica do
  lock isoladamente.
