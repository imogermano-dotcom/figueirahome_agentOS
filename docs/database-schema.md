# Database Schema — Figueirahome Agent Call (Supabase / PostgreSQL)

> Estrutura da base de dados. Nomes de tabelas e colunas em português, snake_case.
> **Actualizado a 07/10/2026 a partir do esquema real** (OpenAPI do PostgREST, só leitura)
> e de `supabase migration list`. Até aqui o documento descrevia o esquema inicial
> (migration `0001`), que fica preservado em «Histórico» no fim.
> **O repo não é a fonte de verdade única**: confirmar sempre contra a base antes de
> escrever SQL (ver «Como confirmar o esquema»).

## Um projecto Supabase (desde 13/09/2026)

- Projecto único `zphasvfopnbzwnaidsnw`: **dados e Auth**. `backend/app/db/supabase_client.py::get_supabase()`
  é o único cliente (`supabase_url` + `supabase_secret_key`, chave nova `sb_secret_…`, papel
  `service_role`, que ignora o RLS). O backend nunca passa o JWT do utilizador ao Postgres.
- A divisão «projecto de dados + projecto de Auth» da migration `0006` (21/07) **já não existe**:
  o de Auth foi eliminado e integrado neste.
- **A base é muito maior do que este repo**: 102 tabelas/vistas e ~200 funções. Este repo gere cerca
  de uma dezena de tabelas; o resto é do espelho do eGO (escrito de fora) e do portal do Miguel e de
  outras aplicações que partilham o projecto. Não alterar o que não está listado como «deste repo».

## Quem gere o quê

| Grupo | Tabelas | Dono / escritor |
|---|---|---|
| **Deste repo** (migrations `0001`–`0046`) | `agente_clientes`, `agente_conversas`, `agente_config`, `agente_interacoes`, `agente_tarefas`, `agente_mensagens_processadas`, `agente_sync_log`, `agente_chamadas` (voz, 1 linha), `leads`, `visitas`, `teste_imoveis`, `teste_oportunidades`; segundo o registo de 25/08 também `imoveis_price_history` e `lead_quality_cache` (sem migration própria no repo) | backend + painel |
| **Morta** | `agente_leads` (1 linha; sem escritores desde 18/08), `agente_chamadas` quase sem uso | — (por apagar) |
| **Espelho do eGO** (não gerir daqui) | `oportunidades` (26 061), `tarefas` (23 747), `notas` (103 814), `oportunidade_preferencias` (14 508), `contactos` (28 513), `imoveis` (4 466), `certificados_energeticos` | nosso scraper (`scraper/`), pipeline do Miguel, RPCs da Meta, assistentes e site (ver `contactos`) |
| **Portal / outras apps** (inferido pelos nomes; confirmar com o Miguel) | `ce_*` (certificados), `fsbo_*`, `idealista_*`, `ruas`, `marketing_*`, `conteudo*`, `conteudos_sociais`, `biblioteca_imagens`, `videos_sociais`, `noticias*`, `plano_*`, `recrut_*`, `recrutamento`, `objecoes_*`, `envios_*`, `meta_lead_*`, `cruz_chamadas`, `custos_portais`, `profiles`, `quiz_reports`, `portal_abas`, `sim_settings`, vistas `v_*` | fora do repo |
| **Leads de angariação** | `leads_angariacao` (88) | Make + consultora; sem `DELETE` (`0026`) |

Relações entre as tabelas deste repo: `agente_conversas 1 ── N agente_interacoes`; `agente_conversas 1 ── N agente_tarefas`
(`conversa_id`); `agente_clientes 1 ── N leads` (`cliente_id`); `agente_conversas 1 ── N leads` (`conversa_id`).
No espelho do eGO: `oportunidades 1 ── N tarefas | notas | oportunidade_preferencias` por `oportunidade_ref`, e
`contactos.id ── contacto_id` em `oportunidades`, `tarefas`, `notas`, `visitas` (ver adiante).

## Migrations: o que o repo sabe e o que a base tem

- Repo: `0001`–`0046` (a `0020` vive só no ramo `feat/landing-pages`).
- Base (`supabase migration list`, 07/10): 31 em comum (`0001`–`0030`), **16 só locais** (`0031`–`0046`,
  corridas à mão no editor SQL e **não registadas** em `supabase_migrations`) e **168 só remotas**
  (nomes com timestamp, de outras ferramentas/utilizadores, até 07/10; não estão no repo).
- **`supabase db push` é proibido** (a `0001` aborta) e a CLI usa-se só para leitura. As migrations
  deste repo são corridas à mão pelo utilizador no editor SQL, depois de explicadas.

## Triggers e funções conhecidos (os que este repo criou ou de que depende)

| Trigger / função | Onde | Para quê |
|---|---|---|
| `tgr_normaliza_aceita_whatsapp` (`0031`) | `leads` (insert/update de `ficha`) | **Quarta fronteira de segurança**: o consentimento de WhatsApp vem daqui, não de Python |
| `tgr_normaliza_origem_leads` (`0041`) | `leads` | preenche `origem` |
| `tgr_normaliza_origem_contactos` (`0042`) | `contactos` | `origem`: `meta` > `assistente` > `scraper` (por `meta_lead_id`, `agente`, `ego_link`); sem sinal fica `NULL` |
| `trg_oportunidades_updated` | `oportunidades` (BEFORE UPDATE) | carimba `atualizado_em`; **desligar em updates em massa** (o backfill de `contacto_id` fê-lo) |
| `tgr_classify_lead`, `tgr_extract_prefs` | `notas` (AFTER INSERT) | chamam edge functions de IA por `net.http_post`; **cada INSERT em `notas` dispara IA** (UPDATE não) |

