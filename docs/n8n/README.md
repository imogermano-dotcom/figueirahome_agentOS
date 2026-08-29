# Fluxos n8n — leads da Meta

O elo do meio do fluxo das leads pagas. Do lado do backend está tudo construído
e deployado; o que falta é isto.

```
Meta Lead Ads → Make (escreve em `leads`) → webhook → n8n (envia o template)
              → a lead responde → webhook do WhatsApp → o A1 assume
```

| Ficheiro | O quê | Estado |
|---|---|---|
| `01-enviar-template.json` | envia o template e marca a lead | pronto a importar |
| `02-backfill-template.json` | recupera quem ficou sem mensagem (manual) | pronto a importar |
| `03-follow-up-48h.json` | segunda tentativa a quem não respondeu (diário) | pronto a importar — precisa da migration `0030` |

## Antes de importar

**1. Template aprovado na Meta.** Mensagens iniciadas pelo negócio exigem um
template pré-aprovado no Business Manager. Sem isso a Graph API recusa.

| | |
|---|---|
| Nome | **`figueirahome_apos_lead`** |
| Idioma | `pt_PT` |
| Variáveis | 2 (`{{1}}` nome, `{{2}}` imóvel) |
| Aprovado | 2026-08-28 |

Já está nos dois ficheiros. Se o idioma tiver sido criado como `pt` ou `pt_BR` em
vez de `pt_PT`, o envio falha com `132001` — trocar em ambos.

**2. Credenciais no cofre do n8n, nunca no corpo dos nós.** Assim não aparecem
em exports do workflow nem nos logs de execução.

**Supabase → credencial *Custom Auth*** (não *Header Auth*: essa só aceita um
par nome/valor, e o PostgREST quer dois):

```json
{
  "headers": {
    "apikey": "<SERVICE_ROLE_KEY>",
    "Authorization": "Bearer <SERVICE_ROLE_KEY>"
  }
}
```

Nos nós HTTP: *Authentication* → Generic Credential Type → Custom Auth.

Tem de ser a **`service_role`**: `leads` tem RLS com política `to authenticated`
apenas, e a `anon` não lê nem escreve lá. Consequência a ter presente — é mais um
sítio com a chave que ignora o RLS em toda a base, além do Make.

Alternativa: o nó nativo **Supabase** (credencial *Host* + *Service Role
Secret*), trocando os dois nós HTTP por *Get a row* e *Update a row*. Trata dos
headers sozinho; é menos explícito sobre o que vai no pedido.

**Meta → *Header Auth*** com `Authorization` = `Bearer <META_WHATSAPP_TOKEN>`.
Se usares o nó nativo do WhatsApp, é a credencial dele (token + Business Account
ID) e este ponto não se aplica.

**3. Variáveis de ambiente** no n8n: `SUPABASE_URL` e `META_PHONE_NUMBER_ID`.

### Identificadores da conta WhatsApp (confirmados 2026-08-16)

| | |
|---|---|
| Phone number ID | `925368620661613` |
| Número | +351 928 318 953 — nome verificado "Imogermano" |
| Webhook configurado na Meta | `https://figueirahome-agentos.fly.dev/webhook/whatsapp` |
| Token | system user `fighome_agent`, **não expira** (`expires_at: 0`) |

**O WhatsApp Business Account ID (WABA) não está guardado no projecto** — o
backend não precisa dele, só o nó do n8n (para listar os templates). Encontra-se
em developers.facebook.com → a app → **WhatsApp → API Setup**, mesmo por cima do
Phone number ID; ou em Business Settings → Contas → Contas do WhatsApp.

Não dá para o tirar do token: o system user tem os scopes mas o WABA está
atribuído pelo negócio, e `assigned_whatsapp_business_accounts` vem vazio.

O webhook apontar para o nosso backend é a confirmação de que este é o número
que o A1 escuta — enviar o template por outro faz a resposta da lead nunca
chegar.

**4. O `phone_number_id` tem de ser o mesmo** que o backend escuta. Se o template
sair de outro número, a resposta da lead nunca chega ao A1 e a conversa morre
sem dar sinal.

