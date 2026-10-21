# Satisfação pós-venda — A5 "Sofia" — plano

2026-10-21. Pedido do Miguel: inquérito de satisfação a compradores e vendedores depois da
escritura e a vendedores que rescindiram o CMI; no fim, se correu bem, pedir avaliação no Google e
testemunho em vídeo (ou, não dando, em texto). Ao vendedor, um resumo da venda ao estilo do
relatório do vendedor (tempo até proposta aceite e até escritura, valor face ao preço inicial e ao
estudo de mercado).

## Decisões (do Miguel, 20–21/10)

| Tema | Decisão |
|---|---|
| Canal | WhatsApp, guião fixo pela assistente (não formulário), respostas estruturadas por tool |
| Quando | escritura + 7 dias, 10h de Lisboa; rescisão detectada + 2 dias |
| Aprovação | envio automático; o portal permite cancelar/reagendar/enviar já |
| Google | pedido a **todos** os inquéritos de escritura com nota ≥ 7 (não só 9–10: *review gating* viola a política do Google); nota ≤ 6 vai primeiro a humano |
| Testemunho | só a 9–10; vídeo por **link** (página `/testemunho?t=` do portal), texto na conversa ou na página; autorização de publicação explícita |
| Nome | Sofia |

## O que já está fora deste repo (portal, `figueira-home-portal`, aplicado 20–21/10)

- `public.satisfacao_inqueritos` / `satisfacao_config` / `satisfacao_rescisoes_vistas`, migrações
  `20261020_10_satisfacao.sql`, `20261021_01_satisfacao_resumo_venda.sql`, `20261021_02_…`.
- `fn_satisf_gerar()` (pg_cron 06:20 UTC) cria a fila; `ligado=false` até ao go-live.
- RPCs `service_role` usadas aqui: `fn_satisf_para_enviar`, `fn_satisf_marcar_envio`,
  `fn_satisf_aberto(telefone)`, `fn_satisf_respondeu`, `fn_satisf_registar(id, p)` (**decide o passo
  seguinte**: `escalar`, `google_link`, `testemunho_link`, `resumo_link`), `fn_satisf_marcar_escalado`,
  `fn_satisf_testemunho`.
- `agente_config` já tem a linha `a5_satisfacao`.
- Páginas `/testemunho?t=` (resumo + Google + testemunho) e `/avaliar?t=` (regista o clique).

## Este repo

1. **`assistants.py`** — `A5 = "a5_satisfacao"`, `NOME_A5 = "Sofia"`, prompt com o guião;
   tools `registar_satisfacao`, `registar_testemunho`. **Sem `escalar_para_humano`**: esta cria
   cliente/lead (`find_or_create_cliente`), o que não faz sentido para quem já comprou/vendeu.
2. **`tools.py`** — `registar_satisfacao` grava por `fn_satisf_registar` e, quando o servidor
   devolve `escalar`, cria a tarefa `escalar` (motivo `satisfação — nota baixa` /
   `satisfação — rescisão`) e o email, uma vez (`fn_satisf_marcar_escalado`). Os links vêm do
   servidor, nunca do modelo. `registar_testemunho` grava texto + autorização.
3. **`guards.agente_de_lead`** — inquérito aberto (`fn_satisf_aberto`: enviado há ≤ 14 dias, não
   concluído há mais de 24 h) **ganha a tudo o resto**: quem acabou de comprar pode ter uma lead
   antiga aberta, e a resposta "9" iria para a Matilde.
4. **`engine._contexto_inicial`** — `A5` → `_contexto_satisfacao`: tipo, primeiro nome, consultor,
   o que já respondeu; injecta o template no 1.º turno de thread nova; `fn_satisf_respondeu`.
5. **`meta_api.send_template`** + **`satisfacao.enviar_inqueritos`** + `POST /api/satisfacao/enviar`
   (`X-Automacao-Secret`): lê a fila, só telemóveis portugueses (9…), manda o template com `{{1}}` =
   primeiro nome, semeia `agente_conversas` com o texto (agente `a5_satisfacao`) e marca o envio.
6. **Cron** `satisfacao-enviar` (`7 * * * *`) — a janela 9h–20h de Lisboa está na RPC.
7. Testes: `tests/test_satisfacao.py`.

## Go-live (utilizador)

1. Criar e aprovar na Meta os templates `satisfacao_comprador`, `satisfacao_vendedor`,
   `satisfacao_rescisao` (pt_PT, sem botões — o webhook ignora mensagens que não são texto) com o
   texto de `satisfacao_config.templates` (visível no portal, aba ⭐ Satisfação).
2. `flyctl deploy` do backend e do `crons` (registar `satisfacao-enviar`).
3. No portal: link de avaliação do Google e "Envio automático ligado".

## Riscos

- O texto semeado tem de ser igual ao aprovado (o modelo lê-o como dito por si).
- `fn_tel9` guarda 9 dígitos: números estrangeiros ficam em `erro` ("não é telemóvel português").
- Resposta só com emoji/áudio: o webhook ignora não-texto; a pessoa fica `enviado` → `sem_resposta`.
