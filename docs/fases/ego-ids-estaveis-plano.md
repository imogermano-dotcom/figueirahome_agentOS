# Ids estáveis do eGO: `ego_lead_id` e `ego_person_id` (pedido #27) — plano

> Plano antes de código. Medido a 01/11 só em leitura (nenhuma escrita). Sem nomes nem telefones de clientes.

## Porquê
Ligamos hoje oportunidades, notas e contactos por nome, telefone ou texto de URL. O eGO tem ids numéricos estáveis que só existem dentro dos URLs
(`/Leads/N`, `/lead/N`, `/person/N`). Uma coluna própria, única, é a chave externa que as fases da API (A2 notas, tarefas, reconciliação) precisam.

## Medido (01/11)
| | |
|---|---|
| `oportunidades` | 26 209 |
| com id no `url` | **21 769** (83 %), todos distintos, 0 repetidos |
| sem `url` | 4 440 (nenhuma está entre as 2 793 ativas da API) |
| formas do `url` | `/egocore/Leads/N` (11 559), `/egocore/lead/N` (10 210), vazio (4 440) |
| `contactos` | 28 859 |
| com `/person/N` no `ego_link` | **12 742**, todos distintos, 0 repetidos |
| sem `ego_link` | 16 117 (pipeline, site, Meta) |
| id da API (`ListOpportunityByPage.id`) == id do `url` | 2 793 de 2 793 ativas (as 157 que pareciam diferir só usam a forma `/lead/N`) |

Duas formas de `url`: um regex só para `/Leads/N` falha 10 210 linhas. Regex único: `/[Ll]eads?/(\d+)`.

## Desenho
1. **Migration `0056`** (corrida à mão por ti): 
   - `oportunidades.ego_lead_id bigint` e `contactos.ego_person_id bigint`, índice único parcial em cada (`where ... is not null`).
   - Backfill por SQL a partir de `url` e `ego_link` (só preenche NULL; não toca em mais nada). `oportunidades` tem `BEFORE UPDATE` que carimba
     `atualizado_em`: o backfill desliga-o durante o UPDATE em massa (como o de `contacto_id`) para não marcar 21 769 linhas como «atualizadas agora».
2. **Quem escreve daí em diante:**
   - `linha_de_oportunidade` (API) grava `ego_lead_id = o["id"]`; o scraper (`mapping_todas_colunas`) extrai-o do `url`/`ego_link` no upsert.
   - Notas e tarefas **não** ganham coluna: apanham o id da oportunidade pela ligação à `oportunidades` (join por `oportunidade_ref`). Coluna a mais = outro valor que
     pode divergir.
3. **Contactos sem link (16 117):** ficam sem `ego_person_id` até serem promovidos no eGO (**pergunta ao Miguel**, já feita no registo a 26/10).
4. **Fase 2 (fora deste plano):** `potencialClientId` da API para preencher o elo oportunidade → pessoa onde só há nome; proprietário no imóvel.

## O que não faz
Não apaga nem corrige linhas; não muda a chave primária de `contactos`; não toca no `contacto_id`. As 4 440 sem `url` ficam sem `ego_lead_id` (a API de arquivadas
numa só página corta a ligação; ver paginação se algum dia for preciso).

## Testes
- Extração do id (ambas as formas de `url`, `ego_link`, texto sem id → `None`).
- `linha_de_oportunidade` leva `ego_lead_id`.
- Query de verificação da migration: contagens de `ego_lead_id`/`ego_person_id` iguais às de cima, 0 repetidos.

## Risco
Baixo: só acrescenta colunas nulas e preenche-as de dados que a linha já tem. O único cuidado é o `BEFORE UPDATE` de `oportunidades` e o índice único (se houvesse
repetidos, a criação falharia; medimos 0).

**Estado: plano escrito a 01/11. Por fazer: migration `0056` (explicada antes de correres), código do scraper e da API, testes.**
