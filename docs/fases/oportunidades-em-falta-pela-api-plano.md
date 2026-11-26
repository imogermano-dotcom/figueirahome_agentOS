# Oportunidades novas do eGO que o relatório demora a trazer (pedido #28, 26/11)

**Plano antes de código; nada deste plano está implementado.** Sem nomes, telefones nem emails de pessoas (só contagens e referências de oportunidades).
Continuação de `notas-dedup-e-cadencia-plano.md` e `notas-autor-e-tipo-plano.md`. É um passo pequeno da A5 de `ego-api-substituir-scrapers-plano.md`.

## Problema
Uma oportunidade criada no eGO (as leads promovidas, como as do FH2585) só chega a `public.oportunidades` pelo relatório das 03:37 UTC, e o relatório só lê as oportunidades **editadas** nas últimas 48 h; criar uma não conta como edição (o mesmo mecanismo das propostas e das notas). Enquanto a linha não existe:
- as notas dessa oportunidade não entram (FK `notas_oportunidade_ref_fkey`): a volta do `sync-notas` conta-as em `sem_oportunidade`;
- o portal, as tarefas e as visitas também não a veem.

## Medido (26/11, só leitura)
- 2 658 oportunidades ativas no eGO; **12 ainda não estão na BD** (criadas entre 25/11 18:20 e 26/11 16:00 UTC, ids seguidos, todas de leads), com **22 notas com texto** à espera. `sem_oportunidade` subiu de 7 (15:07) para 11 (16:07) ao longo do dia.
- Das 12, 5 foram criadas **antes** das 03:37 de hoje e mesmo assim o relatório não as trouxe: a hipótese (não confirmada) é que uma oportunidade nova e sem edição não entra nas «últimas 48 h». Se amanhã aparecerem, é só atraso de um dia; se não, fica confirmado.
- A lista de ativas (`ListOpportunityByPage`, já usada em `ego_api.oportunidades_ativas`) traz, para uma oportunidade nova: `name` (a referência), `id`, `createDate`, `alterDate`, `realestateReference`, `originId`/`leadOrigin`/`leadSubOrigin`, `masterLeadType`/`leadType`, `assignToSecurityUserIds`, `potencialClientId`, `title`, `email`, `phone`, `obs`. O mapa coluna a coluna da `oportunidades` (101 colunas) está em `ego-api-substituir-scrapers-plano.md`.

## Desenho