## Do lado do Make

Módulo **HTTP → Make a request**, a seguir ao que escreve em `leads`:

| Campo | Valor |
|---|---|
| URL | `https://<n8n>/webhook/lead-nova` — **produção**, não `/webhook-test/` |
| Method | `POST` · Body type Raw · Content type JSON |
| Request content | `{"meta_lead_id": "{{id do lead vindo da Meta}}"}` |

**`meta_lead_id` e não o `id` da linha**: o PostgREST só devolve o registo criado
se a inserção mandar `Prefer: return=representation`; sem isso responde `204` sem
corpo e o Make fica sem id para passar adiante. O `meta_lead_id` o Make já o tem
do webhook da Meta, antes sequer de escrever, e a coluna é `UNIQUE`.

**Autenticar o webhook.** Sem isso, quem descobrir o URL dispara envios de
template do vosso número — custa dinheiro e estraga a *quality rating*. O nó
Webhook aceita Header Auth; o Make manda o header.

## O que o fluxo faz

1. **Webhook** — o Make chama com `{"meta_lead_id": "…"}`. A linha é lida a
   seguir na base, para não depender do formato do Make.
2. **Lê a lead** no Supabase.
3. **Guardas** — quatro, e todas importam:
   - `tipo` em `compra`/`arrendamento`. Angariação segue o fluxo humano.
   - tem telefone.
   - `template_enviado_em` vazio. **Idempotência**: o Make pode repetir o
     webhook, e sem isto a pessoa recebia a mensagem duas vezes.
   - **consentimento de WhatsApp**, reconhecido pelo prefixo:
     ```
     {{ ($json.ficha?.aceita_whatsapp || '').trim().toLowerCase().startsWith('sim') }}
     ```
     Boolean → is true. **Nunca por igualdade a uma frase** — ver a quarta
     armadilha.
4. **Lê o imóvel** — `imoveis?imovel_ref=eq.<ref>&select=titulo,natureza,…`.
   Consulta à parte porque **não há FK `leads`→`imoveis`** (o PostgREST responde
   `PGRST200`), logo não dá para embeber no `select` do passo 2.
5. **Resume o imóvel** — nó de código, ver a secção seguinte.
6. **Prepara** o texto renderizado, os dois parâmetros e o número em E.164.
7. **Envia** pela Graph API.
8. **Marca** `template_enviado`, `template_enviado_em` e `estado='contactada'`.

Se a Meta falhar, o nó aborta e a lead fica `nova` — a retentativa apanha-a.

## O texto e os seus dois parâmetros

```
Olá {{1}},
Sou a Matilde, assistente virtual da FigueiraHome.
Recebemos o seu interesse, através das redes sociais, no seguinte imóvel:
{{2}}
Posso ajudar com alguma informação?
```

A segunda linha é **literalmente** a constante `APRESENTACAO_A1` do
`assistants.py` — coincidência aproveitada, não acidente: é o que `engine.py:147`
procura para decidir que a A1 não se volta a apresentar.

| | conteúdo | fallback |
|---|---|---|
| `{{1}}` | **primeiro nome** da lead | `boa tarde` |
| `{{2}}` | `imovel_ref` + resumo, unidos por ` — ` | `um imóvel na Figueira da Foz` |

Renderizado a sério:

> Olá Ana,
> Sou a Matilde, assistente virtual da FigueiraHome.
> Recebemos o seu interesse, através das redes sociais, no seguinte imóvel:
> FH2572 — T4 na cidade em excelente estado com garagem
> Posso ajudar com alguma informação?

**Duas variáveis, não três.** A referência e o resumo vão juntos num só
parâmetro, montado no nó `Set`. Assim degrada sozinho — só ref, só resumo, ou
nenhum dos dois — sem partir a frase, e há menos uma variável a aprovar na Meta.

**Nem o `{{1}}` nem o `{{2}}` podem sair vazios.** A Cloud API recusa parâmetro
vazio; o nó aborta e a lead fica por marcar. Daí os dois fallbacks.

