# Registo do Miguel para o developer: estado a 26/10/2026

O Miguel mantém um registo de pedidos (artefacto partilhado, fora da organização: o acesso direto aos dados está bloqueado e lemos o export em CSV de 25/10).
Este ficheiro é o nosso estado depois de verificar cada ponto contra o código, a base de dados e a API do eGO. Sem nomes de pessoas.

| # | Pedido | Estado | O que falta |
|---|---|---|---|
| 10 | Canais de receção da Meta | Parcial | Formulário instantâneo feito; mensagens que não são texto passaram a ter resposta (26/10). Flow e clique-para-WhatsApp não tratados, sem uso visível. Pergunta ao Miguel. |
| 24 | Link Portal ↔ eGO nas leads de comprador | Bloqueado | Falta o formato do endereço de um contacto/conversa no Portal. O Portal já pode montar `…/Leads/<ego_lead_id>` (`contactos.ego_lead_id`). |
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

Os pontos 1–9 e 11–23 são da especificação dos agentes e da base de dados (contacto_id, tarefas, canais, cascata, estados); vários estão feitos ou em curso e não foram
revistos um a um aqui. A cascata multicanal (#21, #22) e a reativação de leads antigas (#16) não existem.
