# Follow-up de recrutamento (Inês) + routing sem semeadura

## Contexto

Pedido do utilizador: tratar do fluxo n8n para leads que não respondem ao
1º template — âmbito confirmado como **só recrutamento** por agora (A1/A4
ficam de fora desta fase).

Investigação encontrou três factos que mudam o desenho:

1. **Os dois fluxos n8n "follow-up às 48h" existentes são só para A1**
   (`leads`) e nunca correram (zero execuções, um deles com um nó órfão
   duplicado). Não são tocados nesta fase.
2. **Candidatos de recrutamento só escrevem em `contactos`** (`lead_meta_recrutamento`,
   RPC), nunca em `agente_conversas`. Ao contrário do que o padrão antigo
   (`api/leads_meta.py`, endpoint `/conversa-semeada`) sugeria, **esse
   endpoint está morto/inerte desde 15/08** (`docs/fases/leads-meta-sem-semeadura-resumo.md`,
   `docs/decisoes.md:140`) — o projecto abandonou a semeadura de propósito.
   O mecanismo real em produção para o A1/A4 é outro, mais simples:
   `guards.agente_de_lead(telefone)`, chamado pelo **webhook do WhatsApp**
   (`channels/whatsapp/webhook.py:140`) **antes** do router — se há uma lead
   aberta deste número, força o assistente dono, sem depender de regex nem
   de thread semeada. É este padrão que se estende para recrutamento, não o
   endpoint morto. (Perguntei antes se seria via semeadura — esta
   investigação mostrou que não é assim que o resto do sistema já funciona,
   e alinhar com o padrão existente evita reintroduzir um mecanismo que foi
   deliberadamente abandonado.)
3. **`contactos` não tem `respondeu_em` nem `follow_up_em`** — precisos para
   (a) o router saber que a pessoa já está em conversa e (b) o travão de
   "só um follow-up".

Resultado: o fix do routing (bug já activo hoje — uma resposta ao 1º
template pode cair na Maria/A2 em vez da Inês) e o fluxo de follow-up
partilham a mesma base de dados a construir primeiro.

## Desenho

### 1. `contactos` ganha 2 colunas (SQL corrido à mão pelo utilizador)

```sql
ALTER TABLE contactos
  ADD COLUMN respondeu_em timestamptz,
  ADD COLUMN follow_up_em timestamptz;
```

Aditivo, mesmo padrão de `agente`/`id` (20-21/09). Ficheiro
`supabase/migrations/0039_contactos_respondeu_followup.sql` com o mesmo SQL,
comentado — fica no repo como registo, o utilizador corre no editor SQL.

### 2. `guards.py` — estender o padrão existente, não reinventar

- **Nova `contacto_recrutamento_aberto(telefone) -> dict | None`** — espelha
  `lead_aberta` (`guards.py:204`) mas contra `contactos`: filtro
  `tipo_contacto` contém `recrutamento`, `template_enviado_em` não vazio,
  `criado_em >= hoje - _JANELA_LEAD_DIAS` (reutiliza a constante, `guards.py:164`).
  Sem estado fechado equivalente a `_ESTADOS_LEAD_ABERTA` (recrutamento não
  tem — fica registado como limitação, não bloqueante: não há hoje forma de
  "recusar" um candidato).
- **`agente_de_lead` (`guards.py:239`) ganha fallback**: se `lead_aberta`
  não encontrar nada em `leads`, tenta `contacto_recrutamento_aberto` e
  devolve `"a3_recrutamento"`. Zero mudança ao caminho A1/A4 existente.
- **Nova `marcar_contacto_respondeu(contacto_id)`** — espelha
  `marcar_lead_respondeu` (`guards.py:255`), `UPDATE contactos SET
  respondeu_em=now() WHERE id=... AND respondeu_em IS NULL`.

### 3. `engine.py` — marcar a resposta, mesmo sítio do padrão A1

Em `responder()` (`engine.py:448`), ao lado do bloco existente
(`if lead: await marcar_lead_respondeu(...)`), adicionar:

```python
elif agente == A3 and telefone:
    contacto = await contacto_recrutamento_aberto(telefone)
    if contacto:
        await marcar_contacto_respondeu(contacto["id"])
```

(`A3` importado de `assistants.py`, já usado noutros ficheiros do broker
nesta sessão). Não estendo `_contexto_inicial`/injecção de template no
histórico para recrutamento — a Inês já funciona bem sem perfil prévio
(testado ao vivo, 21-22/09); isso ficaria como repetição de saudação depois
de um follow-up, aceite como simplificação conhecida, não bloqueante.