### O resumo — nó de código `Resumo do imóvel`

**Não existe coluna de resumo na `imoveis`** — procurada nas 64 colunas. Usa-se o
**`titulo`**, que é o que a agência escreveu para identificar o imóvel e diz
coisas que nenhum campo estruturado sabe: *"T3+1 duplex com jardim privativo e
vistas de mar"*, *"Lote para Moradia, com vista de mar"*.

Achatado numa linha antes de ir — a Meta **rejeita** parâmetros com quebras de
linha, tabs ou mais de 4 espaços seguidos, e rejeita, não corta. É a mesma razão
por que a **`descricao` não serve nem de rede**: 1100-1300 caracteres com quebras
de linha a sério, e 28 das 54 passam do orçamento de 849.

**A rede**, quando não há título ou ele passa dos 120 caracteres (máximo
observado: 101), compõe-se dos campos estruturados:

```
{natureza} T{quartos}, {área} m², {freguesia}, {preço} €
→ Moradia T8, 474 m², São Julião, 480 000 €
```

- **Tipologia** — 17 dos 54 não têm `quartos`, e é correcto: 12 terrenos, 1 lote,
  1 armazém, 2 prédios de investimento. Zero apartamentos ou moradias, portanto
  omitir o `T` não esconde nada.
- **Área** — `area_util` (zero em 26) → `area_bruta` (recupera 15) →
  `area_terreno` (os 11 restantes, todos terrenos).
- **Freguesia** — sem o sufixo `da Figueira da Foz`: a frase anterior já o disse.
  As outras oito (Buarcos, Lavos, Quiaios…) não têm sufixo e ficam intactas.
- **Preço** — `venda_preco` → `arrendamento_preco`, com separador de milhares.

Hoje a rede serve **um** imóvel: o `FH2298`, o único sem título — e sem descrição
também, o que o tornava o buraco de qualquer abordagem baseada em prosa.

O nó é **idêntico nos fluxos 01 e 02** e corre em `Run Once for Each Item` — no
modo por lote, `$json` seria só o primeiro item.

Medido a 2026-08-28, com o JavaScript do nó corrido em Node contra os **54
imóveis publicados** e o texto contra as **232 leads com consentimento**: zero
divergências face ao espelho em Python, zero parâmetros vazios, zero caracteres
proibidos, resumo de 18-101 caracteres (mediana 47), corpo máximo de **280** de
1024. Coberto por `backend/tests/test_template_meta.py`.

**Não há saída ("se foi engano, ignore") nesta mensagem** — está só no `03`, para
não convidar ao silêncio logo à primeira. Ver a decisão respectiva.

Medido a 2026-08-28, com o JavaScript do nó corrido em Node contra os **54
imóveis publicados** e o texto contra as **232 leads com consentimento**: zero
parâmetros vazios, zero caracteres proibidos, resumo de 32-47 caracteres
(mediana 39), corpo máximo de **228** de 1024. Coberto por
`backend/tests/test_template_meta.py`, que compara o JavaScript do ficheiro com
um espelho em Python.

## Cinco armadilhas

**O `template_enviado` tem de ser o texto renderizado**, com as variáveis já
substituídas — não o nome do template nem `Olá {{1}}`. É esse texto que o
backend injecta no histórico como mensagem do assistente. Se lá for o nome do
template, o A1 lê isso como algo que disse.

**O texto vive em dois sítios**: aprovado na Meta, e copiado no nó *Preparar
texto e número*. A Graph API recebe só os parâmetros, não devolve o texto final
— a duplicação é inevitável. **Se mudares o template na Meta, muda aqui também**,
senão o histórico do A1 passa a mentir. E nos **dois** fluxos: o `01` e o `02`
mandam a mesma frase, e há teste que os compara.

**O texto tem de nomear a Matilde.** Não é estilo: `engine.py:147` faz
`if NOME_A1.lower() in template.lower()` sobre o `template_enviado` gravado para
decidir se a A1 se apresenta. Com o nome lá, cala-se; sem ele, apresenta-se. Tirar
"sou a Matilde" do template põe-na a dizer "Sou a Matilde" logo a seguir a uma
mensagem que já o dizia.