RPCs que este repo chama: `dashboard_metricas`, `agente_metricas` (`0015`, `0017`, `0019`, `0038`),
`propagar_contacto_id`, `set_contacto_oportunidades` (`0046`), `bulk_update_prefs` (scraper). Chamadas
de fora (n8n, Make): `lead_meta_compra`, `lead_meta_recrutamento`, `lead_meta_angariacao` (criadas na
interface, **não estão em nenhuma migration do repo**). `social_imovel_stats` é do Miguel e lê `visitas`.

---

## `contactos`: quem escreve e como se distingue

Chave primária **`(nome, criado_em)`** (não `ego_link`), mais `id uuid` UNIQUE e `ego_link` UNIQUE. O scraper grava
`criado_em` com a **data de alteração** do eGO, logo a PK muda a cada edição: **juntar sempre por `id`**, nunca pela PK
(foi o que partiu a FK composta de `leads_angariacao`, erro `23503`). Há também uma `prospeccao.contactos`:
**qualificar sempre `public.contactos`**.

Cinco escritores, distinguíveis pelas colunas (contagens a 07/10, 28 513 linhas):

| Escritor | Sinal | Particularidades |
|---|---|---|
| **Nosso scraper** | `ego_link` preenchido (`/egocore/person/<id>`; 13 são `/company/<id>`); `origem='scraper'` | sobretudo `telemovel`; `criado_em` = alteração do eGO; descarta contactos sem `ego_link` |
| **Pipeline do Miguel** (formatos antigos) | sem `ego_link`, `origem` NULL, ~15 800 linhas, 2017–2026 | sobretudo `telefone`; `responsavel`, `rgpd_*`; a flag `duplicado` **não** vem do Excel (origem a confirmar) |
| **RPCs `lead_meta_*`** (Meta) | `meta_lead_id`; `origem='meta'` | `telefone` **e** `telemovel`; `ad_*`/`adset_*`; podem **reaproveitar** uma linha existente (8 de 41 têm `criado_em` anterior a 2026) |
| **Assistentes** | `agente` preenchido; `origem='assistente'` | espelho aditivo: nunca mexem em linha que não seja sua |
| **Formulários do site** | `tipos` com `form`/`comprar`/`visita`/`property_detail`/`contacto`/`recrutamento_relatorio`, sem `ego_link` | `mensagem` (com `[Imóvel FHxxxx]` no texto), `imovel_ref` vazio, `whatsapp_permissao` sempre `False`, `origem` NULL (16 linhas desde 09/07) |

A **canónica** de uma pessoa é a linha com `ego_link`. Das 15 867 sem `ego_link`, 11 958 (limite superior, por
telefone/email) têm uma gémea com `ego_link`: a fusão está por fazer (ver `docs/fases/`). O consentimento de WhatsApp
está repartido pelas duplicadas (278 linhas sem `ego_link` com `whatsapp_permissao=true`, 328 com).

## `contacto_id` (migration `0046`)

Coluna `contacto_id uuid REFERENCES public.contactos(id) ON DELETE SET NULL` em `oportunidades`, `tarefas`, `notas` e
`visitas`; `oportunidades.contacto_match` regista a camada (`ego_link` > `telefone` > `email` > `nome`, a última de
baixa confiança, desfazível). **`oportunidades.contacto_id` é a fonte de verdade**; as filhas herdam-no por
`oportunidade_ref` (`propagar_contacto_id()`). **Escreve-se só por RPC**, nunca num upsert em lote do PostgREST (uma chave
presente num só registo escreve `NULL` nos outros). Backfill do histórico a 05/10: 21 022 de 26 057 oportunidades,
18 846 de 23 723 tarefas, 83 137 de 103 721 notas, 1 515 de 1 789 visitas. Detalhe em `docs/fases/contacto-id-plano.md`.

---

## Esquema actual das tabelas (gerado do esquema real, 07/10/2026)

> Tipos e comentários vêm da base. `oportunidades` (98 colunas), `imoveis` (64) e as tabelas do portal não se
> listam aqui: são do espelho do eGO / de fora do repo.

#### `agente_clientes` — 30 linhas

| Coluna | Tipo | Notas |
|---|---|---|
| `id` | uuid | PK; NOT NULL; default `extensions.uuid_generate_v4()` |
| `nome` | text |  |
| `telefone` | text |  |
| `email` | text |  |
| `tipo_interesse` | text |  |
| `orcamento` | numeric |  |
| `zona_preferida` | text |  |
| `notas` | text |  |
| `origem` | text |  |
| `criado_em` | timestamp with time zone | default `now()` |
| `atualizado_em` | timestamp with time zone | default `now()` |

#### `agente_conversas` — 87 linhas

| Coluna | Tipo | Notas |
|---|---|---|
| `id` | uuid | PK; NOT NULL; default `extensions.uuid_generate_v4()` |
| `canal` | text | NOT NULL |
| `participante` | text |  |
| `mensagens` | jsonb |  |
| `criado_em` | timestamp with time zone | default `now()` |
| `atualizado_em` | timestamp with time zone | default `now()` |
| `agente` | text | a1_vendedor \| a2_geral \| broker — assistente que detém a thread (routing sticky) |
| `nudge_em` | timestamp with time zone |  |

#### `agente_config` — 6 linhas

| Coluna | Tipo | Notas |
|---|---|---|
| `id` | uuid | PK; NOT NULL; default `extensions.uuid_generate_v4()` |
| `agente` | text | NOT NULL |
| `persona` | text |  |
| `instrucoes` | text |  |
| `idioma` | text | default `pt-PT` |
| `ativo` | boolean | default `True` |
| `atualizado_em` | timestamp with time zone | default `now()` |

