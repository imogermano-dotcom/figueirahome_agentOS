# Registo do Miguel para o developer: estado a 26/10/2026

O Miguel mantém um registo de pedidos (artefacto partilhado, fora da organização: o acesso direto aos dados está bloqueado e lemos o export em CSV de 25/10).
Este ficheiro é o nosso estado depois de verificar cada ponto contra o código, a base de dados e a API do eGO. Sem nomes de pessoas.
Verificados: todos, exceto os #2, #3, #4, #6, #7 (anteriores, ver fim) e o #25 (voz, parado por decisão).

| # | Pedido | Estado | O que falta |
|---|---|---|---|
| 1 | Pixel e API de Conversões na página de recrutamento | Parcial | O pixel está no site (repo do site, carrega depois dos cookies) e o evento `Lead` dispara no browser. API de Conversões não existe e o formulário não envia `event_id`. Falta o token do dataset (Miguel) e o OK. |
| 5 | Email ao cliente que recusa o WhatsApp | Com o Miguel | Recrutamento tratado pelo portal; compra e angariação não enviam email ao cliente. Nota preparada: o próprio fluxo n8n da recusa pode enviá-lo. Falta texto, se vale para compra, prazo, limite diário e RGPD. |
| 8 | Tarefas do eGO no Supabase | Pendente | Ligadas à oportunidade (100 %) e ao contacto (86 %), mas sem o id da tarefa no eGO e com ~3 300 «pendentes» a mais do que no eGO (5 482 contra 2 149). A API nova (`ListTaskByPage`) dá os ids. Falta o plano e a migration `ego_task_id`. Perguntas ao Miguel: fechar as antigas? O que é o estado 6? |
| 9 | Verificar se o cliente existe e mostrar resumo | Parcial | A verificação existe (oportunidade ativa, já na caixa, contacto antigo). Falta o resumo do cliente e os prazos (#30). |
| 10 | Canais de receção da Meta | Parcial | Formulário instantâneo feito; mensagens que não são texto passaram a ter resposta (26/10). Flow e clique-para-WhatsApp não tratados, sem uso visível. Pergunta ao Miguel. |
| 11 | Messenger e email como canais | Pendente | Não existem. Messenger seria um canal novo do motor (webhook e token da página); o email precisa de endereço de entrada. Sem sinal de procura. |
| 12 | Decidir canais «a definir» | Com o Miguel | Factos entregues: 20 submissões de formulários do site desde 01/07 (13 de compra ou visita) gravam em `contactos` sem aviso nem lead no eGO. Sugestão: comentários do Facebook só sinalizados. Placa: só o Miguel sabe. |
| 13 | Desfechos: engano, sem resposta, interesse real | Parcial | Engano e interesse real (compra) feitos. Recrutamento e angariação sem lead no eGO (#47). «Sem resposta» não marca estado e a cascata não existe. |
| 14 | Propor horário e agendar | Diferente da spec | Decisão de 20/09: os assistentes não propõem nem agendam (só a Inês oferece o link TidyCal). `decisoes.md` ainda diz o contrário. |
| 15 | Templates WhatsApp (22) | Com o Miguel | Em uso: T0, 24 h e 72 h de compra, angariação e recrutamento. Não existem os 9 utility de «não atendeu / sem visita / sem interação» nem os 4 marketing. Estado na Meta não visível daqui. |
| 16 | Reativação e cruzamento de imóveis | Pendente | Não existe. Bloqueio: opt-in (só 739 contactos com WhatsApp, 578 anteriores a 01/09 e pouco fiáveis). O opt-out já está pronto. |
| 17 | Lead no eGO só com interesse real | Parcial | Compra feita (interesse real, recusa, 2 h). Angariação e recrutamento não criam (#47). |
| 18 | Estados `nao_contactado` e `nao_atende` | Pendente | Não existem; a `classify-lead` é do Miguel (fora do repo). Proposta: cron nosso com coluna nova e alerta ao diretor. |
| 19 | `contactado_pelo_agente`, `contactado_em`, conversa completa | Parcial | Conversa guardada (`agente_conversas`) mas ligada só pelo telefone. Os campos equivalem a `whatsapp_entregue_em`. Proposta: `contacto_id` na conversa e vista. |
| 20 | Emails de interesse real | Parcial | Chegam ao diretor e, na compra, à consultora. Falta o resumo da conversa no aviso de qualificada e o bloco de dados do imóvel na angariação. |
| 21 | Cascata multicanal | Pendente | Não existe (nem email ao cliente nem SMS). Falta consentimento (264 leads Meta com email, 17 com `rgpd_email`), texto (#5) e SMS. |
| 22 | Cascata esgotada → lead no eGO | Parcial | Equivalente para compra: sem resposta em 2 h cria a lead. Falta o histórico das tentativas no email e a reativação. |
| 23 | Questões da especificação v2 | Com o Miguel | Posição técnica entregue: telefone encontra, ID liga; recrutamento fora do eGO; falta a secção da Maria; intervalos depois da cascata. |
| 24 | Link Portal ↔ eGO nas leads de comprador | Bloqueado | Falta o formato do endereço de um contacto/conversa no Portal. O Portal já pode montar `…/Leads/<ego_lead_id>` (`contactos.ego_lead_id`). |
| 25 | Agente de voz | Parado | Decisão de 26/10: não avançar para a voz já. |
| 26 | Modelo de tabelas com a oportunidade como eixo | Parcial | Liga por referência (VEN_22232 devolve contacto, imóvel, 6 notas e 4 tarefas). Faltam `atribuicoes`, `imovel_id`, `oportunidade_id`, `proprietario_id`. |
| 27 | Chaves externas `ego_person_id` e `ego_lead_id` | Parcial | Só dentro dos URLs: 12 676 contactos e 21 670 oportunidades (83 %), sem repetidos. Falta criar as colunas únicas e preenchê-las. |
| 28 | Chave única das notas | Entregue | Chave `oportunidade_ref` + texto + data/hora (38 linhas repetidas, todas com data nula). Limite: 53 % das notas só trazem o dia. |
| 29 | Tarefas sem oportunidade para revisão | Parcial | Não entram (correto), mas não há lista de revisão. Pela API: 1 426 sem oportunidade, só 25 pendentes. |
| 30 | Regra dos 90 dias entre consultores | Pendente | Não implementada. Depende de #8, #26 e da normalização dos autores («AS» e «Alexandra Santos»). Pergunta: em que ecrã o consultor B vê o aviso. |
| 31 | Oportunidade apagada no eGO | Entregue | Marcadas VEN_22261 e VEN_22277 (`oportunidades.apagada_no_ego`); cron das 04:17. Portal e `dashboard_metricas` ainda não filtram. |
| 33 | Inês só no concelho da Figueira da Foz | Entregue | Lista de freguesias do prompt por confirmar. |
| 34 | Propostas aceites não chegam | Entregue | Reconciliação diária pela API; falta ver uma proposta de teste no eGO. |
| 35 | Marcação direta via Calendly | Redundante com o #43 | O Miguel deu o TidyCal. |
| 36 | Scraping do CasaFari | Bloqueado | Falta o objetivo; ver termos da plataforma e se há API. |
| 37–40 | Plataforma de referenciação | Não iniciado | Fase nova: quem indica, RGPD, verificação, reunião, voucher (#40 com o Miguel). |
| 41 | Comissões dos imóveis | Bloqueado | O eGO confirmou que a API ainda não as expõe; scraper do relatório à espera de decisão (venda ou arrendamento). |
| 42 | Lead da FH2583 sem imóvel nem consultora | Entregue | A ref sai do nome do anúncio; não se cria sem consultora (decisão consciente). |
| 43 | Link de marcação para candidatos qualificados | Entregue | Vai junto com a frase do responsável; confirmar. |
| 44 | Sync de oportunidades parado | Entregue | Login por escritório e alerta por email. |
| 45 | Imóveis só publicados | Pendente | 1.ª passagem real (705 linhas) à espera do Miguel; cron `sync-imoveis-todos` desligado. |
| 46 | Botão «Falar no WhatsApp» nos emails | Bloqueado | Falta a função de consulta por código (lado do Supabase). |
| 47 | Leads que respondem não chegam ao eGO | Pendente | Interesse real já passa (25/10); perguntas: as 8 que responderam sem sinal, e o destino de recrutamento e angariação. |
| 48 | Escalada sem lead no eGO | Entregue | Lead criada (26/10); ver se a pessoa antiga do eGO é reutilizada quando a consultora a promover. |
| 49 | Insistência depois de uma recusa | Entregue | `nao_contactar_em`; a cascata e a reativação (não existem) terão de a ler. |
| 50 | Link do imóvel em pré-venda | Bloqueado | O que define «pré-venda»: nada na ficha o distingue. O link só apareceu em 2 de 11 conversas. |

Não aparecem acima: o #32 (corrigido desde 13/10) e os #2, #3, #4, #6, #7 (relações e `contacto_id`, anteriores a esta revisão; cobertos pelo #26–#27).

**Cadeia de dependências (ordem sugerida)**
1. #8 (`ego_task_id`, fechar pendentes antigas) e #27 (`ego_person_id`, `ego_lead_id`) — base para tudo.
2. #26 (`atribuicoes`) — depende dos ids.
3. #9 e #30 (resumo e regra dos 90 dias) — dependem de #8 e #26.
4. #21, #22, #16 (cascata e reativação) — dependem de #5 (email ao cliente), #15 (templates) e do consentimento.
