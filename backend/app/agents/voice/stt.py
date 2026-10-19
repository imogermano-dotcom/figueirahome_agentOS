import asyncio
import io
import logging
import struct
import wave

from openai import AsyncOpenAI

from app.config import settings

logger = logging.getLogger(__name__)
_client = AsyncOpenAI(api_key=settings.openai_api_key)
_comparacoes: set[asyncio.Task] = set()  # referência forte: uma tarefa solta pode ser apanhada pelo GC a meio

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
    return any(f in t for f in _ALUCINACOES) or _eco_do_prompt(t)


def _eco_do_prompt(t: str) -> bool:
    """Com áudio curto ou fraco, os modelos devolvem o nosso `prompt` (18/10: o gpt-4o-transcribe respondeu
    «Chamada Telefónica»). Só o INÍCIO do prompt conta: o vocabulário («Figueira da Foz») é resposta legítima."""
    sem_pontuacao = "".join(c for c in t if c.isalnum() or c.isspace()).strip()
    inicio = "".join(c for c in _PROMPT.lower() if c.isalnum() or c.isspace())
    return len(sem_pontuacao) >= 10 and inicio.startswith(sem_pontuacao)


_PICO_ALVO = 22_000   # ~-3,5 dBFS
_GANHO_MAX = 4.0      # +12 dB: levanta voz fraca sem transformar ruído em fala
_PICO_MIN = 300       # abaixo disto não há sinal a normalizar

_PROMPT = ("Chamada telefónica em português de Portugal para uma agência imobiliária na Figueira da Foz. "
           "Vocabulário: T1, T2, T3, moradia, apartamento, comprar, arrendar, Figueira da Foz, Buarcos, Quiaios, "
           "Tavarede, Marinha das Ondas, euros, mil euros, número de telefone, nove dígitos.")


def _normalizar(pcm: bytes) -> bytes:
    """Sobe o volume até o pico ficar em ~22 000 (no máximo +12 dB). O áudio de telefone vem fraco e o STT falha."""
    amostras = [v for (v,) in struct.iter_unpack("<h", pcm)]
    pico = max((abs(v) for v in amostras), default=0)
    if pico < _PICO_MIN:
        return pcm
    ganho = min(_GANHO_MAX, _PICO_ALVO / pico)
    if ganho <= 1.0:
        return pcm
    return struct.pack(f"<{len(amostras)}h", *(max(-32768, min(32767, int(v * ganho))) for v in amostras))


_TAXA_REFORCO = 16_000
_MARGEM_REFORCO_MS = 300


def _para_16k(pcm: bytes) -> bytes:
    """8 kHz -> 16 kHz por interpolação linear (cada amostra + a média com a seguinte)."""
    n = len(pcm) // 2
    v = struct.unpack(f"<{n}h", pcm[: n * 2])
    saida = []
    for i, a in enumerate(v):
        saida.append(a)
        saida.append((a + (v[i + 1] if i + 1 < n else a)) // 2)
    return struct.pack(f"<{len(saida)}h", *saida)


def _to_wav(pcmu_bytes: bytes, reforcado: bool = False) -> bytes:
    """`reforcado`: 16 kHz com 300 ms de silêncio em cada ponta, para a 2.ª tentativa quando a 1.ª vem vazia.
    As respostas curtas («sim», um nome) chegavam vazias: pouca fala, e o modelo desiste."""
    pcm = _normalizar(_ulaw2lin(pcmu_bytes))
    taxa = SAMPLE_RATE
    if reforcado:
        taxa = _TAXA_REFORCO
        margem = bytes(_MARGEM_REFORCO_MS * taxa // 1000 * 2)
        pcm = margem + _para_16k(pcm) + margem
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(taxa)
        wf.writeframes(pcm)
    return buf.getvalue()


async def _pedir(modelo: str, wav_bytes: bytes, com_prompt: bool = True) -> str:
    audio_file = io.BytesIO(wav_bytes)
    audio_file.name = "audio.wav"
    extra = {"prompt": _PROMPT} if com_prompt else {}
    response = await _client.audio.transcriptions.create(model=modelo, file=audio_file, language="pt", **extra)
    return response.text.strip()


async def _comparar(modelos: list[str], wav_bytes: bytes, principal: str, texto: str) -> None:
    """Mesma frase noutros modelos, só para o log. Nunca levanta: uma API diferente num modelo novo não pode
    estragar a chamada."""
    resultados = await asyncio.gather(*(_pedir(m, wav_bytes) for m in modelos), return_exceptions=True)
    partes = [f"{principal}: {texto!r}"] + [
        f"{m}: {('ERRO ' + type(r).__name__ + ' ' + str(r)[:80]) if isinstance(r, Exception) else repr(r)}"
        for m, r in zip(modelos, resultados)
    ]
    logger.info("STT comparar | %s", " | ".join(partes))


async def transcribe(pcmu_bytes: bytes) -> str:
    if not tem_fala(pcmu_bytes):
        return ""
    wav_bytes = _to_wav(pcmu_bytes)
    texto = await _pedir(settings.stt_model, wav_bytes)
    if not texto:  # resposta curta: 2.ª tentativa com 16 kHz, margem de silêncio e sem prompt
        texto = await _pedir(settings.stt_model, _to_wav(pcmu_bytes, reforcado=True), com_prompt=False)
        logger.info("STT 2.ª tentativa (16 kHz, margem, sem prompt): %r", texto)
    alucinacao = e_alucinacao(texto)
    if not texto or alucinacao:  # o log da chamada só mostra o que sobra depois do filtro
        logger.info("STT bruto %r (%s)", texto, "descartado como alucinação" if alucinacao else "vazio")
    extras = [m.strip() for m in settings.stt_comparar.split(",") if m.strip() and m.strip() != settings.stt_model]
    if extras:
        tarefa = asyncio.create_task(_comparar(extras, wav_bytes, settings.stt_model, texto))
        _comparacoes.add(tarefa)
        tarefa.add_done_callback(_comparacoes.discard)
    return "" if alucinacao else texto
