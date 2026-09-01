/*
 * Widget de chat do figueirahome.pt -- apoio + pesquisa de imóveis.
 *
 * Autocontido, sem dependências, sem build. Cola este ficheiro no teu site e
 * inclui:
 *
 *   <script src="/caminho/para/widget.js" defer></script>
 *
 * Para apontar a outro backend (ex.: staging), define ANTES do <script>:
 *
 *   <script>window.FIGUEIRAHOME_CHAT_API = "https://outro-host/api/site/chat";</script>
 *
 * Cada visitante recebe um id aleatório guardado em localStorage -- mesma
 * conversa ao navegar entre páginas do site, sem histórico entre
 * dispositivos (não há login).
 */
(function () {
  "use strict";

  var API_URL = window.FIGUEIRAHOME_CHAT_API || "https://figueirahome-agentos.fly.dev/api/site/chat";
  var STORAGE_KEY = "fh_chat_participante";
  var MAX_MENSAGEM = 2000;

  function idVisitante() {
    try {
      var existente = window.localStorage.getItem(STORAGE_KEY);
      if (existente) return existente;
      var novo = "site-" + Date.now().toString(36) + "-" + Math.random().toString(36).slice(2, 10);
      window.localStorage.setItem(STORAGE_KEY, novo);
      return novo;
    } catch (e) {
      // localStorage indisponível (modo privado, etc.) -- thread nova a cada carregamento.
      return "site-" + Math.random().toString(36).slice(2, 10);
    }
  }

  var participante = idVisitante();

  var estilo = document.createElement("style");
  estilo.textContent =
    ".fh-chat-bolha{position:fixed;bottom:20px;right:20px;width:56px;height:56px;" +
    "border-radius:50%;background:#1a5f4a;color:#fff;border:none;cursor:pointer;" +
    "font-size:24px;box-shadow:0 2px 10px rgba(0,0,0,.25);z-index:999998}" +
    ".fh-chat-painel{position:fixed;bottom:88px;right:20px;width:340px;max-width:92vw;" +
    "height:460px;max-height:75vh;background:#fff;border-radius:12px;" +
    "box-shadow:0 4px 24px rgba(0,0,0,.25);display:none;flex-direction:column;" +
    "overflow:hidden;font-family:system-ui,-apple-system,sans-serif;z-index:999999}" +
    ".fh-chat-painel.aberto{display:flex}" +
    ".fh-chat-cabecalho{background:#1a5f4a;color:#fff;padding:12px 16px;font-weight:600}" +
    ".fh-chat-mensagens{flex:1;overflow-y:auto;padding:12px;display:flex;flex-direction:column;gap:8px}" +
    ".fh-chat-msg{max-width:80%;padding:8px 12px;border-radius:10px;font-size:14px;line-height:1.4;white-space:pre-wrap}" +
    ".fh-chat-msg.user{align-self:flex-end;background:#1a5f4a;color:#fff}" +
    ".fh-chat-msg.assistant{align-self:flex-start;background:#f0f0f0;color:#222}" +
    ".fh-chat-msg.erro{align-self:center;background:#fde2e2;color:#7a1f1f}" +
    ".fh-chat-rodape{display:flex;border-top:1px solid #e5e5e5;padding:8px;gap:6px}" +
    ".fh-chat-input{flex:1;border:1px solid #ddd;border-radius:6px;padding:8px;font-size:14px;resize:none;max-height:80px}" +
    ".fh-chat-enviar{background:#1a5f4a;color:#fff;border:none;border-radius:6px;padding:0 14px;cursor:pointer}" +
    ".fh-chat-enviar:disabled{opacity:.5;cursor:default}";
  document.head.appendChild(estilo);

  var bolha = document.createElement("button");
  bolha.className = "fh-chat-bolha";
  bolha.setAttribute("aria-label", "Abrir chat");
  bolha.textContent = "💬";

  var painel = document.createElement("div");
  painel.className = "fh-chat-painel";
  painel.innerHTML =
    '<div class="fh-chat-cabecalho">FigueiraHome</div>' +
    '<div class="fh-chat-mensagens"></div>' +
    '<div class="fh-chat-rodape">' +
    '<textarea class="fh-chat-input" rows="1" placeholder="Escreve a tua mensagem..."></textarea>' +
    '<button class="fh-chat-enviar">Enviar</button>' +
    "</div>";

  document.body.appendChild(bolha);
  document.body.appendChild(painel);

  var caixaMensagens = painel.querySelector(".fh-chat-mensagens");
  var input = painel.querySelector(".fh-chat-input");
  var botaoEnviar = painel.querySelector(".fh-chat-enviar");

  function adicionarMensagem(texto, classe) {
    var msg = document.createElement("div");
    msg.className = "fh-chat-msg " + classe;
    msg.textContent = texto; // textContent, nunca innerHTML -- entrada e saída não são de confiança
    caixaMensagens.appendChild(msg);
    caixaMensagens.scrollTop = caixaMensagens.scrollHeight;
  }

  bolha.addEventListener("click", function () {
    painel.classList.toggle("aberto");
    if (painel.classList.contains("aberto") && !caixaMensagens.children.length) {
      adicionarMensagem("Olá! Em que posso ajudar? Posso procurar imóveis ou responder a questões gerais.", "assistant");
    }
  });

  var aEnviar = false;

  function enviar() {
    var texto = input.value.trim();
    if (!texto || aEnviar) return;
    if (texto.length > MAX_MENSAGEM) {
      adicionarMensagem("Mensagem demasiado longa (máx. " + MAX_MENSAGEM + " caracteres).", "erro");
      return;
    }

    adicionarMensagem(texto, "user");
    input.value = "";
    aEnviar = true;
    botaoEnviar.disabled = true;

    fetch(API_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ participante: participante, mensagem: texto }),
    })
      .then(function (resp) {
        if (resp.status === 429) {
          throw new Error("Demasiadas mensagens seguidas. Espera um pouco e tenta de novo.");
        }
        if (!resp.ok) {
          throw new Error("Não consegui responder agora. Tenta novamente.");
        }
        return resp.json();
      })
      .then(function (dados) {
        adicionarMensagem(dados.resposta, "assistant");
      })
      .catch(function (erro) {
        adicionarMensagem(erro.message || "Erro de ligação. Tenta novamente.", "erro");
      })
      .finally(function () {
        aEnviar = false;
        botaoEnviar.disabled = false;
      });
  }

  botaoEnviar.addEventListener("click", enviar);
  input.addEventListener("keydown", function (e) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      enviar();
    }
  });
})();
