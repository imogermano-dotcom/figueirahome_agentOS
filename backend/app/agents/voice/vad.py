"""Deteção de fim de frase por energia, para o áudio PCMU (8 kHz, 1 byte por amostra) da Telnyx.

Substitui as janelas fixas de 2 s, que cortavam as frases a meio e faziam a assistente responder a fragmentos
(chamada de teste de 17/10: «Um, uma casa, uma cidade...»). Acumula enquanto a pessoa fala e só devolve a frase
depois de um silêncio. O limiar acompanha o ruído da linha: na 3.ª chamada de teste (17/10) o ruído ficou acima do
limiar fixo de 200, nunca houve «silêncio» e a frase só fechou aos 15 s do teto.
ponytail: energia simples, sem modelo de VAD; afinar os fatores com chamadas reais.
"""

import struct
from collections import deque

from app.agents.voice.stt import LIMIAR_RMS, _ulaw2lin

_BYTES_POR_MS = 8        # PCMU a 8 kHz
FIM_DE_FRASE_MS = 700    # silêncio que fecha a frase
MIN_FALA_MS = 300        # menos que isto é um estalido, não uma frase
MAX_FRASE_MS = 15_000    # corta frases sem fim (ruído contínuo, monólogo)
_PRE_ROLL_MS = 200       # o início da frase costuma estar abaixo do limiar
_CAUDA_MS = 250          # silêncio final que segue com a frase: os 700 ms todos diluíam respostas curtas
_ARRANQUE_BLOCOS = 10    # ~200 ms para medir o ruído antes de aceitar fala
_JANELA_BLOCOS = 100     # ~2 s de histórico para o piso de ruído
_FATOR_PISO = 2.0        # fala = pelo menos 2× o ruído de fundo (+ margem)
_MARGEM_RMS = 50
_LIMIAR_MAX = 1000.0      # teto: a fala fraca ao telefone ronda 1000; sem isto, uma chamada que abre logo com fala
                         # tomava a fala por ruído (o 10.º percentil é a própria fala) e nunca detetava nada


def _rms(pcmu: bytes) -> float:
    pcm = _ulaw2lin(pcmu)
    n = len(pcm) // 2
    if not n:
        return 0.0
    return (sum(v * v for (v,) in struct.iter_unpack("<h", pcm)) / n) ** 0.5


class DetetorDeFrase:
    """`feed(bloco)` devolve os bytes da frase quando ela acaba, senão `None`. `reset()` descarta o que estava a meio
    mas mantém o que já se sabe do ruído da linha."""

    def __init__(self) -> None:
        self._historico: deque[float] = deque(maxlen=_JANELA_BLOCOS)
        self.limiar = float(LIMIAR_RMS)
        self.reset()

    def reset(self) -> None:
        self._frase = bytearray()
        self._pre_roll: deque[bytes] = deque()
        self._pre_roll_bytes = 0
        self._a_falar = False
        self._fala_ms = 0.0
        self._silencio_ms = 0.0

    @property
    def fala_ms(self) -> float:
        """Fala acumulada na frase em curso (0 se ninguém está a falar)."""
        return self._fala_ms if self._a_falar else 0.0

    def _atualiza_limiar(self, rms: float) -> None:
        self._historico.append(rms)
        h = sorted(self._historico)
        piso = h[len(h) // 10]  # 10.º percentil: o ruído, mesmo com fala na janela
        self.limiar = min(_LIMIAR_MAX, max(float(LIMIAR_RMS), piso * _FATOR_PISO + _MARGEM_RMS))

    def _guarda_pre_roll(self, bloco: bytes) -> None:
        self._pre_roll.append(bloco)
        self._pre_roll_bytes += len(bloco)
        while self._pre_roll_bytes > _PRE_ROLL_MS * _BYTES_POR_MS and len(self._pre_roll) > 1:
            self._pre_roll_bytes -= len(self._pre_roll.popleft())

    def escutar(self, bloco: bytes) -> None:
        """Enquanto a assistente fala: mede o ruído e guarda os últimos 200 ms, mas nunca abre frase. Antes
        descartava-se tudo e o início da resposta, dito quando a assistente acaba, perdia-se (18/10: o nome
        dito logo a seguir à pergunta chegou como texto vazio)."""
        self._atualiza_limiar(_rms(bloco))
        if self._a_falar:  # frase a meio quando a assistente começou a falar: descarta
            self.reset()
        self._guarda_pre_roll(bloco)

    def feed(self, bloco: bytes) -> bytes | None:
        ms = len(bloco) / _BYTES_POR_MS
        rms = _rms(bloco)
        self._atualiza_limiar(rms)
        em_arranque = len(self._historico) < _ARRANQUE_BLOCOS  # ainda a medir o ruído: nada é fala

        if rms >= self.limiar and not em_arranque:
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
            self._guarda_pre_roll(bloco)
            return None

        if self._silencio_ms >= FIM_DE_FRASE_MS or len(self._frase) >= MAX_FRASE_MS * _BYTES_POR_MS:
            frase = None
            if self._fala_ms >= MIN_FALA_MS:
                excesso = int(max(0.0, self._silencio_ms - _CAUDA_MS) * _BYTES_POR_MS)
                frase = bytes(self._frase[: len(self._frase) - excesso])
            self.reset()
            return frase
        return None