**`alwaysOutputData: true` no nó *Ler imóvel*.** O n8n reparte um array JSON em
itens, e uma referência sem linha em `imoveis` devolve `[]` — zero itens, o ramo
morre em silêncio. No `01` a lead nunca recebe mensagem; no `02` é pior, porque o
item não chega ao `Esperar 5s`, não volta ao ciclo, e o backfill fica pendurado.
Com a opção ligada sai um item vazio e o fallback trata dele. E **não** se filtra
por `publicado`: o interruptor "publicar apesar de indisponível" do eGO mantém
anúncios a correr sobre imóveis reservados (FH2520, 27/08), e quem clica merece
resposta — o estado real quem o diz a seguir é a Matilde.

**Nunca escrever `respondeu_em`.** Essa coluna é do backend, e é o sinal de que a
pessoa falou. Se o n8n a escrever, o follow-up deixa de saber quem respondeu.

**O consentimento reconhece-se pelo prefixo, nunca por igualdade.** O valor de
`ficha.aceita_whatsapp` mudou de `sim,_aceito_receber_informações_pelo_whatsapp`
para `SIM` e o filtro pinado à frase antiga deixou de deixar passar seja quem
for: **a 20/08, 26 leads consentiram e 2 foram contactadas**. As restantes 24
nunca souberam de nada.

**Quem mudou o valor foi um trigger na base** — `tgr_normaliza_aceita_whatsapp`,
aplicado a **2026-08-20 às 11:34:07** pela interface do Supabase, fora do
repositório. Está registado na `0031`, que é cópia literal e não muda nada. Duas
coisas a reter:

- **Não foi um `UPDATE` de uma vez; é uma regra viva.** Normaliza a cada escrita
  em `ficha`, portanto as leads novas do Make entram já em forma. A 2026-08-24 a
  tabela tinha exactamente `SIM` (194) e `NÃO` (29) — mais nada.
- **A regra dele é a mesma que a nossa**: lista branca por prefixo `sim*`, tudo o
  resto vira `NÃO`, chave ausente ou vazia fica intacta. Por isso o
  `ilike.sim*` do PostgREST e o `startsWith('sim')` do nó `IF` seleccionam o
  mesmo conjunto — verificado, 194 dos dois lados.

Continuar a filtrar pelo prefixo mesmo assim: o trigger pode ser desligado por
quem tem acesso ao painel do Supabase, e o filtro é a segunda tranca.

A mesma armadilha apanhou o distintivo no painel, ao contrário: marcou as 152
leads como recusa. É a mesma lição das duas pontas — comparar com uma frase que
outra pessoa controla é uma bomba com temporizador. `startsWith('sim')` aguenta
`SIM`, `Sim` e a frase longa, e continua a ser lista branca: o que não começa por
"sim" não recebe, incluindo campo vazio ou em falta.

## O que o n8n escreve, e o que não escreve

| Coluna | Quem |
|---|---|
| `template_enviado`, `template_enviado_em`, `estado='contactada'` | **n8n** (fluxos 01 e 02) |
| `estado='sem_resposta'`, `follow_up_em` | **n8n** (fluxo 03) |
| `respondeu_em`, `conversa_id` | backend, quando a lead fala |
| `estado='qualificada'`, `qualificada_em` | backend, quando o MQL fica completo |
| `estado='engano'` / `'sem_interesse'` | backend, quando a Matilde chama `encerrar_lead` |

## `02-backfill-template.json` — recuperar quem ficou sem mensagem

Disparo **manual**, para as leads que consentiram e nunca receberam o template.
Nasceu a 2026-08-21: o filtro do fluxo 01 estava pinado à frase antiga do
consentimento e deixou 24 leads de 20/08 sem nada — 121 no total desde 13/08.

Mesma cadeia do fluxo 01, mas com os **nós nativos** (Supabase e WhatsApp
Business Cloud) em vez de HTTP Request, e a lista a vir de uma consulta em vez
do webhook.

