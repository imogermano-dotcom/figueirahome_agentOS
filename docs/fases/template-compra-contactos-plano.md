# Template da compra (fluxo 01) só com `contactos` — plano

> Mexe no n8n ("FigueiraHome — enviar template à lead da Meta", `4rDc9amm6HpO5F4j`, e o ramo da compra do
> "Meta leads to supabase", `9DQlBhON12R1Pane`), em `engine._contexto_inicial` e em `docs/n8n/`.
> **Plano antes de código** (CLAUDE.md, regra 2). Origem: pedido de 15/10 — usar só `contactos`, como os fluxos de
> Angariação e Recrutamento. Investigação só de leitura (nada corrido nem alterado no n8n).

## Âmbito (decidido a 15/10)
O **RPC `lead_meta_compra` fica como está** (continua a criar a linha em `leads`, a ficha e o estado). **Tudo o resto usa
só `contactos`**: o fluxo 01 (ler e marcar) e a leitura do template pela Matilde. A migração do RPC e da ficha/estado da
Matilde fica fora desta fase.

**Progresso:** P1 (backend) implementado a 15/10, 350 testes, por deployar. P2–P4 (n8n, SQL, docs) por fazer, à espera das
decisões 1–3 abaixo.

## Estado atual (medido a 15/10)

O fluxo 01 **lê** de `leads` (`tipo`, `telefone`, `ficha.aceita_whatsapp`, `template_enviado_em`, `imovel_ref`,
`contacto_humano_em`) e **escreve** em `leads` (`template_enviado`, `template_enviado_em`, `estado='contactada'`).
Nunca toca em `contactos`. Desde 13/10 a campanha de compra voltou: 3 leads novas, cada uma com linha em `leads` **e**
em `contactos` (o RPC `lead_meta_compra` escreve nas duas) — e nas 3, `contactos.template_enviado_em` está vazio.

Consequências já ativas:
1. `guards.contacto_meta_aberto(telefone, "comprador")` exige `template_enviado_em` em `contactos` → devolve nada →
   o fim de turno da Matilde **nunca marca `contactos.respondeu_em`**.
2. Os follow-ups da Matilde (72 h, hoje inativos no n8n) leem `contactos`; reativados, não veriam nem o template nem a resposta.

## O que `contactos` tem e não tem (colunas verificadas)

| Fluxo 01 precisa de | Em `contactos` |
|---|---|
| telefone, nome, `imovel_ref` | `telefone`, `telemovel`, `nome`, `imovel_ref` ✅ |
| consentimento (`ficha.aceita_whatsapp`, texto) | só `whatsapp_permissao` (booleano; o RPC decide como o calcula — **o da angariação aceitava qualquer resposta**) ⚠️ |
| idempotência (`template_enviado_em`) | `template_enviado_em` ✅ |
| `tipo` compra/arrendamento | `tipo_contacto=['comprador']` ✅ (sem distinguir arrendamento) |
| travão `contacto_humano_em` (consultora falou) | **não existe** ❌ (vive em `leads`, escrito pelo painel) |
| `estado='contactada'` | `contactos.estado` existe mas com outro vocabulário; o estado da lead vive em `leads` |
| `ficha` (orçamento/zona do formulário) | **não existe** — a Matilde continua a ler `leads.ficha` |

## Proposta

### P1. Backend primeiro: a Matilde lê o template de `contactos` (`engine._contexto_inicial`)
Hoje o A1 lê `lead["template_enviado"]` de `leads` para saber que já se apresentou. Se o fluxo deixar de o escrever em
`leads`, ela volta a apresentar-se por cima do template. Passa a usar o mesmo padrão da Inês
(`contacto_meta_aberto(telefone, "comprador")` → `template_enviado`), **com fallback para `leads.template_enviado`**
(as 155 leads antigas e as 3 de 13–15/10 só o têm lá). `leads` continua a ser lido para a ficha e o `imovel_ref`.
**Deploy antes de mexer no n8n.**

### P2. Fluxo 01 passa a ler e a escrever só `contactos`
- **Ler**: tabela `contactos`, `meta_lead_id=eq.…`, `select=id,nome,telefone,imovel_ref,whatsapp_permissao,template_enviado_em`.
- **Guardas**: telefone não vazio; consentimento (decisão 2); `template_enviado_em` vazio (tipo `string`); lead encontrada (`id`
  não vazio — sem isto o nó seguinte não consegue marcar). Cai o "só compra/arrendamento" (o fluxo só é chamado pelo ramo da compra).
