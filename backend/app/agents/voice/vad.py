"""Deteção de fim de frase por energia, para o áudio PCMU (8 kHz, 1 byte por amostra) da Telnyx.

Substitui as janelas fixas de 2 s, que cortavam as frases a meio e faziam a assistente responder a fragmentos
(chamada de teste de 17/10: «Um, uma casa, uma cidade...»). Acumula enquanto a pessoa fala e só devolve a frase
depois de um silêncio. ponytail: energia simples, sem modelo de VAD; afinar os limiares com chamadas reais.
"""

import struct
from collections import deque

from app.agents.voice.stt import LIMIAR_RMS, _ulaw2lin

_BYTES_POR_MS = 8        # PCMU a 8 kHz
FIM_DE_FRASE_MS = 700    # silêncio que fecha a frase
MIN_FALA_MS = 300        # menos que isto é um estalido, não uma frase
MAX_FRASE_MS = 15_000    # corta frases sem fim (ruído contínuo, monólogo)
_PRE_ROLL_MS = 200       # o início da frase costuma estar abaixo do limiar


def _rms(pcmu: bytes) -> float:
    pcm = _ulaw2lin(pcmu)
    n = len(pcm) // 2
    if not n:
        return 0.0
    return (sum(v * v for (v,) in struct.iter_unpack("<h", pcm)) / n) ** 0.5


class DetetorDeFrase:
    """`feed(bloco)` devolve os bytes da frase quando ela acaba, senão `None`. `reset()` descarta o que estava a meio."""

    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self._frase = bytearray()
        self._pre_roll: deque[bytes] = deque()
        self._pre_roll_bytes = 0
        self._a_falar = False
        self._fala_ms = 0.0
        self._silencio_ms = 0.0

    def feed(self, bloco: bytes) -> bytes | None:
        ms = len(bloco) / _BYTES_POR_MS
        if _rms(bloco) >= LIMIAR_RMS:
            if not self._a_falar:
                self._a_falar = True
                self._frase.extend(b"".join(self._pre_roll))
                self._pre_roll.clear()
                self._pre_roll_bytes = 0
            self._frase.extend(bloco)
            self._fala_ms += ms
            self._silencio_ms = 0.0
        elif self._a_falar:
            self._frase.extend(bloco)
            self._silencio_ms += ms
        else:
            self._pre_roll.append(bloco)
            self._pre_roll_bytes += len(bloco)
            while self._pre_roll_bytes > _PRE_ROLL_MS * _BYTES_POR_MS and len(self._pre_roll) > 1:
                self._pre_roll_bytes -= len(self._pre_roll.popleft())
            return None

        if self._silencio_ms >= FIM_DE_FRASE_MS or len(self._frase) >= MAX_FRASE_MS * _BYTES_POR_MS:
            frase = bytes(self._frase) if self._fala_ms >= MIN_FALA_MS else None
            self.reset()
            return frase
        return None