**Dois campos a escolher na interface** depois de importar — os valores no
ficheiro são marcadores:

- a **credencial** de cada nó (Supabase API e WhatsApp Business Cloud);
- o **template**, no nó da Meta. É uma lista carregada da conta, no formato
  `nome|idioma`. O mesmo do fluxo 01, com os mesmos dois parâmetros.

O nó *Ler imóvel* aqui é o nó nativo do Supabase, não HTTP Request. **11
referências têm um espaço a sério** (`FH2460 3C`): se alguma falhar, é o encoding
do `filterString` — trocar por um HTTP Request com `encodeURIComponent`, como no
fluxo 01.

**Antes de cada corrida, duas coisas a editar** no nó *Ler leads pendentes*:

| Parâmetro | Para quê |
|---|---|
| `criado_em` = `gte.2026-08-20` no `filterString` | a janela. Sem isto apanha desde 13/08 |
| `Limit` = `5` | o travão. Correr, conferir os 5, e só depois subir |

O filtro está em modo **String** e não Manual porque o manual não deixa escrever
`ficha->>aceita_whatsapp`, que é uma chave dentro de `jsonb`.

**É seguro repetir.** `template_enviado_em=is.null` na consulta e a marcação só
depois do envio: quem já recebeu não volta a aparecer, e quem falhou a meio
aparece na corrida seguinte.

**As guardas estão em dois sítios de propósito** — no `filterString` e no nó
`Guardas`. Um nome de coluna trocado no filtro não dá erro: o PostgREST devolve
linhas a mais em silêncio. O `IF` verifica sobre a linha que chegou.

**O espaçamento é um ciclo explícito, não uma opção do nó.** *Uma de cada vez*
(`Split In Batches`, tamanho 1) → envia → marca → `Wait` de 5 s → volta. Sem
isto o n8n manda as mensagens em rajada: os nós processam os itens em paralelo,
e o `batching` das *options* é do HTTP Request, **não** do nó da Meta — pô-lo lá
não dá erro e não faz nada.

Às 24 leads são 2 minutos, e é isso que dá tempo de ver as primeiras chegarem e
parar a execução se estiverem erradas.

⚠️ **Tudo tem de regressar ao ciclo**, incluindo o ramo falso do `IF`. Um ramo
que morra sem voltar deixa o ciclo pendurado no item em que estava.

**Decidir a idade antes de correr.** As de ontem são leads quentes. As de 13 de
Agosto têm mais de uma semana, e "recebemos o seu pedido" sobre um pedido de há
oito dias soa mal — podem merecer outro texto, ou nenhum.

## `03-follow-up-48h.json` — a segunda tentativa

Desfecho **"Sem resposta"** da spec §2.2: sem resposta em 48h, marca a lead e
manda o follow-up **por template** (a spec é explícita nisso — a janela das 24h
já fechou há muito).

Disparo **diário às 12:00 Europe/Lisbon**. Não às horas dos crons do eGO (03:00 e
06:00 UTC): esses são syncs de máquina, isto é uma mensagem para uma pessoa.

**Era 10:00, e as 10:00 não vinham de dado nenhum** — eram um palpite de "início
da manhã". A 2026-08-25, com 17 conversas reais no histórico, as primeiras
respostas concentram-se às **12h (4), 15h (3) e 16h (3)**; às 10h houve uma só.

⚠️ **O que os dados dizem mesmo é que a hora conta pouco ao pé do dia**: 13 das
17 conversas foram **sábado ou domingo**. Não se restringiu o cron a `6,0` porque
só há **um follow-up por lead** — uma lead elegível à terça esperaria quatro dias
para o gastar, e gastá-lo tarde é pior do que gastá-lo à hora certa de um dia
útil. Se a corrida de controlo desmentir isto, a alternativa é `0 12 * * 6,0`.

