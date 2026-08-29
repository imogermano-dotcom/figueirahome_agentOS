# Contacto humano na lead — a Matilde não fala por cima da consultora

## Porque existe

A 29/08, antes de reenviar as 45 leads que o apagão do WhatsApp deixou por
entregar, cruzou-se a lista com o espelho do eGO (`contactos` = 28 259,
`oportunidades` = 25 824), por telefone (últimos 9 dígitos):

| | |
|---|---|
| leads por reenviar | 45 |
| já existem como contacto no eGO | **8** |
| com oportunidade **activa** e consultora atribuída | **4** |
| mexidas **depois** da lead entrar | **1** (Cristina Tomás, contacto criado a 27/08 pela Alexsandra Ferreira sobre uma lead de 26/08) |

Nas outras sete o registo do eGO é **anterior** à lead — são clientes que a
agência já tinha, não prova de contacto recente. Mas quatro delas têm processo
aberto com uma consultora, e um template automático da Matilde a falar de outro
imóvel entra por cima disso.

**A base não tinha como saber.** Nem coluna, nem sinal, nem sítio para a nota.
A única forma de excluir uma lead do envio era não a incluir na lista à mão — o
que se perde na execução seguinte.

## O que se acrescenta

Uma coluna. O resto já existe e estava por usar.

| precisa | existe? | onde |
|---|---|---|
| a **nota** do contacto | ✅ | `leads.notas` (0021), já editável no painel e já na tabela |
| **quem** contactou | ✅ | `leads.responsavel` (0021) — coluna e campo no modelo, **sem escritor nenhum** até hoje |
| o **travão** dos envios | ❌ | `leads.contacto_humano_em` — migration `0032` |

### Porquê coluna e não estado

Mesma razão da `0030` (`follow_up_em`), escrita em `docs/decisoes.md`: **o
`estado` é editável no painel e reescrito pelo n8n a cada passo do fluxo.**
Marcar `sem_interesse` à mão para travar o envio perde-se no update seguinte —
e mente sobre o desfecho: a pessoa pode estar muito interessada, só que a falar
com uma pessoa em vez da assistente.

### Porquê só os envios que nós iniciamos

O travão vale para o `02` (backfill) e o `03` (follow-up). **Não** vale para a
Matilde responder: se a pessoa escrever no WhatsApp, a assistente responde na
mesma. Calar o agente aí punha o cliente a falar para o vazio, e a conversa é
dela — a consultora não a vê.

`guards.py` não muda. Nem `engine.py`, nem o router.

---

## Alterações

### 1. Migration `0032_leads_contacto_humano.sql` — escrita, por correr

```sql
alter table leads add column if not exists contacto_humano_em timestamptz;
comment on column leads.contacto_humano_em is '…';
```

Sem índice (dezenas de linhas, e aparece sempre ao lado de filtros muito mais
selectivos). Sem CHECK, sem default. **Corre à mão no editor SQL do Supabase.**

### 2. `models/lead.py` — o campo que o painel envia ✅ feito

O `PUT /api/leads/{id}` faz `model_dump(exclude_none=True)`. Um `None` **nunca
chega à base** — logo, com uma coluna `datetime` no modelo, marcar era possível
e **desmarcar não**. Uma consultora marcada por engano ficava marcada para
sempre.

Por isso o painel manda um **booleano**, não um carimbo:

```python
class LeadBase(BaseModel):
    ...
    contacto_humano: Optional[bool] = None   # True = agora; False = limpar
```

`False` não é `None`, portanto sobrevive ao `exclude_none` e o desmarcar
funciona. O carimbo é sempre do servidor — o browser não decide horas.

### 3. `api/leads.py` — traduz o booleano em carimbo ✅ feito

No `_update`, antes do `.update(data)`:

```python
marca = data.pop("contacto_humano", None)
if marca is not None:
    data["contacto_humano_em"] = _now() if marca else None
```

`pop` porque `contacto_humano` não é coluna. Fica no `atualizar_lead` e **não**
no `criar_lead`: uma lead que nasce já contactada por uma pessoa não passa por
esta página.

### 4. `pages/Leads.jsx` — a caixa e o distintivo ✅ feito

No modal de edição, a seguir às Notas:

- checkbox **"Contactada por uma consultora"** → `form.contacto_humano`
- input **Responsável** → `form.responsavel`, só relevante com a caixa marcada

Na tabela, distintivo ao lado do nome quando `lead.contacto_humano_em`, no
mesmo molde do `só telefone` que já lá está:

```jsx
{lead.contacto_humano_em && (
  <span title={`Contactada por ${lead.responsavel || 'uma consultora'}. Os envios automáticos estão travados.`}
    className="ml-2 px-2 py-0.5 rounded-full text-xs font-medium bg-violet-500/15 text-violet-400 border border-violet-500/20">
    consultora
  </span>
)}
```

`openEdit` passa a semear `contacto_humano: !!lead.contacto_humano_em` e
`responsavel: lead.responsavel || ''`.

### 5. n8n — os três fluxos ✅ feito

Guarda dupla, como as outras: `filterString` **e** nó `IF`. Um nome de coluna
trocado no filtro não dá erro nenhum — o PostgREST devolve linhas a mais em
silêncio.

| fluxo | `filterString` | `IF` |
|---|---|---|
| `02-backfill-template.json` | `&contacto_humano_em=is.null` | ✅ |
| `03-follow-up-48h.json` | `&contacto_humano_em=is.null` | ✅ |
| `01-enviar-template.json` | **não** (só no `select`) | ✅ |

