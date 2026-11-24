# Criar em `contactos` as pessoas do eGO que faltam (pedido #4, etapa 3, 24/11)

**Plano antes de código; nada deste plano está implementado.** Sem nomes nem telefones de clientes.

## Pedido
A 19/11 o Miguel respondeu à lista de oportunidades cuja pessoa não existe em `contactos` (sobretudo proprietários de Angariações):
**criar todas a partir do eGO, ativas e arquivadas, com telefone e email, e ligar o `contacto_id`; mantém-se a regra de só preencher campos vazios.**
Está «Com quem: Developer» desde 19/11 e a 20/11 ficou registado que ainda não estava feito. Continuação de `oportunidades-contacto-historico-plano.md` (H1–H3, 01/11).

## Dimensão (medida a 24/11, só leitura)
- Oportunidades sem `contacto_id` cuja pessoa não está em `contactos`: **175 ativas** (CAP 65, VEN 110) e **1 594 arquivadas** (VEN 986, CAP 468, LLO 139, outra 1).
- **1 557 pessoas distintas** (168 ativas + 1 389 arquivadas; a mesma pessoa tem várias oportunidades).
- 271 oportunidades sem id de pessoa na API: **fora** (não há quem criar).
- `GetEntity(entityId)` devolve nome, `personalContacts` (`personalContactTypeId` 2 = telefone; o tipo do email por confirmar no passo 1), `alterDate`. Dá **429 ao fim de umas dezenas**
  (espera 60 s): 1 557 pedidos levam ~1 h; o script repete e retoma (`ego_api.contactos_da_entidade` já faz).
- `contactos` guarda a pessoa com `ego_link` (`…/egocore/person/<id>`, UNIQUE), `ego_person_id` (int) e `criado_em` (PK com `nome`; o pipeline usa a data de alteração do eGO).

## Desenho
Script `backend/scripts/criar_contactos_em_falta.py`, **dry-run por omissão**, saída só com contagens e ids (nunca nomes nem telefones):
1. **Pessoas em falta:** as da medição acima (mesma lógica de `ligar_historico`: `ownerId` nas Angariações, `potencialClientId` nas outras).
2. **Ler no eGO:** `GetEntity` de cada uma (com pausa no 429). Guardar só o que vai para `contactos`: nome, telefone(s), email, `alterDate`.
3. **Não duplicar** (há ~10 000 repetidos conhecidos): comparar cada pessoa com `contactos` existentes por **telefone normalizado** e por **email**:
   a) já existe linha com o mesmo `ego_person_id`/`ego_link` → só liga (não deve haver, é o ponto de partida);
   b) existe **uma** linha sem `ego_link` com o mesmo telefone ou email → **não cria**: preenche `ego_person_id` e `ego_link` nessa linha (só campos vazios) e liga. *Decisão a confirmar com o utilizador.*
   c) existem **várias** ou o telefone/email é de outra pessoa → não cria nem liga, vai para a lista do Miguel;
   d) sem correspondência → **cria**.
4. **Criar (d):** `nome`, `telefone`/`telemovel` (a mesma regra de normalização de `guards.normalizar_telefone`), `email`, `ego_link`, `ego_person_id`, `ego_atualizado_em` e `criado_em` = data do `alterDate`,
   `origem='ego_api'`, `whatsapp_permissao=false` (nunca consentimento por defeito). INSERT linha a linha, nunca upsert em lote (uma chave só presente num registo vira coluna e escreve NULL nos outros).
5. **Ligar:** `ego_api_reconciliar.py --historico --arquivadas --gravar` (já existe, liga por `ego_person_id` e propaga a notas/tarefas/visitas pelo RPC). Depois `--telefones --gravar` (H3).
6. **Registo:** `agente_sync_log` com os ids criados, os preenchidos e os que ficaram para o Miguel. Reversível: apagar só as linhas criadas (pelos `ego_person_id` do registo e do ficheiro de ids; **a `origem='ego_api'` não fica**: a base converte-a em `scraper` no INSERT, visto no 1.º lote de 24/11); as preenchidas voltam a NULL no `ego_link`/`ego_person_id`.

