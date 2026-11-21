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

1. **Quem alimenta a `imoveis_ego_api`? Fechada a 21/11 (Miguel): ninguém.** O portal lê a `imoveis`. A `imoveis_ego_api` só servia a aba «Imóveis» do
   Conteúdo Social e o angariador dos Compradores; ele passa-as a ler a `imoveis` e depois apaga a `imoveis_ego_api`. Ninguém mais escreve lá. O que
   lhe faz falta na `imoveis` é a **latitude/longitude e a morada completa** vindas da API (ver fase 1b).
2. **`minDateAltered`: confirmado a 20/11** (só leitura). Aceita `AAAA-MM-DDTHH:MM:SS` e filtra por `lastUpdate`: sem filtro 5 186; desde há 24 h 4; desde há 7 dias 280; desde há 1 h 0; desde 2030 0. `totalRows` bate com as linhas. A incremental é barata (poucas linhas por corrida).
   Sem ele a «incremental» é uma leitura completa (~5 200 imóveis) de 10 em 10 min; aí passa a 30 ou 60 min ou compara-se `lastUpdate` em memória.
3. **Frequência**: 10 em 10 min são 144 corridas por dia no eGO; medir o tempo de uma leitura completa antes de fixar.

## Fase 1: o estado certo e a sincronização que o Miguel pediu (a Web API mantém-se)

Objetivo: acabar com FH2574 e FH2552 e com a espera de 24 h, sem tocar no que o site mostra.

1. **Estado e «no site» (FEITO a 21/11, `2ad6216`, v226; 1.ª gravação pelo cron de 22/11).** O sync de todos os estados passa a escrever,
   também nos imóveis que a Web API vê, `disponibilidade` (do `realestateStatusId`) e `disponivel_na_api` (= o `portals` tem o `websiteId` 8662,
   o nosso site) e `ego_atualizado_em`. **Porquê:** `disponivel_na_api` só passava a `false` quando um publicado sumia da Web API; os nunca
   publicados ficavam com o valor velho (4 268 linhas, FH2574 incluído), e `publicado` = Disponível + preço + `disponivel_na_api`. Medido a
   21/11: a Web API devolve 53 imóveis (49 Disponíveis com preço = os 49 `publicado`, mais 3 Vendidos e 1 Reservado que o eGO mantém no site
   «apesar de indisponível»), **todos com o site 8662 em `portals`**; o `portals` tem mais 154 (Retirados, Por validar…) que não aparecem na Web API.
   Simulação: `publicado` muda em 0 imóveis (continua 49); estado muda em 2 (FH2574 → Disponível, e fica **fora do site**; FH2552 → Retirado);
   «no site» muda em 370 (335 `true`→`false`, 35 ao contrário), nenhum dos 370 está publicado.
   - Escrita só se a linha ainda estiver como a lemos (estado e `disponivel_na_api`); `fonte='manual'` intocado (FH2483_B só quando o Miguel limpar os
     duplicados); se nenhum imóvel da resposta traz o site, `disponivel_na_api` não se mexe; nunca se escreve `publicado` (GENERATED).
   - Cuidado (por observar): o ritual de publicar e despublicar no eGO faz o estado passar por «Por validar»; o sync só reflete o que o eGO diz.
   - Aviso «eGO deixou de publicar»: com o sync novo a despublicar primeiro, a tarefa pode deixar de nascer; ver se faz falta.
   - Copia dos 370 (antes/depois) fora do repo; reverter = repor os campos de `antes`.
2. **Incremental**: o sync corre de X em X min só sobre os imóveis alterados (`minDateAltered` ou `lastUpdate` > última corrida). Mesma função
   de planear/gravar do passo 1, sobre um subconjunto. Passagem **completa semanal** como rede de segurança (a atual, já diária, passa a semanal ou fica).
3. **Registo e aviso**: cada corrida grava em `agente_sync_log` (`egorealestate_imoveis_todos` ou novo `tipo`), falha de cron manda email
   (`notificacoes.falha_de_sync`, como os outros). Travão: não escreve se a leitura vier com menos de 90% dos imóveis da anterior.
4. **Fase 1b (substitui a antiga ideia de alimentar a `imoveis_ego_api`, abandonada): GPS e morada completa na `imoveis`.** Medido a 21/11, só leitura:
   - **Morada:** a API tem `address` em 4 117 imóveis (a BD tem morada em 3 438; faltam 691 que a API tem), `zipCode` 3 386 (BD 2 787), `buildingNumber`,
     `floor`, `fraction`. A `imoveis` só tem `morada`, `numero`, `codigo_postal`, `concelho`, `freguesia`: **andar e fração não têm coluna** (migration, corrida
     por ti). Nas 3 423 moradas que existem nos dois lados, 3 398 são iguais; as 25 diferentes só diferem em quebras de linha.
   - **GPS: a API devolve o que o eGO guarda em «Coordenadas GPS», e sem pino o eGO guarda o centróide da zona** (confirmado em captura de ecrã a 21/11).
     `gpsLat`/`gpsLon` vêm em 3 925 imóveis; 2 513 partilham coordenada (627 no mesmo ponto, o centróide da freguesia). **`exportGeoreference` não serve de
     sinal** (é «exportar para portais»: o 01604 tem pino real único e `false`). A heurística «coordenada mais repetida da zona» também falha (2 falsos
     centróides em 24).
   - **Sinal escolhido: tamanho do grupo de imóveis com a mesma coordenada.** Distribuição: 1 imóvel → 1 412; 2 a 9 → 823 (280 pontos); 10 a 49 → 239;
     50 ou mais → 1 451. Contra as 24 coordenadas reais conhecidas (Web API `HasGPSLocation`): grupo 1 → 10 iguais, 0 diferentes; 2 a 9 → 9 iguais, 3
     diferentes; 10 a 49 → 0 e 1; 50 ou mais → 1 e 0. As diferenças vistas são pinos afinados no eGO depois da nossa cópia (FH2573: a nossa BD tinha o centróide dos
     627, a API tem o ponto real, **confirmado no eGO a 21/11**).
   - **Regra proposta:** escrever `latitude`/`longitude` se a coordenada é **única**, ou se o grupo tem **2 a 9 imóveis da mesma rua** (frações do mesmo prédio;
     comparar só a rua, não o texto inteiro: «Rua do Pinhal» e «Rua do Pinhal, Buarcos…» são o mesmo sítio). Grupos de **10 ou mais** não se escrevem
     (centróide). 2 a 9 com ruas diferentes: não se escrevem. Dados novos da API substituem a coordenada guardada (a nossa pode ser o centróide).
     Validar antes contra os 49 publicados e contra o mapa do site. **Feito a 21/11** (ver `imoveis-morada-gps-resumo.md`): sem migration (`piso`, `numero`, `fracao` já existiam); só se preenchem campos vazios, também em `manual`.
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

Fase 1b e o ponto 1 da fase 1 (estado e «no site») feitos. Falta, na fase 1, o incremental com `minDateAltered`, o registo/aviso dedicado e o travão dos 90%. Antes: ver o cron de 22/11 gravar os 370 sem erros e com `publicado` a 49.
