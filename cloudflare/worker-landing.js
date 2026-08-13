/**
 * Landing pages sob o domínio do site, não sob o do portal.
 *
 * Rota:   figueirahome.pt/imovel/*
 * Origem: figueirahome-agentos.fly.dev/lp/*
 *
 * Proxy, não redirect: o visitante nunca vê o URL do Fly.io, e as OG tags que
 * o WhatsApp e o Facebook lêem ficam sob o domínio da agência.
 *
 * Instalação (uma vez):
 *   1. Cloudflare → Workers & Pages → Create → Worker → colar este ficheiro.
 *   2. Settings → Domains & Routes → Add route: `figueirahome.pt/imovel/*`
 *      (zona figueirahome.pt).
 *   3. Fly.io: `flyctl secrets set LANDING_BASE_URL=https://figueirahome.pt \
 *      --app figueirahome-agentos` — é o que o backend usa para o canonical e
 *      para as OG tags, já que o `Host` que aqui chega é o do Fly.io.
 *
 * Mudar `PREFIXO_PUBLICO` chega para trocar `/imovel/` por outro caminho; o
 * backend não muda.
 */

const ORIGEM = 'https://figueirahome-agentos.fly.dev'
const PREFIXO_PUBLICO = '/imovel/'
const PREFIXO_ORIGEM = '/lp/'

export default {
  async fetch(request) {
    const url = new URL(request.url)
    if (!url.pathname.startsWith(PREFIXO_PUBLICO)) {
      return new Response('Not found', { status: 404 })
    }

    // Sem a barra final: com ela o FastAPI responde 307 para o caminho `/lp/…`,
    // que a rota deste Worker não apanha — o visitante caía num 404 do site.
    const publico = url.pathname.replace(/\/+$/, '')
    const cauda = publico.slice(PREFIXO_PUBLICO.length)
    const alvo = `${ORIGEM}${PREFIXO_ORIGEM}${cauda}${url.search}`

    // O backend vê `/lp/…` no seu próprio pedido. Sem este cabeçalho, o
    // `action` do formulário e a `og:url` sairiam com o caminho interno, que o
    // domínio público não serve.
    const pedido = new Request(alvo, request)
    pedido.headers.set('X-Public-Path', publico)

    return fetch(pedido)
  },
}
