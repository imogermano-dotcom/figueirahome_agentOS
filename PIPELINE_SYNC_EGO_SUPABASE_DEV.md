# Pipeline eGO/Wigo → Supabase — Documentação para Developer

> Documento gerado a partir da leitura direta de `sync_excel_supabase.py` (76 117 bytes, última alteração 24 Jul 2026) e do schema real das tabelas no Supabase (projeto **EGO Scapper**, `zphasvfopnbzwnaidsnw`, eu-west-1). Todos os mapeamentos de colunas abaixo foram confirmados linha a linha no código-fonte, não copiados de documentação antiga.

---

## 1. Visão geral do pipeline

```
eGO/Wigo (CRM)
   │  exportação manual (utilizador clica "Exportar" no browser)
   ▼
ficheiro .xlsx  →  colocado em  eGO Scraping/exports/
   │
   ▼
sync_excel_supabase.py
   ├─ detect_file_type(nome_ficheiro)      → decide qual parser usar
   ├─ process_*()                          → lê o Excel, mapeia colunas, faz upsert no Supabase
   ├─ archive_file()                       → move o .xlsx para exports/processados/<timestamp>_<nome>.xlsx
   └─ _webapi_sync_fh()                    → (depois do Excel) enriquece imóveis FH via EGO WebAPI (fotos/vídeo)
   │
   ▼
Supabase (zphasvfopnbzwnaidsnw) — tabelas: oportunidades, imoveis, contactos, notas, tarefas
   │
   ▼
Portal KPI (portal.miguelgermano.com) — lê do Supabase
```

O script é **idempotente**: usa `upsert` com chave de conflito por tabela, corre sobre o mesmo ficheiro várias vezes sem duplicar dados, e **nunca sobrescreve um valor existente com `null`** — campos vazios são removidos do payload antes do upsert.

**Script correto a usar:** `sync_excel_supabase.py`. Existe um script antigo, `upsert_all.py`, na mesma pasta — **não deve ser usado**, é uma versão anterior mais limitada mantida apenas por histórico.

**Execução:**
```bash
python3 sync_excel_supabase.py                    # processa tudo em ./exports/
python3 sync_excel_supabase.py --pasta "C:/..."   # pasta alternativa
python3 sync_excel_supabase.py --skip-webapi       # não corre o enriquecimento WebAPI no fim
```
Corre automaticamente todos os dias via tarefa agendada (`ego-pipeline-diario`).

---

## 2. Deteção do tipo de ficheiro (`detect_file_type`)

O parser é escolhido pelo **nome do ficheiro** (case-insensitive), por esta ordem:

| Padrão no nome | Tipo devolvido | Função |
|---|---|---|
| contém `todas_as_colunas` | `todas_as_colunas` | `process_todas_as_colunas()` |
| começa por `tarefas` | `tarefas_ego` | `process_tarefas_ego()` |
| contém `contactos` | `contactos` | `process_contactos()` |
| contém `imoveis` | `imoveis` | `process_imoveis()` |
| contém `powerbi` ou `_powerbi` | `powerbi_oportunidades` | `process_powerbi_oportunidades()` |
| contém `backup_ego` ou `backup` | `backup_completo` | `process_backup_completo()` |
| (nenhum dos anteriores) ficheiro com >1 sheet | `backup_completo` | `process_backup_completo()` |
| nenhum critério | `unknown` | ficheiro **ignorado** (não é arquivado, fica em `exports/` para inspeção) |

Hoje em dia, na prática, **só chega um tipo de ficheiro por via normal**: `todas_as_colunas_*.xlsx`, exportado do Wigo. Os outros formatos (`PowerBI*.xlsx`, `Contactos PBI*.xlsx`, `imoveis*.xlsx`, `tarefas*.xlsx`) foram os exports separados usados antes de o Wigo disponibilizar o ficheiro único — o código continua a suportá‑los (retrocompatibilidade / backfills), mas deixaram de ser gerados no fluxo normal.

---

## 3. Formato principal — `todas_as_colunas_*.xlsx`

Exportação "wide" do Wigo/eGO com **~470–530+ colunas** (o número varia por export). Cada linha representa uma **combinação** de oportunidade + (nota | tarefa | preferência | visita) — ou seja, a mesma oportunidade aparece em várias linhas, uma por cada nota/tarefa/etc. que tem.

Lido com **`python_calamine`** (mais robusto que `openpyxl` contra um bug de stylesheet do Wigo).

