# Plano — Follow-up da Matilde (A1): dentro da conversa e por template

> Fase nova. Análise feita, zero código. Duas frentes distintas, pedidas juntas
> pelo utilizador: (A) lembrete dentro da janela de 24h quando a lead responde
> e depois pára a meio da conversa; (B) melhorias ao follow-up por template
> (fluxos n8n `01`/`02`/`03`, ainda por importar em produção).

## Porquê

O utilizador pediu para analisar as conversas reais da Matilde e ver o que
falta no follow-up. Já se sabia (auditoria 06/09, achados A5/A7) que o email ao
corretor só sai com MQL completo e que o `03` usa 48h em vez das 24h da spec.
O que faltava era olhar para as conversas em si — quantas ficam mesmo por
responder a meio, e onde.

## O que a análise mostrou (dados reais, 2026-09-09)

Consulta directa a `agente_conversas` (agente=`a1_vendedor`, 43 threads):

- **43 de 43 terminam com mensagem da Matilde** — estrutural (o backend
  responde sempre dentro do turno), não é sinal de abandono por si só.
- **Só 4 conversas têm um gap >1h entre mensagens consecutivas** dentro da
  própria thread — confirma o já registado no CLAUDE.md: quem responde,
  responde rápido (mediana <1h). Pausas a meio de uma conversa activa são
  raras.
