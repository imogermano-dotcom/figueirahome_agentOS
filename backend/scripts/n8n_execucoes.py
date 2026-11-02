"""Runs do n8n nas últimas N horas (só leitura): por fluxo, contagem por estado + último erro.

Uso (de backend/): python scripts/n8n_execucoes.py [horas=24]
Lê de backend/.env (ou do ambiente): N8N_URL, N8N_API_KEY, N8N_BASIC_USER, N8N_BASIC_PASS.
O Traefik à frente do n8n pede Basic auth; a API pede X-N8N-API-KEY. Nunca imprime credenciais.
"""
import base64
import json
import os
import sys
import urllib.request
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path


def _env() -> dict:
    cfg = dict(os.environ)
    f = Path(__file__).resolve().parents[1] / ".env"
    if f.exists():
        for linha in f.read_text(encoding="utf-8").splitlines():
            if "=" in linha and not linha.lstrip().startswith("#"):
                k, v = linha.split("=", 1)
                cfg.setdefault(k.strip(), v.strip().strip('"').strip("'"))
    return cfg


def _get(cfg: dict, caminho: str) -> dict:
    basic = base64.b64encode(f"{cfg['N8N_BASIC_USER']}:{cfg['N8N_BASIC_PASS']}".encode()).decode()
    req = urllib.request.Request(
        cfg.get("N8N_URL", "https://n8n.figueirahome.cloud").rstrip("/") + caminho,
        headers={"Authorization": f"Basic {basic}", "X-N8N-API-KEY": cfg["N8N_API_KEY"]},
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def main() -> None:
    cfg = _env()
    em_falta = [k for k in ("N8N_API_KEY", "N8N_BASIC_USER", "N8N_BASIC_PASS") if not cfg.get(k)]
    if em_falta:
        sys.exit(f"Faltam no backend/.env: {', '.join(em_falta)}")
    desde = datetime.now(timezone.utc) - timedelta(hours=float(sys.argv[1]) if len(sys.argv) > 1 else 24)

    nomes = {w["id"]: w["name"] for w in _get(cfg, "/api/v1/workflows?limit=250")["data"]}
    por_fluxo: dict = defaultdict(Counter)
    ultimo_erro: dict = {}
    cursor = ""
    while True:  # execuções vêm da mais recente para a mais antiga
        pag = _get(cfg, "/api/v1/executions?limit=250" + (f"&cursor={cursor}" if cursor else ""))
        for e in pag["data"]:
            ini = datetime.fromisoformat(e["startedAt"].replace("Z", "+00:00"))
            if ini < desde:
                cursor = ""
                break
            nome = nomes.get(e["workflowId"], e["workflowId"])
            por_fluxo[nome][e["status"]] += 1
            if e["status"] in ("error", "crashed") and nome not in ultimo_erro:
                ultimo_erro[nome] = f"{e['id']} às {ini:%d/%m %H:%M} UTC"
        else:
            cursor = pag.get("nextCursor") or ""
        if not cursor:
            break

    for nome, c in sorted(por_fluxo.items()):
        print(f"{nome}: {dict(c)}" + (f"  ← último erro: exec {ultimo_erro[nome]}" if nome in ultimo_erro else ""))
    sem_runs = sorted(set(nomes.values()) - set(por_fluxo))
    print(f"\nSem runs no período: {', '.join(sem_runs) or '—'}")


if __name__ == "__main__":
    main()
