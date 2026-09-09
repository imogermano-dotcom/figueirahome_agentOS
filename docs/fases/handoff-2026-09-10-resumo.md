# Handoff — 2026-09-10

> Sessão mista: continuação (parada) da auditoria de 06/09, investigação ao
> vivo de um bug real de sincronização com o eGO, e uma fase nova completa
> — Matilde, Frente A (nudge dentro da janela de 24h) — planeada,
> implementada, testada em produção com número real, e deployada.

## O que foi implementado

### Matilde — Frente A: nudge dentro da janela de 24h

Quando a Matilde fica sem resposta a meio de uma conversa activa no
WhatsApp (6h a 20h de silêncio desde a sua última mensagem — janela
desenhada para nunca chegar perto do limite de 24h da mensagem livre da
Cloud API), o backend manda agora um lembrete curto com saída explícita:
*"Ainda está interessado? Fico a postos para continuar, ou diga-me só que
não para eu não voltar a incomodar."*

Exclui:
- **Despedidas** — detectadas por marcadores na própria mensagem da
  Matilde (👋, "cuide-se", "boa continuação", "muita força", "boa sorte").
  Voz nossa, controlada, mais fiável que adivinhar o tom de quem escreve.
- **Leads fechadas ou já entregues a um humano** — só quando há mesmo uma
  lead com `estado` em `ESTADOS_FECHADOS` ou `contacto_humano_em`
  preenchido. **Não** quando nunca existiu nenhuma lead — corrigido depois
  do teste ao vivo (ver "Bug encontrado e corrigido" abaixo).
- **Threads sem canal WhatsApp** (site/web) — já ficam fora só pelo filtro
  `canal='whatsapp'`, sem mecanismo extra.

Um nudge por conversa (carimbo `nudge_em`), nunca mais.

**Testado ao vivo**: janela encurtada temporariamente (6h→3min) para
validar sem esperar horas, com o número pessoal do utilizador — mensagem
enviada e recebida com sucesso, janela revertida para os valores
definitivos depois.

### Bug encontrado e corrigido (pós-teste ao vivo)

A guarda inicial usava `guards.lead_aberta(telefone)`, que devolve `None`
tanto para "nunca houve lead" como para "lead fechada" — **indistinguíveis
para quem chama**. Isso excluía precisamente o caso de maior valor que
motivou esta fase: uma proposta de 110 000€ ao FH2571 em que a Matilde
pediu nome/telefone e nunca os recolheu com sucesso — sem `cliente_id` nem
`leads`, ficaria sempre de fora do nudge.

Corrigido com `nudge._pode_enviar(telefone)`: consulta a `leads` mais
recente **sem filtrar por estado aberto**, e só recusa quando há mesmo
`ESTADOS_FECHADOS` ou `contacto_humano_em`. Sem lead nenhuma → elegível.

### Achado eGO — angariador congelado por referência duplicada

Fora do âmbito da Matilde: o utilizador reportou que `FH2483_A` mostrava
"Ana Daniel" no Supabase mas "Sandra Silva" no eGO. Investigação ao vivo
revelou:

- A Web API do eGO devolvia `PropertyAgents: []` para este imóvel — não é
  atraso de sync (cron corria sem erros, 58 imóveis actualizados a cada
  ciclo), é o próprio eGO a não reportar agente para este registo.
- O eGO tinha **3 registos internos diferentes** para a mesma referência
  "FH2483_A": o publicado na Web API (`ego_id` 22836083, sem agente) e mais
  dois só visíveis no backoffice (`26029609` Disponível/Sandra Silva,
  `26927326` Por validar/Miguel Germano) — mesma classe de bug já
  conhecida do `FH2460 4D`, agora confirmada também aqui.
- O utilizador corrigiu a atribuição no eGO (Sandra Silva no registo
  publicado); confirmado que a Web API já a reflecte e o Supabase já
  sincronizou. **O duplicado em si continua por apagar** — Miguel ficou
  disso, ainda não confirmado feito a 09/09.

