# Plano — Migração para as chaves novas do Supabase (incidente 12-13/09)

> Correcção de incidente, não fase de roadmap. Prioridade máxima: produção
> degradada desde 2026-09-12T18:26 UTC.

## O que aconteceu

1. **Supabase desactivou as chaves legacy (`anon`/`service_role`) do projecto
   `zphasvfopnbzwnaidsnw`** a nível de projecto inteiro, 2026-09-12T18:26:39
   UTC. Confirmado nos logs de produção: `nudge` da Matilde e o log do
   uptime check falham com `Legacy API keys are disabled`. Afecta
   provavelmente toda a escrita/leitura do WhatsApp (Matilde/Maria/Bárbara)
   desde essa hora — os erros são engolidos em silêncio por desenho
   (`engine.py`/`tools.py`), a conversa não morre mas não grava nada.
2. **O projecto de Auth (`fykbogojkcqokvopnmkz`) foi eliminado** pelo
   utilizador — confirmado por DNS ("Non-existent domain" em dois
   resolvers). O que lá estava foi **integrado no projecto de dados**
   (`zphasvfopnbzwnaidsnw`) — confirmado pelo utilizador (13/09). Um único
   projecto Supabase a partir de agora, não dois.
3. **"O portal" (e qualquer consumidor externo com a chave antiga — Make,
   bundle das landing pages) fica bloqueado** pelo ponto 1, não é um
   problema à parte.

## Consolidação: um projecto, um cliente

Com o Auth fundido no projecto de dados, `get_supabase()` e
`get_supabase_auth()` deixam de fazer sentido como duas funções — eram dois
projectos, agora é um. Colapsa-se num cliente só.

## Ficheiros a alterar

| Ficheiro | Mudança |
|---|---|
| `backend/app/config.py` | Remove `supabase_service_role_key`, `supabase_imoveis_url`, `supabase_imoveis_key`. Fica só `supabase_url` (URL do projecto único) e `supabase_secret_key` (nova `sb_secret_...`). |
| `backend/app/db/supabase_client.py` | Um cliente só (`get_supabase()`), com a chave nova. Remove `get_supabase_auth()`. |
| `backend/app/api/deps.py` | `require_auth` passa a usar `get_supabase()`. |
| `backend/app/notificacoes.py` | `_consultor_do_imovel` (lê `profiles`) passa a usar `get_supabase()` — a tabela `profiles` deve ter vindo na integração do Auth. |
| `backend/tests/*` | Qualquer teste que faça mock/patch de `get_supabase_auth` passa a `get_supabase`. |
| `.env.example` (backend) | Reflectir as duas variáveis novas, tirar as antigas. |

## Fly — segredos

Depois do código validado localmente com a chave nova (dada pelo
utilizador, criada por ele no dashboard):

1. `flyctl secrets set SUPABASE_URL=... SUPABASE_SECRET_KEY=...` (URL passa a
   ser a do projecto único; hoje `SUPABASE_URL` aponta para o projecto
   eliminado).
2. Deploy, confirmar `/docs` 200 e um `workflow_dispatch` do uptime check
   sem erro nos logs.
3. **Só depois** de confirmado: `flyctl secrets unset
   SUPABASE_SERVICE_ROLE_KEY SUPABASE_IMOVEIS_URL SUPABASE_IMOVEIS_KEY` —
   não antes, para haver caminho de volta se a chave nova falhar.

## Fora do âmbito desta correcção (seguem-se depois)

- **`scraper/`** (app Fly separada, `figueirahome-scraper`) também lê
  Supabase com as mesmas variáveis — mesmíssimo problema, cron diário
  06:00/13:00 UTC. Precisa da mesma migração, noutra app. Sinalizado, não
  incluído aqui para não misturar dois deploys.
- **Portal do Miguel, Make, bundle das landing pages** — externos a este
  repo. Ficam resolvidos **se** as chaves legacy forem reactivadas
  entretanto (decisão do utilizador, ver conversa), ou continuam bloqueados
  até quem os mantém trocar de chave. Não é algo que este repo resolva.
- Actualizar `CLAUDE.md`/`docs/database-schema.md` para "um projecto, não
  dois" — feito no próximo handoff, não urgente para destravar produção.