### 0. Verificações (feitas a 26/11, só leitura)
1. **Esquema da `oportunidades`** (OpenAPI do Supabase): só `oportunidade_ref` é obrigatória (o `id` é gerado e `apagada_no_ego` tem `false` por omissão); `origem_lista` tem `Ativas` por omissão; `ego_data_criacao`/`ego_editado_em` são `date`; `tipo_oportunidade` é um enum. **Por saber:** o `check` de `oportunidade_estado` (o scraper normaliza para `Ativa`).
2. **Como o scraper escreve:** `url` = `https://admin.egorealestate.com/egocore/Leads/<id>` e o `ego_lead_id` sai do fim do URL; `cliente_telefone`/`cliente_email` não vêm do relatório, copiam-se do contacto ligado.
3. **Mapas medidos** (2 648 ativas da BD cruzadas com a API): `masterLeadType.id` 1 → «Angariação», 2 → «Venda», 3 → «Arrendamento»; `leadTypeId` 4 → «Pedido de Informação», 3 → «Pedido de Visita», 1 → «Procura», 7 → «Pedido de Contacto», 0 → vazio. `originId` 11 + `leadSubOriginId` 34798477 → `origem='Outros'`, `sub_origem='Facebook campanha'` (194 de 194). As 12 em falta são «Venda» + «Pedido de Informação».
4. **A lista de «ativas» do eGO inclui oportunidades que a BD tem como `Perdida` (533) e `Ganha` (49):** o esqueleto não pode gravar `Ativa` à cega.
5. **Contacto das 12 (por telefone ou email da lista, só contagens):** 8 têm exatamente 1 contacto sem `ego_link` (leads da Meta), 1 tem 1 contacto com `ego_link`, 3 têm 2 ou mais (duplicados do #27); nenhuma fica sem contacto. Pelo `ego_link` (`potencialClientId`) **0 de 12** existem.
6. **O que o portal faz com uma linha parcial** (sem etapa, imóvel nem preferências): **por perguntar ao Miguel**.

### 1. Criar o esqueleto das oportunidades em falta
Em `app/integrations` (módulo pequeno, junto de `ego_notas`):
- `em_falta(ativas)`: as ativas do eGO cuja `name` não está em `oportunidades` (máx. 50 por volta).
- `criar_esqueleto(o)`: **só INSERT** (nunca UPDATE, nunca toca em linha que exista) com `oportunidade_ref`, `oportunidade_estado='Ativa'`, `cliente_nome`, `cliente_email`, `cliente_telefone`, `ego_lead_id` (o `id` da oportunidade no `url`), `url` (`.../egocore/Leads/<id>`), `ego_data_criacao`, `ego_editado_em` (só a data), `imovel_ref`, `origem`/`sub_origem` e `tipo_oportunidade`/`tipo_pedido` pelos mapas medidos (ponto 0.3), `responsavel` (pelo mapa de utilizadores, como as notas). O resto fica vazio e o relatório completa-o quando a oportunidade for editada (o upsert só escreve os campos que traz).
- **Só se cria a oportunidade realmente aberta** (sem `closedDate` e sem estado de ganha ou perdida); as outras ficam para o relatório e contam em `esqueleto_saltados`. Um código de tipo ou de origem fora dos mapas também salta, em vez de se inventar o valor.
- **Ligação ao contacto:** o `ego_link` das pessoas ainda não existe (0 de 12), por isso liga-se por telefone/email **quando há um só contacto** (`contacto_match='telefone'` ou `'email'`, a confiança menor que o `ego_link`); com 2 ou mais contactos fica **vazio**, sem adivinhar, até à fusão dos duplicados (#27). Nunca se completa o `ego_link` de uma linha da Meta (reescreveria a PK). Quando o relatório trouxer a pessoa e a oportunidade, o elo passa a `ego_link`. Pelo RPC `set_contacto_oportunidades`, nunca por escrita direta.
- Corre no início de `reconciliar_notas` (cron `sync-notas`, de hora a hora), antes de gravar as notas, para as notas dessa volta já terem onde se prender.
- Falha numa oportunidade (check, FK) salta-a e conta `esqueleto_erros`; nunca pára a volta.
- **Interruptor `OPORTUNIDADES_API_EGO`** (vazio = só conta `oportunidades_em_falta` no resumo da volta; `1` = cria), ligado em dois tempos como nos outros casos.

### 2. O que não muda
Nunca se escreve no eGO. Nunca se altera nem se apaga uma oportunidade existente. As colunas do relatório (`proposta`, etapas, imóvel, preferências) continuam a vir do relatório. O trigger `BEFORE UPDATE` que carimba `atualizado_em` não é tocado (só há INSERT). A chave é `oportunidade_ref`: o relatório e o esqueleto convergem na mesma linha.

## Riscos
- **Linha parcial a mais no portal:** a `oportunidades` é lida pelo portal do Miguel; uma linha sem etapa, imóvel nem preferências pode aparecer vazia ou ser filtrada. É a pergunta do ponto 0.4; **não se liga sem a resposta dele**.
- **Estado errado:** só se cria com `oportunidade_estado='Ativa'` (a lista é a das ativas); outro estado não se escreve.
- **Telefone/email em formatos diferentes** do relatório: usar as funções de normalização do scraper (ponto 0.2) e não inventar formatos.
- **Pedidos à API:** a lista de ativas já se lê em cada volta (`novas()`); não há pedidos novos.
- **Preferências por IA:** não há trigger de INSERT em `oportunidades` conhecido; confirmar no ponto 0.1.

## Prova
- Testes sem rede: oportunidade em falta cria esqueleto com os campos certos; oportunidade que já existe não se toca; uma recusada (check) salta e conta `esqueleto_erros`; interruptor desligado só conta; máximo de 50 por volta.
- Dry-run em produção (só leitura): `oportunidades_em_falta` esperado ≈ 12 e a lista de campos que se gravaria, sem pessoas.
- 1.ª volta real: as notas das 12 oportunidades entram (`sem_oportunidade` desce), nenhuma linha duplicada e o relatório das 03:37 seguinte completa-as sem erros.

## Passos (cada um com OK próprio)
1. **Feito:** verificações 0.1 a 0.5 (só leitura). **Falta:** (a) ler as RPCs `set_contacto_oportunidades` e `propagar_contacto_id` para ver se aceitam ligar por `contacto_id` conhecido (a camada «telefone» do backfill de 05/10 já o fazia); se não, decidir com o utilizador antes de escrever `contacto_id`; (b) o `check` de `oportunidade_estado`; (c) a pergunta ao Miguel (0.6).
2. Código e testes, sem tocar em produção; commit, push, deploy do agentos (interruptor vazio).
3. Ver `oportunidades_em_falta` numa volta; ligar `OPORTUNIDADES_API_EGO=1` (`secrets deploy`) com a resposta do Miguel.
4. Ver a volta seguinte e o relatório das 03:37 (sem erros, `sem_oportunidade` a 0); nota no registo (#28) e CLAUDE.md.

## Para o Miguel
As leads promovidas só chegam à `oportunidades` depois do relatório das 03:37 do dia seguinte (ou nem isso, se o eGO não as contar como editadas). Propomos criá-las na hora pela API, com os campos que a API dá (referência, cliente, imóvel, origem, tipo, responsável, datas); o resto (etapa, preferências, proposta) continua a vir do relatório. **Pergunta:** o portal e o vosso pipeline lidam bem com uma oportunidade sem etapa, imóvel nem preferências durante algumas horas, ou preferem que só apareça completa?