- **O padrão real é outro**: a conversa acaba com uma pergunta ou uma ficha
  da Matilde, e a pessoa nunca mais volta — a thread expira ao fim de 48h
  (`_CONVERSATION_TTL_HOURS`, `conversation.py:10`) e fica órfã. Amostra do que
  ficou sem resposta, por idade:
  - **`351913702003`, 820h atrás**: fez uma proposta de 110 000€ ao FH2571,
    a Matilde pediu nome+telefone para avançar — **e nunca mais respondeu**.
    É o caso de maior valor perdido encontrado na amostra.
  - Várias fichas de imóvel enviadas (`FH2450A`, `FH2542`, `FH2578`, `FH2397`,
    etc.) sem qualquer resposta a seguir, 100h+ depois.
  - Perguntas de qualificação da Matilde ("é moradia ou apartamento?", "até
    que orçamento?") também sem resposta.
- **Nem todo o "silêncio" é abandono** — várias conversas terminam em
  despedida normal ("Cuide-se, Maria 👋", "Boa continuação, João 😊") e não
  precisam de nudge nenhum.

Conclusão: a oportunidade não é "conversas com pausas longas a meio" (raro),
é **"conversas que terminam com uma pergunta/ficha da Matilde em aberto e
nunca mais continuam"** — e isso é comum.

## Restrição que define tudo: a janela de 24h é do WhatsApp, não nossa

`_CONVERSATION_TTL_HOURS = 48` é só o nosso critério de "ainda é a mesma
conversa" para efeitos de histórico. A regra que importa é a da Cloud API:
**mensagem livre (sem template) só é aceite até 24h depois da última mensagem
da pessoa** — depois disso a Meta rejeita e é preciso um template aprovado
(como o `03` já faz para leads frias).

Por isso um nudge "dentro da janela" só pode usar `send_text_message` (livre,
sem custo de template) se disparar **claramente antes das 24h**, com margem
para o cron correr — na prática, a janela útil de disparo é algo como
**3h–20h** depois da última mensagem da pessoa, nunca perto das 24h.

## Frente A — nudge dentro da janela de 24h (nova)

**Âmbito**: conversas `agente_conversas` onde a última mensagem é da Matilde,
o `canal='whatsapp'`, o participante tem lead/cliente **sem** `contacto_humano_em`
nem estado fechado (`engano`/`sem_interesse`/`qualificada` — quem já qualificou
não precisa de nudge, já vai para o corretor), e passaram **N horas** desde essa
última mensagem sem resposta nova (N a decidir — proponho 6h, ajustável).

**O que NÃO fazer** (para não repetir erros já documentados no projecto):
- Nunca escrever por cima de `contacto_humano_em` nem mexer em leads já
  entregues a uma consultora.
- Um nudge por conversa, nunca mais — precisa de carimbo próprio (nova coluna,
  ex. `agente_conversas.nudge_em`), no mesmo espírito de `follow_up_em`
  (`0030`): carimbo do fluxo, não o estado, que é editável no painel.
- Não nudge-ar despedidas — precisa de alguma heurística (ex.: já existe
  `encerrar_lead`/desfecho gravado, ou a última mensagem da Matilde não é uma
  pergunta) para não mandar "ainda está aí?" depois de um "de nada, boa sorte".
  A decidir: lista de desfechos já fechados chega, ou é preciso olhar o
  conteúdo da última mensagem.

**Como implementar** (reaproveitando o que já existe, nada de novo a monte):
- Endpoint novo, protegido por `X-Automacao-Secret` (mesmo padrão de
  `require_automacao_access` já usado nos syncs eGO), disparado por cron
  GitHub Actions (mesmo padrão de `sync-imoveis.yml`), a correr de hora a hora
  (janela de disparo é ampla, não precisa de precisão ao minuto).
- Query: `agente_conversas` com `agente='a1_vendedor'`, `canal='whatsapp'`,
  `nudge_em is null`, `atualizado_em` entre `now-20h` e `now-6h` (a favor da
  segurança de nunca passar as 24h mesmo com atraso do cron), cruzado com
  `leads`/`agente_clientes` para excluir fechados/com consultora.
  Reutilizar `normalizar_telefone`/`variantes_telefone` (`guards.py`) para o
  cruzamento por telefone, como já se faz em `load_conversation`.
- Envio: `send_text_message` (`meta_api.py:24`) com um texto curto e humano
  (não outro monólogo da Matilde) — ex. *"Ainda está por aí? Fico a postos se
  quiser continuar."* — texto a validar com o utilizador, não decidir sozinho.
- **Gravar no histórico**: apendar a mensagem a `mensagens` e chamar
  `save_conversation` (`conversation.py:69`) com o mesmo `conversa_id`, para o
  nudge aparecer no histórico do painel e não confundir a próxima leitura do
  A1. Marcar `nudge_em` na mesma escrita.
- Formatação: passar pelo mesmo `formatacao.py` do canal WhatsApp (sem
  Markdown) — ponto único de saída, não duplicar regras.

**Migration necessária**: coluna `agente_conversas.nudge_em` (timestamp,
nullable) — à mão no editor SQL, como todas as outras.

## Frente B — follow-up por template (01/02/03)

Estes fluxos já estão desenhados e documentados (`docs/n8n/README.md`), só
faltam importar/publicar (Próximos passos 1 do CLAUDE.md). O que a análise de
hoje acrescenta a esse trabalho já conhecido:

- O `03` dispara às 48h; a spec original fala de 24h (achado A7). Os dados
  (16/17 respostas em <1h) não provam nem desmentem 48h vs 24h para quem
  **nunca** respondeu ao primeiro template — é população diferente da Frente
  A. Manter 48h até haver corrida de controlo que diga o contrário (já é a
  posição do próprio ficheiro do `03`).
- Nada de novo a mudar no texto/lógica do `01`/`02`/`03` a partir desta
  análise — o trabalho que falta aí é o já listado no CLAUDE.md (importar,
  corrigir atraso de 12h do `01`, `AUTOMACAO_SECRET` em produção).

## Por decidir antes de código

1. ~~**N horas** de silêncio antes do nudge~~ — **decidido: 6h** (2026-09-09).
2. ~~**Texto do nudge**~~ — **decidido (2026-09-09)**: *"Ainda está
   interessado? Fico a postos para continuar, ou diga-me só que não para eu
   não voltar a incomodar."* Saída explícita, como o `03` já faz às 48h —
   uma resposta negativa aqui também devia poder chamar `encerrar_lead`
   (a confirmar no desenho da Frente A: o nudge precisa de voltar a passar
   pelo motor da Matilde na resposta, não só disparar e esquecer).
3. ~~**Heurística de "não interromper despedidas"**~~ — **decidido
   (2026-09-09)**: lista curta de marcadores de fecho verificada na última
   mensagem **da Matilde** (voz controlada por nós, mais fiável que adivinhar
   o tom da pessoa) — ex. 👋, "cuide-se", "boa continuação", "muita força",
   "boa sorte". Mesmo padrão de allowlist pequena e testada já usado no
   projecto (`_TOOLS_INPUT_SEGURO` e semelhantes); lista fica em código, fácil
   de estender.
4. ~~Threads **sem** lead associada~~ — **não é decisão, resolve-se pelo
   âmbito**: confirmado por query que todos os `site-*`/`painel_auto`/`teste-*`
   são `canal='site'` ou `canal='web'`, nunca `canal='whatsapp'`. O filtro
   `canal='whatsapp'` da Frente A já os exclui sem mecanismo extra.

## Verificação

- Teste unitário novo em `backend/tests/` que monta um `agente_conversas` com
  `atualizado_em` fora/dentro da janela e confirma que só os elegíveis entram
  na query (mesmo padrão dos testes de `validar_disponibilidade_crm`).
- Correr manual com `Limit` pequeno antes de pôr no cron, como o `02`/`03` já
  exigem — mesma cautela, mesmo motivo (não mandar em rajada para gente real).
