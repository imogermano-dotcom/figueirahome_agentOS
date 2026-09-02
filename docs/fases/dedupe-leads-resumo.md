# Resumo — lead duplicada por falta de dedupe por telefone/email

> Achado a investigar uma pergunta directa do utilizador sobre uma lead no
> painel (2026-09-02). Bug pequeno e isolado, sem plano prévio — mesmo
> padrão da correcção do "Isabel Braga" (handoff 31/08): investigar,
> corrigir, documentar.

## O bug

`_criar_lead_se_preciso` (`tools.py`) só verificava se já havia lead aberta
por `cliente_id`. Uma lead do funil da Meta nasce **sem** `cliente_id` — só
o ganha quando `_promover_lead` qualifica o MQL por completo (`tipo_interesse`
+ `orcamento` + `zona_preferida`), o que a maioria das conversas nunca
atinge. Resultado: alguém que já tinha uma lead `contactada` do próprio
anúncio ganhava uma **segunda lead, à parte**, sempre que uma conversa nova
com o A1 fechava com `tipo_interesse` preenchido (o fecho normal da
conversa, via `guardar_dados_cliente`).

Confirmado com um caso real: **Carla Emeleana** (962467128) tinha uma lead
de 22/08 vinda da Meta (`meta_lead_id`, `cliente_id` nulo). A 01/09 voltou a
escrever, a conversa fechou normalmente, e nasceu uma segunda lead — sem
`meta_lead_id`, sem histórico, ligada a um `cliente_id` que a primeira nunca
teve. No painel apareciam como duas pessoas.

## O fix

`_criar_lead_se_preciso` passa a procurar lead aberta por **telefone → email
→ cliente_id**, a mesma ordem de prioridade do dedup de clientes
(`_procurar_cliente`, spec §2.7). Encontrando uma lead sem `cliente_id`,
**liga-a** em vez de criar uma nova. Só cria quando não há nenhuma.

Passou a receber o `cliente` inteiro (não só o `id`), porque precisa do
telefone/email para procurar — mudança de assinatura, testes ajustados.

## Dados de produção corrigidos

Ligação manual feita para o caso real encontrado: `cliente_id` da Carla
ligado à lead original de 22/08 (a que tem `meta_lead_id`), notas fundidas,
a lead duplicada de 01/09 apagada. Não foi feita varredura ao resto da
tabela `leads` à procura de outros duplicados antigos — este fix trava
duplicados **novos**, não desfaz os que já existiam antes dele.

## Testes

`test_leads_api.py`: `test_assistente_nao_reabre_lead_ja_aberta` ajustado
para uma lead já ligada; novo
`test_assistente_liga_cliente_a_lead_da_meta_em_vez_de_duplicar` replica o
caso da Carla (lead sem `cliente_id`, encontrada por telefone, liga em vez
de duplicar). Suite: **237** (era 236).

## Ficheiros

- `backend/app/agents/broker/tools.py` — `_criar_lead_se_preciso` e o
  import de `normalizar_email`/`variantes_telefone`.
- `backend/tests/test_leads_api.py`.
