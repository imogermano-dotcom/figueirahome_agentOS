import io
import struct
import wave

from openai import AsyncOpenAI

from app.config import settings

_client = AsyncOpenAI(api_key=settings.openai_api_key)

SAMPLE_RATE = 8000
_BIAS = 0x84  # G.711 µ-law

# RMS (16 bits) abaixo do qual um bloco de 2 s é silêncio ou ruído de linha. Fala ao telefone ronda 1000-4000;
# o silêncio descodificado fica em ~0-50. ponytail: valor de partida, afinar com chamadas reais.
LIMIAR_RMS = 200

# Whisper inventa legendas quando recebe silêncio ou ruído (17/10: «Legendas pela comunidade Amara.org»).
_ALUCINACOES = ("amara.org", "legendas pela comunidade", "legendado por", "obrigado por assistir",
                "subtitles by", "thanks for watching")


def _ulaw2lin(ulaw_bytes: bytes) -> bytes:
    """Decode µ-law (PCMU) bytes to 16-bit signed linear PCM (G.711: `((m<<3)+0x84)<<exp - 0x84`).

    A versão anterior (`((m<<1)|1)<<(exp+2) - 33`) dava metade da amplitude em todos os 256 valores
    (medido contra `audioop` a 17/10): o Whisper recebia áudio deformado e devolvia lixo.
    """
    result = bytearray(len(ulaw_bytes) * 2)
    for i, byte in enumerate(ulaw_bytes):
        byte = (~byte) & 0xFF
        sample = (((byte & 0x0F) << 3) + _BIAS << ((byte >> 4) & 0x07)) - _BIAS
        struct.pack_into("<h", result, i * 2, -sample if byte & 0x80 else sample)
    return bytes(result)


def tem_fala(pcmu_bytes: bytes) -> bool:
    """Energia do bloco acima do limiar. Silêncio e ruído de linha não vão ao Whisper."""
    pcm = _ulaw2lin(pcmu_bytes)
    n = len(pcm) // 2
    if not n:
        return False
    soma = sum(v * v for (v,) in struct.iter_unpack("<h", pcm))
    return (soma / n) ** 0.5 >= LIMIAR_RMS


def e_alucinacao(texto: str) -> bool:
    t = texto.lower()
    return any(f in t for f in _ALUCINACOES)


def _to_wav(pcmu_bytes: bytes) -> bytes:
    pcm = _ulaw2lin(pcmu_bytes)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(pcm)
    return buf.getvalue()


async def transcribe(pcmu_bytes: bytes) -> str:
    if not tem_fala(pcmu_bytes):
        return ""
    wav_bytes = _to_wav(pcmu_bytes)
    audio_file = io.BytesIO(wav_bytes)
    audio_file.name = "audio.wav"
    response = await _client.audio.transcriptions.create(
        model="whisper-1",
        file=audio_file,
        language="pt",
        prompt="Chamada telefónica em português de Portugal para uma agência imobiliária.",
    )
    texto = response.text.strip()
    return "" if e_alucinacao(texto) else texto