## O que não muda
Nada se escreve no eGO. Nunca se apaga nem se altera um campo já preenchido. Os assistentes e o pipeline do Miguel não são tocados.
O scraper continua a fazer upsert por `ego_link`: as linhas novas passam a ser atualizadas por ele, como qualquer outra pessoa com `ego_link`.

## Riscos
- **Duplicados:** o ponto 3 é a defesa; sem ele criavam-se ~1 500 repetidos. A comparação por telefone/email tem de ser conservadora (na dúvida, lista ao Miguel).
- **`oportunidades` tem `BEFORE UPDATE` que carimba `atualizado_em`**: ao ligar milhares, desligar o trigger durante a escrita e religá-lo (como a 01/11, SQL do utilizador, `tgenabled = 'O'` no fim).
- **Triggers de IA em `notas`** só disparam em INSERT; aqui só se faz UPDATE do `contacto_id`, por isso não correm.
- 429 do eGO: ~1 h de execução; o script tem de retomar sem repetir pedidos (guardar o progresso num ficheiro fora do repo).
- Entidades que não são pessoas (empresas, imobiliárias): vêm com nome e podem não ter telefone; criam-se na mesma se o Miguel as quer, senão ficam na lista.

## Passos (cada um com OK próprio)
1. **Dry-run** (só leitura, ~1 h): contagens por caso a/b/c/d, quantas têm telefone e email, tipo de contacto do email.
2. **Rever as contagens** com o utilizador, sobretudo o caso (b) e as empresas.
3. **Criar e preencher** (`--gravar`), 1 lote pequeno primeiro e verificar uma amostra por contagem.
4. **Ligar o histórico** e os telefones, com o trigger desligado (SQL do utilizador).
5. **Verificar** (contagens antes/depois de `sem contacto_id` e `sem telefone`), nota ao Miguel e atualizar o CLAUDE.md.
6. **Rotina:** `ligar_historico` como 4.ª parte do sync das 04:17 (interruptor), para as oportunidades novas.

## Resultados do dry-run (24/11, só leitura; `scripts/criar_contactos_em_falta.py`)
1 557 pessoas em falta, lidas no eGO (`GetEntity`, ~1 h com o 429; o sistema parou a 1.ª corrida por falta de memória e retomou-se do cache).

| Caso | Pessoas | Destino |
|---|---|---|
| a (já tem `ego_person_id`) | 0 | — |
| b (uma só linha sem `ego_link` com o mesmo telefone/email) | 663 | **661 completar** (nome igual ou contido); 2 sem nomes em comum → Miguel |
| c (várias linhas, ou a linha é de outra pessoa do eGO) | 695 | **Miguel** (precisa da fusão de duplicados) |
| d (sem correspondência) | 199 | **79 criar** (nome + telefone e/ou email); 120 sem telefone nem email → Miguel (3 são empresas) |

- Desdobramento do c: 331 com 3+ linhas (algumas já com ego), 254 pares sem identificação, 70 com 3+ sem identificação, 36 pares com uma já identificada, 4 outras. Das 29 085 linhas de `contactos`, 16 222 não têm `ego_link` nem `ego_person_id`.
- Nome no b: 658 iguais, 3 um contém o outro, 2 sem nomes em comum. Chave: 264 só telefone, 291 telefone e email, 108 só email.
- Tipos de contacto do eGO: telefone 2 (1 373), 5 (19), 1 (5); email 1 (762). **A deteção é pelo «@»**, não pelo tipo.

## Regra final (substitui o ponto 3 do desenho)
Completar só com **uma** linha candidata, **sem** identificação do eGO e com **nome igual ou contido**; criar só **sem correspondência** e com nome e telefone ou email (nunca consentimento de WhatsApp); o resto vai ao Miguel, que decide a fusão.
`--gravar` com `--limite N` para o 1.º lote; os ids tocados ficam num ficheiro fora do repo (reversão) e em `agente_sync_log` (`egorealestate_contactos_em_falta`).
Ligar o `contacto_id` é outro comando (`ego_api_reconciliar.py --historico --arquivadas --gravar`), com o trigger `trg_oportunidades_updated` desligado (SQL do utilizador).
Estado: dry-run feito, `--gravar` escrito e testado (1 004 testes) mas **não corrido**; por commit/OK do utilizador para o 1.º lote.
