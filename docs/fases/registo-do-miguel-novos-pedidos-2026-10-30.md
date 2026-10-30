# Registo do Miguel: pedidos novos e atualizações (30/10/2026)

Texto para colar no artefacto «Registo para o developer». Sem nomes nem telefones de clientes.
Origem: análise de 29/10 06:00 a 30/10 ~11:00 UTC, cruzada com o registo exportado a 30/10 (#1 a #54).

## Pedidos novos

### N1 — Sync das oportunidades perde as acabadas de promover («Criada»)
- **Tema:** Sync eGO / Oportunidades · **Urgência:** Alta · **Estado:** Entregue (corrigido no código; deploy do scraper a seguir) · **Com quem está:** Developer
- **O que se passava:** o relatório do eGO traz o estado «Criada» (oportunidade acabada de promover de lead) e a tabela só aceita Ativa, Ganha e Perdida. O check recusava a linha e as notas dessa oportunidade caíam em cascata. Perdas medidas: 14, 37, 30 e 22 oportunidades por dia (27 a 30/10) e 93 e 63 notas nos dois últimos dias, cerca de metade das oportunidades novas.
- **Efeito visível:** as 7 leads criadas no piloto de 29/10 foram promovidas pela consultora no mesmo dia e nenhuma chegou ao Supabase. Também afeta a regra «oportunidade ativa: não cria lead nova» (a pessoa parece não ter oportunidade).
- **Correção:** «Criada» passa a «Ativa» no mapeamento do scraper (é uma oportunidade em aberto). O sync lê as últimas 48 h, por isso as de 28 a 30/10 recuperam-se no 1.º cron seguinte ao deploy; as anteriores precisam de uma corrida completa.
- **Como verificar:** depois do deploy, no resumo do cron das 03:37 UTC, `oportunidades_ignoradas` tem de ficar a 0 e as 7 oportunidades do piloto têm de existir no Supabase.
- **Relacionado:** #44, #26, #27. A API do eGO elimina o problema (`leadStage` 1/2/3 = Ativa/Ganha/Perdida).

### N2 — Escalada no 1.º turno fica sem ligação à conversa (o nudge incomoda quem espera chamada)
- **Tema:** Agentes / Matilde · **Urgência:** Alta · **Estado:** Entregue (corrigido no código; deploy a seguir) · **Com quem está:** Developer
- **O que se passava:** quando a pessoa pede «podem ligar-me?» como primeira resposta, a Matilde cria a tarefa `escalar`, mas a conversa só era gravada no fim do turno: a tarefa ficava com `conversa_id` vazio. O nudge procura as escaladas por `conversa_id`, não a viu e, no dia seguinte, perguntou «Ainda está interessado?» a quem já esperava a chamada. Também ficavam desligadas a deduplicação e a atualização da escalada com informação nova.
- **Correção:** a linha da conversa é criada antes das ferramentas (só em conversas novas, e não na voz).
- **Como verificar:** uma lead nova que peça uma chamada na 1.ª resposta gera uma tarefa `escalar` com `conversa_id` preenchido, e o nudge não lhe é enviado.

### N3 — A Matilde nega o preço à primeira pergunta
- **Tema:** Agentes / Matilde · **Urgência:** Média · **Estado:** Pendente · **Com quem está:** Miguel (decisão)
- **Caso:** uma lead perguntou «Qual o preço, por favor» e a resposta foi «Antes de lhe dar o preço, qual o montante que tenciona investir?». A pessoa insistiu três horas depois («o interesse depende do preço»). Noutra conversa, no mesmo dia, o preço foi dado logo.
- **Pergunta ao Miguel:** a especificação v2 manda qualificar antes de dar o preço, ou a Matilde deve dar o preço de imediato e qualificar a seguir? O que prefere para quem chega de um anúncio com o preço já visível?
- **Proposta:** dar sempre o preço do imóvel do anúncio e passar à qualificação na mesma resposta. Ligado ao alargamento do «interesse real» a pedidos de preço (#17).

### N4 — Saber se alguém falou com a lead antes de parar os follow-ups
- **Tema:** Agentes / Cascata multicanal · **Urgência:** Média · **Estado:** Pendente · **Com quem está:** Developer (desenho) e Miguel (pergunta)
- **Situação:** os follow-ups de 24 h e 72 h (n8n) enviam «Ainda está interessado?» a quem não respondeu, mesmo que a lead já esteja no eGO. Em 30/10, as 5 pessoas que receberam o follow-up da Matilde já tinham lead criada. Ter lead no eGO só prova que a consultora a recebeu, não que alguém falou com a pessoa; por isso não se deve parar o follow-up só por isso.
- **O que falta:** um sinal fiável de que um humano contactou a lead. `contactos.contacto_humano_em` já existe (migration 0047) mas **ninguém o escreve**, está sempre vazio. Os follow-ups também não leem `nao_contactar_em` nem `contacto_humano_em` (hoje não faz mal, mas deixa de proteger numa recusa sem resposta ou num contacto manual).
- **Proposta:** (1) ver no eGO o que fica registado quando a consultora fala com a pessoa (nota, tarefa, mudança de fase) nas oportunidades já promovidas; (2) o cron das leads do eGO marca `contacto_humano_em` quando houver esse sinal; (3) só então os follow-ups passam a respeitar `contacto_humano_em` e `nao_contactar_em`.
- **Pergunta ao Miguel:** que sinal as consultoras deixam no eGO quando falam com uma lead? Uma nota, uma tarefa concluída, mudar a fase? E devem os follow-ups da Matilde parar assim que há uma lead criada, ou só quando há contacto humano?
- **Relacionado:** #19 (`contactado_pelo_agente`); este seria o equivalente do lado humano. Também `limit=5` no follow-up diário da Matilde (travão da 1.ª corrida, a rever).

## Atualizações a pedidos existentes

### #17 e #47 — Quem respondeu e parou chega ao eGO (piloto feito)
- Regra construída (`LEAD_RESPONDEU_EGO`): 4 h depois da última mensagem, sem pedido de visita, escalada, recusa nem consultor, a lead vai para o eGO com «Disse:» e as últimas 3 mensagens. Exclui quem se despediu ou recusou numa das últimas 3 mensagens, e quem agradeceu com emoji.
- **Piloto de 29/10:** 7 leads de 10 candidatas (duas duvidosas e uma recusa disfarçada ficaram de fora). Foram criadas em 10 e 20 minutos, atribuídas à consultora do imóvel, e promovidas a oportunidade no mesmo dia.
- **Aberto a todas desde 30/10 12:00 (`LEAD_RESPONDEU_EGO=1`):** nessa mesma tarde entraram mais 4 leads de compra (as duas que pareciam duvidosas eram legítimas: uma voltou a pedir para comprar depois de ouvir que não havia arrendamento; outra pediu visita e esbarrou no preço). Verificadas no eGO: atribuídas à consultora do imóvel, com o resumo da conversa no OBS.
- **Resposta à pergunta (a) do #47:** na prática, as que respondem passam ao eGO e são tratadas. Fica por decidir o destino de recrutamento e angariação (pergunta (b)).

### #25 — Agente de voz
- Passa de Pendente para **Em curso**: a voz já atende como canal do motor (+351 233 060 000), com saudação por hora, estilo mais natural, desligar após silêncio e proteção contra repetição. Em ensaio: STT de números («trezentos e cinquenta mil»), latência de 3 a 5 s por turno, barge-in desligado.
- Pendente (reunião de 28/10): vozes diferentes por agente, sem ElevenLabs.

### #19 — Pergunta ainda sem resposta
- A base das 48 h é a entrega (`whatsapp_entregue_em`) ou o envio (`template_enviado_em`)? A entrega é a única que prova receção.

## Resultados desta análise que não precisam de pedido
- Crons de 29 e 30/10: todos correram à hora; 0 falhas de login ou timeout. WhatsApp: 7 templates enviados, todos entregues, 0 falhas.
- Conversas: 11 turnos da Matilde, 0 erros, latência mediana 5,5 s, cache 91 %.
- n8n (29 e 30/10): todos os fluxos correram sem erros, exceto «Faturas 2026 — Miguel Gmail», que falha todas as noites às 01:00 há pelo menos 14 dias porque a credencial «Gmail account miguel» precisa de ser reconectada. **Ação do Miguel:** reconectar a credencial no n8n, ou desligar o fluxo se já não o usa.
- Tarefas: 3 397 pendentes antigas que nenhum sync fecha (conhecido, #8). O contador «fechadas» do sync fica a 0 mas os números batem.