### 4. Zero mudanças ao fluxo n8n "enviar template Recrutamento"

Ao contrário do que descrevi antes de investigar a fundo: **não é preciso
chamar endpoint nenhum a seguir ao envio do 1º template.** O routing passa a
funcionar sozinho via `agente_de_lead`, tal como já funciona para o A1.

### 5. Novo fluxo n8n — "FigueiraHome — follow-up recrutamento (diário)"

Construído de raiz (`n8n_create_workflow`), a espelhar a estrutura do `03`
existente (nunca activado, mas o desenho está correcto):

`Schedule Trigger` (diário, 12:00 Europe/Lisbon — mesmo horário do A1, sem
dados próprios de recrutamento para justificar outro) → `Ler candidatos sem
resposta` (Supabase nativo, tabela `contactos`, filtro `tipo_contacto=cs.{recrutamento}
&whatsapp_permissao=eq.true&respondeu_em=is.null&follow_up_em=is.null&template_enviado_em=lt.{{ $now.minus(48,'hours').toUTC().toISO() }}
&order=template_enviado_em.asc`, `Limit=5` até confirmar) → `Split In Batches`
(1) → `Guardas` (IF: respondeu_em vazio, follow_up_em vazio, whatsapp_permissao
true, telefone não vazio — repetidas de propósito, mesmo motivo do `03`) →
`Preparar texto e número` (Set: `texto_renderizado` = texto completo do
template aprovado com `{{1}}` substituído, `nome_lead` = primeiro nome com
fallback, `telefone_e164`, `contacto_id`) → `WhatsApp: enviar follow-up`
(nó nativo, template `figueirahome_recrutamento_followup|pt_PT`, 1
parâmetro de corpo = `nome_lead`, `phoneNumberId=925368620661613`,
credencial `n8n figueirahome whatsapp` [`Z2UseXbXEgkH4TNf`]) → `Supabase:
marcar follow-up` (update `contactos`: `follow_up_em=now()`,
`template_enviado`/`template_enviado_em` actualizados) → `Esperar 5s` → volta
ao `Split In Batches`. Ramo `done` → `Fim` (noOp).

Credencial Supabase: `Supabase ImoGermano Agentos` (`49QG5sCifQeiauCk`),
igual a todos os outros fluxos.

**Fica inactivo até correr à mão com `Limit=5`** e o utilizador confirmar —
mesmo ritual dos outros três fluxos, nenhum atalho.

## Ficheiros

- `backend/app/agents/broker/guards.py` — `contacto_recrutamento_aberto`,
  `marcar_contacto_respondeu`, extensão de `agente_de_lead`.
- `backend/app/agents/broker/engine.py` — bloco novo em `responder()`.
- `backend/tests/test_guards.py` — testes das duas funções novas + extensão
  de `agente_de_lead` (espelham os testes já existentes de `lead_aberta`/
  `marcar_lead_respondeu`).
- `supabase/migrations/0039_contactos_respondeu_followup.sql` — novo.
- n8n: 1 workflow novo (via MCP), zero mudanças aos existentes.
- `docs/decisoes.md` — registar a extensão do padrão `agente_de_lead` a
  `contactos`/recrutamento.
- `docs/fases/recrutamento-followup-plano.md` / `-resumo.md` — por
  convenção do projecto.
- `CLAUDE.md` — bullet no handoff.

## Por confirmar

Nada bloqueante — desenho alinhado com o padrão já em produção para A1/A4.
Se o utilizador quiser outra hora/janela para o cron, ajusta-se no fluxo
antes de activar (fica inactivo de qualquer forma até à corrida manual).

## Verificação

1. `pytest backend/tests/` — testes novos + existentes verdes.
2. Utilizador corre o `ALTER TABLE` — confirmo via PostgREST.
3. Deploy backend (confirmação explícita, como sempre).
4. Teste de routing: candidato com `contactos` aberto (tipo_contacto
   recrutamento, template_enviado_em preenchido) responde "Sim" no
   WhatsApp → confirmar que cai em `a3_recrutamento`, não A2; confirmar
   `contactos.respondeu_em` gravado no fim do turno.
5. Corrida manual do novo fluxo n8n com `Limit=1` sobre um candidato de
   teste sem resposta e `template_enviado_em` > 24h (alterado de 48h para
   24h a 22/09 — abre espaço para um 3º fluxo a 72h) — confirmar WhatsApp
   entregue, `contactos.follow_up_em` gravado, e que uma segunda corrida não
   reenvia (guarda) nem envia a quem entretanto respondeu.
6. Só depois de tudo confirmado: activar o `Schedule Trigger` (confirmação
   explícita).
