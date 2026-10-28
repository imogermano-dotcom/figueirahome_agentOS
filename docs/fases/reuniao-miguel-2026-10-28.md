# Reunião com o Miguel — 28/10/2026

Fonte: resumo automático do Zoom (tem erros de transcrição: «Eagle» e «Igor» = eGO, «Superbase» = Supabase). Este texto
separa o que foi decidido do que ficou em aberto e liga cada ponto ao que já existe no projeto. O resumo original não
entra no repo (público).

## Decisões

| # | Decisão | Estado no projeto |
|---|---|---|
| 1 | Avançar com a API do eGO para substituir o scraper (notas, tarefas, visitas, contactos, imóveis). Só faltam faturação e comissões. | Plano e apresentação feitos (`ego-api-substituir-scrapers-plano.md`). Nada implementado. As comissões continuam sem fonte na API (pedido #41). |
| 2 | Recontacto de quem não responde: **uma só tentativa, 2 h depois**; sem resposta, cria-se a lead no eGO. | Já existe para o comprador Meta (cron `leads-compra-para-ego`, 9h–20h, e `LEAD_RESPONDEU_EGO`, por ligar). Falta confirmar que o aviso é único e o que acontece a recrutamento e angariação (pedido #47). |
| 3 | Quando a lead é criada no portal/eGO, acrescentar o **resumo da conversa** do agente (contexto vem do Supabase), para a consultora ver clientes repetidos. | Já vai «Disse:» + últimas 3 mensagens no OBS das leads criadas por interesse real. Falta definir o formato para todos os casos. |
| 4 | Sincronização nos dois sentidos entre Supabase e eGO (notas e dados de oportunidade), para faturação, comissões e relatórios. | Depende do ponto 1. Escritas no eGO só com ordem expressa. |
| 5 | Voz: reduzir a latência, **sem ElevenLabs** (custo), e testar **vozes diferentes por agente**. | Em curso (voz como canal do motor, 28/10). A voz por agente é nova; hoje há uma só. |
| 6 | Proteção contra **prompt injection** nos canais de texto (WhatsApp e outros). | Por fazer. Falta um ensaio de ataque e as regras em `guards.py`, não no prompt. |
| 7 | Imóveis fora do Supabase (≈700) entram com tag própria, para cruzar com os clientes interessados. | É a 1.ª passagem do pedido #45 (`disponivel_na_api=false`, nunca publica). Falta autorizar a passagem real e a tag. |
| 8 | Landing page de recrutamento: analisar Google Analytics e Search Console (pontos de fuga, links antigos). | Por fazer; o Miguel estima cerca de um mês para o Search Console limpar. |

## Ideias novas (sem decisão de construir)

- **Referenciação de clientes**: voucher a quem indique alguém que assine contrato. O Miguel desenha o fluxo (regras de
  validação, interface, risco de rescisões fraudulentas, contratos exclusivos). Um agente intermediário qualifica antes de
  passar ao consultor. Fica à espera dessa proposta.
- **Newsletter** no site com notícias locais, automática. Fica à espera das fontes que o Miguel envia.
- **Base de conhecimento a responder a dúvidas legais no site**: só discutida. Atenção ao risco de aconselhamento jurídico.
- **Campanha na Meta** para captar mais leads (ligada ao token do Data Set).
- **Chat com quatro participantes** entre agentes: a verificar, sem desenho.
- Preocupação do Miguel com o **consumo de tokens da API**: acessos de dados a otimizar quando se implementar o ponto 1.
- **Limpar as tarefas** sem relevância no portal dos agentes (há 3 397 pendentes legadas que nenhum sync fecha).

## Ações

**João**
1. Implementar a API do eGO em substituição do scraper (por fases; ver plano).
2. Verificar o recontacto único às 2 h e o resumo da conversa na lead criada (pontos 2 e 3).
3. Voz: latência e vozes diferentes por agente, sem ElevenLabs.
4. Prompt injection nos canais de texto.
5. Sincronização Supabase ↔ eGO.
6. Analisar Analytics e Search Console da landing de recrutamento.

**Miguel**
1. Enviar as fontes de notícias para a newsletter.
2. Desenhar e enviar o fluxo da referenciação (voucher por contrato assinado).
3. Resolver o token do Data Set com a Meta; se não houver solução em 15 dias (até ≈12/11), refazer o processo.
4. Configurar os alertas do artefacto para ser avisado dos comentários do João.

## Pendentes do registo de 26/10 que esta reunião mexe

- **#45** imóveis de todos os estados: a passagem real passa a ter motivo (≈700 linhas). Falta a autorização expressa.
- **#41** comissões: continua sem fonte na API; bloqueia a faturação.
- **#47** leads que respondem e destino de recrutamento/angariação: ligado ao ponto 2.

## Fora do âmbito

O resumo automático mistura uma conversa sobre o valor patrimonial de uma garagem, a agenda de sábado e o Zoom/AI Act.
Não faz parte do projeto e não foi tratada aqui.

## Para confirmar com o Miguel

- «Uma só tentativa às 2 h» vale para os três assistentes ou só para a compra?
- O formato do resumo da conversa na lead: texto livre no OBS ou campos?
- O que é o «portal do Pinheirinho» referido na transcrição (o nome é ambíguo no resumo).