### 3.1 Offset dinâmico (SHIFT)

O número de colunas do bloco de contacto/notas/tarefas/preferências/visitas **varia entre exports** (o Wigo acrescenta colunas de amenidades ao bloco do imóvel com o tempo, empurrando tudo para a direita). O script compensa isto automaticamente:

1. Procura a coluna cujo cabeçalho é exatamente `"Nome"`, depois da posição 200.
2. `SHIFT = posição_encontrada − 316` (316 é a posição base de um export de referência).
3. Todas as colunas do bloco de contactos/notas/tarefas/prefs/visitas são lidas como `I(base) = base + SHIFT`.

Isto significa que **não é preciso alterar código quando o Wigo muda o número de colunas** — só quando muda a *ordem* dos campos dentro de cada bloco.

Além disso, algumas colunas específicas (URL, estado fechado em, ponto de situação, data da escritura, valor do negócio, motivo de transação) são localizadas **por nome de cabeçalho**, com um índice fixo como fallback caso o nome não seja encontrado.

### 3.2 Tabela `oportunidades` (colunas fixas 0–83 do ficheiro)

Uma oportunidade é criada/atualizada por `oportunidade_ref` (coluna 0). Chave de upsert: `oportunidade_ref`.

| Coluna Excel (índice) | Campo Supabase | Notas |
|---|---|---|
| [0] Referência | `oportunidade_ref` | chave de upsert |
| [1] Potencial cliente | `cliente_nome` | |
| [2] Proprietário | `imovel_proprietario` | |
| [4] Tipo de negócio | `tipo_oportunidade` | normalizado via `TIPO_OP_MAP` (ex: "angariacao"→"Angariação") |
| [6] Origem | `origem` | |
| [7] Sub origem | `sub_origem` | |
| [9] Estado | `oportunidade_estado` | normalizado via `ESTADO_MAP` ("Activa"→"Ativa") |
| [42] Etapa | `etapa_atual` | |
| [43] Imóvel preço | `imovel_preco` | numérico |
| [44] Proposta | `proposta` | numérico |
| [46] Data da proposta | `data_proposta` | parseada para ISO |
| [47] Estado (proposta) | `estado_proposta` | |
| [49] Data de criação | `ego_data_criacao` | |
| [50] Editado em | `ego_editado_em` | |
| [52] Agência | `agencia` | |
| [55] Responsável | `responsavel` | |
| [66] Referência imóvel | `imovel_ref` | |
| [67] Natureza | `imovel_natureza` | |
| [68] Distrito | `imovel_distrito` | |
| [69] Concelho | `imovel_concelho` | |
| [70] Freguesia | `imovel_freguesia` | |
| [71] Venda (€) | `imovel_venda` | numérico |
| "Link" (dinâmico, fallback 72) | `url` | só grava se começar por `http` — nunca sobrescreve um URL já existente com null |
| "Estado fechado em" (dinâmico, fallback 73) | `estado_fechado_em` | só incluído no payload se tiver valor (não apaga datas existentes) |
| "Ponto de situação" (dinâmico, fallback 74) | `ponto_situacao` | |
| "Ponto de situação (Alterado em)" (dinâmico, fallback 76) | `ponto_situacao_alterado_em` | |
| "Data da escritura" (dinâmico, fallback 79) | `data_escritura` | |
| "Valor do negócio" (dinâmico, fallback 80) | `valor_negocio` | numérico |
| "Motivo de transação" (dinâmico, fallback 83) | `motivo_transacao` | |
| — | `origem_lista` | valor fixo `"todas_as_colunas"` |

> Campos `None` são removidos do dicionário antes do upsert — um export sem "Valor do negócio", por exemplo, não apaga um valor já gravado anteriormente.

### 3.3 Tabela `imoveis` (bloco rico, a partir de `_IMV_START`)

Logo a seguir à coluna "Motivo de transação" (índice dinâmico `_IMV_START = _IDX_MOTIVO + 1`) vem um **segundo bloco de imóvel**, mais completo que o de `oportunidades`. Como nomes como "Referência", "Estado" e "Morada" se repetem no ficheiro, o script procura sempre a **primeira ocorrência a partir de `_IMV_START`**. Chave de upsert: `imovel_ref`.

