# Imóveis só pela API nova do eGO: plano em 2 fases (pedido #45, nota do Miguel de 19/11)

> **Plano, nada implementado (20/11/2026).** Escrito antes de código, por regra do projeto. Medições só de leitura.
> Continua `imoveis-todos-os-estados-plano.md` (sync de todos os estados, já em produção, cron 06:47 UTC).

## Porquê

O Miguel pediu sync automática (nota de 19/11 no #45): a `imoveis_ego_api` só foi lida uma vez, a 30/10 13:43, as alterações do eGO não
chegam ao portal, e FH2574, FH2552 e FH2483_B continuam errados. Pediu: sync incremental de 10 em 10 min pela `ListRealestateByPage` com
`minDateAltered`, passagem completa semanal, registo de cada corrida com aviso se falhar, e webhook quando a Janela Digital o criar.

### O que medi a 20/11 (só leitura)

- **`imoveis_ego_api`** (5 163 linhas): todas com `sincronizado_em` = 30/10 13:43, `ego_alterado_em` máximo 29/10. **Nenhum código nem migration do
  repo a escreve** (não há uma única ocorrência do nome no histórico git): foi criada e preenchida fora de nós, numa leitura única.
- **Na nossa `imoveis`** o dry-run do sync de todos os estados (5 182 no eGO, 5 199 no Supabase) dá **3 divergências**, não 8 (os 8 do Miguel são
  contra a `imoveis_ego_api` de 30/10):

  | Imóvel | `imoveis` | eGO | Porque não corrige |
  |---|---|---|---|
  | FH2574 | Por validar | Disponível | a Web API vê-o, o sync de todos os estados não escreve nele |
  | FH2552 | Por validar | Retirado | idem |
  | FH2483_B | Retirado | Por validar | `fonte='manual'`; o eGO tem registos duplicados (Miguel) |

- **Causa**: nos imóveis que a Web API vê, o `disponibilidade` só se atualiza pela validação CRM completa, manual desde sempre (estourava o
  tempo do cron). O sync novo já traz o estado certo mas, por regra de coexistência, não escreve nesses imóveis.
- **A API nova (`ListRealestateByPage`, 227 chaves) traz**: `realestateStatusId` e `lastUpdate` (5 186/5 186), `description` (2 608), `features`
  (4 033), `gpsLat`/`gpsLon` (3 928), `hasVirtualTour` (36), `portals` (222 imóveis com a lista de portais), `brokerId`. **Não traz fotos**
  (só `firstMedia`, `firstMediaId`, `hasImages360`) e as chaves de comissão existem mas vêm **todas vazias** (0/5 186; o eGO ainda não as implementou, #41).
- **`portals` como «publicado no site»**: o `websiteId` 8662 aparece em 207 imóveis; **os 49 `publicado` da BD têm todos esse website** (nenhum falha).
  Há 158 com o website e não `publicado` (preço zero ou não Disponíveis, esperado: `publicado` exige as duas coisas).
- `disponivel_na_api` está a `true` em 4 440 linhas (sobretudo valor por omissão de linhas antigas): hoje **não** diz «está na Web API agora».

## Decisões por tomar (antes da fase 1)

1. **Quem alimenta a `imoveis_ego_api`?** O portal do Miguel lê `imoveis` ou `imoveis_ego_api`?
   - **A. Nós** escrevemos a `imoveis_ego_api` num sync novo (preciso do esquema exato e de saber se mais alguém escreve lá).
   - **B. O portal passa a ler a `imoveis`**, que já recebe os syncs (a `imoveis_ego_api` fica abandonada).
2. **`minDateAltered`: confirmado a 20/11** (só leitura). Aceita `AAAA-MM-DDTHH:MM:SS` e filtra por `lastUpdate`: sem filtro 5 186; desde há 24 h 4; desde há 7 dias 280; desde há 1 h 0; desde 2030 0. `totalRows` bate com as linhas. A incremental é barata (poucas linhas por corrida).
   Sem ele a «incremental» é uma leitura completa (~5 200 imóveis) de 10 em 10 min; aí passa a 30 ou 60 min ou compara-se `lastUpdate` em memória.
3. **Frequência**: 10 em 10 min são 144 corridas por dia no eGO; medir o tempo de uma leitura completa antes de fixar.

## Fase 1: o estado certo e a sincronização que o Miguel pediu (a Web API mantém-se)

Objetivo: acabar com FH2574 e FH2552 e com a espera de 24 h, sem tocar no que o site mostra.

1. **Estado dos imóveis que a Web API vê**: o sync de todos os estados passa a atualizar `disponibilidade` e `ego_atualizado_em` também nesses,
   quando o estado do eGO difere. **Nunca** escreve `publicado` (GENERATED) nem `disponivel_na_api`. `fonte='manual'` continua intocado
   (FH2483_B só se resolve quando o Miguel limpar os duplicados). Dry-run primeiro; esperado: FH2574 e FH2552 corrigem-se, `publicado` continua 49.
   - Cuidado: o ritual de publicar e despublicar no eGO (memória do projeto) faz o estado passar por «Por validar»; o sync não pode impedir
     essa dança, só refletir o que o eGO diz. Verificar que um imóvel `publicado` não passa a não publicado por um estado transitório lido a meio.
2. **Incremental**: o sync corre de X em X min só sobre os imóveis alterados (`minDateAltered` ou `lastUpdate` > última corrida). Mesma função
   de planear/gravar do passo 1, sobre um subconjunto. Passagem **completa semanal** como rede de segurança (a atual, já diária, passa a semanal ou fica).
3. **Registo e aviso**: cada corrida grava em `agente_sync_log` (`egorealestate_imoveis_todos` ou novo `tipo`), falha de cron manda email
   (`notificacoes.falha_de_sync`, como os outros). Travão: não escreve se a leitura vier com menos de 90% dos imóveis da anterior.
4. **`imoveis_ego_api` fica fora da fase 1** (decidido 20/11): a fase 1 só escreve na `imoveis`. A tabela espelho trata-se numa **fase 1b**,
   depois de a `imoveis` estar certa e estável: copiar da `imoveis` (ou da leitura da API) para a `imoveis_ego_api`, consoante a decisão 1.
   Limite conhecido: se o portal do Miguel ler a `imoveis_ego_api`, ele continua a ver dados de 30/10 até a 1b estar feita; por isso
   perguntar-lhe já qual das duas tabelas o portal lê, e pedir-lhe o esquema da `imoveis_ego_api` (colunas e quem mais escreve lá).
5. **Webhook da Janela Digital**: fora do nosso controlo, só quando existir.

Prova da fase 1: dry-run em produção antes; 1.ª passagem real com OK; contar `publicado` (49) antes e depois; FH2574 e FH2552 corretos; site igual.
Reverter: desligar o cron novo (`enabled:false`) e reverter o commit; os estados escritos mantêm-se corretos (são os do eGO).

## Fase 2: largar a Web API (só depois de a fase 1 estar estável uns dias)

Objetivo: uma única fonte (API nova), sem coexistência nem `disponivel_na_api` enganador.

Bloqueadores a resolver **antes** de qualquer código (cada um com medição só de leitura):

1. **Fotos**: a listagem só tem a primeira. Procurar na API nova o endpoint de média dos imóveis (`api-1.json`) e medir se devolve as fotos que o
   site e as landing pages usam (ordem, URLs estáveis, tamanhos). Se não existir, a Web API fica só para as fotos e a fase 2 não se fecha.
2. **GPS real**: a Web API só dá coordenadas reais com `HasGPSLocation=true`; a API nova dá `gpsLat`/`gpsLon` sem esse sinal. Comparar para os imóveis
   publicados: iguais à Web API ou centróide da freguesia? (a diferença dá o pino do mapa errado, já nos custou 40 coordenadas.)
3. **`disponivel_na_api` e `publicado`**: recalcular «está no site» a partir do `portals` (websiteId 8662). Validar nos 49 publicados e nos 158 que têm o
   website sem estar publicados, **contra o site real**, antes de ligar. `publicado` é GENERATED e é o que o site mostra: um erro aqui põe imóveis no
   ar ou tira-os.
4. **Campos que a Web API dá e a nova não** (`FeatureTags` vs features, descrições em várias línguas, extras de `_map_extras`): mapear campo a campo e
   listar os que desaparecem. As Três allowlists (`CAMPOS_PUBLICOS`, `_FEATURE_BOOLS`, `_TOOLS_INPUT_SEGURO`) mantêm-se e têm teste.
5. **Id por referência, nunca por id**: o `id` da API nova (backoffice) não é o `ego_id` da Web API (385/4 452 coincidem); o `metabaseId` da Web API
   continua a ser usado em `imoveis.ego_id` e no `RID` da criação de leads (Web API). Antes de desligar, ver quem mais depende do `ego_id` e do `RID`.

Passos (se os bloqueadores se resolverem): sync novo escreve também fotos/GPS/features → `disponivel_na_api` passa a derivar do `portals` →
período de convivência com os dois syncs a comparar (relatório de diferenças, sem escrever) → desligar `sync-imoveis-manha`/`tarde` → apagar o código
da Web API só depois de semanas sem uso.

Prova: relatório de diferenças a zero nos imóveis publicados (campos, fotos, GPS); site e landing pages iguais campo a campo; `publicado` igual antes
e depois. Reverter: religar os 2 crons da Web API (o código fica até ao fim).

## Fora do âmbito

Comissões (#41, o eGO ainda não as expõe), o webhook da Janela Digital (depende deles) e a decisão sobre os 258 imóveis legados sem angariador.

## Próximo passo

Fase 1 em dry-run (`minDateAltered` já confirmado), só sobre a `imoveis`. A decisão 1 (A/B) só é precisa para a fase 1b.
