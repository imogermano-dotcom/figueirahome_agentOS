# Responsável nas leads Meta (pedido #17, etapa de 01/11) — plano

> Plano antes de código. Medido a 01/11 só em leitura (nada escrito). Sem nomes nem telefones de clientes.

## Pedido
Numa lead Meta de compra, o responsável é o **angariador do imóvel do anúncio**. Hoje não chega ao Supabase: `leads.responsavel` em **0 de 430** leads Meta,
`contactos.responsavel` em **22 de 325** contactos Meta. O portal calcula-o na leitura (remendo, migração `20261101_04` do lado dele) e passa a ler o valor gravado quando existir.
(a) gravar à entrada; (b) preencher as existentes; (c) só origem Meta (nas outras o responsável continua a ser o do eGO).

## Medido (01/11)
| | |
|---|---|
| `leads` Meta (`meta_lead_id` não nulo) | 430, **todas** com `imovel_ref` que existe em `imoveis` (430/430 resolvem pelo `imovel_ref`) |
| `imoveis` | 4 470 linhas, 4 231 com `angariador` (o nome tal como o eGO o escreve) |
| `contactos` Meta | 325: compradores 119, recrutamento 99, vendedor 97, fsbo 6 |
| compradores com `imovel_ref` em `contactos` | 114 resolvem; 7 sem `imovel_ref` no contacto (a `leads` tem-no, por `meta_lead_id`) |
| `contactos.responsavel` já preenchido que o angariador contradiz | 3 (1 igual, 3 diferentes): vêm do eGO (a pessoa já existia lá), ver E1 |

Recrutamento e angariação **não têm imóvel**: o pedido só se aplica às leads de **compra**.

## Onde se escreve hoje
O RPC `lead_meta_compra` (12 argumentos, versão em `supabase/migrations/0051_lead_meta_compra_consentimento.sql`) insere em `leads` (com `p_imovel_ref`) e insere ou atualiza `contactos`.
Não olha para `imoveis` nem grava `responsavel`. O n8n chama este RPC e não precisa de mudar (a assinatura mantém-se).

## Desenho
1. **Migration `0057` — o RPC grava o responsável à entrada.** Mesmo corpo da `0051` mais: `v_resp := (select angariador from imoveis where imovel_ref = p_imovel_ref)`
   (e, se a ref vier com sufixo, pela ref curta `[A-Za-z]*\d+`), e grava-o em `leads.responsavel` (sempre) e em `contactos.responsavel` (insert e update, **só onde está vazio**, E1).
   Sem imóvel em `imoveis` ou sem angariador: fica nulo (E3).
2. **Backfill (SQL, corres tu, por partes):** `leads` Meta sem responsável → angariador pelo `imovel_ref` (430); `contactos` Meta de **comprador** sem responsável → angariador pelo
   `contactos.imovel_ref` ou, se vazio, pelo `leads.imovel_ref` do mesmo `meta_lead_id`. Antes: contagem e lista dos 3 contactos que já têm outro responsável (não se tocam).
   `contactos` tem o trigger `tgr_normaliza_origem_contactos` em qualquer UPDATE: confirmar que não muda a `origem` (o valor depende de `meta_lead_id`, que não se mexe).
3. **Rede para o imóvel que chega depois** (caso FH2588 a 31/10: ainda não estava em `imoveis`): o cron `leads-compra-para-ego` (10 em 10 min) já corre sobre os contactos Meta; acrescentar-lhe um passo
   `preencher_responsavel_meta()` que preenche `responsavel` onde ainda está nulo e o imóvel já existe. Sem tocar no eGO e sem custo (uma leitura de `imoveis`). Alternativa: só a migration + backfill, sem rede.

## Decisões (tuas)
- **E1 — DECIDIDO (01/11): versão fina.** `leads.responsavel` leva sempre o angariador (a tabela está vazia, sem conflito); `contactos.responsavel` só onde está vazio. Os 3 contactos que já têm outro responsável (vindo do eGO) não se tocam e vão numa lista ao Miguel.
- **E2** — a regra vale para leads de **compra** (recrutamento e angariação não têm imóvel). Confirmar.
- **E3** — imóvel que ainda não está em `imoveis` ou sem angariador: deixar nulo e deixar a rede (passo 3) preencher depois, ou ir logo ao eGO à entrada (depende do #45 e do `GetEntity`).
- **E4** — fazer o passo 3 (rede no cron): sim / não.

## Testes
- Função SQL: casos para ref direta, ref com sufixo, imóvel inexistente, angariador vazio, `responsavel` já preenchido (não muda). Verificação por contagens (leads Meta sem responsável antes e depois, 0 divergentes mudados).
- `preencher_responsavel_meta`: só preenche nulos, só contactos Meta de comprador, nunca levanta.

## Risco
Baixo. Só preenche campos vazios; o RPC mantém a assinatura e o resto do corpo; a migration é a segunda vez que o RPC é recriado (a `0051` fez o mesmo). Cuidado a copiar o corpo inteiro da `0051` e a conferir a versão em produção antes de a substituir
(**o repo não é a fonte de verdade única do esquema**: ler a definição viva com `pg_get_functiondef` antes).

**Estado: migration e código escritos a 01/11, por correr/deployar (ordem tua).**
- E2–E4: aplicadas as propostas (só compra; imóvel em falta fica nulo; rede no cron). A função de produção lida com `pg_get_functiondef` era igual à da `0051`.
- `supabase/migrations/0057_lead_meta_compra_responsavel.sql`: partes 0 (triggers, só leitura), 1 (função), 2 (backfill `leads`), 3 (backfill `contactos`), 4 (verificação). Corre-se por partes.
- `leads_para_ego.preencher_responsavel_meta` (chamada em `processar`, depois do portão das 9h–20h) e `angariador_da_ref`; 806 testes passam.
- Por fazer: correr a `0057`; deploy do `figueirahome-agentos`; lista dos 3 contactos divergentes ao Miguel; verificar uma lead Meta nova com responsável gravado.