| Coluna Excel (nome) | Campo Supabase |
|---|---|
| Referência | `imovel_ref` (chave de upsert) |
| Natureza | `natureza` |
| Disponibilidade | `disponibilidade` |
| Estado | `estado` |
| Proprietário | `proprietario` |
| Angariador | `angariador` |
| Vendedor | `vendedor` |
| Título | `titulo` |
| Quartos | `quartos` (inteiro) |
| Área útil | `area_util` (numérico) |
| Área bruta | `area_bruta` (numérico) |
| Área terreno | `area_terreno` (numérico) |
| Conservação | `conservacao` |
| Piso | `piso` |
| Número de pisos | `num_pisos` (inteiro) |
| Venda (€) | `venda_preco` (numérico) |
| Morada | `morada` |
| Código postal | `codigo_postal` |
| Número | `numero` |
| Fração | `fracao` |
| Concelho | `concelho` |
| Freguesia | `freguesia` |
| Zona | `zona` |
| Data de criação | `data_criacao` |
| Data de alteração | `data_alteracao` |
| Comissão da agência (Venda) | `comissao_agencia` (numérico) |
| Comissões dos angariadores (Venda) | `comissao_angariador` (numérico) |
| Comissões dos vendedores (Venda) | `comissao_vendedor` (numérico) |
| Certificação Energética | `certificacao_energetica` |
| Descrição | `descricao` |
| Contrato de mediação - Exclusividade | `exclusividade` |
| — | `ego_atualizado_em` = timestamp da execução |

⚠️ **Este bloco nunca inclui:** `fotos`, `foto_principal`, `video_url`, `panoramic_url`, `ego_id`, `casas_banho`, `suites`, `arrendamento_preco`, nem os booleanos de amenidades (`elevador`, `garagem`, `piscina`, `jardim`, `terraco`, `varanda`, `vista_mar`, `vista_praia`, `ar_condicionado`, `aquecimento_central`, `arrecadacao`, `estacionamento`). Confirmado por análise exaustiva de todos os exports arquivados — o Excel simplesmente não traz esses dados. Ver secção 5 sobre como esses campos **são** preenchidos (via API, não via Excel).

### 3.4 Tabela `contactos`

Bloco de contacto, lido com o offset dinâmico `I()`. Chave de upsert: **`ego_link`** (não `nome, criado_em` como nos formatos legados — ver secção 6).

| Coluna Excel (índice base, some `+SHIFT`) | Campo Supabase |
|---|---|
| I(317) — Nome | `nome` |
| I(319) — Telemóvel | `telemovel` |
| I(321) — Email | `email` |
| I(456) — Link do contacto no eGO | `ego_link` |
| I(458) — data de atualização | `ego_atualizado_em` e `criado_em` |

Contactos sem `ego_link` são **ignorados** (não têm chave de conflito fiável) e o script regista quantos foram descartados no log.

### 3.5 Tabela `notas` (FK → `oportunidades.oportunidade_ref`)

| Coluna Excel (índice base +SHIFT) | Campo Supabase |
|---|---|
| I(463) | `nota_texto` (truncado a 1200 caracteres — limite do índice btree do Postgres) |
| I(464) | `nota_data_raw` / `nota_data_iso` (parseada) |
| I(465) | `nota_autor` |
| I(466) | `nota_tipo` |
| I(467) | `nota_anexos` |
| [1] Potencial cliente | `cliente_nome` |
| "Link" (dinâmico) | `url` |
| — | `origem_lista` = `"todas_as_colunas"` |

Uma linha é tratada como nota se `nota_texto` **ou** `nota_autor` estiverem preenchidos. Chave de upsert: `(oportunidade_ref, nota_texto, nota_data_raw)`.

### 3.6 Tabela `tarefas` (FK → `oportunidades.oportunidade_ref`)

| Coluna Excel (índice base +SHIFT) | Campo Supabase |
|---|---|
| I(468) | `tarefa_titulo` |
| I(469) | `tarefa_descricao` |
| I(470) | `tarefa_due_raw` / `tarefa_due_iso` |
| I(471) | `tarefa_responsavel` |
| I(472) | `tarefa_criado_por` |
| I(473) | `tarefa_status` (normalizado via `STATUS_MAP`; usado também para **detetar** se a linha é uma tarefa — valores válidos: "Concluído", "Em Curso", "Pendente") |
| I(474) | `tarefa_criado_em` |
| I(475) | `tarefa_reagendamento_iso` |
| I(476) | `tarefa_reagendada` |
| [1] Potencial cliente | `cliente_nome` |
| [72] Link | `url` |
| — | `tipo_oportunidade` (copiado da oportunidade já processada na mesma passagem) |
| — | `origem_lista` = `"todas_as_colunas"` |

