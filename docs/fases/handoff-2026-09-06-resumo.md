# Handoff — 2026-09-06

> Sessão de leitura, não de código. O utilizador entregou o documento
> "Leads de Campanha — Fluxo e Contexto" (01/09, não técnico) e pediu, por
> esta ordem: análise, auditoria do código contra o documento, relatório em
> HTML, planos de acção. **Zero alterações ao código, zero migrations, zero
> deploys.** Produção continua em `4a91a00` (handoff de 05/09).

## O que foi implementado

Nada em código. Dois entregáveis de documentação:

### 1. Análise do documento

Documento de enquadramento com 10 secções: agente fala primeiro, lead entra
no eGO com contexto, 4 desfechos, dois limites (eGO só se escreve 1×; a
mesma pessoa em 5 sítios), cartão de 500 chars, regra dos 90 dias, carimbo
anti-contacto-duplo, secção 9 = redesenho da BD com `contacto` ao centro.
Bem fundamentado; o diagnóstico da duplicação (nome+data como chave) está
certo. Contradições com o repo identificadas e registadas no relatório.

### 2. Auditoria + relatório + planos de acção

`docs/fases/auditoria-leads-campanha-2026-09-06.html` — standalone, abre no
browser. Também publicado como artefacto Claude (link na sessão). Estrutura:

- **Matriz documento vs. código**, secção a secção, com estado
  (Feito / Parcial / Em falta / Bloqueado / Divergente).
- **12 achados a alterar** (A1–A12), por gravidade, com `ficheiro:linha`.
- **13 a implementar** (I1–I13): 9 sem dependência externa, 4 presos.
- **6 melhorias**, **8 recomendações**, tabela **a decidir** (quem
  desbloqueia o quê).
- **7 planos de acção P0–P6**, cada um com objectivo, âmbito, fora,
  pré-requisitos, passos, verificação, riscos, esforço.

Auditado: `backend/app` (engine, guards, tools, leads, leads_meta,
notificacoes, webhook WhatsApp, dashboard), `frontend/src/pages`
(Leads, Clientes), `scraper/` (upsert e mapping de `contactos`),
`supabase/migrations`, `docs/n8n/*.json`. **Fora**: portal do Miguel (não
está no repo), Make, pipeline `xlsx_*`.

## Achados que importam (resumo — detalhe no HTML)

| # | Grav. | Onde | O quê |
|---|---|---|---|
| A9 | Crítico | `webhook.py:31`, `main.py` | Recibos `delivered` só em `logger.info` com raiz em WARNING → invisíveis. n8n marca `template_enviado_em` pelo `200 accepted`. É por isto que ninguém sabe quem são os 155 sem mensagem |
| A5 | Crítico | `guards.py:134`, `03.json` | Email ao corretor só com MQL completo. Desfecho 1 (conversou sem fechar MQL) e 2 (`sem_resposta`) não avisam ninguém. Assunto varia, sem thread; sem "o que disse", sem histórico, sem botão |
| A10 | Alto | `mapping_todas_colunas.py:300-306` | **Scraper escreve `contactos.criado_em := ego_atualizado_em`.** PK real é `(nome, criado_em)`. Causa mecânica plausível dos 8.855 duplicados "só na data" do doc 5.2 — o item 1 da secção 10 do doc é metade nosso. Confirmar com query (R2) |
| A11 | Alto | `mapping:112` | `telemovel` do eGO sem normalização → telefone acha 54/281, email 232 |
| A3 | Alto | `guards.py:379` | `_procurar_cliente` sequencial `limit(1)`: telefone→A, email→B → fica A, ambiguidade invisível (17 leads) |
| A4 | Alto | `guards.py:477` | `find_or_create_cliente` faz `update(dados)` → 2.º telefone/email **apaga** o 1.º. Doc 5.9.1: guardar ao lado |
| A1 | Alto | `tools.py:915` | `_consultar_leads` do broker lê `agente_leads` (morta desde 18/08) com estados antigos |
| A6 | Médio | `0032` | `contacto_humano_em` por lead, não por pessoa |
| A8 | Médio | `guards.py:199` | `lead_aberta` só por telefone; lead só com email nunca entra na A1 |
| A7 | Baixo | `03.json:26`, `conversation.py:10` | 48h no código vs 24h no doc |

**Já fechado, que o doc dá como aberto**: bug da Filipa Pedro (campos MQL
em branco) — `_extrair_mql_do_resumo` desde 31/08 (`8e72c4c`), um dia
depois do caso; as 3 leads citadas ficaram para trás (backfill em P0).
Carimbo `contacto_humano_em` já trava 01/02/03. Desfechos engano /
sem_interesse já fecham.

**Bloqueado pela chave de integração do eGO**: secção 3 (criar lead no
eGO) e 6 (cartão 500 chars). `egorealestate.py` só GET; backoffice é
scraping. O doc assume API de criar lead/contacto que não existe.

