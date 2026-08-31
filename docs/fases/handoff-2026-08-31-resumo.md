# Handoff — 2026-08-31

> Sessão de auditoria ao vivo: análise da última conversa real da Matilde
> (Filipa Pedro / FH2581), quatro bugs reais encontrados e corrigidos, troca
> de fornecedor de notificações. Cinco commits, cinco deploys (`v57`→`v62`).
> Continuação directa do handoff de 30/08 (`handoff-2026-08-30-resumo.md`).

## O que foi implementado

### 1. `pesquisar_imoveis` mostra estado/features em vez de fingir que batem (`1f2c739`)

Analisada a última conversa real do A1 (Filipa Pedro, lead real — **não** é
a `teste-manual-001` de ontem, apesar de partilhar a ref FH2581; confirmar
sempre por `meta_lead_id`/nome, nunca só pela ref). A cliente pediu moradia
"recente ou renovada" com "espaço exterior"; a Matilde ofereceu três moradias
`estado='Usado'`, zero com `jardim`/`terraco`/`varanda` — uma delas nem
moradia acabada é ("Espaço para converter").

Causa: `tools.py` (`pesquisar_imoveis`, schema e `_consulta_imoveis`) nunca
teve campos de condição/features — só `natureza`, `quartos`, `zona`, preço.
**Não filtramos por isto na query**: `jardim=true` em só 1/54 publicados
(as booleanas de `FeatureTags` do eGO têm histórico de dados incompletos);
filtrar a sério esconderia moradias reais por falta de dado. Em vez disso,
`estado` e as features que existem passam a aparecer no resultado, para o
modelo poder ser honesto ("é Usado, sem jardim") em vez de omitir.

### 2. MQL recuperado quando o A1 só escreve prosa (`8e72c4c`)

Mesma conversa: `guardar_dados_cliente` gravou um `resumo` completo
(orçamento, tipo, zona) mas deixou `tipo_interesse`/`orcamento`/
`zona_preferida` a **null** — os três campos que `guards.lead_qualificada`
lê. `qualificada_em` nunca preenche, nenhuma tarefa nasce para o corretor,
apesar de os dados existirem em texto.

Medido em produção: **5 de 9** `agente_clientes` têm `tipo_interesse` vazio
(mesmo sendo o único campo `required` no schema da tool — a API da
Anthropic não valida `required` a sério). **2 (Filipa Pedro, Junior
Marques)** têm os três campos vazios com o resumo cheio de dados por
extenso — Junior Marques está assim desde 22/08, 9 dias sem qualificar.

Fix: quando falta pelo menos um dos três campos e há `resumo`, uma segunda
chamada pequena e forçada por tool extrai o que estiver explícito — mesmo
padrão já usado em `save_call.py` (voz). Nunca sobrepõe o que o modelo já
deu.

### 3. Notificações: Microsoft Graph → Resend (`90d2354`)

Decisão do utilizador. O Graph chegou a ser implementado (16/08) mas nunca
teve credenciais em produção — registo de app no Entra ID e consentimento
de administrador são trabalho de backoffice que nunca aconteceu. Resend é
mais simples para o caso de uso (API key estática, sem OAuth, sem cache de
token). **Terceira vez que a troca prova o desenho de `notificacoes.py`**:
mudou só o corpo de `notificar()`; `_promover_lead` e `_escalar_para_humano`
continuam sem saber do canal.

`RESEND_API_KEY`/`RESEND_REMETENTE`/`NOTIFICACOES_PARA` preenchidos pelo
utilizador, staged e deployados como Fly secrets. Testado com **envio real**
(200 OK) antes do commit.

### 4. Email de escalamento diz "Matilde", não "a1_vendedor" (`c6ff9de`)

Achado ao enviar, a pedido, o email de escalamento real da conversa da
Filipa (a Matilde tinha mesmo chamado `escalar_para_humano` naquele turno,
30/08 — só que na altura o Graph estava inerte e o email nunca saiu; este
foi o primeiro a sair a sério). `contexto["agente"]` é o id interno
(`a1_vendedor`), ilegível para quem recebe. `_NOME_AGENTE` mapeia para o
nome público; a frase mudou de "O {agente} escalou" para "A assistente
{agente} escalou" para não ficar com género errado ("O Matilde").

Email real enviado ao director e a **Alexandra Santos** (consultora do
FH2581, resolvida via `_consultor_do_imovel`).

