# Vigia das leads da Meta — plano (03/11/2026)

> Estado: **Fase 1 implementada e ativa a 03/11** (`b924f1b`; fluxo n8n `v03lokXyOY0r7JWO`), mas **por contagens da conta de anúncios** (sem acesso à página, não há ids): ver `docs/decisoes.md`. Fase 2 (opt-in sem template e comprador sem lead no eGO) por fazer. 1.º aviso real por ver.

## Incidente que motiva isto

Nos testes de segurança do webhook (02/11), o cenário do Make ficou desligado por distração. Entre as 21:29 de 02/11 e as 19:43 de 03/11 **nenhuma chamada do Make chegou ao n8n**; às 19:43 entraram 12 de uma vez (backlog do Make). 8 leads de compradores receberam o template 0,5 a 21,4 h depois de preencherem o formulário (medido em `contactos.meta_created_at` → `template_enviado_em`). A premissa do projeto é «a lead responde na 1.ª hora ou nunca» (16 de 17).

**Nada avisou.** `verificacao_diaria.py leads` tem o alarme `optin_sem_template>1h`, mas só corre quando alguém o chama, e **não apanharia este caso**: as leads nunca chegaram ao Supabase.

## O que cada falha deixa à vista

| Onde se perde | Sinal no Supabase | Já há alarme? |
|---|---|---|
| Meta → Make → n8n (Make parado, erro de autenticação, n8n em baixo) | **nenhum** (a lead não existe) | não |
| n8n → Supabase (RPC falha, filtro de teste engole) | nenhum | só o erro do n8n, se alguém o vir |
| Supabase → template (opt-in, sem `template_enviado_em`) | `whatsapp_permissao` sem template | só na verificação diária |
| Supabase → eGO (`ego_lead_em` vazio) | comprador Meta sem `ego_lead_em` | só na verificação diária; o cron regista `warning` nos logs |

O buraco grande é o primeiro: a única fonte que sabe quantas leads existem é a **Meta**.

## Desenho

### Fase 1 — Reconciliação com a Meta (a que teria apanhado o incidente)

1. **n8n** (fluxo novo, a cada 30 min): lista na Graph API as leads dos últimos 120 min (`/{form_id}/leads`, filtro `time_created`) dos formulários ativos e envia só os ids ao backend. O n8n já tem credencial Meta (o nó `Meta Lead Info` lê `/{lead_id}`); **por confirmar** que essa credencial também lista leads (`leads_retrieval`) e quantos formulários há (um por anúncio, ex.: «FRM T4 FH2572»).
2. **Backend** `POST /api/leads/meta/reconciliar` (`X-N8N-Secret`, como a recusa): recebe `{ids: [...]}`, compara com `contactos.meta_lead_id` e `leads.meta_lead_id`, devolve os que faltam há mais de 15 min (margem para o fluxo normal) e, se houver, manda **email** ao `notificacoes_para` + `ALERTAS_PARA` («N leads da Meta não chegaram ao Supabase», com ids e hora; nunca nome/telefone no assunto). Alerta repetido no máximo de 2 em 2 h (registo em `agente_sync_log`, tipo `vigia_leads`).
3. **Não reinjeta sozinho** nesta fase: reprocessar uma lead pelo webhook cria contacto e envia template, e o ramo de recusa pode repetir email/criação no eGO. A reinjeção manual (colar os ids no webhook) fica documentada; a automática é decisão tua depois de veres o alerta a funcionar.
4. Testes do diff (faltam/chegaram/margem/dedup do alerta) sem rede.

### Fase 2 — Alarmes dentro do Supabase (tudo no repo, um deploy)

Cron `vigia-leads-meta` de 15 em 15 min → `POST /api/leads/meta/vigia` (`X-Automacao-Secret`), `?dry=1` devolve o texto sem enviar. Dois alarmes, mesmo email/dedup da Fase 1:
1. **Opt-in sem template há mais de 1 h** (mesma regra de `verificacao_diaria.py leads`; exclui `whatsapp_falhou_em` e `nao_contactar_em`).
2. **Comprador Meta sem `ego_lead_em`** passadas 4 h de `meta_created_at` (2 h de espera do cron + margem) **e dentro das 9h–20h**; o email diz o motivo provável (sem email, sem consultora, fora do horário) em vez de só contar.

