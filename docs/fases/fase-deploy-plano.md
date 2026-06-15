# Deploy — Fly.io (Backend) + Vercel (Frontend)

## Objectivo

Backend FastAPI em produção no Fly.io. Frontend React em produção no Vercel.
Eliminar dependência de ngrok e localhost.

---

## Tarefas

### Backend — Fly.io

1. Instalar Fly CLI (`winget install Fly.io.flyctl`)
2. Autenticar (`flyctl auth login`)
3. Criar `backend/Dockerfile`
4. Criar `backend/fly.toml`
5. Criar app no Fly (`flyctl launch --no-deploy`)
6. Configurar secrets (env vars) no Fly
7. Deploy (`flyctl deploy`)
8. Verificar `/health` em `https://<app>.fly.dev/health`

### Frontend — Vercel

9. Actualizar `frontend/.env.production` com URL do backend Fly
10. Deploy Vercel (via CLI ou push GitHub)
11. Actualizar CORS no backend com URL Vercel
12. Re-deploy backend com CORS actualizado

---

## Ficheiros a criar/alterar

| Ficheiro | Acção |
|---|---|
| `backend/Dockerfile` | Criar |
| `backend/fly.toml` | Criar |
| `backend/.dockerignore` | Criar |
| `frontend/.env.production` | Criar/actualizar |
| `backend/app/main.py` | CORS ajustado para produção |
| `CLAUDE.md` | Marcar deploy ✅ |

---

## Decisões em aberto

1. **Nome da app Fly** — ex: `figueirahome-api`. Tens preferência?
2. **Região Fly** — `mad` (Madrid, mais perto de PT) ou outra?
3. **Frontend no Vercel** — já tens projecto criado ou é de raiz?
4. **Secrets Telnyx/Meta** — sem credenciais reais, ficam como placeholder ou omitidos?

---

## Secrets a configurar no Fly

```
SUPABASE_URL
SUPABASE_SERVICE_ROLE_KEY
ANTHROPIC_API_KEY
OPENAI_API_KEY
APP_BASE_URL=https://<app>.fly.dev
ENVIRONMENT=production
# Placeholders (sem credenciais reais):
TELNYX_API_KEY
TELNYX_PUBLIC_KEY
TELNYX_PHONE_NUMBER
META_WHATSAPP_TOKEN
META_APP_SECRET
META_PHONE_NUMBER_ID
META_VERIFY_TOKEN
```

---

## Dockerfile previsto

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

---

## Como testar

```bash
curl https://<app>.fly.dev/health
# {"status":"ok","version":"0.4.0","environment":"production"}
```

---

## Decisões em aberto — responder antes de avançar.