Chave de upsert: `(oportunidade_ref, tarefa_titulo, tarefa_due_raw)`.

### 3.7 Preferências do comprador — campos `pref_*` em `oportunidades`

| Coluna Excel (índice base +SHIFT) | Campo Supabase |
|---|---|
| I(477) | `pref_zona` |
| I(478) | `pref_natureza` |
| I(480) | `pref_negocio` |
| I(481) | `pref_tipologia` (nº quartos → "T1"/"T2"/… via `PREF_QUARTOS_MAP`) |
| I(485) | `pref_preco_min` |
| I(486) | `pref_orcamento_max` |
| I(489) | `pref_disponibilidade` |

**Precedência:** estes 7 campos (`PREF_SHARED_CAMPOS`) só são escritos por uma **RPC** dedicada, `bulk_update_prefs(updates jsonb)`, que **só atualiza a oportunidade se `pref_extraido_em IS NULL`**. Ou seja: se já existe uma extração automática por IA a partir das notas (feita por `extract_preferences.py`, script separado que corre localmente), essa extração **prevalece** e o Excel não a sobrescreve. O Excel só serve de "primeira aproximação" enquanto não há extração por IA.

### 3.8 Visitas — campos `visita_*` / `imovel2_*` em `oportunidades`

| Coluna Excel (índice base +SHIFT) | Campo Supabase |
|---|---|
| I(490) | `visita_ref_ego` |
| I(491) | `visita_anulada` — também usado para **detetar** se a linha é visita (valores válidos: "Sim"/"Não") |
| I(492) | `visita_interessado` |
| I(493) | `visita_data` |
| I(494) | `visita_imovel_proprietario` |
| I(495) | `visita_cliente` |
| I(496) | `visita_pontos_positivos` |
| I(497) | `visita_pontos_negativos` |
| I(498) | `visita_sobre_negocio` |
| I(499) | `visita_observacoes` |
| I(500) | `visita_responsavel` |
| I(501) | `visita_imovel_ref` e `imovel2_ref` |
| I(502) | `imovel2_distrito` |
| I(503) | `imovel2_concelho` |
| I(504) | `imovel2_freguesia` |
| I(505) | `imovel2_venda` |

Estes campos são gravados por `update()` direto na oportunidade (não usam a RPC de preferências) — sempre sobrescrevem, sem condição.

---

## 4. Formatos legados (ainda suportados, já não gerados normalmente)

### 4.1 `*PowerBI*.xlsx` → tabela `oportunidades`

Ficheiro "rico" de ~55 colunas do PowerBI. Usa **índices posicionais** (não por nome — o ficheiro tem cabeçalhos duplicados). Chave de upsert: `oportunidade_ref`.

Mapeamento completo (posição → campo): `Referência`[0]→`oportunidade_ref`, `Potencial cliente`[1]→`cliente_nome`, `Proprietário`[2]→`imovel_proprietario`, `Tipo de negocio`[3]→`tipo_oportunidade`, `Tipo de pedido`[4]→`tipo_pedido`, `Origem`[5]→`origem`, `Sub origem`[6]→`sub_origem`, `Portal`[7]→`portal`, `Estado`[8]→`oportunidade_estado`, `Etapa`[9]→`etapa_atual`, `Imóvel preço`[10]→`imovel_preco`, `Proposta`[11]→`proposta`, `Diferença`[12]→`diferenca`, `Data da proposta`[13]→`data_proposta`, `Estado`[14]→`estado_proposta`, `Etapa`[15]→`etapa_proposta`, `Data de criação`[16]→`ego_data_criacao`, `Editado em`[17]→`ego_editado_em`, `Probabilidade`[18]→`probabilidade`, `Agência`[19]→`agencia`, `Email da agência`[20]→`agencia_email`, `Telefone da agência`[21]→`agencia_telefone`, `Responsável`[22]→`responsavel`, `Etapas de CPCV`[23]→`etapas_cpcv`, `Etapas de escrituras`[24]→`etapas_escrituras`, `Checklist financiamento`[25]→`checklist_financiamento`, `Checklist CPCV`[26]→`checklist_cpcv`, `Checklist escrituras`[27]→`checklist_escrituras`, [28] ignorado (duplicado), `Referência imóvel`[29]→`imovel_ref`, `Natureza`[30]→`imovel_natureza`, `Distrito`[31]→`imovel_distrito`, `Concelho`[32]→`imovel_concelho`, `Freguesia`[33]→`imovel_freguesia`, `Venda (€)`[34]→`imovel_venda`, `Estado fechado em`[35]→`estado_fechado_em` (só se preenchido), `Data da escritura`[36]→`data_escritura`, `Valor do negócio`[37]→`valor_negocio`, `Equipa responsável`[38]→`equipa_responsavel`, `Referência visita`[39]→`visita_imovel_ref`, `Visita anulada`[40]→`visita_anulada`, `Ficou interessado`[41]→`visita_interessado`, `Data visita`[42]→`visita_data`, [43]→`visita_imovel_proprietario`, [44]→`visita_cliente`, `Pontos positivos`[45]→`visita_pontos_positivos`, `Pontos negativos`[46]→`visita_pontos_negativos`, `Sobre o negócio`[47]→`visita_sobre_negocio`, `Observações`[48]→`visita_observacoes`, [49]→`visita_responsavel`, `Referência imóvel 2`[50]→`imovel2_ref`, `Distrito 2`[51]→`imovel2_distrito`, `Concelho 2`[52]→`imovel2_concelho`, `Freguesia 2`[53]→`imovel2_freguesia`, `Venda (€) imóvel 2`[54]→`imovel2_venda`.

