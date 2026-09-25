"""Lock de `responder()` por (canal, participante) — evita a corrida que
duplicava conversas quando a mesma pessoa manda 2 mensagens quase juntas
(achado ao vivo 25/09, Margarida Lopes: 2 linhas `agente_conversas`, 3s de
diferença, cada uma com a sua própria resposta).

Corre com `pytest backend/tests/` ou directamente com
`python backend/tests/test_engine_lock.py`.
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agents.broker import engine  # noqa: E402


def test_mesma_conversa_fica_serializada(monkeypatch):
    ordem = []

    async def _fake(canal, participante, mensagem, agente=None):
        ordem.append(f"start:{mensagem}")
        await asyncio.sleep(0.05)
        ordem.append(f"end:{mensagem}")
        return "ok"

    monkeypatch.setattr(engine, "_responder_sem_lock", _fake)

    async def _correr():
        t1 = asyncio.create_task(engine.responder("whatsapp", "351900000001", "primeira"))
        await asyncio.sleep(0.01)  # a 1ª já está a "trabalhar" quando a 2ª chega
        t2 = asyncio.create_task(engine.responder("whatsapp", "351900000001", "segunda"))
        await asyncio.wait_for(asyncio.gather(t1, t2), timeout=2)

    asyncio.run(_correr())

    # Sem lock isto intercalava: start:primeira, start:segunda, end:primeira, end:segunda
    assert ordem == ["start:primeira", "end:primeira", "start:segunda", "end:segunda"]


def test_participantes_diferentes_nao_se_bloqueiam(monkeypatch):
    ordem = []

    async def _fake(canal, participante, mensagem, agente=None):
        ordem.append(f"start:{participante}")
        await asyncio.sleep(0.05)
        ordem.append(f"end:{participante}")
        return "ok"

    monkeypatch.setattr(engine, "_responder_sem_lock", _fake)

    async def _correr():
        t1 = asyncio.create_task(engine.responder("whatsapp", "351900000001", "oi"))
        await asyncio.sleep(0.01)
        t2 = asyncio.create_task(engine.responder("whatsapp", "351900000002", "oi"))
        await asyncio.wait_for(asyncio.gather(t1, t2), timeout=2)

    asyncio.run(_correr())

    assert ordem == ["start:351900000001", "start:351900000002", "end:351900000001", "end:351900000002"]


def demo() -> None:
    test_mesma_conversa_fica_serializada(_NoOpMonkeypatch())
    test_participantes_diferentes_nao_se_bloqueiam(_NoOpMonkeypatch())
    print("test_engine_lock: ok")


class _NoOpMonkeypatch:
    def setattr(self, obj, nome, valor):
        setattr(obj, nome, valor)


if __name__ == "__main__":
    demo()
