import io
import struct
import wave

from openai import AsyncOpenAI

from app.config import settings

_client = AsyncOpenAI(api_key=settings.openai_api_key)

SAMPLE_RATE = 8000


def _ulaw2lin(ulaw_bytes: bytes) -> bytes:
    """Decode µ-law (PCMU) bytes to 16-bit signed linear PCM."""
    result = bytearray(len(ulaw_bytes) * 2)
    for i, byte in enumerate(ulaw_bytes):
        byte = (~byte) & 0xFF
        sign = byte & 0x80
        exp = (byte >> 4) & 0x07
        mantissa = byte & 0x0F
        sample = (((mantissa << 1) | 1) << (exp + 2)) - 33
        if sign:
            sample = -sample
        sample = max(-32768, min(32767, sample))
        struct.pack_into("<h", result, i * 2, sample)
    return bytes(result)


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
    wav_bytes = _to_wav(pcmu_bytes)
    audio_file = io.BytesIO(wav_bytes)
    audio_file.name = "audio.wav"
    response = await _client.audio.transcriptions.create(
        model="whisper-1",
        file=audio_file,
        language="pt",
    )
    return response.text.strip()