### 4.2 `imoveis*.xlsx` / `*imoveis*.xlsx` → tabela `imoveis`

Detecta colunas **por nome de cabeçalho** (não posicional). Mapeia: Referência→`imovel_ref` (chave de upsert), Natureza→`natureza`, Disponibilidade→`disponibilidade`, Estado→`estado`, Proprietário→`proprietario`, Angariador→`angariador`, Vendedor→`vendedor`, Título→`titulo`, Quartos→`quartos`, Área útil/bruta/terreno→`area_util`/`area_bruta`/`area_terreno`, Conservação→`conservacao`, Piso→`piso`, Número de pisos→`num_pisos`, Venda (€)→`venda_preco`, Arrendamento (€)→`arrendamento_preco`, Morada/Código postal/Número/Fração/Concelho/Freguesia/Zona→campos homónimos, Data de criação/alteração→`data_criacao`/`data_alteracao`, comissões→`comissao_agencia`/`comissao_angariador`/`comissao_vendedor`, Certificação Energética→`certificacao_energetica`, Descrição→`descricao`, Casa(s) de Banho→`casas_banho`, Contrato de mediação - Exclusividade→`exclusividade`, coluna de vídeo (se existir, vários nomes possíveis)→`video_url`. Além disso, deteta dinamicamente colunas de amenidades (elevador, garagem, piscina, jardim, terraço, varanda, vista mar, "perto da praia"→`vista_praia`, ar condicionado, aquecimento central, arrecadação, estacionamento) e grava-as como booleano (`IMOVEL_BOOL_MAP`).

### 4.3 `Contactos PBI*.xlsx` / `*contactos*.xlsx` → tabela `contactos`

Colunas por nome: Nome→`nome`, Email→`email`, Tipo→`tipos` (array), Criado em→`criado_em`. Linhas sem nome ou sem data de criação são ignoradas. Chave de upsert: `(nome, criado_em)` — **diferente** da chave usada no formato `todas_as_colunas` (`ego_link`).

### 4.4 `tarefas*.xlsx` → tabela `tarefas`

Colunas por nome: Assunto→`tarefa_titulo`, Data de agendamento→`tarefa_due_raw`/`tarefa_due_iso`, Estado da Tarefa→`tarefa_status`, Referência→`oportunidade_ref`, Tipo de negocio→`tipo_oportunidade`, Potencial cliente→`cliente_nome`, Link→`url`. Linhas sem `oportunidade_ref` são ignoradas.

### 4.5 `backup_ego*.xlsx` / `*backup*.xlsx` (multi-sheet) → `oportunidades` + `notas` + `tarefas`

Único formato lido com `pandas`/`openpyxl` em vez do leitor XML próprio. Espera 3 folhas: **Oportunidades**, **Notas**, **Tarefas**, cada uma já com nomes de coluna iguais aos campos Supabase (`oportunidade_ref`, `nota_texto`, `tarefa_titulo`, etc. — ver código para a lista exata). Usado apenas para **backfills históricos**, não faz parte do fluxo diário normal.