### 5. Dedupe de mensagens WhatsApp — a causa das tarefas duplicadas (`0bc54c4`)

Ao ver as tarefas pendentes no painel: **visitas duplicadas** (Álvaro
Marçal, Miguel/FH2536, Tania Portela) e uma **lead qualificada em duplicado**
(João Marques, 5 tarefas idênticas). Todos os pares de duplicados têm
**30-65 segundos** de diferença entre cópias — não é reconfirmação humana,
é reentrega de webhook.

Causa raiz: `webhook.py` extraía o `message_id` (wamid da Meta) só para
`mark_as_read`, nunca para dedupe. A Meta garante "at least once" e reenvia
o mesmo webhook em falhas transitórias; sem dedupe, a reentrega reprocessa
a mensagem do zero — Claude responde outra vez, chama as mesmas tools outra
vez.

Fix: tabela `agente_mensagens_processadas` (`message_id` PK, migration
`0033`, **corrida pelo utilizador**) + `INSERT ... ON CONFLICT DO NOTHING`
atómico antes de processar (`_ja_processada`). Falha na BD nunca bloqueia —
degrada para o comportamento actual. Este é o achado mais sério da sessão:
sistémico, toca produção desde pelo menos 06/08, não só visitas — qualquer
tool chamada pela Matilde podia duplicar-se.

## Achado sem fix (investigação, não código)

**Cruzamento leads × notas do eGO** (por telefone, via `oportunidades`):
**34 das 271 leads** já tinham notas prévias no eGO — nenhuma com
`contacto_humano_em` marcado. Relevante para o "Próximos passos 1" de
ontem (a volta à Alexandra/Alexsandra antes do reenvio das 45). CSV com
PII real entregue fora do repo, nunca commitado.

## Ficheiros principais modificados

- `backend/app/agents/broker/tools.py` — `_consulta_imoveis` (estado/features),
  `_guardar_dados_cliente`/`_extrair_mql_do_resumo`, `_NOME_AGENTE`.
- `backend/app/notificacoes.py`, `backend/app/config.py` — Resend.
- `backend/app/agents/broker/channels/whatsapp/webhook.py` — dedupe.
- `supabase/migrations/0033_dedupe_whatsapp.sql` — nova tabela.
- `backend/.env.example`, `backend/.env` (local, não commitado) — `RESEND_*`.
- 4 ficheiros de teste novos, suite em **217** (era 207 ontem).
- `docs/decisoes.md` — troca Graph→Resend registada.

## Decisões arquitecturais

Uma nova, já em `docs/decisoes.md`: **Resend em vez de Microsoft Graph**
para notificações (secção "Notificações ao corretor", revisão 2026-08-31).

## Bugs conhecidos — mudanças

- ✅ **Fechado**: `pesquisar_imoveis` ignorava estado/features do imóvel.
- ✅ **Fechado**: `guardar_dados_cliente` perdia o MQL em prosa.
- ✅ **Fechado**: notificações inertes (Graph sem credenciais) — Resend
  configurado e testado, `NOTIFICACOES_PARA` preenchido.
- ✅ **Fechado**: tarefas duplicadas (visitas, qualificação) — causa raiz
  era a falta de dedupe no webhook do WhatsApp, não as tools em si.
- Os restantes bugs conhecidos (bug de timestamp do `03`, atraso de 12h do
  `01`, falta de `logging.basicConfig`, `agente_leads` morta, dedup de
  clientes sob carga, agente de voz) **inalterados** — ver `CLAUDE.md`.

## Próximos passos

1. **Tudo o que já estava no handoff de 30/08** continua por fazer: importar
   `02`/`03`, decidir chão de data do `03`, apagar leads de teste, reenviar
   as 45 leads (prazo 23/09), a volta à Alexandra/Alexsandra.
2. Confirmar que o dedupe do WhatsApp aguenta produção — sem forma de testar
   uma reentrega real da Meta sem esperar que aconteça sozinha.
3. As 34 leads com notas prévias no eGO (achado desta sessão) — decidir
   quais marcar `contacto_humano_em` antes do reenvio.
4. `Junior Marques` (cliente desde 22/08, MQL agora recuperável) — confirmar
   que uma futura mensagem dele dispara a promoção correctamente com o fix
   novo, ou promover à mão se não houver mais contacto dele.
