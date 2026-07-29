import hmac
import logging

from fastapi import FastAPI, Header, HTTPException

import config
import oportunidades_completo

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()


@app.get("/health")
async def health():
    return {"status": "ok"}


def _check_secret(x_scraper_secret: str | None) -> None:
    if not config.scraper_service_secret or not x_scraper_secret or not hmac.compare_digest(
        x_scraper_secret, config.scraper_service_secret
    ):
        raise HTTPException(status_code=401, detail="Secret inválido.")


@app.post("/run/oportunidades-completo")
async def run_oportunidades_completo(x_scraper_secret: str = Header(None, alias="X-Scraper-Secret")):
    _check_secret(x_scraper_secret)
    try:
        return await oportunidades_completo.run(headless=True)
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e))
    except Exception:
        logger.exception("Falha no scrape de oportunidades (relatório completo)")
        raise HTTPException(status_code=502, detail="Falha ao correr o scraper de oportunidades.")