---

## 5. Enriquecimento pós-Excel — EGO WebAPI (`_webapi_sync_fh`)

Depois de processar todos os `.xlsx`, o script chama sempre (a menos que se use `--skip-webapi`) a **EGO WebAPI** (`http://websiteapi.egorealestate.com`) para cada imóvel com referência `FH*` e `disponibilidade = 'Disponível'`. **Isto não vem do Excel** — é uma chamada HTTP direta à API do eGO, feita uma vez por imóvel, com pausa de 3s entre chamadas (e retry com backoff em caso de erro 429).

Campos que só chegam a `imoveis` por esta via (nunca pelo Excel):

| Campo Supabase | Origem na resposta da API |
|---|---|
| `foto_principal` / `fotos` | `Images[].Original` |
| `video_url` | `Videos[].VideoUrl` (normalizado para link do YouTube) |
| `panoramic_url` | `MainPanoramicUrl` |
| `area_util` / `area_bruta` / `area_terreno` | tags `AREA_U` / `AREA_B` / `AREA_T` (só sobrescreve se > 0) |
| `quartos` | tag `PROPERTY_HAS_BEDROOM` |
| `casas_banho` | tag `PROPERTY_BATHROOM` |
| `piso` | tag `PROPERTY_FLOOR` |
| `conservacao` | tag `FEATURE_CONDITION` |
| `certificacao_energetica` | `EnergyCertification` |
| `garagem`, `elevador`, `piscina`, `terraco`, `varanda`, `jardim`, `vista_mar`, `ar_condicionado`, `aquecimento_central`, `arrecadacao`, `estacionamento` | booleanos derivados de várias tags (ver `bool_map` no código) |

> Nota: colunas `suites`, `vista_praia`, `arrendamento_preco`, `ego_id`, `portais`, `disponivel_na_api`, `publicado`, `fonte` existem na tabela `imoveis` mas **não são escritas nem pelo Excel nem por este enriquecimento WebAPI** — a origem delas (manual, portal, ou outro processo) deve ser confirmada separadamente antes de assumir que estão sempre atualizadas.

---

## 6. Estratégia de upsert, chaves de conflito e deduplicação

```python
BATCH = 200  # linhas por pedido HTTP
```

| Tabela | Chave de conflito usada pelo sync | Observação |
|---|---|---|
| `oportunidades` | `oportunidade_ref` | |
| `notas` | `oportunidade_ref, nota_texto, nota_data_raw` | |
| `tarefas` | `oportunidade_ref, tarefa_titulo, tarefa_due_raw` | |
| `contactos` | `nome, criado_em` (formatos legados) **ou** `ego_link` (formato `todas_as_colunas`) | duas estratégias diferentes coexistem no mesmo script |
| `imoveis` | `imovel_ref` | |

Antes de cada upsert, `upsert_batch()`:
1. Deduplica as linhas pela chave de conflito (evita o erro do Postgres "cannot affect row a second time within a single statement").
2. Envia em lotes de 200.
3. Em caso de falha de um lote inteiro, tenta sub-lotes de 10; se ainda falhar, tenta linha a linha (e regista no log a linha que falhou definitivamente).

Todos os payloads passam por uma limpeza que **remove chaves com valor `None`** antes de enviar — por isso um export parcial nunca apaga dados já existentes no Supabase.

---

## 7. Normalizações aplicadas

| Campo | Valor no Excel | Valor gravado no Supabase |
|---|---|---|
| `oportunidade_estado` | `"Activa"` | `"Ativa"` |
| `tipo_oportunidade` | `"angariacao"` | `"Angariação"` (e variantes CASASAPO) |
| `tarefa_status` | `"Em Curso"` | `"pendente"` |
| `pref_tipologia` | `"2"` (nº de quartos) | `"T2"` |
| datas | vários formatos PT (`dd/mm/aaaa`, texto por extenso "16 de junho de 2026", etc.) | ISO `YYYY-MM-DD` |
| preços | `"150.000,00 €"` | `150000.0` (float) |
| `nota_texto` | qualquer comprimento | truncado a 1200 caracteres (limite do índice do Postgres) |
| booleans de amenidades | `"Sim"` / `""` (ou `1`/`0`) | `true` / `false` |

---

## 8. Fluxo de execução (`main()`)

