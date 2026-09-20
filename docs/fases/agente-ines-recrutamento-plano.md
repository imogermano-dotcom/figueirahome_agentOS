# Plano — A3 "Inês", assistente de recrutamento

> Fase nova, pedida pelo utilizador (20/09). Zero código ainda.

## Porquê

A3 (recrutamento) está na spec (`assistentes-ia-especificacao.md` §5) desde
o início mas foi sempre adiado — `router.py` já reconhece as frases
(`_A3_RE`) mas manda tudo para o A2, que só recolhe contacto e escala. O
envio de template WhatsApp (18–20/09,
`docs/fases/handoff-2026-09-20-resumo.md`) já usa o nome **Inês** no texto
aprovado pela Meta — esta fase dá-lhe conversa a sério, mesmo padrão da
Bárbara (A4, `agente-barbara-angariacao-plano.md`).

## Decisão arquitectural (já registada, `docs/decisoes.md:15`)

> "Acrescentar A3/A4 é uma entrada no dict + uma linha em `agente_config`,
> não um ficheiro novo."

Mesmo motor (`engine.py`), zero tabelas novas, zero tools novas. Inês
distingue-se de Matilde/Maria/Bárbara só por prompt e subconjunto de tools.

## Escopo

**Dentro:**
- Registar `a3_recrutamento` em `assistants.ASSISTENTES` (prompt da Inês,
  tools, sem forcing).
- Router: `_A3_RE` já existe — só trocar o destino de `A2` para `A3`
  (`router.py:77-78`).
- Seed de `agente_config` para `a3_recrutamento` (migration `0037`, padrão
  da `0036`).
- Painel: entrada na Sidebar, rota `/agentes/a3_recrutamento`,
  `AgenteConfig.jsx`, opção no `Chat.jsx` para testar sem depender do
  WhatsApp real.
- `_NOME_AGENTE[A3] = "Inês"` em `tools.py`.
- `guardar_dados_cliente`: acrescentar `"recrutamento"` ao enum de
  `tipo_interesse` (hoje só `compra/arrendamento/venda/outro`).
- Testes: `test_router.py` (A3 deixa de ser tratado como adiado).

**Fora (deliberado, mesmo critério da Bárbara):**
- Tool nova para "entrevista" — reaproveita `escalar_para_humano`
  (`motivo="entrevista de recrutamento"`), sem gate nenhum (não há
  equivalente ao "80%" aqui).
- Dados concretos de diferenciação que a spec pede (§5.3: "60-90 dias para
  1ª transacção", níveis de carreira, exemplos de comissão) — sem fonte
  real ainda; ver pergunta 2 abaixo.
- Nudge 24h — só a A1 tem.
- **Seeding de conversa via `leads`** (o mecanismo que faz a Matilde
  responder a um simples "Sim" sem apanhar o router do zero,
  `docs/decisoes.md`): `agente_de_lead`/`lead_aberta` (`guards.py`) leem só
  a tabela `leads` — leads de recrutamento (e de angariação, já em
  produção) nunca lá chegam, só em `contactos`. **A Inês herda a mesma
  limitação que a Bárbara já tem em produção**: uma resposta genérica ao
  template ("Sim", "Olá") cai no router do zero, não no `_A3_RE`, e pode
  ir parar ao A2. Não corrigido nesta fase — é uma fase à parte (tocaria
  `agente_de_lead`, e possivelmente o plano maior de unificação em
  `contactos`, `contactos-unificado-assistentes-plano.md`).

## Fluxo de conversa da Inês (adaptado de §5.2/§5.3 da spec)

1. Saudação + confirma que é sobre a candidatura (mesmo padrão A1/A2/A4).
2. Pergunta em bloco curto: contexto profissional actual, motivação para o
   sector imobiliário.
3. Apresenta o modelo: comissões (rendimento variável, sem tecto — **sem
   valores concretos**, ver pergunta 3), formação inicial, suporte, CRM.
4. Qualifica: disponibilidade (full-time/part-time), zona preferencial.
5. Regista com `guardar_dados_cliente` (`tipo_interesse="recrutamento"`) e
   escala com `escalar_para_humano` (`motivo="entrevista de recrutamento"`)
   — cria tarefa + email ao responsável, tal como a Bárbara faz para
   visitas de avaliação.
6. Engano/desistência → `encerrar_lead`, igual às outras.

Tools da Inês: `guardar_dados_cliente`, `escalar_para_humano`,
`encerrar_lead`. Sem `pesquisar_imoveis`/`ficha_imovel`/`pedir_visita`/
`link_imovel` (são do lado comprador) e sem `consultar_*` (fronteira de
segurança do `broker`, intocada).

## Ficheiros a alterar

| Ficheiro | Mudança |
|---|---|
| `backend/app/agents/broker/assistants.py` | `A3 = "a3_recrutamento"`, `NOME_A3 = "Inês"`, `_PROMPT_A3`, entrada em `ASSISTENTES`; enum de `tipo_interesse` ganha `"recrutamento"` |
| `backend/app/agents/broker/router.py` | `_A3_RE` passa a devolver `A3` em vez de `A2` |
| `backend/app/agents/broker/tools.py` | `_NOME_AGENTE[A3] = "Inês"` |
| `supabase/migrations/0037_assistente_a3_recrutamento.sql` | Seed `agente_config`, padrão da `0036` |
| `frontend/src/components/Sidebar.jsx` | Entrada `/agentes/a3_recrutamento` |
| `frontend/src/pages/AgenteConfig.jsx` | Entrada em `META` |
| `frontend/src/pages/Chat.jsx` | Opção no selector para testar no painel |
| `backend/tests/test_router.py` | `_A3_RE` → `A3`, não `A2` |

## Por confirmar antes de escrever o prompt final

1. **Persona/tom da Inês** — mesmo registo cordial de Matilde/Maria/Bárbara?
2. **Dados de diferenciação** (§5.3: timelines de 60-90 dias, níveis de
   carreira) — sem fonte real ainda. Ficam de fora do prompt, ou entram como
   texto genérico em `instrucoes` (editável no painel depois)?
3. **Salário/comissões** — a spec pede "cenários realistas de consultores
   activos". Informar valores concretos, ou remeter sempre para o
   responsável de recrutamento (mais seguro, mesmo critério da comissão da
   Bárbara)?
4. Confirma que esta fase é **texto/routing apenas**, testado no chat do
   painel — sem tocar no WhatsApp real até validado.

## Verificação

- `pytest backend/tests/` — router actualizado, testes actuais não quebram.
- Testar no `Chat.jsx` (`/api/broker/chat`, `agente=a3_recrutamento`) antes
  de qualquer exposição no WhatsApp.
