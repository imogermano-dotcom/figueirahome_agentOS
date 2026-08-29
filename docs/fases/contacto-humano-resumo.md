# Contacto humano na lead — resumo de execução (2026-08-29)

> Plano: `contacto-humano-plano.md`. Commit `be18602`, backend `v56`.
> Fase irmã do mesmo dia: `incidente-whatsapp-mudo-2026-08-29.md`.

## O que motivou

Antes de reenviar as 45 leads que o apagão do WhatsApp deixou por entregar,
cruzou-se a lista com o espelho do eGO (`contactos` = 28 259, `oportunidades` =
25 824), por telefone, pelos últimos 9 dígitos:

| | |
|---|---|
| leads por reenviar | 45 |
| já existem como contacto no eGO | **8** |
| com oportunidade **activa** e consultora atribuída | **4** |
| mexidas **depois** da lead entrar | **1** — Cristina Tomás, lead 26/08, contacto criado a 27/08 pela Alexsandra Ferreira |

Nas outras sete o registo é **anterior** à lead: são clientes que a agência já
tinha, não prova de contacto recente. Mas quatro têm processo aberto com uma
consultora, e um template automático da Matilde sobre outro imóvel entra por
cima disso.

**A base não tinha como saber.** Nem coluna, nem sinal, nem sítio para a nota.
Excluir uma lead do envio só era possível não a incluindo na lista à mão — o que
se perde na execução seguinte.

## O que foi implementado

### Uma coluna; o resto já existia

| precisa | onde |
|---|---|
| a **nota** do contacto | `leads.notas` (`0021`) — já editável no painel |
| **quem** contactou | `leads.responsavel` (`0021`) — existia e **nunca tivera escritor** |
| o **travão** dos envios | `leads.contacto_humano_em` — **novo**, migration `0032` |

### Backend

`models/lead.py` — `contacto_humano: Optional[bool]` no `LeadUpdate` (não no
`LeadCreate`). `Lead` expõe `contacto_humano_em` para o painel o ler.

`api/leads.py`, dentro do `atualizar_lead`:

```python
marca = data.pop("contacto_humano", None)
if marca is not None:
    data["contacto_humano_em"] = _now() if marca else None
```

O `pop` não é arrumação: `contacto_humano` não é coluna, e sem ele o PostgREST
devolve `PGRST204` e o guardar do painel rebenta com um erro que não diz nada.

### Painel

`pages/Leads.jsx` — caixa **"Contactada por uma consultora"** no modal, com o
campo *quem* a aparecer só quando marcada, e a data da marcação por baixo.
Distintivo violeta `consultora` na tabela, ao lado do `só telefone` que já lá
estava.

### n8n — os três fluxos

| fluxo | `filterString` | `IF` |
|---|---|---|
| `01-enviar-template.json` | não (só no `select`) | ✅ |
| `02-backfill-template.json` | `&contacto_humano_em=is.null` | ✅ |
| `03-follow-up-48h.json` | `&contacto_humano_em=is.null` | ✅ |

E os três nós do `01` que falavam com o PostgREST por HTTP Request passaram a
`n8n-nodes-base.supabase`, como o `02` e o `03` já eram.

## Decisões

**Coluna, não estado.** Mesma forma que o `follow_up_em` (`0030`) e pela mesma
razão: o `estado` é editável no painel *e* reescrito pelo n8n a cada passo.
Marcar `sem_interesse` à mão para travar o envio perde-se no update seguinte — e
mente sobre o desfecho: a pessoa pode estar muito interessada, só que a falar
com uma pessoa em vez da assistente.

**Trava o que nós iniciamos, nunca as respostas.** Vale para o template do `02`
e o follow-up do `03`. Se a pessoa escrever no WhatsApp, a Matilde responde na
mesma — calá-la punha o cliente a falar para o vazio, e a conversa é dela, que a
consultora não vê. `guards.py`, `engine.py` e o router não mudaram.

**Booleano do painel, carimbo do servidor.** `atualizar_lead` faz
`model_dump(exclude_none=True)`: um `None` nunca chega à base. Com um campo
`datetime` no modelo, marcar funcionava e **desmarcar não** — uma consultora
marcada por engano ficava marcada para sempre e a lead nunca mais recebia
mensagem. `False` não é `None`, sobrevive ao filtro e limpa a coluna. E a hora é
do servidor: o browser não decide quando é agora.

**O `01` levou a guarda, contra o que o plano dizia.** O raciocínio original —
"dispara sobre uma lead que a Meta acabou de criar, ninguém teve tempo de lhe
tocar" — deixou de valer: desde 28/08 o `01` dispara **~12h depois** da lead
entrar, e meio dia chega e sobra para uma consultora pegar no telefone.

