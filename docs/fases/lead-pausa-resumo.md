# Resumo — novo estado `pausa` para leads (28/09)

Achado ao analisar a última conversa da Matilde: Sandra Nascimento respondeu
ao template antigo a dizer que tem problema de saúde grave em família (mãe na
UTI, Brasil) e pediu para suspender o interesse por 60 dias. Matilde respondeu
bem, com empatia — mas não havia tool nenhuma que coubesse (não é `engano`,
não é `sem_interesse`, ela quer continuar, só não agora). Sem tool, sem
escrita: `leads.estado` ficou `"contactada"`, e dentro de ~2h o nudge ia
mandar-lhe "Ainda está interessado?" outra vez — o oposto do que ela pediu.

Cruzando os dados descobriu-se ainda que a mesma pessoa é lead dupla: também
tem um `contactos` de recrutamento (A3), com sequência de follow-up própria e
activa — mandou-lhe um template de "última tentativa" no mesmo dia. Fora de
âmbito aqui (ligado à limpeza de duplicados já planeada,
`docs/fases/contactos-unificado-assistentes-plano.md`) — só o lado `leads`
(A1) foi tratado.

## Fix

- `app/models/lead.py` — `ESTADOS` ganha `"pausa"`. Fica **fora** de
  `ESTADOS_FECHADOS` de propósito (mesmo princípio do `sem_resposta`): a
  pessoa continua interessada, fechar quebrava `lead_aberta` e ela chegava ao
  A2 sem contexto do imóvel quando voltasse a escrever.
- `guards.py` — `pausa` entra em `_ESTADOS_LEAD_ABERTA` (routing/dedup
  continuam a reconhecê-la) e em `_MOTIVOS_ENCERRAMENTO` (a tool já a aceita,
  mesma escrita que `engano`/`sem_interesse` — só o estado muda).
- `tools.py` — `encerrar_lead` ganha `"pausa"` no enum de `motivo`, descrição
  actualizada a explicar quando usar cada um dos 3.
- `nudge.py` — `_pode_enviar_a1` recusa explicitamente quando
  `estado == "pausa"` (não está em `ESTADOS_FECHADOS`, por isso precisa de
  verificação própria, à parte da dos fechados).

## Limitação conhecida, não corrigida

`guards._JANELA_LEAD_DIAS = 30` — `lead_aberta()` só olha para leads com
`criado_em` nos últimos 30 dias. A lead da Sandra é de 03/09; se ela só voltar
a escrever depois de ~60 dias (o que ela pediu), essa janela já a esconde de
qualquer forma, independentemente do fix da `pausa`. Não alterado agora —
afectaria todas as leads, não só as pausadas, decisão maior a tomar à parte.

## Aplicado em produção

`leads.estado` da Sandra Nascimento (`351914058671`) actualizado para
`"pausa"`, nota com o motivo — via PATCH directo (Sandra já tinha o estado
antigo `"contactada"`, sem tool a correr retroactivamente).

## Testes

`test_leads_meta.py::test_pausa_regista_estado_sem_fechar`,
`test_nudge.py::test_lead_pausada_nao_recebe_nudge` — novos. Suite: **281**
(era 279).
