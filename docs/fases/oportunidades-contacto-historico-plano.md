# Pedido #4, etapa 2: `contacto_id` e telefone no histórico das oportunidades — plano

> Plano antes de código. Medido a 01/11 só em leitura (nenhuma escrita). Sem nomes nem telefones de clientes.

## Ponto de partida (verificação de 01/11)
| | sem telefone | sem `contacto_id` | baseline 29/10 |
|---|---|---|---|
| Vendas (VEN) | 2 528 | 2 821 | 5 711 / 2 796 |
| Angariações (CAP) | 538 | 801 | 561 / 800 |
| Arrendamentos (LLO) | 297 | 286 | 813 / 286 |

- Telefone: desceu (as 4 Vendas do caso estão preenchidas; `cbedd79` já impede gravar vazio por cima). `contacto_id`: **nada desceu** (+25 nas Vendas).
- O sync por relatório só liga o `contacto_id` quando apanha a oportunidade numa edição; o histórico antigo nunca foi ligado por id.

## Medido nas 2 793 ativas da API (id da API == `ego_lead_id`, 2 793/2 793 na BD)
- Campo da pessoa: `potencialClientId` (Venda/Arrendamento) e `ownerId` (Angariação). **Atenção à grafia: `potencialClientId`.** Preenchido em 2 302; `ownerId` em 486.
- Sem `contacto_id` na BD: **689** (VEN 603, CAP 73, LLO 12, 1 de outro tipo).
  - **507** resolvem: o id da pessoa é o `ego_person_id` de um contacto (VEN 494, LLO 12, CAP 1).
  - **177** têm id de pessoa que **não está em `contactos`** (CAP 67, VEN 109): a pessoa não foi sincronizada (sem `ego_link`, ver #27).
  - 5 Angariações sem pessoa na API.
- Das que já têm `contacto_id` e cuja pessoa resolve: 1 945 iguais, **32 diferentes**. Não se tocam (ficam num relatório para o Miguel).

## O que o código existente já faz
`ego_api_reconciliar.ligar_contactos(api, refs)`: liga por `potencialClientId` → `/person/N` do `ego_link`, só com elo único, pelo RPC `set_contacto_oportunidades` (propaga a notas, tarefas, visitas). **Só ativas, só `potencialClientId`.**

## Desenho
1. **H1 — ativas (507):** `ligar_contactos` passa a usar `ego_person_id` (coluna indexada, em vez de reler os 28 859 contactos), com `ownerId` quando o tipo é Angariação. Só liga onde `contacto_id` é NULL; nunca muda um existente. Dry-run por omissão (conta), `--gravar` com ordem tua.
2. **H2 — arquivadas (~18 985):** `leadArchived: 1` numa só página falha por resposta demasiado grande. Paginar (`pageIndex`/`numberOfRecords`, como `todos_os_imoveis`) e aplicar a mesma regra. Medir primeiro (quantas resolvem) antes de gravar.
3. **H3 — telefone das Angariações sem telefone (538):** do proprietário, `GetEntity(ownerId)` → `personalContacts[]` com `personalContactTypeId 2`. O `GetEntity` dá **429 ao fim de umas dezenas** (`retry_after_seconds` 60): pausa e retoma, em lotes, só nas que têm `ownerId`. Preenche só onde `cliente_telefone` está vazio.
4. **Sem tocar:** as 177 sem contacto na BD (precisam do contacto criado, fora deste plano; lista ao Miguel), as 32 divergentes, as 5 sem pessoa.
5. **Rotina diária (ponto 1 e 2 do pedido):** o sync de propostas (04:17) já tem 3 partes; acrescentar H1 como 4.ª, atrás de interruptor vazio (só conta), como `NOTAS_API_EGO`. Fica para depois da corrida única validada.

## Testes
- `ligar_contactos`: liga só `NULL`, escolhe `ownerId` em Angariação e `potencialClientId` nas outras, ignora elo ambíguo e id desconhecido, não muda existente.
- H3: parser de `personalContacts` (tipo 2), pausa no 429 (cliente simulado).
- Verificação (a)–(d) do pedido, por contagem antes/depois.

## Risco
Escritas só em `NULL` (RPC existente, usada no backfill de 05/10). `oportunidades` tem `BEFORE UPDATE` que carimba `atualizado_em`: o RPC já é o caminho usado hoje; confirmar que não marca 500 linhas como «atualizadas agora» em coisa que o portal do Miguel lê (decisão tua: religar/desligar como na `0056`).
Registo em `agente_sync_log` com os pares ligados (reversível por `contacto_match='ego_link'` + data).

**Estado: plano escrito a 01/11. Nada gravado. Próximo passo: H1 em dry-run (só contagem).**