**O `01` levou a guarda, ao contrário do que este plano dizia.** O raciocínio
original — "dispara sobre uma lead que a Meta acabou de criar, ninguém teve
tempo de lhe tocar" — deixou de valer: desde 28/08 o `01` dispara **~12h depois**
da lead entrar, e meio dia chega e sobra para uma consultora pegar no telefone.
Corrigido o atraso, a guarda fica na mesma: custa nada e fecha a janela.

Mas **só no `IF`, nunca no `filterString`**: lá a lead é procurada por
`meta_lead_id`, e filtrar na consulta devolveria zero linhas para uma lead
marcada — o nó morria antes das guardas, indistinguível de "lead não
encontrada". Saltar tem de ser decisão do `IF`, onde se vê qual condição falhou.

#### Nós nativos do Supabase, nos três fluxos

O `01` falava com o PostgREST por **HTTP Request** (`$env.SUPABASE_URL` +
credencial *Custom Auth* com dois cabeçalhos). Os três nós passaram a
`n8n-nodes-base.supabase`, como o `02` e o `03` já eram. Ganha-se: o URL da base
sai de dentro do fluxo, e o `template_enviado` deixa de precisar de
`JSON.stringify()` — num corpo montado à mão, um título com aspas partia o JSON.

⚠️ **Um custo real, num nó só.** O `Ler imóvel` do `01` encodava a referência
com `encodeURIComponent`, e **11 das 54 referências têm um espaço a sério**
(`FH2460 3C`). O nó nativo não expõe onde encodar. O `02` corre assim desde
28/08 sem falha conhecida, mas **não está verificado** — testar com uma lead do
`FH2460 3C`. Sintoma: `{{2}}` sai só com a ref, sem resumo.

#### Bug encontrado a ler: o `03` nunca tinha corrido

`connections` tinha a chave `"Todos os dias às 10h"` e o nó chamava-se
`"…às 12h"` (renomeado a 25/08). O n8n importa isto **sem um aviso** e o
Schedule Trigger fica ligado a nada. Corrigido, e com teste que varre as
ligações dos três ficheiros.

⚠️ Os três ficheiros **já estavam por importar no n8n** desde 28/08 (template
`figueirahome_apos_lead`). Tudo isto vai no mesmo import — não são duas idas.

### 6. Documentação

- `docs/n8n/README.md`: a coluna entra na lista de guardas do `02` e do `03`.
- `docs/decisoes.md`: uma linha — *o travão dos envios é coluna, nunca estado;
  e trava só o que nós iniciamos, nunca as respostas*.
- `CLAUDE.md`: `contacto_humano_em` na secção de dados.

---

## Testes

✅ **`backend/tests/test_leads_contacto_humano.py`** — 5 testes. Captura o que
sai mesmo para o PostgREST no `atualizar_lead`:

- `contacto_humano: True` → `contacto_humano_em` com carimbo do servidor, e
  **não** a chave `contacto_humano` (não é coluna: o PostgREST devolvia
  `PGRST204` e o painel rebentava com um erro que não diz nada).
- `contacto_humano: False` → `contacto_humano_em = None`. **É a regressão que
  interessa**: é o `exclude_none` que a ameaça, e sem ela não há como desmarcar.
- Um PUT que só muda o estado ou as notas não toca na coluna.
- `LeadCreate` não conhece o campo.

Ficheiro próprio e não dentro do `test_leads_meta.py`: aquele monkeypatcha o
`get_supabase` dos `guards`, este precisa do de `api.leads`. Fake de 15 linhas
que guarda o payload numa lista — mais pequeno do que adaptar o de lá.

✅ **`backend/tests/test_n8n_guardas.py`** — feito, 15 testes. Lê os JSON do n8n:
a guarda está nos três `IF` e no `filterString` dos dois que varrem a tabela; o
`01` tem a coluna no `select` e **não** no filtro; nenhum `update` escreve
`respondeu_em` nem `contacto_humano_em`; nenhum nó HTTP aponta ao `/rest/v1/`;
e **todas as ligações apontam a nós que existem** — foi este último que apanhou
o `03` partido. Apanha o dia em que alguém reexportar um fluxo por cima destes.

## Verificação

1. `pytest backend/tests/` a partir de `backend/` — **187 verdes hoje**, mais os
   novos.
2. **Migration `0032` corrida à mão** no editor SQL, com a verificação que está
   no fim do ficheiro.
3. Deploy do backend, e uma volta no painel: marcar uma lead de teste, ver o
   distintivo, desmarcar, ver desaparecer.
4. Antes do reenvio das 45, contagem de controlo:
   ```sql
   select count(*) from leads
    where template_enviado_em is null and contacto_humano_em is not null;
   ```

**Escrita em produção**: o ponto 2 e o deploy do 3. Confirmar antes de cada um.

---

## O que isto resolve das 45

Depois da volta às consultoras, marcam-se as do shortlist — Cristina Tomás e as
quatro com oportunidade activa — e o `02` deixa-as em paz **sozinho**. Sem lista
à parte, sem `Limit` a contar à mão, sem ninguém se lembrar da excepção daqui a
três semanas.

O resto do reenvio (`template_enviado_em` a `NULL`, `estado` a `nova`) continua
como estava, e continua **à espera da data exacta do WhatsApp Manager →
Insights**. Prazo **23/09** (`guards._JANELA_LEAD_DIAS = 30`).

## Fora de âmbito

- **Descobrir contactos sozinho.** A coluna só sabe o que alguém escrever. Uma
  chamada não registada continua invisível — igual a hoje. Ligar isto ao eGO em
  tempo real é fase própria, e precisa da chave de integração que não temos.
- **Travar a Matilde a responder.** Ver acima: é deliberado.
- **Histórico de contactos.** Um carimbo, o último. Se um dia a pergunta for
  "quantas vezes e quando", aí vale uma tabela — não vale hoje.
- **Escrever no eGO.** Nunca, e por decisão registada.