1. Lê credenciais Supabase (`SUPABASE_URL` + `SUPABASE_SERVICE_KEY`/`SUPABASE_KEY`, por ordem: variáveis de ambiente → `.env` na pasta do script → `config.py`).
2. Cria o cliente Supabase e força HTTP/1.1 (workaround para erros "Server disconnected" observados em alguns sandboxes com HTTP/2).
3. Lista todos os `*.xlsx` em `exports/` (ou na pasta passada por `--pasta`), ordenados por nome.
4. Para cada ficheiro: deteta o tipo, chama o parser correspondente, e **só arquiva o ficheiro se não houver exceção** (ficheiros com erro ficam em `exports/` para retry na próxima corrida).
5. No fim (a menos que `--skip-webapi`), corre `_webapi_sync_fh()` para todos os imóveis FH disponíveis.
6. Regista tudo em `sync_log.txt` (mesma pasta do script) e no stdout.

---

## 9. Notas de manutenção / armadilhas conhecidas

- **Adicionar um novo tipo de ficheiro:** criar `process_novo_tipo()` e adicionar um `elif` em `detect_file_type()` **e** em `main()`.
- **O Wigo muda o número de colunas com frequência.** O `SHIFT` é recalculado automaticamente por export — não precisa de intervenção manual, mas se o Wigo mudar a *ordem* dos campos dentro de um bloco (não só o número de colunas), os índices fixos (`I(463)`, `I(477)`, etc.) deixam de bater certo e é preciso reanalisar um export novo.
- **Ficheiro truncado pelo OneDrive:** já aconteceu o OneDrive truncar o `.py` a meio de uma edição. Se aparecerem erros de sintaxe, confirmar se `main()` e o `if __name__ == "__main__":` final ainda estão presentes.
- **`upsert_all.py` não deve ser usado** — script antigo e mais limitado, mantido só por histórico.
- **`extract_preferences.py`** (extração de preferências por IA a partir das notas) não corre dentro do Cowork (timeout de 45s) — tem de correr localmente.
- Mensagens "Server disconnected" no Playwright/httpx durante o sync podem ser ignoradas (o script já tem retry/workaround para isto).
- **Colunas do schema que existem mas não são escritas por este pipeline** (confirmado por grep ao código-fonte — úteis para não perder tempo a "debugar" um campo sempre vazio):
  - `oportunidades`: `xlsx_valor`, `xlsx_comm_ag`, `xlsx_comm_ang`, `xlsx_comm_vend`, `xlsx_margem`, `xlsx_estado_prop`, `xlsx_data_fecho`, `xlsx_data_prop`, `xlsx_exclusivo`, `xlsx_origem`, `xlsx_ref_im`, `xlsx_angariador`, `imovel_arrendamento`, `preferencia_imovel`, `etapa_dias`, `ultima_consulta_em`, `titulo_imovel` — legado de uma versão anterior do pipeline (provavelmente `upsert_all.py`), hoje sem escrita ativa.
  - `oportunidades`: `data_criacao_raw`/`data_criacao_iso` só são escritos pelo parser `backup_completo` (backfill histórico), não pelo fluxo diário `todas_as_colunas`.
  - `oportunidades`: `pref_outros` e `pref_extraido_em` são escritos por `extract_preferences.py` (script separado, IA), não por este sync.
  - `notas`: `nota_resultado`, `nota_origem` — sem origem ativa identificada neste script.
  - `contactos`: `whatsapp_permissao`, `whatsapp_data`, `telefone`, `data_nascimento`, `nacionalidade`, `responsavel`, `rgpd_telefone`, `rgpd_telemovel`, `rgpd_email`, `duplicado` — não vêm do Excel; origem (manual/portal) a confirmar.
  - `imoveis`: `suites`, `vista_praia`, `arrendamento_preco`, `ego_id`, `portais`, `disponivel_na_api`, `publicado`, `fonte` — não escritos nem pelo Excel nem pelo enriquecimento WebAPI atual.

---

## 10. Referência rápida — dependências e credenciais

```bash
pip install supabase "httpx[socks]" socksio python-dotenv pandas python-calamine openpyxl requests
```

Projeto Supabase: `zphasvfopnbzwnaidsnw` (eu-west-1, "EGO Scapper"). Credenciais em `.env` na mesma pasta do script (`SUPABASE_URL`, `SUPABASE_SERVICE_KEY`). Chave da EGO WebAPI hardcoded como fallback em `_webapi_sync_fh()` (variável de ambiente `EGO_API_KEY` tem prioridade).
