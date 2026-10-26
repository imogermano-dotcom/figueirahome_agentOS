# Propostas aceites e fim de conversa no WhatsApp (resumo, 22–25/10)

## 1. Propostas aceites que não chegavam ao Supabase (pedido #34)

**Causa.** O sync das oportunidades (`scraper/oportunidades_completo.py`) lê o relatório «Editado em > últimas 48 h». Aceitar ou
recusar uma proposta não altera a data de edição da oportunidade, por isso a oportunidade nunca volta a ser lida e o
`estado_proposta` fica atrasado. Casos: VEN_22173 (corrigido à mão a 12/10), VEN_20521 e VEN_20311 (corrigidos a 25/10).
Não provado com um teste no eGO (aceitar uma proposta sem mexer em mais nada); o padrão das 3 oportunidades encaixa.

**Verificação (22/10, só leitura).** A API (`ListOpportunityByPage`) filtra por `proposalMinDate` e `proposalStatusIDList`. Códigos
deduzidos por correspondência com o Supabase (88 de 90 coincidiam): **1 Em avaliação, 3 Aceite, 4 Rejeitado**. Das 92 oportunidades
ativas com proposta, 2 estavam atrasadas.

**Correção.** `ego_api.estados_de_proposta()` (3 pedidos, uma página cada; levanta se vier página incompleta) e
`oportunidades_sync.reconciliar_propostas()`: corrige só o `estado_proposta` das linhas que o têm e divergem. As que a API conhece
e o Supabase não são só contadas (`por_ler`). Endpoint `POST /api/oportunidades/sync/propostas` (`X-Sync-Secret`), cron
`sync-propostas` às 04:17 UTC, registo em `agente_sync_log` (`egorealestate_propostas`), falha → email como os outros syncs.
Testes em `backend/tests/test_propostas_reconciliacao.py`.

**Limites.** Só oportunidades ativas (não arquivadas) e propostas desde 2020. Valor e data da proposta continuam a vir do relatório.
Oportunidades apagadas no eGO (VEN_22261, VEN_22277) continuam no Supabase como ativa/perdida: pedido #31, por fazer.

## 2. Fim de conversa no WhatsApp

**Problema (22/10).** Uma lead trocou ~40 mensagens de emojis e «tchau» com a Matilde e o modelo respondeu a todas. Em separado, o
nudge perguntou «Ainda está interessado?» a quem tinha agradecido, e a quem tinha dito «não estou interessada».

**Correção.** Em `engine._responder_sem_lock`, no WhatsApp: se a última mensagem é uma despedida da assistente (ou só um emoji) e a
mensagem da pessoa é só emojis, agradecimento ou saudação final, devolve `""` sem chamar o modelo; o webhook não envia respostas vazias.
O nudge salta agradecimentos e recusas curtas sem pergunta. Detetores públicos em `guards.py`. Testes em
`backend/tests/test_fim_de_conversa.py` (10) e `test_nudge.py`.

**Prompt da Matilde (22/10).** A KB dizia «Zona de atuação: concelho da Figueira da Foz» e a Matilde afirmou que o FH2584 (Porto) estava
«fora da nossa área». Linha corrigida e regra acrescentada em `agente_config` (`a1_vendedor`): nunca dizer que um imóvel da ficha está fora
da área. A fonte (`kb-a1-vendedor.md`, fora do repo) tem de receber a mesma correção.

## 3. A recusa fica gravada (pedido #49, 26/10, `c89deba`, migration `0053`)

**Problema (24/10).** A Bárbara (angariação) recebeu um nudge 2 h depois de a pessoa dizer «não estou interessada». O `encerrar_lead` só
escrevia em `leads` e os contactos de angariação e recrutamento vivem só em `contactos`: ficava `nova` e nada registava a recusa. Os follow-ups
de 24 h e 72 h do n8n já não escrevem a quem respondeu (`respondeu_em` vazio), por isso o nudge era o único envio automático em causa.

**Correção.** `contactos.nao_contactar_em` (coluna, não o `estado`: o estado é editável no painel e reescrito pelo n8n). `encerrar_lead`
grava-a mesmo sem linha em `leads`; um opt-out explícito («não me contactem», «deixem de me enviar», «stop») grava-a em código, no motor,
antes do modelo; o nudge dos 3 assistentes consulta-a (falha fechado). Só bloqueia envios proativos: se a pessoa escrever, responde-se.
A cascata e a reativação do pedido #21 ainda não existem e terão de ler a mesma marca. Testes em `test_nao_contactar.py` e `test_nudge.py`.

## 4. Inês só no concelho da Figueira da Foz (pedido #33, 25/10, `4c52023`)

O prompt não dizia que a agência só atua no concelho: a Inês registava qualquer zona (Sesimbra, Cantanhede, Sintra) e dava a candidatura como
entregue. Secção «ZONA DE ACTUAÇÃO» no `_PROMPT_A3`: zona de fora ou mista → explica, pergunta se interessa, **só escala depois de a pessoa
aceitar** (`encerrar_lead` se não). Ensaiado contra o modelo com 9 situações sintéticas (zonas de fora, mistas, fronteira com Pombal, dentro
do concelho): nenhuma escalada de fora. A lista de freguesias do prompt é nossa; o Miguel ainda não a confirmou.
