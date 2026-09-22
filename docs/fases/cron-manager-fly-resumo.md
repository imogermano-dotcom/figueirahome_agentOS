# Cron Manager no Fly — resumo (22/09)

> Trabalho iterativo em conversa directa, sem plano prévio — investigação e
> construção na mesma sessão. Registo depois do facto, para o handoff.

## O problema

Pedido do utilizador: olhar aos cron jobs. Investigação com `gh run list`
contra o histórico real de execuções (não só os `.yml`) mostrou que o desvio
de minuto feito a 18-20/09 (17/23/37/12 em vez de 0) **não resolveu nada**:

| Cron | Agendado | Atraso real medido (15-22/09) |
|---|---|---|
| `sync-imoveis` (2×/dia) | 06:17 / 13:23 UTC | 3-6h40 |
| `sync-oportunidades` (1×/dia) | 03:37 UTC | 4-5h40 |
| `nudge-matilde` (hora a hora) | `:12` | corridas a 4-5h de distância — ~80% dos gatilhos perdidos |
| `site-uptime` (5/5 min) | `*/5 * * * *` | corridas a 2-6h40 de distância — >98% dos gatilhos perdidos |

Não é bug no `.yml` — é o GitHub Actions a atrasar/saltar `schedule` em repos
públicos sob carga global, sem fix do nosso lado dentro da plataforma.

## Investigação de alternativas (Fly.io)

- `flyctl machine --schedule` nativo: só `hourly/daily/weekly/monthly`,
  "fuzzy" (sem hora fixa, sem garantia de espaçamento entre 2 máquinas
  `daily`), e **não dá para disparar à mão** — não serve para os 4 casos.
- **Cron Manager** ([fly-apps/cron-manager](https://github.com/fly-apps/cron-manager)),
  recomendado nas docs do Fly para isto: app separada, `schedules.json` com
  cron syntax a sério, uma máquina efémera isolada por corrida, disparo
  manual via `cm jobs trigger <id>` (SSH). Resolve os 4 casos.
- Custo: app do Cron Manager sempre ligada (~$2/mês, shared-cpu-1x/256mb) +
  cêntimos/mês nas máquinas efémeras (facturadas ao segundo, `curl` demora
  segundos). Sem breakdown fiável por app/máquina na factura do Fly —
  confirmado, é pedido aberto da comunidade, não existe hoje.

## O que foi feito

- `crons/` — clone do `fly-apps/cron-manager` (MIT), `.git` aninhado
  removido, `fly.toml` (`app=figueirahome-crons`, `primary_region=ams`),
  `schedules.json` com os 4 jobs (mesmos comandos `curl` que os `.yml`
  já usavam, secrets via env herdado da app).
- App `figueirahome-crons` criada (org `miguel-germano`), volume `data` 1GB
  para o estado (sqlite), deployada.
- `AUTOMACAO_SECRET` **rodado** — não existia legível em lado nenhum (só
  secret write-only no Fly/GitHub desde a criação, commit `85a3465`,
  12/08). Novo valor gerado e gravado nos 3 sítios: GitHub Actions, Fly
  `figueirahome-agentos`, Fly `figueirahome-crons`.
- `FLY_API_TOKEN` do Cron Manager: token de deploy **scoped à app**
  (`fly tokens create deploy -a figueirahome-crons`), não o token pessoal —
  o pessoal dava `unauthorized` a criar máquinas (achado ao testar).

## Estado dos 5 schedules

| Nome | Agendado | Estado |
|---|---|---|
| `nudge-matilde` | `12 * * * *` | **activo**, testado (`cm jobs trigger`, exit 0) |
| `site-uptime` | `*/5 * * * *` | **activo**, testado (exit 0) |
| `sync-imoveis-manha` | `17 6 * * *` | `enabled:false` — GitHub ainda o corre |
| `sync-imoveis-tarde` | `23 13 * * *` | `enabled:false` — idem |
| `sync-oportunidades` | `37 3 * * *` | `enabled:false` — idem |

Os 3 de eGO ficam desligados de propósito: `sync-imoveis` e
`sync-oportunidades` usam a MESMA conta do eGO backoffice, e correrem juntos
já derrubou a app principal por OOM (18/08, ver `sync-oportunidades.yml`).
Activar aqui sem desligar o GitHub duplicava execuções e podia repetir isso.

`.github/workflows/nudge-matilde.yml` e `site-uptime.yml`: `schedule`
desligado (fica só `workflow_dispatch`, para correr à mão). Os outros dois
`.yml` (`sync-imoveis`, `sync-oportunidades`) **não foram tocados** — continuam
a disparar pelo GitHub até os do Fly serem confirmados e activados.

## Por fazer

- Confirmar uns dias de `nudge-matilde`/`site-uptime` no Fly (disparo real
  pelo `cron`, não só o `cm jobs trigger` manual).
- Decidir horas para `sync-imoveis`/`sync-oportunidades` no Cron Manager com
  folga suficiente entre si (o `.yml` original já tinha essa preocupação,
  ver comentário em `sync-oportunidades.yml`), activar, e só depois desligar
  o `schedule` do GitHub para esses dois.
- Ver a factura real do Fly ao fim do mês — confirmar a estimativa de
  cêntimos.

## Como verificar

```bash
flyctl ssh console -a figueirahome-crons -C "cm schedules list"
flyctl ssh console -a figueirahome-crons -C "cm jobs trigger <id>"
flyctl ssh console -a figueirahome-crons -C "cm jobs show <job-id>"
```