**Mas só no `IF`, nunca no `filterString`.** Lá a lead é procurada por
`meta_lead_id`; filtrar na consulta devolvia zero linhas para uma lead marcada,
o nó morria antes das guardas, e o resultado ficava indistinguível de "lead não
encontrada". Saltar tem de ser decisão do `IF`, onde se vê na execução qual das
condições falhou.

**Nós nativos do Supabase nos três fluxos.** O URL da base sai de dentro do
fluxo (era uma segunda configuração a manter a par da credencial), e o
`template_enviado` deixa de precisar de `JSON.stringify()` — num corpo montado à
mão, um título com aspas partia o JSON.

## Ficheiros

| ficheiro | o quê |
|---|---|
| `supabase/migrations/0032_leads_contacto_humano.sql` | **novo** — a coluna. Corrida à mão a 29/08 |
| `backend/app/models/lead.py` | `contacto_humano` no `LeadUpdate`, `contacto_humano_em` no `Lead` |
| `backend/app/api/leads.py` | traduz o booleano em carimbo |
| `frontend/src/pages/Leads.jsx` | caixa, campo `responsavel`, distintivo |
| `docs/n8n/01-enviar-template.json` | 3 nós → nativos · guarda no `IF` |
| `docs/n8n/02-backfill-template.json` | guarda no filtro e no `IF` |
| `docs/n8n/03-follow-up-48h.json` | guarda · **ligação corrigida** |
| `backend/tests/test_n8n_guardas.py` | **novo**, 15 testes |
| `backend/tests/test_leads_contacto_humano.py` | **novo**, 5 testes |
| `docs/n8n/README.md` · `decisoes.md` · `database-schema.md` | documentação |

**207 testes** (eram 187 ao início do dia). Frontend compila.

## Bug encontrado a ler: o `03` nunca teria corrido

`connections` tinha a chave `"Todos os dias às 10h"` e o nó chama-se
`"…às 12h"` desde 25/08, quando o horário mudou. **O n8n importa isto sem um
aviso** e o Schedule Trigger fica ligado a nada — o fluxo activava-se e não
fazia nada, para sempre.

Apanhado pelo teste que varre as ligações dos três ficheiros e verifica que
apontam a nós que existem. É a asserção mais barata do lote e foi a única que
encontrou um problema real.

## Riscos assumidos

⚠️ **O `Ler imóvel` do `01` perdeu o `encodeURIComponent`.** Era a razão de ser
um HTTP Request: **11 das 54 referências têm um espaço a sério** (`FH2460 3C`) e
cru, no URL, o PostgREST parte o filtro. O nó nativo não expõe onde encodar — o
`filterString` é repartido por `&` e entregue ao cliente HTTP, que encoda
sozinho; encodar à mão daria `%2520`. O `02` corre assim desde 28/08 sem falha
conhecida, mas **não está verificado**.

**Testar com uma lead do `FH2460 3C`.** Sintoma se falhar: o `{{2}}` sai só com
a referência, sem resumo — degrada em silêncio, não rebenta. Correcção: voltar a
pôr um HTTP Request com `encodeURIComponent` **só nesse nó**.

**A coluna só sabe o que alguém escrever.** Uma chamada que a consultora não
registe continua invisível, tal como hoje. Isto resolve daqui para a frente; as
8 de 29/08 são marcadas à mão.

## Por fazer

1. **Importar os três fluxos no n8n** — credencial *Supabase API* em cada nó
   (3+3+2), e o template de follow-up no `03`. Até lá sai o texto antigo, sem o
   imóvel e sem a guarda.
2. **Testar o `01` com o `FH2460 3C`** (ver acima).
3. **Volta às consultoras** — a Alexandra e a Alexsandra confirmam quais das 8
   já foram contactadas. Depois marcar `contacto_humano_em` no painel; o `02`
   passa a saltá-las sozinho, sem lista à parte nem `Limit` contado à mão.
4. **Reenviar as restantes**, com a data exacta do WhatsApp Manager → Insights.
   Prazo **23/09** (`guards._JANELA_LEAD_DIAS = 30`).

## Fora de âmbito, de propósito

- **Descobrir contactos sozinho** — ligar isto ao eGO em tempo real precisa da
  chave de integração que não temos.
- **Travar a Matilde a responder** — ver Decisões.
- **Histórico de contactos** — um carimbo, o último. Se a pergunta um dia for
  "quantas vezes e quando", aí vale uma tabela.
- **Escrever no eGO** — nunca, e por decisão registada.
