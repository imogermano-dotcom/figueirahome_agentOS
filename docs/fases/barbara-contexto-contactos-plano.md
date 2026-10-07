# Bárbara (A4) com o contexto de `contactos` — plano

> Fase pequena, só backend. **Plano antes de código** (CLAUDE.md, regra 2).
> Segue o padrão já fechado para a Inês: `engine._contexto_recrutamento` (29/09).

## Problema

A angariação da Meta vive em `contactos` (`tipo_contacto=['vendedor']`, RPC
`lead_meta_angariacao`), nunca em `leads`. Em `engine._contexto_inicial` só o A3
tem ramo próprio (`engine.py:193`); para o A4 cai-se em `lead_aberta` (tabela
`leads`) e **não há contexto nenhum**. Consequência prevista, igual à que a
Inês teve ao vivo a 29/09:

- o vendedor recebe o template (*"Olá X, sou a Bárbara…"*), responde, e a thread
  nasce **sem o template no histórico** — a Bárbara não sabe que já se
  apresentou nem que já chamou a pessoa pelo nome;
- tende a **apresentar-se outra vez** e a **perguntar o nome** (o passo 4 do
  prompt manda recolhê-lo) a quem o template já tratou por ele.

O fim de turno já está tratado (`engine.py:577`: `marcar_contacto_respondeu`
para A4) e o routing também (`agente_de_lead` cai em `vendedor`). Só falta o
**início**: perfil + template.

## O que se sabe e o que não se sabe

- **Não houve nenhum caso real.** Em `agente_conversas` há **uma só** conversa
  da Bárbara (11/09, anterior a todo este desenho) e **zero** `contactos`
  `vendedor` com `template_enviado_em`. A campanha de angariação nunca correu
  com leads reais, e hoje só corre a de recrutamento. A fase é **preventiva**,
  não corrige uma falha observada — e a hipótese acima vem do que aconteceu à
  Inês, não de uma conversa da Bárbara.
- **Por verificar antes de codar** (read-only, n8n `ABCe9SJcuYBxp8eM` "Enviar
  template Angariação"):
  1. o texto do template inclui o nome da Bárbara (para a frase "já te
     apresentaste")? O guarda é `NOME_A4.lower() in template.lower()`;
  2. que campos do formulário chegam a `contactos` além do nome (tipo de
     imóvel, zona?). Se houver, entram no perfil e a Bárbara não os volta a
     perguntar; se não houver, só nome + template.

## Proposta

Generalizar `_contexto_recrutamento` em vez de copiá-la (regra do projecto:
"um motor, N assistentes", nunca N cópias). Só três coisas mudam entre A3 e A4:

| | A3 | A4 |
|---|---|---|
| `tipo_contacto` | `recrutamento` | `vendedor` |
| nome para o guarda de apresentação | `NOME_A3` | `NOME_A4` |
| frase de origem no perfil | "candidatou-se por um anúncio da Meta" | "pediu contacto sobre o seu imóvel por um anúncio da Meta" |

Forma: `_contexto_contacto_meta(telefone, perfil, thread_nova, tipo, nome_agente, origem)`;
`_contexto_recrutamento` deixa de existir como corpo próprio e `_contexto_inicial`
despacha por um dict `{A3: (...), A4: (...)}` em vez de `if agente == A3`.

- **Não** afirmar o que o formulário não diz: a frase de origem do A4 não
  presume morada, tipo ou "quer vender" (pode ser arrendar); diz só que veio de
  um anúncio e que o nome já se sabe.
- Se o passo 2 da verificação acima mostrar campos úteis, acrescentam-se ao
  perfil numa segunda iteração (fora do âmbito mínimo).
- Sem alteração ao prompt da Bárbara: o `engine` já injecta o que lhe falta.
  (O passo 1 do prompt pede morada/tipo/agência num só bloco — continua válido.)

## Fora desta fase

- **Nudge/horas de silêncio** — decisão adiada para alinhar com o Miguel.
- **`leads_angariacao`** (Make + consultora) — outro caminho, outra tabela.
- **Teste ao vivo** — sem leads de angariação reais, a validação ao vivo fica
  dependente de uma lead de teste ou da reactivação da campanha. Confirmar o
  `meta_lead_id`/nome antes de assumir que uma lead é de teste.

## Testes (`backend/tests/test_leads_meta.py`)

Espelham `test_ines_recebe_template_e_nome_do_contacto` (`:416`):

1. **A4 com contacto `vendedor`**: perfil leva nome + "não o perguntes" e
   "não voltes a apresentar-te"; `template` volta como mensagem do assistente
   no 1.º turno; `tipo` pedido a `contacto_meta_aberto` é `vendedor`.
2. **Mesma conversa, `thread_nova=False`**: sem template (já está no histórico).
3. **A4 sem contacto aberto**: devolve `perfil` inalterado, `template=None`.
4. **Regressão A3**: o teste existente da Inês passa sem alterações (pede
   `recrutamento`, não `vendedor`).
5. **Template que não menciona a Bárbara**: não acrescenta "já te apresentaste".

`pytest backend/tests/` de `backend/` (hoje 289).

## Deploy e risco

Só `figueirahome-agentos`. Sem migration, sem dados, sem n8n. Risco baixo e
isolado: só altera o prompt do A4 quando existe um contacto `vendedor` aberto —
caso que hoje não ocorre em produção. O A3 (único com tráfego) é tocado pela
refactorização, daí o teste de regressão 4; reversível com `git revert`.

## Decisões por confirmar

1. **Generalizar** `_contexto_recrutamento` (recomendado) ou copiar para
   `_contexto_angariacao`? Copiar é mais rápido hoje e deixa duas cópias a
   divergir.
2. Fazer a verificação do template/campos no n8n **antes** de codar
   (recomendado, é só leitura) ou assumir só nome + template?
3. Vale a pena fazer agora, sem tráfego de angariação? Alternativa: deixar
   para quando a campanha for reactivada, e usar o tempo noutro passo.