⚠️ **A premissa das 48h continua por confirmar.** Das 17 que responderam, **16
responderam em menos de UMA hora**, mediana imediata, máximo 1,3 h — ninguém
respondeu tarde, nunca. O follow-up pode valer como segundo toque a quem ignorou
o primeiro, mas isso ainda não está demonstrado. A corrida com `Limit=5` é a
medição, não uma formalidade: se as 5 não responderem, a hipótese cai.

**Precisa da migration `0030`** (`leads.follow_up_em`). Sem a coluna o filtro
`follow_up_em=is.null` não bate e o PostgREST devolve erro.

Mesma cadeia do `02` — nós nativos, `Split In Batches` (1) → envia → marca →
`Wait 5s` → volta ao ciclo — com o `Disparo manual` trocado por `Schedule
Trigger` e outra consulta.

### A consulta

```
respondeu_em=is.null
follow_up_em=is.null
estado=in.(nova,contactada)
telefone=not.is.null
ficha->>aceita_whatsapp=ilike.sim*
template_enviado_em=lt.{{ $now.minus(48, 'hours').toISO() }}
```

**`follow_up_em` é o travão, e é a razão de ser da `0030`.** Sem ele um
*Schedule Trigger* diário reenvia a mesma mensagem à mesma pessoa todos os dias
até ela responder ou bloquear o número. Um follow-up por lead, uma só vez.

Coluna própria e não o estado: o `estado` é editável no painel, e um corretor a
reabrir uma lead para `contactada` fazia sair segunda mensagem. O carimbo é do
fluxo e ninguém lhe mexe.

`respondeu_em` (`0027`) tira de circulação quem já está a falar com a Matilde.

### Três coisas a saber

**O template é outro.** Não reutilizar o do `01`: a pessoa recebia a mesma frase
duas vezes e parece um sistema avariado. Precisa de aprovação própria na Meta. O
texto proposto dá uma saída explícita — *"se preferir, diga-nos só que não"* — e
isso não é cortesia: uma resposta negativa faz a Matilde chamar `encerrar_lead`,
e a pessoa sai da lista de vez em vez de ficar `sem_resposta` para sempre.

**A saída vive só aqui, e de propósito.** A primeira mensagem chegou a ter
*"se foi engano, pode ignorar esta mensagem"* e saiu: convidar ao silêncio logo
à primeira é dar uma desculpa a quem ainda nem leu a proposta, e o silêncio é
indistinguível de desinteresse. Às 48h já não é — quem não respondeu teve tempo,
e aí a saída poupa-lhe a insistência e poupa-nos a lead morta na lista.

**`sem_resposta` NÃO é um estado fechado.** Quer dizer "desistimos de insistir",
não "não falar com esta pessoa". `guards._ESTADOS_LEAD_ABERTA` inclui-o: se
responder uma semana depois, a conversa volta à Matilde com o `imovel_ref` do
anúncio, e se trouxer o MQL completo ainda qualifica. Passá-lo para
`ESTADOS_FECHADOS` mandava essa pessoa para o A2 sem contexto nenhum — há um
teste em `test_guards.py` só para isto.

**Quem nunca consentiu fica de fora, e é assim que deve ser.** Sem consentimento
nunca houve template, logo `template_enviado_em` é NULL e a lead não aparece
aqui: fica `nova` para sempre. Marcá-la "sem resposta" seria mentira — nunca lhe
perguntámos nada. Essas leads têm o caminho do telefone, sinalizado no painel.

### Antes de ligar a agenda

O `Schedule Trigger` fica **inactivo** até a primeira corrida à mão passar. Como
no `02`: `Limit = 5`, correr, conferir as cinco que saíram, e só depois subir o
limite e activar.

Contagem de controlo antes disso, para saber quantas vai apanhar:

```sql
select count(*) from leads
 where respondeu_em is null and follow_up_em is null
   and estado in ('nova','contactada')
   and lower(ficha->>'aceita_whatsapp') like 'sim%'
   and template_enviado_em < now() - interval '48 hours';
```

**Uma segunda tentativa e mais nenhuma.** A spec é omissa sobre o que fazer a
seguir; `follow_up_em is null` fecha essa porta. Passar a duas é acrescentar um
contador, não refazer o fluxo.
