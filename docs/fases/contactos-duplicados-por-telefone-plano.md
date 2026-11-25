# Contactos: o sync deixa de criar uma linha nova quando a pessoa já existe com o mesmo telefone (pedido #27 reaberto, 25/11)

**Plano antes de código; nada deste plano está implementado.** Sem nomes nem telefones de clientes (o caso é citado só pelos ids e formatos).

## Pedido
Nota de 25/11 no #27 (passou de Verificado a Pendente): o sync cria uma linha nova quando a pessoa já existe em `contactos` com o mesmo telefone noutro formato. Caso dado: um número de linha fixa com 2 linhas; 9 064 pares.

## Medido (25/11, só leitura)
- 29 167 linhas em `contactos`. **9 204 telefones** (9 últimos dígitos, juntando `telefone` e `telemovel`) estão em 2 ou mais linhas: **17 237 pares**. Em **8 224** as linhas têm formatos diferentes (9 dígitos, `00351…`, `351…`, `+351…`, com espaços).
- **7 460** são pares de exatamente 2 linhas com só uma `ego_link`: a linha antiga do pipeline do Miguel (sem `ego_link`, sem `agente`, sem `meta_lead_id`) e a do scraper.
- Caso dado: linha de 2019 com o número em 9 dígitos e sem `ego_link`; linha de 2026 com `00351…`, `ego_link` e origem `scraper`.

## Causa (verificada no código)
- Quem escreve é o sync `sync-oportunidades` (cron 03:37 UTC): `POST /api/oportunidades/sync/completo` → app `figueirahome-scraper` (Playwright, relatório «todas as colunas») → `scraper/upsert.py:_upsert_contactos`. **Não é a API nova**: só as tarefas e as notas já vão por ela. As visitas (A4) e os contactos (A6) do plano `ego-api-substituir-scrapers-plano.md` não estão começados, e a A5 (oportunidades) é parcial.
- O `_upsert_contactos` faz `upsert` registo a registo com a chave da tabela e **nunca compara o telefone**. Uma pessoa com `ego_link` novo gera linha nova, mesmo havendo uma linha sem `ego_link` com o mesmo número.
- O telefone vem como o CRM o mostra (`mapping_todas_colunas.py:112-118`), por isso os formatos variam.
- A API nova (A6) não resolveria sozinha: o upsert seria por `ego_person_id`/`ego_link`, e a comparação por telefone teria de existir na mesma. A regra escreve-se uma vez e serve aos dois caminhos.

## Desenho

### 1. Prevenção em `scraper/upsert.py` (o que se faz nesta etapa)
Antes do upsert de cada lote, para os registos cujo `ego_link` **ainda não existe** em `contactos` (lê-se por `ego_link`, em lotes de 50, como `_ligar_contactos`):
1. Normalizar o telefone do registo (9 últimos dígitos; ignora o que tem menos de 9) e procurar em `contactos` as linhas **sem `ego_link` e sem `ego_person_id`** com o mesmo número em `telefone` ou `telemovel`.
2. **Uma só candidata e nome igual ou contido** (sem acentos, sem maiúsculas): **completa-se essa linha** (`ego_link`, `ego_person_id`, `ego_atualizado_em`; telefone/email só se vazios). Não se toca em `nome` nem em `criado_em` (a PK fica como está; o upsert seguinte por `ego_link` já a encontra). É a regra do #4 (24/11, `criar_contactos_em_falta.py`).
3. **Várias candidatas, ou nome sem relação** (o mesmo número de uma família ou da agência): cria-se como hoje e conta-se em `duplicados_por_resolver`, para a fusão. Nunca se adivinha.
4. **Sem candidata:** cria-se como hoje.
5. O resumo do sync ganha `completados_por_telefone`, `duplicados_por_resolver` e `criados_com_gemeo` (os criados que tinham gémeo por telefone). **É a medição de quantos duplicados novos nascem por dia**, que hoje não existe (o `criado_em` é a data de alteração do eGO e não dá a de criação da linha).
6. **Interruptor `COMPLETAR_POR_TELEFONE`** (segredo do scraper no Fly): vazio = só conta e não completa, como um dry-run em produção; `1` = completa. Liga-se em dois tempos, depois de ver as contagens de uma corrida.
7. Falha na procura nunca derruba o lote: cria-se como hoje e regista-se.

A normalização do telefone é uma cópia pequena dentro do scraper (a app é separada e não importa o `backend`, como `ego_auth.py`); o teste prende as duas à mesma saída.

### 2. Fusão dos 9 204 que já existem (fora desta etapa)
É a «fusão de duplicados» que o CLAUDE.md reserva ao Miguel: a canónica é a linha com `ego_link`, repontando o `contacto_id` (RPC) e sem apagar nada sem ele. Os 7 460 pares de 2 com uma só `ego_link` têm regra simples e seriam o primeiro lote; os restantes (3+ linhas, ou nomes diferentes no mesmo número) ficam em lista para ele. **Plano próprio, depois deste.** Pergunta para o Miguel: o pipeline dele lê as linhas antigas por `(nome, criado_em)`?

## O que não muda
Nada se escreve no eGO. Nunca se apaga nem se sobrescreve campo preenchido. A chave `(nome, criado_em)` e a regra `criado_em` = data de alteração ficam (não se muda sem o Miguel). `oportunidades` tem `BEFORE UPDATE` que carimba `atualizado_em`: esta etapa não toca em oportunidades.

## Riscos
- **Completar a pessoa errada:** número partilhado entre pessoas. Defesa: só uma candidata e nome compatível; na dúvida, cria e conta.
- **PK referenciada:** o upsert posterior por `ego_link` pode mudar `nome`/`criado_em` da linha completada e bater na FK de `leads_angariacao` (23503). Já é apanhado por `_ERROS_POR_REGISTO` e contado como ignorado; acompanhar.
- **Mais pedidos por corrida:** uma procura por registo novo, e só para os `ego_link` novos (poucos por dia); o limite de 240 s do endpoint cobre-os. Medir no 1.º resumo.
- **Deploy do scraper** é app à parte e a RAM é escassa (só consultas pequenas).

## Testes
Auto-testes em `upsert.py` (`python upsert.py`), com um Supabase de mentira como os de `_upsert_contactos`:
- mesmo número em `00351…` e 9 dígitos, uma candidata, nome igual: completa em vez de criar;
- nome contido («Ana Silva» e «Ana Maria Silva»): completa; nome sem relação: cria e conta em `duplicados_por_resolver`;
- 2 candidatas: cria e conta; candidata que já tem `ego_link`: cria;
- interruptor desligado: não completa, mas conta;
- falha na procura: cria como hoje;
- normalização igual à do backend para `00351…`, `351…`, `+351…`, com espaços e com 2 números no mesmo campo.

## Passos (cada um com OK próprio)
1. Código e auto-testes, sem commit.
2. Commit e push.
3. Deploy do `figueirahome-scraper` (de `scraper/`), com o interruptor vazio.
4. Ver o resumo do cron das 03:37 de 26/11 (contagens por dia) e só depois ligar `COMPLETAR_POR_TELEFONE=1` e `flyctl secrets deploy`.
5. Nota ao Miguel no #27 (reaberto) e CLAUDE.md; plano da fusão (ponto 2).
