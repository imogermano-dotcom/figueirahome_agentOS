# API do eGO CRM — procedimento e armadilhas

Conhecimento geral da API, válido para qualquer cliente com eGO. Dados de cada
agência (ids, contagens, contactos) ficam no `README.md` do cliente, nunca aqui.

Fonte: testes só de leitura, mais duas escritas de teste, feitos a 2026-10-14 na
agência de outro cliente. Estado em 2026-10-16:
não retestado.

- Especificação (OpenAPI, 806 operações): `references/ego/api-1.json`
- Base URL: `https://api.egocrm.com`
- Autenticação: Bearer JWT, validade de 24 horas.

## Antes de começar

- Credenciais num `.env` da pasta do cliente (gitignored): `EGO_BASE_URL`,
  `EGO_USERNAME`, `EGO_PASSWORD`, `EGO_APPLICATION_ID`. Não escrever a password
  no chat nem em ficheiros versionados.
- Cada agência tem o seu `applicationId`. Usar só o da agência do cliente em
  causa; o login pode listar outras agências a que o utilizador tem acesso.
- Primeiro só leituras (`Get*`, `List*`). Escritas só com ordem do João.

## Login (dois passos)

1. `POST /authentication/Authentication/Login` com `{username, password}`.
   Devolve `applicationsAvailable` (agências) e um token ainda sem agência.
2. `GET /authentication/Authentication/LoginToApplication?applicationId=X`
   devolve o token já preso à agência. Usar este.

## Armadilhas já encontradas

- **Cloudflare:** o User-Agent por omissão do Python dá 403 (erro 1010).
  Enviar um User-Agent de browser. Também nos nós HTTP do n8n.
- **`applicationId` na query:** as listagens POST (`ListLeadByPage`,
  `ListOpportunityByPage`, `ListRealestateByPage`) levam `?applicationId=X`.
  Sem isso, `ListLeadByPage` dá 400. Corpo `{}` devolve tudo.
- **`GetEmployee`:** precisa de `?securityUserId=...&applicationId=...`. Sem
  `securityUserId` dá 404.
- **Listagens POST de entidades** (`ListEntityByPage`, `...FastSearch`) deram 401
  mesmo com permissão `entity/list`. Funciona
  `GET /entity/Entity/ListEntityByApplication?applicationId=X`, que devolve todas.
  Causa do 401 por apurar.
- **Git Bash no Windows:** argumentos que começam por `/` são convertidos em
  caminhos do Windows. Usar `MSYS_NO_PATHCONV=1`.
- **Python:** `python -I` ignora `PYTHONIOENCODING`; usar
  `sys.stdout.reconfigure(encoding="utf-8")`. Gravar JSON com `encoding="utf-8"`.

## Escrever com `UpdateEntity` (risco real)

Não há endpoint só para adicionar um contacto: só `PUT /entity/Entity/UpdateEntity`,
que recebe a entidade inteira.

- **Incidente (2026-10-14):** o `UpdateEntity` não aceita `rolesBitFlag` e o servidor
  recalcula-o a partir de `roles`. Numa entidade com `roles` vazio e
  `rolesBitFlag` `None`, o PUT passou-o a 0 e a entidade **desapareceu das
  listagens e da interface**. Repôs-se atribuindo um tipo de contacto no PUT
  (`roles: [{"id": N}]`).
- **Regra:** nunca fazer PUT numa entidade com `roles` vazio sem atribuir antes um
  tipo (por exemplo 19 «Outros» ou 109 «Parceiro de Negócios»).
- **Procedimento:**
  1. `GetEntity?entityId=...&applicationId=...` e guardar cópia (UTF-8).
  2. Montar o corpo só com os campos de `EntityRequestDto`.
  3. Contacto novo: `{id: 0, contact, personalContactTypeId,
     personalContactPlaceId, entityId}`. `personalContactPlaceId` é obrigatório.
  4. PUT, depois `GetEntity` outra vez e comparar campo a campo.
  5. Confirmar que continua em `ListEntityByApplication`.
- **Efeito residual:** o PUT pôs `securityGroupId` a 0 numa entidade que tinha 6906;
  `securityGroupIds` manteve-se. Sem impacto visível confirmado.
- `Insert*` e `Delete*` não foram testados.

## Tabelas de referência (globais, `applicationId` 0)

Confirmar sempre com a chamada indicada; podem mudar.

- **Fases de lead** (`ListLeadStage`): 1 Activa, 2 Ganha, 3 Perdida.
- **Origens** (`ListLeadOrigin`): 1 Internet, 2 Placa/Autocolante, 3 Ponto de
  Venda, 4 Folheto, 5 Imprensa, 6 Amigo, 7 Outdoor, 8 Feira, 9 Rádio, 10 TV,
  11 Outros, 12 Prospeção de Rua, 13 Loja/Agência, 21 Parceiro de Negócios.
  Não existe origem «Meta»: as leads Meta vêm como Internet, com sub-origem
  própria (`ListLeadSubOrigin`, configurada por agência).
- **Tipos de lead** (`ListLeadType`): 1 Procura, 2 Oferta, 3 Pedido de Visita,
  4 Pedido de Informação, 5 Pedido de Reserva, 6 Crédito, 7 Pedido de Contacto,
  16 Pedido de Proposta, entre outros. O valor 0 é «sem tipo».
- **Estados de imóvel** (`ListRealestateStatus`): 2 Disponível, 3 Vendido,
  4 Reservado, 5 Arrendado, 7 Em Prospecção, 8 Retirado, 9 Por validar.
  Filtro: `ListRealestateByPage` com `{"realestateStatus": [2]}`.
- **Tipos de contacto / roles** (`GetRole?roleId=N`), com o `rolesBitFlag`
  observado: 1 Potencial Cliente (1), 2 Proprietário (2), 4 Angariador (8),
  6 Cliente (16), 17 Comercial (64), 19 Outros (64), 109 Parceiro de Negócios (64).
- **Contactos** (`personalContacts`): tipo 2 é telefone; o tipo 1 é email mas
  também traz telefones, por isso classificar pelo formato do valor.
  Telefones aparecem em vários formatos (`9…`, `00351…`, `+351…`).
- Nomes de imóveis, naturezas e negócios: `ListNatureType`, `ListBusinessType`
  (a chave é `Id`) e `ListLocationById`. Preço em `businesses[].prices[].value`.

## Leitura útil

- `ListOpportunityByPage?applicationId=X` com `{}`: a base real de contactos
  comerciais. As leads novas são promovidas a oportunidades, por isso
  `ListLeadByPage` fica quase vazio.
- `ListEntityByApplication`: todas as entidades, com `personalContacts`.
- `ListRealestateByPage`: imóveis. Cuidado: pode incluir imóveis de rede/MLS que
  não são da agência (referências `I99P…`, sem morada).
- `ListSecurityFeatures` e `GetPermissionsForGroup`: permissões do utilizador e
  de um grupo.

## RGPD

As entidades trazem NIF, IBAN, data de nascimento e observações. Ler só o que o
projecto precisa (nome, email, telefone, ids) e não guardar o resto. Antes de
importar contactos para email marketing, confirmar o significado de `rgpdStatus`
(0, 1 e 2 observados; significado por confirmar) e dos códigos `emailSMTPStatus`
(0, 500, 511, 700).