#### `agente_interacoes` — 411 linhas

| Coluna | Tipo | Notas |
|---|---|---|
| `id` | uuid | PK; NOT NULL; default `extensions.uuid_generate_v4()` |
| `conversa_id` | uuid | FK → `agente_conversas.id`; id`. |
| `agente` | text | NOT NULL |
| `canal` | text | NOT NULL |
| `modelo` | text | NOT NULL |
| `tokens_input` | integer | NOT NULL; default `0` |
| `tokens_output` | integer | NOT NULL; default `0` |
| `tokens_cache_read` | integer | NOT NULL; default `0` |
| `tokens_cache_write` | integer | NOT NULL; default `0` |
| `custo_usd` | numeric | NOT NULL; default `0` |
| `latencia_ms` | integer |  |
| `iteracoes` | integer | NOT NULL; default `1` |
| `tools_usadas` | text[] |  |
| `tool_forcada` | boolean | NOT NULL; default `False` |
| `erro` | text |  |
| `criado_em` | timestamp with time zone | NOT NULL; default `now()` |
| `tools_detalhe` | jsonb | Tools chamadas com argumentos. Só tools de pesquisa trazem input — nunca PII. |

#### `agente_tarefas` — 78 linhas

| Coluna | Tipo | Notas |
|---|---|---|
| `id` | uuid | PK; NOT NULL; default `extensions.uuid_generate_v4()` |
| `titulo` | text | NOT NULL |
| `descricao` | text |  |
| `imovel_ref` | text |  |
| `estado` | text | default `pendente` |
| `prazo` | date |  |
| `responsavel` | text |  |
| `criado_em` | timestamp with time zone | default `now()` |
| `atualizado_em` | timestamp with time zone | default `now()` |
| `tipo` | text | visita \| escalar — antes só dava para inferir do titulo por ILIKE. |
| `agente` | text |  |
| `conversa_id` | uuid | FK → `agente_conversas.id`; Null quando a tarefa nasce no 1.º turno de uma conversa nova (o id só existe depois do save_conversation). id`. |
| `motivo` | text |  |

#### `agente_chamadas` — 1 linhas — voz, quase sem uso

| Coluna | Tipo | Notas |
|---|---|---|
| `id` | uuid | PK; NOT NULL; default `extensions.uuid_generate_v4()` |
| `cliente_id` | uuid | FK → `agente_clientes.id`; id`. |
| `call_control_id` | text |  |
| `numero_origem` | text |  |
| `duracao` | integer |  |
| `transcricao` | text |  |
| `resumo_ia` | text |  |
| `gravacao_url` | text |  |
| `data_hora` | timestamp with time zone | default `now()` |

#### `agente_leads` — 1 linhas — morta desde 18/08

| Coluna | Tipo | Notas |
|---|---|---|
| `id` | uuid | PK; NOT NULL; default `extensions.uuid_generate_v4()` |
| `cliente_id` | uuid | FK → `agente_clientes.id`; id`. |
| `imovel_id` | uuid |  |
| `estado` | text | default `novo` |
| `notas` | text |  |
| `criado_em` | timestamp with time zone | default `now()` |
| `atualizado_em` | timestamp with time zone | default `now()` |

#### `agente_mensagens_processadas` — 234 linhas — dedup de mensagens do WhatsApp

| Coluna | Tipo | Notas |
|---|---|---|
| `message_id` | text | PK; NOT NULL |
| `criado_em` | timestamp with time zone | NOT NULL; default `now()` |

#### `agente_sync_log` — 1 245 linhas — log dos syncs do eGO

| Coluna | Tipo | Notas |
|---|---|---|
| `id` | uuid | PK; NOT NULL; default `extensions.uuid_generate_v4()` |
| `tipo` | text | NOT NULL; default `egorealestate` |
| `executado_em` | timestamp with time zone | default `now()` |
| `resumo` | jsonb |  |
| `detalhes` | jsonb |  |
| `origem` | text |  |

#### `leads` — 330 linhas

| Coluna | Tipo | Notas |
|---|---|---|
| `id` | uuid | PK; NOT NULL; default `gen_random_uuid()` |
| `tipo` | text | NOT NULL; default `compra` |
| `estado` | text | NOT NULL; default `nova` |
| `nome` | text |  |
| `telefone` | text |  |
| `email` | text |  |
| `meta_lead_id` | text |  |
| `meta_form_name` | text |  |
| `meta_created_at` | timestamp with time zone |  |
| `imovel_ref` | text |  |
| `ficha` | jsonb | NOT NULL |
| `responsavel` | text |  |
| `notas` | text |  |
| `cliente_id` | uuid | FK → `agente_clientes.id`; id`. |
| `conversa_id` | uuid | FK → `agente_conversas.id`; id`. |
| `qualificada_em` | timestamp with time zone |  |
| `criado_em` | timestamp with time zone | NOT NULL; default `now()` |
| `atualizado_em` | timestamp with time zone | NOT NULL; default `now()` |
| `template_enviado` | text | Texto do template de WhatsApp enviado pelo n8n. Entra no histórico como mensagem do assistente no primeiro turno (engine._contexto_inicial). |
| `template_enviado_em` | timestamp with time zone | Quando o template saiu. Único sinal de que a lead foi contactada neste fluxo. |
| `respondeu_em` | timestamp with time zone | Quando a lead respondeu pela primeira vez. NULL = ainda não falou. É este o sinal para o follow-up, não `conversa_id`. |
| `origem` | text | NOT NULL; default `manual`; De onde veio a lead: meta \| assistente \| voz \| landing \| manual. Eixo distinto de `tipo`, que é o interesse. |
| `follow_up_em` | timestamp with time zone | Quando saiu o follow-up das 48h. NULL = ainda não saiu. É o travão do cron do n8n: um follow-up por lead, uma só vez. Não usar o estado para isto — o estado é editável no painel. |
| `contacto_humano_em` | timestamp with time zone | Quando uma consultora falou com a lead FORA do agente. NULL = ninguém falou. Travão dos fluxos 02/03 do n8n: nenhuma mensagem iniciada por nós sai para quem já está a ser tratado por uma pessoa. Não trava as respostas da Matilde a quem escreve primeiro — ver o comentário desta migration. |
| `follow_up_2_em` | timestamp with time zone | Quando o fluxo n8n de follow-up da Matilde a 72h mandou a 3ª mensagem (última tentativa). Travão de "só uma vez", independente de follow_up_em. |