## Planos de acção (ordem R1)

| Plano | Cobre | Depende de | Esforço |
|---|---|---|---|
| P0 Higiene imediata | docx no `.gitignore`, backfill 3 leads, apagar `agente_leads`, leads de teste, vocabulário `origem` | — | ½ dia |
| P1 Saber quem recebeu | `template_entregue_em` + `entrega_erro` escritos pelo webhook, `logging.basicConfig`, tempo de resposta no dashboard | — | 1 dia |
| P2 Uma pessoa por lead à entrada | trigger BEFORE INSERT em `leads` (procura `agente_clientes` por tel+email, marca ambígua), não sobrescrever contactos (`outros_contactos`), `lead_aberta` por email, carimbo propagado por pessoa | decisão trigger vs endpoint (recomendado: trigger) | 3 dias |
| P3 Avisar nos 4 desfechos | `avisar_consultor()` com assunto fixo por lead, `aviso_em`, endpoint para o `03`, botão "já falei" HMAC, `03` a 24h | `AUTOMACAO_SECRET` em produção, P2 | 3 dias |
| P4 Identidade dos contactos | query R2, colunas GENERATED `telemovel_norm`/`email_norm` em `contactos`, `criado_em` no scraper | aval do Miguel | 2 dias |
| P5 Histórico e cartão | `historico_fh(tel, email)` sobre `oportunidades`/`notas`/`visitas`, filtro de notas automáticas, `cartao_ego()` puro, A1 corrigido | P4, P3 | 3 dias |
| P6 Tabela de pessoas | secção 9 do doc | P2, P4, chave do portal, dono das fusões, RGPD, decisão do cliente | semanas — só enquadramento |

Sequência: P0 e P1 já; P2 ∥ P4; P3 depois de P2; P5 depois de P4; P6 só se
o cliente decidir. Cada plano, ao arrancar, ganha `docs/fases/<nome>-plano.md`.

## Ficheiros principais modificados

- `docs/fases/auditoria-leads-campanha-2026-09-06.html` — **novo**, o
  entregável.
- `docs/fases/handoff-2026-09-06-resumo.md` — este.
- `CLAUDE.md` — secção de estado substituída.
- **Untracked na raiz**: `Leads de Campanha - Fluxo e Contexto.docx`. Tem
  nomes reais de clientes e consultoras; o repo é público. **Não comitar** —
  P0 põe-no no `.gitignore`.
- Código, testes, migrations: **intocados**. Suite continua em 237.

## Decisões arquitecturais

Nenhuma tomada — só recomendadas, para o utilizador decidir:

- **Trigger na base em vez de endpoint** para ligar a lead à pessoa à
  entrada (P2): apanha as três portas (Make, site, assistente) sem depender
  do `AUTOMACAO_SECRET`; custa replicar `normalizar_telefone` em SQL, com
  teste que compara as duas. Mesmo padrão do `tgr_normaliza_aceita_whatsapp`.
- **Colunas GENERATED em `contactos`** para normalizar telefone/email
  (P4): aditivo, apanha as duas portas, não toca no que o portal do Miguel
  lê. Precisa do aval dele.
- **Não esconder contexto pela regra dos 90 dias** (R4): dispara em 1 lead
  em 282; aviso informativo chega (o próprio doc o degrada em 5.9.2).
- **Não migrar `mensagens` jsonb para linhas** (R5): a decisão de Agosto
  de rejeitar `ai_messages` continua válida até haver pergunta que o jsonb
  não responda.
- **Email pelo backend, nunca pelo n8n** (P3): o `03` chama um endpoint;
  mandar Resend do n8n duplicaria o template fora do repo.

## Bugs conhecidos — mudanças

Novos, identificados pela auditoria (nenhum corrigido): A1, A3, A4, A8,
A9, A10, A11 acima. Os anteriores (atraso de 12h do `01`, falta de
`logging.basicConfig` — agora é o A9 —, `agente_leads` morta — agora
agrava o A1 —, dedup sob carga, agente de voz) inalterados.

## Próximos passos

1. **Decidir por onde começar**: P0 e P1 não precisam de decisão nenhuma.
   Plano em `docs/fases/<nome>-plano.md` antes de código (regra 2).
2. **Query R2** antes de qualquer conversa sobre consolidar `contactos`:
   contar pares nome-igual em que um tem `ego_link` e o outro não.
3. **Perguntar ao Miguel**, por esta ordem: chave do portal (desbloqueia a
   `0022`), API de escrita do eGO + limite do cartão (desbloqueia I10),
   quem alimenta a "porta 2" de `contactos`, aval às colunas GENERATED.
4. Os anteriores mantêm-se: widget do site, importar `02`/`03`, reenviar
   as 45 até **23/09** — de preferência **depois de P1**, para haver prova
   de entrega.
