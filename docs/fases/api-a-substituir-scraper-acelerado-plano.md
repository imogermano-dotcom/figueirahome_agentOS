# Trocar o scraper pela API o mais depressa possível: plano acelerado (26/11)

**Plano antes de código; nada deste plano está implementado.** Sem nomes, telefones nem emails de pessoas (só contagens e referências).
Reordena as fases A3–A8 de `ego-api-substituir-scrapers-plano.md` (28/10): o mapa de campos e as medições desse plano mantêm-se; muda a **ordem** e o **tempo de observação**.
Pedido do utilizador (26/11): trocar o scraper pela API **o mais rápido possível**, não em meses.

## Onde estamos (26/11)

| Peça | Estado |
|---|---|
| Cliente da API (A1) | Feito (`ego_api.py`) |
| Tarefas (A3) | **Feito e ligado** (`TAREFAS_VIA_API` ligado no agentos; o cron das 05:07 já lê pela API) |
| Notas (A2) | Feito e a correr de hora a hora, com autor e tipo. Falta: comparação com o relatório, `nota_resultado`, desligar o relatório |
| Imóveis (A7) | Todos os estados já pela API. Falta a validação/detalhe pelo CRM em HTML (`egorealestate_crm.py`) |
| Oportunidades (A5) | Feita só a **criação** (esqueleto com imóvel, etapa, preferências; `OPORTUNIDADES_API_EGO=1`). Falta **atualizar as existentes** |
| Visitas (A4) | Por fazer |
| Contactos (A6) | Parcial (`entidade`, `contactos_da_entidade`); sem sync |

**O que o scraper noturno (03:37 UTC) ainda escreve:** oportunidades (as existentes), contactos, visitas, notas e preferências. É só isto que falta substituir.

## Princípio: sombra em paralelo, não em fila

O plano de 28/10 tinha as peças em fila e «um mês estáveis» antes de desligar. Aqui:
1. **Cada peça corre em sombra** (a API lê e compara com o que o relatório gravou; **não escreve**) e todas as sombras andam **ao mesmo tempo**.
2. Cada peça tem um **script de comparação** que conta, por coluna, onde a API e o relatório divergem (sem imprimir texto de pessoas).
3. **Paridade curta:** a peça passa a escrever pela API quando as colunas batem ≥ 99 % durante **3 dias úteis seguidos** e as divergências estão explicadas (em vez de 1 semana, ou um mês no total).
4. **Desligar o scraper** (A8) quando as 4 peças estão a escrever pela API há **5 dias úteis** sem regressões (em vez de um mês).
5. Reversão sempre por interruptor (`secrets unset`), como nas peças já ligadas.

## As peças, por ordem de risco (a sombra de todas começa na semana 1)

### P1. Notas: fechar (já feito 90 %)
- Script `scripts/comparar_notas_api_relatorio.py` (leitura): autor e tipo iguais, as 11 diferenças de autor e as 48 notas que não batem pela chave (47 com emoji à cabeça na API).
- `nota_resultado` (15 % no relatório, a API não o dá): pergunta ao Miguel; se ninguém o usa, perde-se.
- Interruptor `RELATORIO_SEM_NOTAS` no scraper: o relatório deixa de gravar notas.
- **Critério:** autor e tipo ≥ 99 % em 3 dias úteis; nenhuma nota que o relatório tinha falta na API.

### P2. Visitas (`ListRealestateVisitFile`)
- Medido a 28/10: 200 leads em 0,5 s; 12 campos `visita_*` com correspondente direto; `visita_imovel_ref` ← `realestateId` → imóvel (**as visitas contam-se por `visita_imovel_ref`**, nunca por `oportunidades.imovel_ref`).
- Módulo `visitas_api.py` + `POST /api/oportunidades/sync/visitas` (`dry` por omissão), em lotes de 200 `leadIds` das ativas. Mesma chave e colunas que o relatório (`visitas`, `0023`); só INSERT/UPDATE linha a linha.
- Sombra: a API devolve ⊇ as 1 791 linhas da BD? Explicar a diferença antes de gravar. A `social_imovel_stats` do Miguel lê `visitas`: não mudar a forma.
- **Critério:** API ⊇ BD nas ativas; datas e estado (`cancelled`, `notAttended`) iguais.

