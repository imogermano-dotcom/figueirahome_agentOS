# Registo do Miguel — atualizações de 26/11/2026

Notas curtas por pedido. Sem nomes nem telefones de pessoas.

## #28 — Notas pela API (reaberto a 23/11)
- **Estado:** Pendente → **Em curso** · **Com quem está:** Miguel (confirmar que não falta nenhuma nota).
- **Nota (Developer):** 26/11 Claude: Importação pela API ligada (24/11) e agora de hora a hora, das 07:07 às 19:07 UTC. Escreve em `public.notas` com as mesmas colunas, chave `nota_ego_id`. Backfill coberto: falta só o que é de hoje e entra nas próximas voltas. O relatório do scraper continua a correr todas as noites e trouxe 7 notas do portal em duplicado (25–26/11); o dedup está ligado e as 7 foram apagadas.
- **Resposta ao Miguel (pontos 1–4 de 23/11):**
  - **Buraco de 21/11:** confirmado. Entre 21/11 03:38 e 24/11 03:38 o relatório não gravou notas novas (22/11 leu 168, todas já existiam; 23/11 não correu: 0 oportunidades editadas em 48 h). Voltou a gravar a 24/11. O scraper **não saiu**: corre todas as noites às 03:37 e ainda é a fonte das oportunidades, contactos, visitas e preferências.
  - **1.** Importação ligada desde 24/11, escreve em `public.notas` com as mesmas colunas e chave `nota_ego_id`. De hora a hora (07:07–19:07 UTC), 1 nota por oportunidade por volta (as extrações de preferências não correm em paralelo): 3 notas novas da mesma oportunidade entram em 3 horas.
  - **2.** Backfill feito: comparadas as notas da API com as nossas para as oportunidades ativas desde 15/11, falta só o de hoje.
  - **3.** A importação reconhece as notas do portal pelo `nota_ego_id`. O relatório não as reconhecia (o texto do eGO traz o sufixo) e entraram 7 duplicados. Corrigido e apagados. **O sufixo «— registado no portal Figueira Home por …» tem de continuar igual**; se mudar, avisar.
  - **4.** Podem desligar o `ego_notas_api` quando a hora a hora estiver estável e o relatório deixar de trazer notas (só com o fim do scraper). Aviso quando for.
  - **Pedido:** se faltar uma nota que já está no eGO, mandar a referência da oportunidade e o dia.
- **Feito:** commits `9d5033d`, `dc4ecd2`, `f02d12b`; `DEDUP_NOTAS_PORTAL=1` no scraper; cron `sync-notas`. Plano: `notas-dedup-e-cadencia-plano.md`.
- **Por ver:** a 27/11 depois das 03:37 UTC, `notas_portal.saltadas` e que não nasça duplicado novo.

## #27 — Duplicados de contactos por telefone
- **Estado:** **Em curso** · **Com quem está:** Developer, até ver a corrida de 27/11; depois Miguel.
- **Nota (Developer):** 26/11 Claude: Prevenção em produção. O sync completa a linha antiga (sem `ego_link`) com o mesmo telefone em vez de criar outra, só quando há uma candidata com nome compatível e que não seja de assistente nem da Meta. Nasciam ~11 duplicados por dia, ~6 evitáveis. Os 9 204 telefones já duplicados não foram tocados: a fusão depende do Miguel.
- **Perguntas ao Miguel:** em que chave o pipeline lê as linhas antigas (`(nome, criado_em)`?); apagar ou marcar os duplicados; se o pipeline ainda cria linhas sem `ego_link`.
