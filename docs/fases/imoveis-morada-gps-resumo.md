# Imóveis: morada completa e GPS pela API nova (fase 1b, 21/11/2026)

Plano: `imoveis-so-api-nova-plano.md`. Pedido do Miguel: a `imoveis` trazer morada completa e latitude/longitude para ele apagar a `imoveis_ego_api`.

## O que foi feito

- `sync_morada_gps(origem, dry=True)` em `integrations/imoveis_sync.py`; endpoint `POST /api/imoveis/sync/morada-gps` (só conta por omissão, escrever = `?dry=0`).
- **Só preenche campos vazios**, também em `fonte='manual'`, e nunca troca o que lá está. Cada coluna escreve-se com a condição «ainda vazia». Campos: `morada`, `codigo_postal`, `numero`, `piso`, `fracao` (API `address`, `zipCode`, `buildingNumber`, `floor`, `fraction`: 1:1, 0 conflitos) e `latitude`/`longitude`. Piso 0 (rés-do-chão) não é vazio.
- Sem migration: as colunas já existiam.
- Testes: `tests/test_imoveis_gps.py`. Commits `a7ab99c`, `bd8ef9b`; deploy v224.

## Regra do GPS

O eGO guarda o centróide da zona em «Coordenadas GPS» quando ninguém põe o pino, e a API devolve-o. `exportGeoreference` **não** serve de sinal (é «exportar para portais»). Escreve-se se a coordenada é **única** ou partilhada por **2 a 9 imóveis da mesma rua**; 10 ou mais é centróide e não se escreve; 2 a 9 de ruas diferentes também não. Confirmado no eGO com FH2573 (a nossa cópia antiga tinha o centróide, a API tem o pino).

## Resultado em produção (21/11)

2 505 imóveis atualizados, 0 erros: morada 691, código postal 611, número 404, piso 193, fração 107, GPS 2 014. `publicado` ficou 49. 2.ª passagem em dry-run: 0. Log: `agente_sync_log`, tipo `egorealestate_morada_gps`.

## Por tratar

- 3 GPS que diferem da API (FH2006, FH2573, FH2497) e 21 moradas diferentes: não se alteram, ver com o Miguel.
- 1 889 imóveis sem GPS por serem centróide ou grupo ambíguo: só vêm com o pino posto no eGO.
- Cópia para reverter fora do repo (valores de antes e depois): reverter = voltar os campos a vazios.
- Sem cron: a 1b correu uma vez. Os imóveis novos ou editados só entram se alguém voltar a correr o endpoint.