#### `leads_angariacao` — 88 linhas — Make + consultora; fora deste repo

| Coluna | Tipo | Notas |
|---|---|---|
| `id` | uuid | PK; NOT NULL; default `gen_random_uuid()` |
| `created_at` | timestamp with time zone | default `now()` |
| `contacto_nome` | text | NOT NULL |
| `contacto_criado_em` | date | NOT NULL |
| `meta_lead_id` | text |  |
| `meta_form_name` | text |  |
| `meta_created_at` | timestamp with time zone |  |
| `responsavel` | text |  |
| `atribuido_em` | timestamp with time zone |  |
| `atribuido_por` | text |  |
| `estado` | text | NOT NULL; default `nova` |
| `estado_alterado_em` | timestamp with time zone | default `now()` |
| `retorno_data` | date |  |
| `retorno_hora` | time without time zone |  |
| `retorno_notas` | text |  |
| `ficha` | jsonb |  |
| `outcome` | text |  |
| `reuniao_data` | date |  |
| `reuniao_hora` | time without time zone |  |
| `reuniao_local` | text |  |
| `notas` | text |  |
| `notas_imovel` | text |  |
| `nao_atende_count` | integer | default `0` |
| `template_enviado` | text |  |
| `template_enviado_em` | timestamp with time zone |  |

#### `contactos` — 28 513 linhas — espelho do eGO + Meta + assistentes + site

