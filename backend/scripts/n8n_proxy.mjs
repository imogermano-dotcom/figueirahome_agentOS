// Proxy local para o MCP do n8n: junta a palavra-passe do Traefik (Basic) e reencaminha SÓ /api/v1 e /healthz.
// O n8n-mcp não converte `user:pass@` do URL em cabeçalho Authorization (testado 02/11), por isso o Traefik responde 401.
// Uso: `node backend/scripts/n8n_proxy.mjs` (pede a palavra-passe escondida; ou N8N_BASIC_PASS no ambiente, nunca em ficheiro)
// e apontar N8N_API_URL a http://127.0.0.1:5679.
import http from "node:http";
import https from "node:https";

const USER = process.env.N8N_BASIC_USER || "miguelgermano";
const ALVO = process.env.N8N_ALVO || "n8n.figueirahome.cloud";
const PORTA = Number(process.env.N8N_PROXY_PORT || 5679);

// Palavra-passe: do ambiente ou pedida aqui (escondida), sempre sem espaços nas pontas.
function pedirPass() {
  return new Promise((ok) => {
    process.stderr.write(`Palavra-passe do Traefik (${USER}): `);
    let txt = "";
    const ler = (c) => {
      for (const ch of c) {
        if (ch === "\r" || ch === "\n") {
          process.stdin.setRawMode(false).pause().off("data", ler);
          process.stderr.write("\n");
          return ok(txt);
        }
        if (ch === "\u0003") process.exit(1); // Ctrl+C
        if (ch === "\b" || ch === "\u007f") txt = txt.slice(0, -1);
        else txt += ch;
      }
    };
    process.stdin.setRawMode(true).resume().setEncoding("utf8").on("data", ler);
  });
}

const PASS = (process.env.N8N_BASIC_PASS || (await pedirPass())).trim();
if (!PASS) {
  console.error("Falta a palavra-passe do Traefik.");
  process.exit(1);
}
const basic = "Basic " + Buffer.from(`${USER}:${PASS}`).toString("base64");

http.createServer((req, res) => {
  if (!req.url.startsWith("/api/v1") && req.url !== "/healthz") {  // o resto do n8n não passa por aqui
    res.writeHead(403).end("so /api/v1 e /healthz");
    return;
  }
  const headers = { ...req.headers, host: ALVO, authorization: basic };  // X-N8N-API-KEY segue como veio
  const saida = https.request({ host: ALVO, path: req.url, method: req.method, headers }, (r) => {
    res.writeHead(r.statusCode, r.headers);
    r.pipe(res);
  });
  saida.on("error", () => res.writeHead(502).end("n8n inacessivel"));
  req.pipe(saida);
}).listen(PORTA, "127.0.0.1", () => console.error(`proxy n8n em http://127.0.0.1:${PORTA} (so /api/v1 e /healthz); utilizador "${USER}", palavra-passe de ${PASS.length} caracteres`));