- **Marcar enviado**: `contactos` por `meta_lead_id` (`template_enviado`, `template_enviado_em`), como o Recrutamento.
  **Deixa de escrever em `leads`** (`template_enviado`, `estado='contactada'`, `atualizado_em`).
- O resto (Ler imóvel, Resumo do imóvel, texto, Send template) não muda. Telefone vem de `contactos.telefone`
  (9 dígitos → o nó já converte para E.164).

### P3. Consentimento: passar a resposta crua, como nos outros fluxos (decisão 2)
O ramo da compra do "Meta leads to supabase" passa `whatsapp_optin` (a resposta `whatsapp_contact` do formulário) ao
fluxo 01, que o valida com `startsWith('sim')` — igual a Angariação e Recrutamento. Não se confia em `whatsapp_permissao`
enquanto não se souber como o RPC `lead_meta_compra` o calcula (o de angariação marcava `True` a quem recusava).

### P4. Dados e docs
- **SQL (corres tu)**: copiar para `contactos` o template das 3 leads já enviadas:
  `update contactos c set template_enviado = l.template_enviado, template_enviado_em = l.template_enviado_em
  from leads l where c.meta_lead_id = l.meta_lead_id and c.template_enviado_em is null and l.template_enviado_em is not null;`
  (esperado: 3).
- `docs/n8n/01-enviar-template.json` e `docs/n8n/README.md` refletem o fluxo novo; `test_n8n_guardas.py` passa a verificar
  que o 01 só usa `contactos` e que o consentimento é `startsWith('sim')`.

## Consequências a aceitar
- **`leads.estado` fica `nova` depois do template** (antes passava a `contactada`). `lead_aberta`, o nudge e a promoção
  no fim de turno já contam `nova`; o painel de Leads mostra "nova" para leads que já receberam o template.
- **Sem o travão `contacto_humano_em`** no 01 (decisão 1). O 01 dispara em ~2 s (mediana 0 h nas 150 leads de
  compra com template), por isso ninguém da equipa chega a falar antes; o travão existia por causa do atraso de ~12 h
  que **não se confirmou** (`CLAUDE.md`, "Matilde sem leads novas"). Os follow-ups (inativos) é que precisarão dele.
- As 308 leads de compra antigas **não têm linha em `contactos`**: o fluxo 02 (backfill, inativo) não as encontraria.

## Fora desta fase
- Migrar a Matilde por inteiro para `contactos` (ficha, estado, `contacto_humano_em`): é a migração maior já registada
  nos "por fazer", sem plano.
- Reativar os follow-ups da Matilde e os fluxos 02/03.
- Pôr `contacto_humano_em` em `contactos`.

## Testes
1. P1 (backend): A1 com contacto em `contactos` com template → entra como mensagem do assistente e diz que já se
   apresentou; sem contacto → fallback `leads.template_enviado`; nenhum dos dois → como hoje.
2. P4: `test_n8n_guardas.py` (01 só lê/escreve `contactos`; consentimento por prefixo; tipo `string` nos timestamps; ligações a nós que existem).

## Ordem e risco
1. Plano aprovado → 2. P1 (backend, com testes) → deploy → 3. SQL do P4 → 4. P2 e P3 no n8n (editar com o fluxo
**fechado** no browser; só a versão publicada corre) → 5. testar sem enviar WhatsApp (execução manual só até ao "Send
template", **nunca** com lead real) e confirmar na próxima lead real.
Risco: mexe num fluxo que envia WhatsApp reais. A ordem (backend primeiro, fallback para `leads`) evita que a Matilde se
apresente duas vezes; a guarda "lead encontrada" evita enviar sem conseguir marcar.

## Decisões por confirmar
1. **`contacto_humano_em`**: largar o travão no 01 (proposta) ou acrescentar a coluna a `contactos` (migration + painel)?
2. **Consentimento**: resposta crua (`startsWith('sim')`) passada pelo "Meta leads to supabase" (proposta) ou `whatsapp_permissao`?
3. **`leads.estado` fica `nova`** após o template: aceitas?
4. Fazer P1 já (backend) e deixar o n8n para depois do deploy, como na ordem proposta?
