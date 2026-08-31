"""A Meta garante "at least once" e reenvia o mesmo webhook em falhas
transitórias -- sem dedupe por `message_id`, a reentrega reprocessa a
mensagem do zero e duplica o que as tools escrevem (achado em produção:
visitas e leads qualificadas duplicadas, sempre 30-65s de diferença entre
cópias, 2026-08-31)."""

import asyncio

from app.agents.broker.channels.whatsapp import webhook


class _FakeQuery:
    def __init__(self, existentes):
        self._existentes = existentes
        self.data = None

    def upsert(self, row, on_conflict=None, ignore_duplicates=None):
        message_id = row["message_id"]
        if message_id in self._existentes:
            self.data = []  # conflito ignorado -- já existia
        else:
            self._existentes.add(message_id)
            self.data = [row]
        return self

    def execute(self):
        return self


class _FakeSupabase:
    def __init__(self, existentes):
        self._existentes = existentes

    def table(self, _name):
        return _FakeQuery(self._existentes)


def test_primeira_vez_processa(monkeypatch):
    monkeypatch.setattr(webhook, "get_supabase", lambda: _FakeSupabase(set()))
    assert webhook._ja_processada("wamid.AAA") is False


def test_reentrega_e_ignorada(monkeypatch):
    monkeypatch.setattr(webhook, "get_supabase", lambda: _FakeSupabase({"wamid.AAA"}))
    assert webhook._ja_processada("wamid.AAA") is True


def test_sem_message_id_nao_bloqueia(monkeypatch):
    def _explode():
        raise AssertionError("não devia ir à BD sem message_id")

    monkeypatch.setattr(webhook, "get_supabase", _explode)
    assert webhook._ja_processada("") is False
    assert webhook._ja_processada(None) is False


def test_falha_na_bd_deixa_processar(monkeypatch):
    """Dedupe é uma optimização, não uma trava -- se a BD falhar, processa na
    mesma. Melhor arriscar uma duplicada rara do que perder uma mensagem."""

    class _Explode:
        def table(self, _name):
            raise RuntimeError("BD em baixo")

    monkeypatch.setattr(webhook, "get_supabase", lambda: _Explode())
    assert webhook._ja_processada("wamid.AAA") is False


def test_handle_message_nao_reprocessa_reentrega(monkeypatch):
    monkeypatch.setattr(webhook, "get_supabase", lambda: _FakeSupabase({"wamid.AAA"}))

    chamou = {"sim": False}

    async def _explode(*a, **k):
        chamou["sim"] = True

    monkeypatch.setattr(webhook, "mark_as_read", _explode)
    asyncio.run(webhook._handle_message("912345678", "wamid.AAA", "olá"))

    assert chamou["sim"] is False
