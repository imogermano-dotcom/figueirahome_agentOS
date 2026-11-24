# Notas pela API do eGO — rotina diária (A2.3, pedido #8, 24/11)

Continuação de `ego-api-notas-plano.md` (passos 1 e 2 feitos a 31/10). **Plano antes de código.** Nada deste plano está implementado.

## Problema
O cron das 04:17 UTC já lê as notas das ativas pela API (`oportunidades_sync.reconciliar_notas`, janela de 3 dias) mas só **conta**: `NOTAS_API_EGO`
vazio no Fly. Desde 18/11 devolve `por_gravar: 0`, por isso hoje não falta nenhuma nota (o relatório das 03:37 e o pipeline do portal cobrem-nas).
Fica desligado porque cada INSERT em `notas` dispara `tgr_classify_lead` e `tgr_extract_prefs` (`AFTER INSERT … FOR EACH ROW`, `net.http_post`) e,
com N notas da mesma oportunidade, o `extract-preferences` corre N vezes em paralelo e as execuções apagam e reescrevem
`oportunidade_preferencias` umas contra as outras (o debounce só olha para `pref_ai_processado_em`, carimbado no fim). Pergunta do Miguel de 24/11:
«as notas estão a ser importadas pela API nova?» — não, de propósito, e isto é o que falta para ligar.

## Decisão (24/11)
**Escolha 1: os triggers ficam como estão.** Aceita-se a corrida e corrige-se a seguir: depois de `gravar`, uma chamada
`extract-preferences` com `{"oportunidade_ref", "force": true}` **por oportunidade afetada**, em sequência (nunca em paralelo), que repõe o
resultado certo. Volume baixo (31/10: 341 notas em 163 oportunidades, em meses; por dia serão poucas). Rejeitada a escolha 2 (`disable trigger`
durante a gravação): é SQL do utilizador e, se o cron falhar a meio, os triggers ficam desligados.

## O que se muda
1. `ego_notas.gravar` devolve também as `refs` com notas inseridas.
2. Nova função `ego_notas.reprocessar(refs)`: POST sequencial à edge function com `{"oportunidade_ref", "force": true}`, tolera falhas por
   oportunidade (conta-as, não levanta), máx. 30 por volta (o resto fica para o dia seguinte e conta-se). `reconciliar_notas` chama-a depois de gravar e acrescenta
   `reprocessadas`/`reprocessar_erros` ao resumo.
3. Interruptor novo `NOTAS_REPROCESSAR` (vazio = só grava, como hoje) para ligar a gravação e o reprocessamento em dois tempos.

## Por confirmar antes de código (bloqueia o ponto 2)
A edge function `extract-preferences` é do Miguel, **fora do repo**. Sei, pelo registo de 31/10, que aceita `{"oportunidade_ref","force":true}`, mas
**não está escrito no repo o URL nem a autenticação** (o Fly só tem `SUPABASE_URL`/`SUPABASE_SECRET_KEY`). Confirmar, só em leitura, como chamei as
163 a 31/10 e se `POST {SUPABASE_URL}/functions/v1/extract-preferences` com a chave de serviço serve. Se não servir, pedir ao Miguel o URL/segredo
(ou uma RPC `reprocessar_preferencias(ref)` que faça o `net.http_post` do lado da base, que não precisa de segredo nosso).

## O que não muda
Só INSERT em `notas` (nunca apaga nem edita); dedup por `nota_ego_id` e pela chave `(ref, dia, texto)`; sem `InsertNote`/`UpdateNote` no eGO;
relatório das 03:37 e pipeline do portal continuam (retirá-los é a F3, à parte); arquivadas e notas antigas de fora.

## Prova
- Teste de `reprocessar`: só as `refs` com notas inseridas, em sequência, uma falha não pára as seguintes, respeita o máximo de 30 (sem rede, `httpx.MockTransport`).
- Teste de `reconciliar_notas`: interruptor desligado = não chama; ligado = chama depois de gravar e conta no resumo.
- Dry-run em produção (só leitura): `por_gravar` e `refs` afetadas; esperado ≈ 0 (nada falta hoje).
- 1.ª gravação real observada: `agente_sync_log` `egorealestate_notas_api` e `oportunidade_preferencias` das refs afetadas com `pref_ai_processado_em` posterior.

## Passos (cada um com OK próprio)
1. Confirmar em leitura como chamar a edge function (ponto acima); se não der, perguntar ao Miguel.
2. Código e testes (`reprocessar`, interruptor, resumo), sem tocar em produção.
3. Commit, push e deploy.
4. Ligar `NOTAS_API_EGO=1` e `NOTAS_REPROCESSAR=1` no Fly (`flyctl secrets deploy`).
5. Observar o cron das 04:17 seguinte (`gravadas`, `reprocessadas`, erros, sem duplicados) e responder ao Miguel.

## Riscos
- Durante a janela entre os INSERT e o `force`, as preferências da oportunidade podem estar a meio (segundos). Aceite.
- A edge function falhar ou mudar de contrato: o cron regista o erro e continua; as preferências ficam como a corrida as deixou até ao dia seguinte (`por_gravar` já será 0: nesse caso reprocessa-se à mão com `scripts/ego_api_notas.py`).
- Reprocessar custa uma chamada de Sonnet por oportunidade afetada: custo baixo, dependente do volume de notas novas.

## Decisão final (24/11): 1 nota por oportunidade e por volta, em vez do `force`
Mais simples e sem depender da função do Miguel: `ego_notas.uma_por_oportunidade` grava a mais antiga de cada oportunidade em cada volta do cron (04:17) e adia as outras
(`adiadas` no resumo); cada INSERT corre sozinho, sem execuções paralelas do `extract-preferences`. A janela de `reconciliar_notas` sobe de 3 para 7 dias para as
adiadas não saírem dela. Juntar notas numa linha rejeitado: perde autor/data por nota e parte o dedup por `nota_ego_id`. **Fica por fazer, só se o atraso incomodar:** o `force`
por oportunidade (secções acima), que depende de saber como chamar a função (URL/auth). O resto do plano (`reprocessar`, `NOTAS_REPROCESSAR`) **não se implementa**.
Passos que faltam: deploy; `NOTAS_API_EGO=1` no Fly (`secrets deploy`); ver o cron das 04:17 seguinte (`gravadas`, `adiadas`, `erros`).