### P3. Oportunidades: atualizar as existentes (a peça grande)
Sync incremental pela lista de ativas, **sem a janela de 48 h**: comparar `alterDate` com o guardado; as alteradas vão ao `GetOpportunity`/preferências. Mais as ganhas/perdidas e arquivadas que a lista traz.
- **Campos diretos** (plano de 28/10): `oportunidade_estado` ← `leadStage`, `origem`/`sub_origem`, `tipo_*`, `responsavel`, `valor_negocio`, `data_escritura`, `probabilidade`, `ponto_situacao`(+data), `motivo_transacao`, `estado_fechado_em`.
- **Etapa:** `ListOpportunityByPageIsReport` (`etapas_ativas`, feito). **Imóvel:** derivado de `imoveis` (feito no esqueleto), proprietário e preços.
- **Preferências:** `pref_de_api` já traduz os códigos (feito a 26/11); sai de borla o **bug da tipologia** do scraper (`pref_tipologia_raw` que o RPC ignora). Continua pelo RPC `bulk_update_prefs` (só se `pref_extraido_em` é nulo: a IA prevalece).
- **Regras de segurança (mantêm-se):** escrita linha a linha ou RPC (nunca upsert em lote com chaves esparsas); **não sobrescrever com nulo** (`portal` das antigas vem `None`); `BEFORE UPDATE` carimba `atualizado_em`: sem updates em massa; `contacto_id` só por RPC.
- **`proposta` (valor): não existe na API** (16 ativas). Decisão sua: (a) ficar nulo, com estado e data pela API (as duas já vêm); (b) pedir o endpoint ao eGO como as comissões (#41). Recomendo (a) já e (b) em paralelo.
- Sombra: script que monta a linha pela API e compara coluna a coluna com a da BD (contagem de divergências **por coluna**), nas ~2 660 ativas.
- **Critério:** 0 linhas ignoradas; estado = `leadStage`; cada coluna ≥ 99 %; divergências explicadas.

### P4. Contactos (a peça mais arriscada: o portal e o pipeline do Miguel lêem-na)
- `ListEntityByPage` com `minAlterDate` + `ListEntityByLead` (liga à oportunidade). Traz NIF/IBAN/data de nascimento: **ler só nome, contactos, ids e datas**.
- **Invariantes a respeitar:** PK `(nome, criado_em)` com `criado_em` = data de **alteração** por instrução do pipeline do Miguel; `ego_link` UNIQUE; as linhas de assistente e da Meta nunca se tocam; a regra de duplicados por telefone (`_gemeos_por_telefone`, #27) tem de ser portada para o novo caminho.
- **Esta peça só avança com o OK do Miguel** (as respostas às perguntas do #27 e da chave).
- **Critério:** `ego_link` e telefone iguais aos do relatório nas alteradas; zero colisões novas de PK.

### P5. Imóveis (A7) e desligar (A8)
- Trocar `egorealestate_crm.fetch_all/fetch_detail/find_by_ref` (HTML) por `ListRealestateByPage`/`GetRealestate` com o id de backoffice (`imoveis.ego_backoffice_id`). Os 10 imóveis «invisíveis» deixam de falhar.
- Só depois das P1–P4 estáveis: desativar o cron `sync-oportunidades`, parar a app `figueirahome-scraper` (RAM), remover `egorealestate_crm.py` e `scraper/` num commit à parte.

## Calendário (estimativa, dias úteis; depende de eu escrever o código e do Miguel)

| Semana | O quê |
|---|---|
| 1 | P1 comparação + `nota_resultado`; P2 e P3 código em sombra (nada grava) |
| 2 | Sombras a correr de noite; P1 → `RELATORIO_SEM_NOTAS`; P2 a escrever; P3 corrigir divergências; P4 código em sombra |
| 3 | P3 a escrever (por colunas, uma de cada vez); P4 a escrever se o Miguel aprovar; P5 imóveis |
| 4 | 5 dias úteis com tudo pela API; desligar o scraper |

**Tempo total estimado: ~4 semanas.** O que o pode atrasar: a resposta do Miguel (contactos, `nota_resultado`), divergências grandes na P3, a decisão da proposta.

## Riscos
- **Regressão silenciosa:** por isso a sombra comparar **por coluna** e só avançar com ≥ 99 % e divergências explicadas.
- **Escrever por cima de dados melhores** (IA, edição manual): RPC de preferências com `pref_extraido_em`; nunca nulo por cima de valor; `manual` intocado.
- **O portal do Miguel lê `oportunidades`/`contactos`/`visitas`:** só colunas existentes; nada se apaga; avisar antes de cada peça passar a escrever.
- **Login e limites da API:** token de 24 h, `User-Agent` de browser, repetição em 401/429 (já em `ego_api.py`).
- **Um relatório sem scraper deixa de dizer «Criada»:** `leadStage` 0 = Ativa (o esqueleto já o faz).

## Decisões para ti
1. **Critérios curtos:** 3 dias úteis de paridade por peça e 5 dias úteis estáveis no total, em vez de um mês. OK?
2. **Valor da proposta:** nulo (estado e data pela API) e pedir o endpoint ao eGO em paralelo?
3. **Contactos (P4):** pedir já ao Miguel o OK e as respostas do #27, para não bloquear a semana 3?
4. Ordem: começar por P1 (script de comparação) e P2 (visitas, sem risco) e ir para a P3 em seguida?

## Passos (cada um com OK próprio)
1. Aprovar este plano.
2. P1: script de comparação das notas (só leitura) e pergunta do `nota_resultado` ao Miguel.
3. P2: código das visitas em sombra; commit, push, deploy; ver a sombra.
4. P3: script de comparação coluna a coluna e módulo de atualização (dry); só depois escrever, uma coluna de cada vez.
5. P4: perguntas ao Miguel; código em sombra; escrever só com o OK dele.
6. P5 e A8: desligar o scraper; atualizar CLAUDE.md e `docs/decisoes.md`.
