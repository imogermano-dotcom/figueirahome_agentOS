from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.agents.broker.channels.whatsapp.webhook import router as whatsapp_router
from app.agents.voice.audio_ws import router as audio_ws_router
from app.agents.voice.webhook import router as voice_webhook_router
from app.api.broker import router as broker_chat_router
from app.api.clientes import router as clientes_router
from app.api.imoveis import router as imoveis_router
from app.api.leads import router as leads_router
from app.api.config import router as config_router
from app.api.dashboard import router as dashboard_router
from app.config import settings

app = FastAPI(
    title="Figueirahome Agent Call API",
    version="0.4.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if settings.environment == "development" else [settings.frontend_url],
    allow_origin_regex=r"https://[a-z0-9]+\.figueirahome-agentos\.pages\.dev" if settings.environment == "production" else None,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(voice_webhook_router)
app.include_router(audio_ws_router)
app.include_router(whatsapp_router)
app.include_router(broker_chat_router)
app.include_router(clientes_router)
app.include_router(imoveis_router)
app.include_router(leads_router)
app.include_router(config_router)
app.include_router(dashboard_router)


@app.get("/health")
async def health():
    return {"status": "ok", "version": "0.4.0", "environment": settings.environment}
