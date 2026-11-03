# Tarefas dos agentes que ninguém vê — plano (03/11/2026)

> Estado: **plano, nada implementado.** Pedido do utilizador depois da verificação diária de 03/11.

## Problema

`agente_tarefas` recebe escaladas (`escalar`), pedidos de visita (`visita`) e avisos «Lead qualificada pelo assistente… Criar o contacto no eGO…». **Ninguém abre essa tabela**: a equipa vê o eGO e o Supabase pelo portal do Miguel, não o painel dos agentes. Na prática o único canal é o email do momento.

Medido a 03/11 (últimas 60 tarefas): `responsavel` vazio em todas (nenhum código o preenche — não é sinal de nada); ~25 `escalar` de recrutamento pendentes desde 03/10; 11 «Criar o contacto no eGO…» pendentes desde 08/10, mesmo as de compradores Meta cuja lead o cron `leads-compra-para-ego` já criou. Ruído e falta de sinal ao mesmo tempo.

## Fora de âmbito

- Criar tarefas no eGO (escrita no eGO só por ordem expressa; endpoint por estudar).
- Vista de `agente_tarefas` no portal do Miguel (pede-se-lhe em paralelo; do nosso lado é só dar-lhe a tabela).
- Preencher `responsavel` / reatribuir.
- Migration: **nenhuma** (`tipo` e `estado` são `text`; `conversa_id`, `agente`, `motivo` já existem).

## Parte A — fechar sozinha a tarefa «Criar o contacto no eGO»

1. **Marcar a tarefa na origem.** `guards._promover_lead` (`guards.py` ~327) passa a gravar `tipo='lead_ego'` e `agente`. Hoje nasce sem `tipo`, por isso nada a distingue.
2. **Fechar ao marcar a lead.** Em `leads_para_ego.processar`, quando se grava `ego_lead_em` (nos dois casos: criada agora **e** `ja_existiam`), `concluida` em todas as `agente_tarefas` `pendente` com `tipo='lead_ego'` e `titulo = "<_TAREFA_QUALIFICADA> — <quem>"` para `quem` ∈ {nome, telefone, email} da linha. Função pura `fechar_tarefas_da_lead(linha)` em `leads_para_ego.py`; falha só regista (nunca impede a marca `ego_lead_em`).
   - `ponytail`: a chave é o título (como o dedup de 24 h em `_promover_lead`). Duas pessoas com o mesmo nome e sem telefone partilhariam o fecho. Se acontecer, coluna `contacto_id` em `agente_tarefas`.
3. **O que fica de fora de propósito:** leads de venda/assistente sem `meta_lead_id` nunca têm `ego_lead_em`; essas tarefas ficam pendentes e são o conteúdo útil do resumo.
4. **Limpeza do histórico (uma vez, à parte, com OK expresso).** Script em `backend/scripts/` com `--dry` por omissão: tarefas `pendente` com título `Lead qualificada —%` sem `tipo`, cruzadas por nome/telefone/email com `contactos.ego_lead_em`. Mostra a lista (só iniciais/ids) e só escreve com `--aplicar`. As restantes ficam.

## Parte B — resumo diário das pendentes

1. **Endpoint** `POST /api/tarefas/pendentes/resumo` (`require_automacao_access`, como `whatsapp_falhas.py`; em `app/api/tarefas.py`). `?dry=1` devolve o texto sem enviar.
2. **Seleção:** `estado='pendente'`, `tipo` ∈ {`escalar`, `visita`, `lead_ego`}, `criado_em` entre 12 h e **7 dias** atrás (a de menos de 12 h já foi avisada por email; a janela impede que o histórico repita para sempre). As mais antigas entram numa só linha («+N fora da janela»).
3. **Texto:** agrupado por assistente (compra/visita, recrutamento, angariação, geral), uma linha por tarefa: idade, motivo, `imovel_ref`, quem. Email interno (os emails de escalada já levam nome e telefone). Só envia se houver linhas; assunto «Tarefas por tratar: N».
4. **Envio:** `notificar(...)` para os `notificacoes_para`; os `ALERTAS_PARA` (`para_extra=_alertas_extra()`) só se a decisão 3 for sim.
5. **Cron** `resumo-tarefas-pendentes` em `crons/schedules.json`, diário 09:07 UTC (≈ 09:07/10:07 Lisboa), registado `enabled: false` e ligado depois de 1 corrida manual com `?dry=1` e de ver o email real. Segue `cron-manager-fly-resumo.md`.
6. **Testes** (`backend/tests/test_tarefas_pendentes.py`): janela (11 h fora, 13 h dentro, 8 dias fora), tipos, agrupamento, sem linhas → não envia; `fechar_tarefas_da_lead` fecha por nome/telefone/email, ignora `escalar`, não fecha outra pessoa.

## Ordem e rollout

1. Parte A (código + testes) → deploy **só com autorização** → correr o script de histórico em `--dry`, mostrar, esperar OK, `--aplicar`.
2. Parte B (código + testes) → deploy → `?dry=1` em produção → registar o cron desligado → ligar.
3. Atualizar `CLAUDE.md` e `docs/decisoes.md` («tarefas = lembrete por email, não fila»), `docs/api-spec.md`.

## Riscos / medir

- Quem fecha as `escalar`? Hoje ninguém (o painel não é aberto). O resumo repete 7 dias e expira: **não fecha nada**. Se quiserem fechar, é pelo painel ou a pedido. Medir: nº de pendentes na janela por semana.
- Fecho por título pode falhar silenciosamente → medir `lead_ego` pendentes cujo contacto já tem `ego_lead_em` (deve ser 0).
- O resumo depende de a Resend funcionar (`notificar` engole erros): sem email, continua tudo invisível. A verificação diária passa a incluir «pendentes na janela».

## Decisões para o utilizador

1. Janela de 7 dias e mínimo de 12 h estão bem?
2. Hora do resumo (09:07 UTC) e se inclui fins de semana (13 de 17 conversas reais foram ao fim de semana → sim por omissão).
3. Destinatários: só `notificacoes_para` (Miguel) ou também os `ALERTAS_PARA`?
4. Aplicar a limpeza do histórico (Parte A.4) — quando?
