# Handoff 18–20/09 — A1 sem agendamento, envio Recrutamento, infra

## A1 já não agenda visita

Pedido do utilizador: o A1 deixa de negociar horário. `agendar_visita` →
**`pedir_visita`** (`tools.py`): regista o pedido, garante lead (chama
`_criar_lead_se_preciso` — fechava um buraco real: `pedir_visita` criava
`agente_clientes` mas nunca `leads`, só `guardar_dados_cliente` chamava essa
função, e uma conversa podia pedir visita sem alguma vez passar por lá,
achado a analisar conversas reais em produção), mantém a guarda dos 80% e o
aviso por email (director + consultora do imóvel, já existia em
`notificacoes.py`). Prompt do A1 (`assistants.py`) já não propõe horários —
diz que a consultora entra em contacto directamente. Testado ao vivo (site,
"Alexandra") depois de deployado: lead criada, sem hora nenhuma na resposta.
Commit `17cff59`.

## Bug de filtro no log de sincronização

`agente_sync_log` é partilhada por 5+ automações (`egorealestate_api/crm`,
`egorealestate_oportunidades_completo`, `nudge_matilde`, `site_uptime`). O
`GET /api/imoveis/sync/log` lia a tabela **sem filtrar por `tipo`** — o
painel "Sincronização API" misturava tudo. Como `nudge_matilde`/`site_uptime`
não têm os campos `criados`/`atualizados`/`corrigidos`/`não_publicados`,
React renderizava `undefined` como nada — pareciam execuções fantasma
"(cron)" sem números. O `DELETE` tinha o mesmo problema: "Apagar histórico"
apagava o de todas as automações, não só imóveis (nunca chegou a ser
clicado). Os dois ganharam `.eq("tipo", "egorealestate_api")`. Commit
`281d1ec`.

## Crons atrasados 4-5h — desviados do minuto 0

`sync-imoveis` (`0 6`/`0 13`), `sync-oportunidades` (`0 3`) e `nudge-matilde`
(`0 * * * *`) disparavam sempre no minuto exacto — o GitHub avisa
oficialmente que é o pico de carga global de crons, e confirmámos 4-5h de
atraso constante em todas as corridas de 15–19/09 (`gh run list`). Desviados
para minutos 17/23/37/12; `site-uptime` (`*/5`) fica, o tick seguinte
absorve sozinho. Commit `fb8bd14`.

## `contactos` ganhou `id`

Primeiro passo do pedido "uniformizar leads → todas em `contactos`,
independente da origem" (plano completo, ainda por decidir entre 3 opções:
`docs/fases/contactos-unificado-assistentes-plano.md`). `contactos` tinha PK
composta `(nome, criado_em)` e nenhuma coluna própria para se referir a uma
linha de forma estável — bloqueador para ligar `leads`/tarefas lá. Aditivo,
PK antiga intacta (é provavelmente o `ON CONFLICT` do upsert do Miguel):

```sql
ALTER TABLE contactos ADD COLUMN id uuid NOT NULL DEFAULT uuid_generate_v4();
ALTER TABLE contactos ADD CONSTRAINT contactos_id_unique UNIQUE (id);
```

Corrido pelo utilizador, confirmado nas ~28 401 linhas existentes. Nenhum
outro passo do plano foi aplicado — falta decidir opção A/B/C.

## Fluxo de envio Recrutamento — construído e testado

Completa o que ficou deliberadamente por fazer em 14–17/09
(`leads-meta-n8n-resumo.md`, "só o RPC e routing feitos"). Template aprovado
na Meta: `figueirahome_lead_recruta|pt_PT`, persona "Inês". Nova workflow
n8n **`FigueiraHome — enviar template Recrutamento`** (`WkuMB0fnVY1mc6Re`,
pasta "Fluxos para a Inês"), mesmo padrão da Angariação: lê `contactos` por
`meta_lead_id`, guarda (telefone + opt-in WhatsApp + ainda não contactado —
`template_enviado_em` comparado como `type: "string"`, não `"object"`, para
não repetir o bug do `01`), envia o template, marca `template_enviado(_em)`.
Ligada ao `Meta leads to supabase` via novo nó `Enviar template
(Recrutamento)`, a seguir a `Supabase: criar lead recrutamento`. Activada.

**Testada sem lead real** (só o Miguel tem acesso à ferramenta de teste de
leads da Meta): `contactos` de teste inserido directo (`meta_lead_id:
teste-recruta-001`), workflow filha disparada via pin data no
`Execute Workflow Trigger` na UI do n8n (não pelo webhook da Meta — sem
acesso à Graph API para um `meta_lead_id` inventado). WhatsApp real entregue
ao utilizador, `template_enviado_em` gravado, texto conferido. Registo de
teste apagado a seguir. Fluxo ponta-a-ponta pelo webhook real continua por
confirmar — só quando chegar a 1.ª candidatura real.

## Por fazer

- Confirmar amanhã se os crons desviados (17/23/37/12) deixaram de atrasar.
- Decidir opção A/B/C do plano `contactos` unificado (ver plano).
- Testar Recrutamento ponta-a-ponta com candidatura real da Meta.
