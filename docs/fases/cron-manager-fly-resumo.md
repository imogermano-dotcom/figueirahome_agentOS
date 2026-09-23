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

## Bug real apanhado depois de deployar: CRLF no `process-job`

Schedules registados certo, crontab instalado certo (confirmado por SSH),
hora do sistema certa — e mesmo assim nada disparava sozinho, só
`cm jobs trigger` manual. Root cause: `bin/process-job` (shebang
`#!/bin/bash`) tinha finais de linha **CRLF** no working tree local — o
`git clone` num Windows com `core.autocrlf=true` converte para CRLF no
checkout, e o `flyctl deploy .` constrói a partir do disco, não do commit
(o blob no repo já estava LF, normalizado no `git add` original — só o
ficheiro em disco ficava corrompido a cada novo checkout). Com
`#!/bin/bash\r`, o kernel procura um interpretador que não existe e falha
com `ENOENT` — sem MTA configurado no container, o `cron` engole o erro em
silêncio. Corrigido: `sed -i 's/\r$//'` no ficheiro + `crons/.gitattributes`
(`bin/process-job text eol=lf`) para não voltar a acontecer no próximo
checkout. Confirmado ao vivo: `site-uptime` disparou sozinho na marca exacta
dos 5 minutos depois do redeploy.

## Estado dos 5 schedules (23/09)

| Nome | Agendado | Estado |
|---|---|---|
| `nudge-matilde` | `12 * * * *` | **activo**, confirmado a disparar sozinho horas seguidas (04:12-08:12) |
| `site-uptime` | `*/5 * * * *` | **desactivado 23/09** — redundante com o UptimeRobot (5/5 min grátis, já em uso), que vai passar a alimentar o dashboard via API. Confirmado a funcionar antes de desligar. 197 linhas de `agente_sync_log` (`tipo=site_uptime`) apagadas. |
| `sync-imoveis-manha` | `17 6 * * *` | **activo**, testado à mão (`cm jobs trigger`, 56 actualizados, 0 erros) |
| `sync-imoveis-tarde` | `23 13 * * *` | **activo** |
| `sync-oportunidades` | `37 3 * * *` | **activo**, testado à mão, exit 0 |

Os 4 `.yml` do GitHub Actions ficam só com `workflow_dispatch` (schedule
desligado nos 4). Sequência real ao activar `sync-imoveis`/`sync-oportunidades`
(23/09): editei o `.yml` localmente mas só fiz push **depois** de testar no
Fly — nesse intervalo, o `sync-oportunidades` do GitHub (ainda activo,
disparo atrasado ~5h13 desde as 03:37) correu às 08:50, e o meu teste manual
no Fly correu às 08:53 — 3 minutos de intervalo, mesma sessão eGO, o risco de
concorrência exacto que motivou desligar o GitHub primeiro (já tinha
derrubado a app principal por OOM a 18/08). Desta vez não houve crash
(`/health` 200 depois), mas foi sorte de tempo, não de desenho — o `.yml`
devia ter sido desligado (push) antes do teste, não depois. Lição para a
próxima vez que se mexer nestes dois: push do `.yml` primeiro, sempre.

## Por fazer

- Confirmar `sync-imoveis`/`sync-oportunidades` na próxima corrida real
  (06:17/13:23/03:37 UTC) — só testados à mão até agora.
- Ver a factura real do Fly ao fim do mês — confirmar a estimativa de
  cêntimos.

## Como verificar

```bash
flyctl ssh console -a figueirahome-crons -C "cm schedules list"
flyctl ssh console -a figueirahome-crons -C "cm jobs trigger <id>"
flyctl ssh console -a figueirahome-crons -C "cm jobs show <job-id>"
```
