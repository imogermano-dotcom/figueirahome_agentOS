# Construtor de Landing Pages — Plano

## Objectivo

Gerar landing pages por imóvel, para usar como anúncio (Meta Ads, WhatsApp,
etc.), com geração de conteúdo por IA em vez de template preenchido à mão.

**Activo desde 2026-08-08.** Vinha do backlog do portal marcado "não
prioritário" — decisão do João em avançar já, mesmo antes do resto do âmbito
prioritário do portal fechar. Ver `clients/miguel-germano/portal-agentes-ia/
README.md` e `decisions/log.md` (2026-08-08) no repo JAWOS para o histórico da
decisão.

---

## Motor: geração dinâmica, não formulário

A Artinvest (outro cliente) tem um construtor de landing pages diferente:
template preenchido a partir de formulário. **Este é deliberadamente outro
motor** — a IA (API da Anthropic) escreve o conteúdo da página dentro de um
template base, não é o utilizador a preencher campos de um formulário
genérico. Não juntar os dois.

---

## Decisões fechadas

| Item | Decisão |
|---|---|
| Dados de entrada | Eagle → Supabase (sync diário já existente) dá o básico: preço, fotos, descrição. Formulário/PDF **novo** complementa com vídeo, mapa e conteúdo extra que o Eagle não tem |
| Template | Existe um template base; a IA escreve o conteúdo dentro dele — não gera HTML livre |
| Preço | Campo configurável mostrar/esconder — imóvel como chamariz (esconder) ou qualificador (mostrar) |
| Volume | Só imóveis que o Miguel seleccionar manualmente — não gerar para o portefólio inteiro (controla custo de API) |
| Geração | Uma vez por imóvel, guardada; regenera só se os dados-fonte do imóvel mudarem — não a cada visita |
| Imóvel sai do Eagle (vendido/retirado) | Landing page passa a mostrar "já não disponível" durante um período. Remoção definitiva da página: **sem critério decidido ainda** |
| Gate de qualificação antes de mostrar o imóvel | 4 campos: nome, telefone/WhatsApp, email, prazo de compra (`<3 meses` / `3–6 meses` / `>6 meses` / `só a pesquisar`) |

---

## Decisões em aberto — fechadas a 2026-08-08

| Estava em aberto | Ficou |
|---|---|
| Estrutura do template (secções fixas vs. variáveis por tipo) | **Fixas**: headline, subheadline, destaques, descrição longa, envolvente, CTA. A variação por tipo entra no prompt (a `natureza` vai no input), não em secções diferentes |
| Onde entra o complemento e quem o preenche | **Formulário no painel**, preenchido pelo Miguel: vídeo, mapa, notas. Upload de PDF ficou de fora |
| Schema Supabase e estado | Tabela `landing_pages` (migration `0020`). **Sem coluna de estado** — "já não disponível" é derivado de `imoveis.publicado` a cada visita |
| Gate: página própria ou modal | **Nem uma nem outra**: o conteúdo protegido não é servido até o formulário ser submetido. Nada para remover no inspector |
| Critério de remoção definitiva | **Continua sem decisão.** Hoje é o botão Remover no painel |

Uma decisão nova que não estava na lista: as páginas são servidas **pelo backend
em HTML**, sob o caminho do site (`site.pt/imovel/{slug}`) via Worker da
Cloudflare — não como rota do painel em React. A razão é a pré-visualização no
WhatsApp; ver `landing-pages-resumo.md`.

## Próximo passo

Feito — ver `landing-pages-resumo.md` para o que ficou construído e o que falta
(migration por correr, Worker por instalar).
