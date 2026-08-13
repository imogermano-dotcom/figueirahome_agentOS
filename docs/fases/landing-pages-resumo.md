# Resumo — Construtor de Landing Pages (2026-08-08)

Âmbito de negócio em `landing-pages-plano.md`. Isto é o que ficou construído.

## O que existe agora

O Miguel escolhe um imóvel no painel (Imóveis → **Landing pages**), preenche o
que o eGO não tem (vídeo, mapa, notas), decide se o preço aparece, e carrega em
**Criar e gerar**. Passados ~15 s tem um URL público pronto para pôr num anúncio.
Quem lá chega vê o suficiente para se interessar e tem de se identificar para ver
o resto — cliente, lead e tarefa aparecem no painel.

```
Cloudflare Worker              FastAPI (Fly.io)                    Supabase
site.pt/imovel/{slug}   ─►  GET  /lp/{slug}          ─►  landing_pages + imoveis
                            POST /lp/{slug}/lead     ─►  agente_clientes/leads/tarefas
painel (Pages)          ─►  /api/landing-pages/*     ─►  gerador ─► API Anthropic
```

## Decisões que valem mais do que o código

- **HTML servido pelo backend, não uma rota no SPA.** As OG tags têm de existir
  no HTML entregue: sem elas, o link partilhado no WhatsApp — que é metade do
  uso — mostra pré-visualização genérica. Como efeito lateral, o gate passou a
  ser real e o "template base" ficou um `.html` que se itera sem rebuild.
- **CSS à mão, sem Tailwind por CDN.** A página abre a partir de um anúncio
  pago; 300 kB de JS a compilar classes antes do primeiro pixel paga-se em
  leads perdidas. Zero pedidos externos.
- **O gate esconde mesmo.** Galeria, descrição longa, morada, vídeo e notas não
  estão no HTML inicial — vêm no corpo da resposta ao POST. Um teste falha se
  alguma dessas coisas voltar a aparecer antes do formulário.
- **`CAMPOS_PUBLICOS` é fronteira de segurança.** `imoveis` tem `proprietario`,
  `angariador` e três colunas de comissão. Allowlist explícita, nunca
  `select("*")`; coluna nova do eGO fica de fora por omissão. Teste dedicado.
- **Sem coluna de estado.** "Já não disponível" é derivado de `imoveis.publicado`
  (GENERATED, migration 0008) a cada visita. Nada de cron, nada que dessincronize.
  O formulário fica — quem chega por um anúncio antigo ainda vale como lead.
- **`fonte_hash` decide se se paga API.** sha256 do que o modelo vê. Editar o
  vídeo ou esconder o preço regenera; trocar a foto principal não. Baixar o
  preço com o preço escondido também não — não entra no hash.
- **Saída do modelo forçada por tool** (`escrever_landing_page`), não pedida em
  prosa: é o que garante que as secções chegam sempre na mesma forma.
- **`PRAZOS` por extenso** ("Até 3 meses"), não `<3 meses`: vai para
  `agente_clientes.prazo_compra` e daí para relatórios e prompts, onde `<`
  chegaria escapado.

## Ficheiros

| Ficheiro | |
|---|---|
| `supabase/migrations/0020_landing_pages.sql` | NOVO — tabela + `prazo_compra` + `agente_leads.imovel_ref` |
| `backend/app/landing/gerador.py` | NOVO — allowlist, hash, chamada à API |
| `backend/app/landing/templates/imovel.html` | NOVO — página + OG tags + gate |
| `backend/app/landing/templates/conteudo.html` | NOVO — fragmento pós-gate |
| `backend/app/api/landing.py` | NOVO — router público + router do painel |
| `backend/tests/test_landing.py` | NOVO — 17 testes, sem BD nem API |
| `frontend/src/components/LandingPagesTab.jsx` | NOVO — aba do painel |
| `frontend/src/components/ui.jsx` | NOVO — `Modal`/`Field`/`inputCls` que estavam copiados |
| `cloudflare/worker-landing.js` | NOVO — proxy do domínio público |
| `backend/app/main.py`, `config.py`, `requirements.txt`, `pages/Imoveis.jsx` | EDIT |

## Custo

~3k tokens de entrada e ~1,5k de saída por imóvel: **~$0,03**. O system prompt
vai com `cache_control`, por isso gerar vários seguidos custa menos. O custo de
cada geração fica gravado em `landing_pages.custo_usd` e somado no topo da aba.

## Por fazer

> **2026-08-11 — em standby.** A arquitectura de alojamento (backend + Worker vs
> estático independente) está por decidir com o cliente. Ver *Decisão em aberto*
> no `CLAUDE.md`. Os pontos 1–3 abaixo só valem se a decisão for manter como está.

1. **Correr a migration 0020** no editor SQL do Supabase.
2. **Instalar o Worker** e pôr `LANDING_BASE_URL` nos secrets do Fly.io —
   instruções no cabeçalho de `cloudflare/worker-landing.js`. Sem isto as
   páginas servem-se na mesma pelo URL do Fly.io.
3. **Confirmar a pré-visualização real** no WhatsApp com um link verdadeiro.
4. Critério de **remoção definitiva** continua sem decisão: hoje é o botão
   Remover no painel.
5. Pixel da Meta: um campo em `agente_config` e uma linha no `<head>` — fora do
   âmbito desta fase, mas é o passo natural quando as campanhas arrancarem.
6. `Modal`/`Field`/`inputCls` continuam copiados em `Clientes.jsx`, `Leads.jsx`
   e `AgenteConfig.jsx` — passam a importar de `components/ui.jsx` quando
   alguém lá voltar.
