from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class CallSession:
    call_control_id: str
    numero_origem: str
    iniciada_em: datetime = field(default_factory=datetime.utcnow)
    audio_buffer: bytearray = field(default_factory=bytearray)
    transcricao_acumulada: str = ""
    historico: list = field(default_factory=list)
    system_prompt: str = ""
    is_speaking: bool = False
    stt_fail_count: int = 0


_sessions: dict[str, CallSession] = {}


def create_session(call_control_id: str, numero_origem: str) -> CallSession:
    session = CallSession(call_control_id=call_control_id, numero_origem=numero_origem)
    _sessions[call_control_id] = session
    return session


def get_session(call_control_id: str) -> CallSession | None:
    return _sessions.get(call_control_id)


def remove_session(call_control_id: str) -> CallSession | None:
    return _sessions.pop(call_control_id, None)
