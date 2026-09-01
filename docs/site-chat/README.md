# Widget de chat — figueirahome.pt

Cola `widget.js` no teu site e adiciona, antes de `</body>`:

```html
<script src="/caminho/para/widget.js" defer></script>
```

Não precisa de mais nada — sem build, sem dependências. Fala directamente
com `https://figueirahome-agentos.fly.dev/api/site/chat`.

**CORS já libertado** no backend para `https://figueirahome.pt` e
`https://www.figueirahome.pt` (`backend/app/main.py`). Se o site estiver
noutro domínio ou subdomínio, o `fetch` do widget é bloqueado pelo browser
até esse domínio ser acrescentado lá.

Para testar contra outro backend (ex.: local), define antes do `<script>`:

```html
<script>window.FIGUEIRAHOME_CHAT_API = "http://localhost:8000/api/site/chat";</script>
```

Cada visitante fica com um id aleatório em `localStorage` — mesma conversa
ao mudar de página, sem histórico entre dispositivos (não há login).
