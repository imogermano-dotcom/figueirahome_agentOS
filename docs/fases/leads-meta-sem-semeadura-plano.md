# Fase — A1 assume a lead da Meta sem semeadura

## Objectivo

Quando a lead responde ao template, o A1 assume a conversa já a saber o que ela
respondeu no formulário e o que lhe foi enviado — **sem** ninguém ter de chamar
um endpoint nosso, e portanto sem `AUTOMACAO_SECRET`.

## Contexto

O fluxo real é: Meta → **Make** (webhook, escreve a lead no Supabase) → webhook
para o **n8n** → n8n envia o template → a lead responde → o A1 entra.

Não há passo nenhum a chamar `POST /api/leads/{id}/conversa-semeada`. Sem
semeadura, hoje acontece isto:

| | |
|---|---|
| `guards.agente_de_lead` encontra a lead `nova` e força o A1 | ✅ já funciona |
| `load_conversation` cria thread nova | ✅ |
| `engine._perfil_cliente` procura em `agente_clientes` | ❌ não há linha → devolve `""` |

Ou seja o A1 assume, mas **cego**: pergunta outra vez o orçamento, a zona e o
tipo de interesse a quem os acabou de escrever no formulário. E como o template
não está no histórico, arrisca cumprimentar de novo.

As respostas já estão no Supabase, em `leads.ficha`, escritas pelo Make. Falta
lê-las no momento da resposta em vez de as copiar antecipadamente para
`agente_clientes`.

A qualificação não precisa de alterações: `promover_se_qualificada` (2026-08-14)
já aceita leads `nova`, precisamente porque o turno é prova de que respondeu.

## Tarefas

1. **Migration `0024_leads_template.sql`** — `template_enviado text` e
   `template_enviado_em timestamptz` em `leads`. Duas colunas, `add column if
   not exists`, sem tocar em RLS (a `0021` já o fez). Dá também o sinal
   explícito de que o template saiu e quando, que hoje não existe em lado nenhum.

2. **`guards.py`** — mover `_ALIAS_FICHA` e `_campos_mql` de
   `api/leads_meta.py` (é onde já vive a definição do MQL, `_CAMPOS_MQL`), e
   extrair de `agente_de_lead` um `_lead_aberta(telefone)` partilhado: mesma
   consulta por `variantes_telefone` + `_ESTADOS_LEAD_ABERTA` + janela de 30
   dias. `agente_de_lead` passa a usá-lo; a função nova de contexto também.

3. **`engine.py`** — `_contexto_inicial(telefone)`, testável, que devolve:
   - o texto de perfil: de `agente_clientes` como hoje e, **só se não houver
     linha**, dos campos MQL de `leads.ficha`;
   - a mensagem de template a injectar, se a lead tiver `template_enviado` **e**
     a thread for nova (`mensagens == []`), como `{"role": "assistant", ...}`.

   `responder` usa-a no lugar da chamada actual a `_perfil_cliente`.

4. **`api/leads_meta.py`** — passa a importar o mapa de alias de `guards.py`.
   Fica **inerte mas intacto**: sem `AUTOMACAO_SECRET` recusa tudo, e se um dia
   se quiser voltar a semear está testado e pronto.

5. **Testes** em `backend/tests/test_leads_meta.py`:
   - perfil construído a partir de `leads.ficha` quando não há `agente_clientes`;
   - `agente_clientes` ganha à `ficha` quando ambos existem (o cliente é mais
     recente);
   - template entra como `assistant` **só** no primeiro turno, nunca num
     seguinte;
   - sem lead aberta, o comportamento é o de hoje (perfil vazio, sem template);
   - lead fora da janela de 30 dias ou já `qualificada` não injecta nada.

6. **Documentação** — `docs/decisoes.md` (a decisão passa a ser "contexto lido
   no momento da resposta, não copiado antecipadamente", com o porquê) e
   `CLAUDE.md`.

## Ficheiros

| Ficheiro | O quê |
|---|---|
| `supabase/migrations/0024_leads_template.sql` | criar |
| `backend/app/agents/broker/guards.py` | alias da ficha + `_lead_aberta` |
| `backend/app/agents/broker/engine.py` | `_contexto_inicial` |
| `backend/app/api/leads_meta.py` | importar o alias, resto igual |
| `backend/tests/test_leads_meta.py` | testes novos |
| `docs/decisoes.md`, `CLAUDE.md` | registo |

## Dependências novas

Nenhuma.

## Decisões em aberto

1. **Quem escreve `template_enviado`** — assumo o **n8n**, logo a seguir a enviar
   a mensagem. Se for o Make, muda quem tem de ser configurado.
2. **`_ALIAS_FICHA` continua a ser palpite.** Mapeia `tipo_interesse`,
   `orcamento` e `zona_preferida` a partir de nomes tirados do formulário de
   **angariação**. O de venda não existe. Se os nomes reais não baterem, o A1
   fica cego na mesma e a lead nunca é qualificada — o código fica pronto, mas a
   fase só entrega valor depois de confirmares os campos reais.

## Como testar

1. `pytest backend/tests/` a partir de `backend/` — 69 verdes hoje, mais os novos.
2. Correr a `0024` e confirmar as duas colunas.
3. Fim a fim, com o backend deployado:
   - inserir uma lead de teste com `ficha` preenchida e `template_enviado`;
   - responder "Sim" desse número no WhatsApp;
   - confirmar que o A1 **não** pergunta orçamento/zona/tipo e que não
     cumprimenta como se fosse a primeira mensagem;
   - confirmar que ao fim do turno a lead fica `qualificada` e nasce a tarefa.
4. Regressão: uma conversa de WhatsApp de alguém **sem** lead aberta continua a
   comportar-se como hoje.