### Fica de fora

- Heartbeat «sem leads há N horas»: ruidoso (as leads chegam em rajadas e há intervalos normais de 3 h; mediu-se a 03/11) e só apanharia o Make parado depois de horas. A Fase 1 apanha-o em ≤ 45 min e com os ids.
- Reinjeção automática; vista no portal do Miguel; alterar o Make (monitorizar o Make em si, ex. alerta de cenário desligado, é configuração dele, fora do repo).

## Ordem e rollout

1. **Sondagem em leitura no n8n**: a credencial Meta lista leads? quantos formulários? (sem escrever nada).
2. Fase 1: endpoint + testes → deploy (com OK) → fluxo n8n criado **desativado**, corrido à mão, comparar com o Supabase → ativar.
3. Fase 2: endpoint + cron registado `enabled: false` → `?dry=1` → ligar.
4. Atualizar `CLAUDE.md`, `docs/decisoes.md`, `docs/api-spec.md`, a skill `verificacao-diaria` (passa a ver o último alerta) e `docs/n8n/README.md`.

## Riscos

- **O próprio vigia pode falhar em silêncio** (cron parado, n8n em baixo): o email diz sempre «verificado às HH:MM» quando há alerta, mas a ausência de alerta não prova nada. Mitigação: a verificação diária confirma o registo `vigia_leads` mais recente (≤ 45 min).
- **Falso alarme** de lead filtrada como teste (`Filtrar leads de teste`): o backend ignora ids que o n8n reporta como filtrados ou o diff compara só leads com `is_organic=false`/não de teste — por decidir na sondagem.
- **Segredo do webhook visível** nos dados das execuções do n8n (visto a 03/11); o fluxo novo não pode repetir isso: não guardar dados de execução com cabeçalhos.

## Decisões para o utilizador

1. Fase 1 primeiro (recomendo) ou Fase 2 primeiro?
2. Margem de 15 min e alerta repetido de 2 em 2 h: bem?
3. Destinatários: `notificacoes_para` + `ALERTAS_PARA` (é falha do sistema, como os syncs) ou só o Miguel?
4. Reinjeção das leads em falta: manual (proposto) ou automática depois?

## Aviso quando o próprio vigia falha (10/11/2026, `dcc07c6`, deploy v213, fluxo n8n editado ao vivo)

**Incidente:** o token da credencial n8n «Facebook Figueira Home» (colado à mão a 08/09, ~60 dias) deixou de ser aceite a 09/11
(`OAuthException 190/492`); o vigia falhou de 30 em 30 min durante ~1 dia **sem ninguém saber**, e o webhook do Make também deixou
de receber leads (a ligação ao Facebook do Make expirou na mesma altura): 5 leads da Meta de 09–10/11 não entraram no Supabase.
O nó `Meta Lead Info` do fluxo principal usa a MESMA credencial, por isso um token morto pára as leads à entrada.

**Aviso (revisto no mesmo dia):** `continueErrorOutput` fazia a execução acabar como `success` e escondia a falha; ficou o **Error Workflow** do n8n. Workflow «Alerta de falhas (Error Workflow)» (`RWtN895PmrN8Igai`, `Error Trigger` → `POST /api/n8n/falhou`, `X-N8N-Secret`, `?dry=1`), ligado em «Definições → Error Workflow» ao vigia, ao «Meta leads to supabase» e aos follow-ups 24h/72h da Matilde.
O backend (`notificacoes.falha_de_workflow`, `6eed923`, v214) manda email a `notificacoes_para` + `ALERTAS_PARA`, **1 por fluxo em 12 h**, e regista `n8n_falha` em `agente_sync_log`. **Provado a 10/11 com «Execute workflow» no «Alerta de falhas» (email recebido, `n8n_falha` registado); ainda sem uma falha espontânea.** Limites: backend em baixo = sem email; n8n parado ou fluxo desligado não se detetam.

**Prevenção:** lembrete aos ~50 dias para reautenticar a ligação do Make; token do n8n de utilizador do sistema (não expira).