| Coluna | Tipo | Notas |
|---|---|---|
| `nome` | text | PK; NOT NULL |
| `criado_em` | date | PK; NOT NULL |
| `email` | text |  |
| `tipos` | text[] |  |
| `ego_atualizado_em` | timestamp with time zone | default `now()` |
| `whatsapp_permissao` | boolean | default `False`; Permissão para contacto via WhatsApp (recolhida em campanha) |
| `whatsapp_data` | date | Data em que a permissão WhatsApp foi obtida |
| `telefone` | text |  |
| `telemovel` | text |  |
| `data_nascimento` | date |  |
| `nacionalidade` | text |  |
| `responsavel` | text |  |
| `rgpd_telefone` | text | RGPD para contacto por telefone: consentido \| nao_consentido \| pre_consentido |
| `rgpd_telemovel` | text | RGPD para contacto por telemóvel: consentido \| nao_consentido \| pre_consentido |
| `rgpd_email` | text | RGPD para contacto por email: consentido \| nao_consentido \| pre_consentido |
| `duplicado` | boolean | default `False` |
| `ego_link` | text | URL do contacto no EGO CRM (ex: https://admin.egorealestate.com/egocore/person/<id>). Usado como chave de match na importação de Excel. |
| `mensagem` | text | Texto livre do pedido, escrito pelo visitante no site (nao vem do eGO). |
| `estado` | text |  |
| `template_enviado` | text |  |
| `template_enviado_em` | timestamp with time zone |  |
| `meta_lead_id` | text |  |
| `meta_form_name` | text |  |
| `meta_created_at` | timestamp with time zone |  |
| `tipo_contacto` | text[] |  |
| `id` | uuid | NOT NULL; default `extensions.uuid_generate_v4()` |
| `agente` | text | Slug do assistente que criou/actualizou esta linha (a1_vendedor, a2_geral, a3_recrutamento, a4_angariador). NULL = veio do scraper, do pipeline do Miguel, ou de antes desta coluna existir. |
| `respondeu_em` | timestamp with time zone | Primeira resposta desta pessoa depois do template — escrito por marcar_contacto_respondeu (guards.py). NULL = nunca respondeu. |
| `follow_up_em` | timestamp with time zone | Quando o fluxo n8n de follow-up de recrutamento mandou a 2ª mensagem. Travão de "só uma vez" — sem isto o cron diário reenviava. |
| `follow_up_2_em` | timestamp with time zone | Quando o fluxo n8n de follow-up de recrutamento a 72h mandou a 3ª mensagem (última tentativa). Travão de "só uma vez", independente de follow_up_em. |
| `origem` | text | De onde veio o contacto: meta \| assistente \| scraper. NULL = escritor externo sem ego_link (scraper antigo ou pipeline do Miguel, indistinguíveis) ou anterior a esta coluna. |
| `imovel_ref` | text | Referência do imóvel do anúncio, para os follow-ups da Matilde citarem qual. Preenchida pelo fluxo n8n a partir de leads.imovel_ref (por meta_lead_id) na 1ª vez, não por trigger. |
| `ad_id` | text | ID do anúncio Meta que gerou a lead (RPCs lead_meta_*, campo já pedido pelo n8n à Graph API). Sempre sobrescrito na submissão mais recente. |
| `ad_name` | text | Nome do anúncio Meta que gerou a lead. |
| `adset_id` | text | ID do conjunto de anúncios (adset) Meta que gerou a lead. |
| `adset_name` | text | Nome do conjunto de anúncios (adset) Meta que gerou a lead. |

#### `tarefas` — 23 747 linhas — espelho do eGO

| Coluna | Tipo | Notas |
|---|---|---|
| `id` | bigint | PK; NOT NULL |
| `oportunidade_ref` | text | FK → `oportunidades.oportunidade_ref`; NOT NULL; oportunidade_ref`. |
| `tipo_oportunidade` | public.tipo_oportunidade_enum |  |
| `cliente_nome` | text |  |
| `tarefa_titulo` | text |  |
| `tarefa_due_raw` | text |  |
| `tarefa_due_iso` | date |  |
| `tarefa_status` | public.status_tarefa_enum | default `pendente` |
| `url` | text |  |
| `origem_lista` | public.origem_lista_enum | default `Ativas` |
| `criado_em` | timestamp with time zone | default `now()` |
| `tarefa_descricao` | text |  |
| `tarefa_responsavel` | text |  |
| `tarefa_criado_por` | text |  |
| `tarefa_criado_em` | date |  |
| `tarefa_reagendamento_iso` | date |  |
| `tarefa_reagendada` | text |  |
| `contacto_id` | uuid | FK → `contactos.id`; id`. |

#### `notas` — 103 814 linhas — espelho do eGO

| Coluna | Tipo | Notas |
|---|---|---|
| `id` | bigint | PK; NOT NULL |
| `oportunidade_ref` | text | FK → `oportunidades.oportunidade_ref`; NOT NULL; oportunidade_ref`. |
| `tipo_oportunidade` | public.tipo_oportunidade_enum |  |
| `cliente_nome` | text |  |
| `nota_texto` | text | NOT NULL |
| `nota_data_raw` | text |  |
| `nota_data_iso` | date |  |
| `nota_autor` | text |  |
| `url` | text |  |
| `origem_lista` | public.origem_lista_enum | default `Ativas` |
| `criado_em` | timestamp with time zone | default `now()` |
| `nota_resultado` | text |  |
| `nota_origem` | text | default `crm` |
| `nota_anexos` | text |  |
| `nota_tipo` | text |  |
| `contacto_id` | uuid | FK → `contactos.id`; id`. |

#### `visitas` — 1 789 linhas

| Coluna | Tipo | Notas |
|---|---|---|
| `visita_ref_ego` | text | PK; NOT NULL |
| `oportunidade_ref` | text | NOT NULL |
| `visita_imovel_ref` | text |  |
| `visita_data` | text |  |
| `visita_anulada` | text |  |
| `visita_interessado` | text |  |
| `visita_cliente` | text |  |
| `visita_imovel_proprietario` | text |  |
| `visita_pontos_positivos` | text |  |
| `visita_pontos_negativos` | text |  |
| `visita_sobre_negocio` | text |  |
| `visita_observacoes` | text |  |
| `visita_responsavel` | text |  |
| `criado_em` | timestamp with time zone | default `now()` |
| `atualizado_em` | timestamp with time zone | default `now()` |
| `contacto_id` | uuid | FK → `contactos.id`; id`. |


---

## Histórico — migration `0001` (esquema inicial, **não** reflecte o estado actual)

> Mantém-se por referência. Correspondência de nomes: `clientes` → `agente_clientes`, `chamadas` → `agente_chamadas`,
> `conversas` → `agente_conversas`, `config_agentes` → `agente_config`; `imoveis` e `leads` evoluíram muito
> (`leads` é hoje a tabela única de leads não qualificadas, `0021`/`0029`). Não usar para escrever SQL novo.

## SQL — Migrations

Guardar como `supabase/migrations/0001_initial_schema.sql`.

```sql
-- ════════════════════════════════════════════════
-- FIGUEIRA HOME — Schema inicial
-- ════════════════════════════════════════════════

-- Extensão para gerar UUIDs
create extension if not exists "uuid-ossp";

-- ──────────────────────────────────────────────
-- CLIENTES
-- ──────────────────────────────────────────────
create table clientes (
  id              uuid primary key default uuid_generate_v4(),
  nome            text,
  telefone        text,
  email           text,
  tipo_interesse  text,        -- 'compra' | 'arrendamento' | 'venda' | 'outro'
  orcamento       numeric,
  zona_preferida  text,
  notas           text,
  origem          text,        -- 'chamada' | 'manual' | 'chat'
  criado_em       timestamptz default now(),
  atualizado_em   timestamptz default now()
);

-- ──────────────────────────────────────────────
-- IMOVEIS — vive no PROJECTO SECUNDÁRIO Supabase
-- (supabase_imoveis_url/key, id zphasvfopnbzwnaidsnw), NÃO no principal.
-- Tabela real, alimentada originalmente por export do eGO Real Estate CRM.
-- Chave de negócio é `imovel_ref` (não há coluna `id` uuid separada).
-- Migration 0004 adiciona só `fonte`; o resto já existia em produção.
-- ──────────────────────────────────────────────
create table imoveis (
  imovel_ref            text primary key,
  natureza              text,        -- 'Apartamento' | 'Moradia' | ...
  disponibilidade       text,        -- 'Disponível' | 'Em Prospecção' | 'Por validar' | 'Retirado'
  estado                text,        -- condição: 'Novo' | 'Usado' | 'Renovado' | 'Recuperado' | ...
  fonte                 text not null default 'manual',
                                     -- 'egorealestate' | 'site_proprio' | 'idealista' | 'imovirtual' | 'manual' | 'csv'
  titulo                text,
  descricao             text,
  proprietario          text,
  angariador            text,
  vendedor              text,
  quartos               integer,
  casas_banho           integer,
  suites                integer,
  piso                  text,
  num_pisos             integer,
  numero                text,
  fracao                text,
  area_util             numeric,
  area_bruta            numeric,
  area_terreno          numeric,
  conservacao           text,
  certificacao_energetica text,
  venda_preco           numeric,
  arrendamento_preco    numeric,
  comissao_agencia      numeric,
  comissao_angariador   numeric,
  comissao_vendedor     numeric,
  exclusividade         text,
  morada                text,
  codigo_postal         text,
  concelho              text,
  freguesia             text,
  zona                  text,
  piscina               boolean,
  garagem                boolean,
  jardim                boolean,
  terraco               boolean,
  varanda                boolean,
  vista_mar             boolean,
  vista_praia           boolean,
  ar_condicionado       boolean,
  elevador              boolean,
  aquecimento_central   boolean,
  arrecadacao           boolean,
  estacionamento        boolean,
  portais               text,        -- lista de portais onde está syndicado (via eGO), texto separado por vírgulas
  foto_principal        text,
  fotos                 jsonb default '[]'::jsonb,   -- array de URLs (eGO CDN)
  plantas               jsonb default '[]'::jsonb,   -- array de URLs de plantas (eGO CDN). Migration 0012 — vem de `BluePrints` na Web API, confirmado ao vivo 2026-07-30 (2/55 imóveis tinham na altura)
  panoramic_url         text,        -- panorâmica NATIVA do eGO (`MainPanoramicUrl`). **Não** é a visita virtual — ver `visita_virtual_url`. Vazia em 0/54 publicados a 2026-08-18: a agência não usa esta funcionalidade. Adicionada directo em produção, sem migration — documentada em 2026-07-26
  video_url             text,        -- URL de vídeo (ex: YouTube). 26/54 publicados. Adicionada directo em produção, sem migration — documentada em 2026-07-26
  visita_virtual_url    text,        -- Migration 0028 — visita virtual externa (`ExternalVirtualTours[0].Url`), 7/56 publicados a 2026-08-18, todas Matterport. **Só vem do endpoint de detalhe** `/v1/Properties/{ID}` (104 campos); a listagem tem 82 e não o traz
  destaque              boolean default false,  -- Migration 0013 — vem da tag de sistema {"ID":1,"Name":"Destaque"} em `Tags` na Web API, confirmado ao vivo 2026-07-30 (1/55 imóveis tinha na altura)
  ego_id                bigint,      -- ID da propriedade no eGO Real Estate (null = nunca sincronizado)
  ego_atualizado_em     timestamptz,
  data_criacao          date,
  data_alteracao        date,
  disponivel_na_api     boolean not null default true,  -- Migration 0008: true se a última pull completa da Web
                                                          -- API pública ainda devolveu este imovel_ref. Mantido pela
                                                          -- app (`_flag_unpublished`), não generated — é o único
                                                          -- facto certo a cada pull; `disponibilidade` pode ficar
                                                          -- stale ("Disponível") até o CRM corrigir, esta coluna não.
  publicado             boolean generated always as (   -- Migration 0008: critério real p/ aparecer no site,
    disponibilidade = 'Disponível'                       -- cumulativo. GENERATED = Postgres recalcula sempre,
    and length(trim(imovel_ref)) > 0                      -- nunca fica dessincronizado do resto da linha.
    and coalesce(venda_preco, arrendamento_preco, 0) > 0
    and disponivel_na_api
  ) stored
);
create unique index idx_imoveis_ego_id on imoveis(ego_id);  -- integridade (Postgres permite múltiplos NULL); sync eGO faz upsert por imovel_ref, não por este
-- `disponibilidade` tem 2 fontes: Web API pública do eGO (só publicados, `imoveis_sync.py::sync_egorealestate_api`)
-- e o backoffice autenticado (visibilidade total, incl. nunca-publicados; `imoveis_sync.py::validar_disponibilidade_crm`,
-- via `egorealestate_crm.py` — scraping de sessão, credenciais EGOREALESTATE_CRM_*). O backoffice é autoritativo.
-- Colunas preenchidas pela Web API desde 2026-08-12 (`_map_property`): as 11 booleanas
-- de features, `conservacao`, `certificacao_energetica`, `angariador`, `suites`,
-- `exclusividade`, `data_criacao`, `data_alteracao`. As booleanas vêm de `FeatureTags`
-- e a tag tem de ser a do imóvel, não a da zona envolvente — `SWIMMING_POOLS` e
-- `PROPERTY_NEAR_GARDENS` são "há na zona"; ver comentário em `imoveis_sync.py`.
-- `arrecadacao`, `numero`, `proprietario`, `vendedor` e as 3 comissões não existem
-- na Web API pública (só Excel/CRM) — o mapeamento nunca lhes toca.
-- Campos esparsos (`conservacao`, `certificacao_energetica`, `angariador`, `suites`,
-- `piso`, `latitude`, `longitude`) saem por `_map_extras` e são aplicados com um
-- UPDATE por linha, FORA do upsert. O upsert por lotes é um único INSERT ... ON
-- CONFLICT sobre a UNIÃO das chaves do lote: uma chave presente num só registo vira
-- coluna e escreve NULL em todos os outros. Omitir a chave não protege — custou 40
-- coordenadas em 2026-08-12. `_map_property` devolve sempre as mesmas chaves.
-- `latitude`/`longitude` só se escrevem com `HasGPSLocation=true` (13/53): sem o flag
-- o eGO devolve o centróide da zona, não a morada — 40 imóveis em 11 coordenadas, 19
-- no mesmo ponto. As linhas já preenchidas com esse centróide vêm do import Excel.
create index idx_imoveis_fonte on imoveis(fonte);
create index idx_imoveis_disponibilidade on imoveis(disponibilidade);
create index idx_imoveis_publicado on imoveis(publicado);
create index idx_imoveis_publicado on imoveis(publicado);

-- ──────────────────────────────────────────────
-- LEADS
-- ──────────────────────────────────────────────
create table leads (
  id              uuid primary key default uuid_generate_v4(),
  cliente_id      uuid references clientes(id) on delete cascade,
  imovel_id       uuid,        -- sem FK, sempre null na prática hoje; ligação leads↔imoveis por fazer (fora de âmbito da migration 0006)
  estado          text default 'novo',   -- 'novo' | 'contactado' | 'visita' | 'proposta' | 'fechado' | 'perdido'
  notas           text,
  criado_em       timestamptz default now(),
  atualizado_em   timestamptz default now()
);

-- ──────────────────────────────────────────────
-- CHAMADAS
-- ──────────────────────────────────────────────
create table chamadas (
  id              uuid primary key default uuid_generate_v4(),
  cliente_id      uuid references clientes(id) on delete set null,
  call_control_id text,        -- id da chamada na Telnyx
  numero_origem   text,
  duracao         integer,     -- segundos
  transcricao     text,
  resumo_ia       text,
  gravacao_url    text,
  data_hora       timestamptz default now()
);

-- ──────────────────────────────────────────────
-- CONVERSAS (Agente 2)
-- ──────────────────────────────────────────────
create table conversas (
  id              uuid primary key default uuid_generate_v4(),
  canal           text not null,   -- 'web' | 'whatsapp' | 'telegram' | 'email'
  participante    text,            -- identificador do interlocutor (nº, email, etc.)
  mensagens       jsonb default '[]'::jsonb,  -- [{role, content, timestamp}, ...]
  criado_em       timestamptz default now(),
  atualizado_em   timestamptz default now()
);

-- ──────────────────────────────────────────────
-- CONFIG_AGENTES
-- ──────────────────────────────────────────────
create table config_agentes (
  id              uuid primary key default uuid_generate_v4(),
  agente          text not null unique,  -- 'voz' | 'broker'
  persona         text,                  -- descrição da personalidade
  instrucoes      text,                  -- instruções de comportamento (system prompt)
  idioma          text default 'pt-PT',
  ativo           boolean default true,
  atualizado_em   timestamptz default now()
);

-- ──────────────────────────────────────────────
-- Dados iniciais — config dos dois agentes
-- ──────────────────────────────────────────────
insert into config_agentes (agente, persona, instrucoes) values
('voz',
 'Assistente de atendimento simpático e profissional da agência Figueirahome.',
 'Atende chamadas em Português de Portugal. Sê cordial e eficiente. Recolhe nome, contacto, tipo de interesse, orçamento e zona preferida. Confirma os dados antes de terminar.'),
('broker',
 'Assistente interno que ajuda o broker a consultar dados de clientes, imóveis e leads.',
 'Responde sempre em Português de Portugal. Consulta a base de dados antes de responder. Sê directo e preciso.');

-- ──────────────────────────────────────────────
-- AGENTE_TAREFAS — migration 0005 (projecto PRINCIPAL)
-- Entidade genérica de tarefas, não exclusiva de imóveis.
-- ──────────────────────────────────────────────
create table agente_tarefas (
  id            uuid primary key default uuid_generate_v4(),
  titulo        text not null,
  descricao     text,
  imovel_ref    text,                       -- sem FK: imoveis vive noutro projecto Supabase
  estado        text default 'pendente',    -- 'pendente' | 'em_curso' | 'concluida' | 'cancelada'
  prazo         date,
  responsavel   text,
  criado_em     timestamptz default now(),
  atualizado_em timestamptz default now()
);
create index idx_agente_tarefas_estado on agente_tarefas(estado);
create index idx_agente_tarefas_imovel on agente_tarefas(imovel_ref);

-- ──────────────────────────────────────────────
-- LEADS — migration 0021
-- Leads NÃO qualificadas, de qualquer origem. Esquema genérico de propósito:
-- `agente_leads` e `leads_angariacao` vão convergir para aqui (ainda não).
-- Ciclo: `nova` -> n8n manda template e marca `contactada` -> o A1 conversa e
-- qualifica -> `qualificada` + tarefa para o corretor passar ao eGO à mão.
-- `telefone` e `email` ficam na própria linha: `leads_angariacao` depende de um
-- join a `contactos` por (nome, data) que resolve 74/79 mas parte-se assim que
-- dois leads com o mesmo nome cheguem no mesmo dia.
-- NÃO escrever em `contactos` a partir daqui — ver `docs/decisoes.md`.
-- ──────────────────────────────────────────────
create table leads (
  id              uuid primary key default gen_random_uuid(),
  tipo            text not null default 'compra',  -- 'compra'|'arrendamento' vão para o A1; 'angariacao' fica com a consultora
  estado          text not null default 'nova',    -- nova | contactada | qualificada | sem_interesse | perdida
  nome            text,
  telefone        text,                            -- normalizado a 9 dígitos (guards.normalizar_telefone)
  email           text,
  meta_lead_id    text unique,                     -- unique = idempotência para o Make
  meta_form_name  text,
  meta_created_at timestamptz,
  imovel_ref      text,                            -- sem FK: pode citar imóvel ainda por sincronizar
  ficha           jsonb not null default '{}'::jsonb,
  responsavel     text,                            -- quem da equipa lhe pegou; sem escritor até 2026-08-29
  notas           text,
  contacto_humano_em timestamptz,                   -- 0032. Uma PESSOA falou com ela. Trava os envios do n8n (fluxos 01/02/03); não trava a Matilde a responder
  cliente_id      uuid references agente_clientes(id) on delete set null,
  conversa_id     uuid references agente_conversas(id) on delete set null,
  qualificada_em  timestamptz,
  criado_em       timestamptz not null default now(),
  atualizado_em   timestamptz not null default now()
);
create index idx_leads_telefone on leads(telefone);  -- caminho quente: webhook procura por telefone a cada mensagem
create index idx_leads_estado on leads(estado);
create index idx_leads_tipo on leads(tipo);

-- ──────────────────────────────────────────────
-- Índices úteis
-- ──────────────────────────────────────────────
create index idx_leads_cliente on leads(cliente_id);
create index idx_leads_imovel on leads(imovel_id);
create index idx_chamadas_cliente on chamadas(cliente_id);
create index idx_conversas_canal on conversas(canal);
```

---

## Row Level Security (RLS)

> **ACTIVO desde Fase 4c** (`supabase/migrations/0003_rls.sql`).
> Backend usa `service_role_key` → bypass automático. Frontend nunca acede directamente.

### Estado actual — tabelas `agente_*`

| Tabela | RLS | Política |
|---|---|---|
| `agente_clientes` | ✅ | `auth_full_access` — authenticated |
| `agente_imoveis` | ✅ | **deprecated** (Fase A reformulação imóveis) — sem leitura/escrita nova, dashboard/API/broker usam `imoveis` no projecto secundário |
| `agente_leads` | ✅ | `auth_full_access` — authenticated |
| `agente_chamadas` | ✅ | `auth_full_access` — authenticated |
| `agente_conversas` | ✅ | `auth_full_access` — authenticated |
| `agente_config` | ✅ | `auth_full_access` — authenticated |
| `agente_tarefas` | ✅ | `auth_full_access` — authenticated (migration 0005) |

### Verificação

```sql
select relname, relrowsecurity
from pg_class
where relname like 'agente_%'
order by relname;
-- relrowsecurity = true em todas ✅
```


> **Aviso (medido a 25/08/2026, ver `docs/decisoes.md` e a migration `0025`)**: esta tabela só cobre as `agente_*`. As tabelas
> do espelho do eGO (`contactos`, `oportunidades`, `notas`, `tarefas`, `imoveis`…) chegaram a ser **legíveis pela chave `anon`**
> (pública por desenho no Supabase), e a escrita anónima foi fechada na `0025`. Não está revisto desde então: confirmar o
> RLS real antes de assumir fronteira nestas tabelas. `imoveis.panoramic_url`/`video_url` foram adicionadas directamente
> em produção, sem migration.

## `visitas` (migration 0023, 2026-08-14)

Visitas do eGO, uma linha por visita. PK `visita_ref_ego` (`VF_2886`, id do eGO).
Escrita por `scraper/upsert.py`; backfill inicial de 1739 linhas a partir das
colunas `visita_*` de `oportunidades`, que **continuam a existir e a ser
escritas** (a primeira visita de cada oportunidade) por haver consumidores fora
deste repo.

```sql
visita_ref_ego  text primary key   -- 'VF_2886'
oportunidade_ref text not null
visita_imovel_ref text             -- o imóvel VISITADO — não confundir com oportunidades.imovel_ref
visita_data, visita_anulada, visita_interessado, visita_cliente,
visita_imovel_proprietario, visita_pontos_positivos, visita_pontos_negativos,
visita_sobre_negocio, visita_observacoes, visita_responsavel   -- todos text (ver 0011)
criado_em, atualizado_em  timestamptz
```

**Contar visitas de um imóvel é por `visita_imovel_ref`.** Por `imovel_ref` (o
imóvel da oportunidade) perdem-se as visitas de clientes que andavam a ver outra
coisa — no FH2571 são 7 contra 4. Porquê a tabela existe: `docs/decisoes.md`,
secção "Visitas do eGO".


## Como confirmar o esquema antes de escrever SQL

- **Colunas e comentários reais** (só leitura): `GET {SUPABASE_URL}/rest/v1/` com `apikey`/`Authorization: Bearer <chave>` e
  `Accept: application/openapi+json` devolve as definições de todas as tabelas e vistas (chaves, FKs e comentários).
- **Migrations aplicadas**: `supabase migration list` (só leitura). As `0031`–`0046` aparecem como «só local» porque foram
  corridas à mão; isso não quer dizer que não estejam aplicadas.
- **Funções e triggers**: não aparecem no OpenAPI de tabelas; ler no editor SQL (`pg_trigger`, `pg_proc`).

## Notas para o Claude Code

- Migrations novas em `supabase/migrations/NNNN_nome.sql`, **explicadas ao utilizador antes** (corre-as ele). Nunca `db push`.
- Não criar tabelas novas sem actualizar este documento primeiro.
- `oportunidades`, `contactos`, `tarefas`, `notas` e `imoveis` são partilhadas com o portal do Miguel: colunas novas só
  nullable e com `ADD COLUMN IF NOT EXISTS`; escrever sempre qualificando `public.contactos`.
- Sem staging: perguntar antes de escrever em produção (sync, backfill, migration).