**Achado colateral, corrige memória de 18/08**: o "bloqueio de carteira" da
conta CRM (`crm-sem-acesso-a-carteira-da-alexandra`) não era falta de
permissão — era **espaço de ID errado**. `imoveis.ego_id` (da Web API) não
é o mesmo ID que o backoffice usa em `/egocore/realestate/{id}`; passar o
nosso `ego_id` lá devolve sempre "não pode consultar", indistinguível de
bloqueio real. Confirmado em 5/5 amostras, mesmo replicando sessão de
browser real (cookies, User-Agent). O backoffice tem o seu próprio ID,
obtido pela pesquisa por referência (`find_by_ref`) — que já não tem este
bloqueio. `validar_disponibilidade_crm` (Caso 3) já usava esse fallback
correctamente; só é ineficiente (tenta sempre `fetch_detail(ego_id)`
primeiro, sabendo agora que falha sempre) — não corrigido, valor baixo.

## Ficheiros principais modificados

| Ficheiro | O quê |
|---|---|
| `backend/app/agents/broker/nudge.py` | Novo. `_candidatos()`, `_pode_enviar()`, `_e_despedida()`, `enviar_nudges()` |
| `backend/app/api/nudge.py` | Novo. `POST /api/matilde/nudge`, `require_automacao_access` |
| `backend/app/main.py` | Router do nudge registado |
| `backend/tests/test_nudge.py` | Novo. 7 testes |
| `supabase/migrations/0035_agente_conversas_nudge.sql` | Coluna `agente_conversas.nudge_em` |
| `.github/workflows/nudge-matilde.yml` | Cron de hora a hora |
| `docs/fases/matilde-followup-plano.md` / `-resumo.md` | Plano e resumo da fase |
| `CLAUDE.md` | Estado actual substituído, `Próximos passos` e `Bugs conhecidos` actualizados |

`backend/app/agents/broker/guards.py` foi alterado e depois revertido no
mesmo dia (tentativa de reaproveitar `lead_aberta`, substituída por
`nudge._pode_enviar`) — sem diferença face ao commit anterior.

## Decisões arquitecturais (desta fase)

- **Janela de disparo é da Cloud API, não nossa**: 6h–20h desde a última
  mensagem da Matilde, não a TTL de 48h da conversa (`conversation.py`) —
  a restrição real é a mensagem livre do WhatsApp expirar às 24h.
- **Reaproveitar `X-Automacao-Secret`** em vez de criar um terceiro segredo
  — o cron do GitHub Actions é mais uma automação, mesma fronteira que
  Make/n8n.
- **Despedida detectada na mensagem da Matilde, não da pessoa** — voz
  controlada por nós, mais previsível que adivinhar o tom de quem escreve.
- **Sem lead nenhuma ≠ lead fechada** — só recusar com estado fechado ou
  `contacto_humano_em` explícitos; ausência de registo não é motivo para
  excluir (ver "Bug encontrado e corrigido").
- **`flyctl deploy` corre de dentro de `backend/`** — Dockerfile e
  `fly.toml` vivem lá, não na raiz do repo (confirmado ao vivo, primeira
  tentativa falhou por isso).

## Bugs conhecidos (novos ou tocados nesta fase)

- **Resposta "não" ao nudge não confirmada a chamar `encerrar_lead`** — a
  lógica de desfecho já existe no motor, mas o caminho a partir desta
  mensagem em concreto não foi testado ao vivo.
- **Referência duplicada no eGO** (`FH2483_A`, 3 registos) — não é bug
  nosso, é dado sujo do eGO; mesma classe do `FH2460 4D` já conhecido.
  Ainda por limpar (Miguel).
- **`validar_disponibilidade_crm` (Caso 3) ineficiente** — tenta sempre
  `fetch_detail(ego_id)` sabendo que falha por espaço de ID errado, antes
  de cair no `find_by_ref` que resolve. Não corrigido (valor baixo, 1
  pedido HTTP extra por imóvel divergente).
- Restam os da auditoria de 06/09 e os anteriores — ver CLAUDE.md.

## Próximos passos (desta fase)

0. Confirmar se o Miguel apagou o duplicado `FH2483_A` (`ego_id`
   `26927326`) — ainda lá a 09/09.
1. Confirmar o primeiro envio real do nudge da Matilde em produção
   (`agente_sync_log`, `tipo='nudge_matilde'`) — só testado com 1 número
   até agora.
2. Se o duplicado for confirmado como padrão recorrente (não só este
   imóvel), considerar uma rotina de detecção — **não desenhar já**: só um
   caso confirmado até agora.

Restantes próximos passos (auditoria, n8n, etc.) — ver CLAUDE.md, secção
"Próximos passos".
