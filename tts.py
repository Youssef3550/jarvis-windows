"""Speech: turn JARVIS's text into audio.

English uses a local Coqui TTS voice (free, offline, no API key). Dutch uses Microsoft's
free neural voices via edge-tts, because the Coqui VCTK voices only speak English. If
Coqui is not installed or fails, English falls back to edge-tts too, and if that fails
the browser's own voice is the last resort.
"""
from __future__ import annotations

import asyncio
import importlib.util
import io
import logging
import os
import re
import threading
import wave

import config

log = logging.getLogger("jarvis.tts")

try:
    import edge_tts
except ImportError:          # the browser's own voice is the fallback
    edge_tts = None


class CoquiVoice:
    """A Coqui TTS model, loaded once and shared. The model is not thread-safe,
    so every call goes through one lock."""

    def __init__(self, model_name: str, speaker: str = "", speaker_wav: str = "") -> None:
        self.model_name = model_name
        self.speaker = speaker
        self.speaker_wav = speaker_wav
        self._model = None
        self._lock = threading.Lock()
        self.error: str | None = None   # set once loading failed; we then stop trying

    @staticmethod
    def installed() -> bool:
        return importlib.util.find_spec("TTS") is not None

    def _load(self):
        if self._model is not None or self.error:
            return self._model
        try:
            # The VCTK voice turns text into phonemes with espeak-ng.exe, which the
            # Windows installer does not put on PATH. Coqui looks for it on import.
            if config.ESPEAK_DIR and os.path.isdir(config.ESPEAK_DIR) \
                    and config.ESPEAK_DIR not in os.environ.get("PATH", ""):
                os.environ["PATH"] = config.ESPEAK_DIR + os.pathsep + os.environ.get("PATH", "")
            from TTS.api import TTS   # slow import (torch), so only when needed

            log.info("loading Coqui voice %s (first time downloads it)…", self.model_name)
            model = TTS(self.model_name, progress_bar=False).to("cpu")
            speakers = [s.strip() for s in (model.speakers or []) if s.strip()]
            if speakers and not self.speaker_wav and self.speaker not in speakers:
                log.warning("Coqui speaker %r not in this model; using %s",
                            self.speaker, speakers[0])
                self.speaker = speakers[0]
            self._model = model
            log.info("Coqui voice ready (%s, speaker %s)", self.model_name,
                     self.speaker_wav or self.speaker or "default")
        except Exception as exc:
            self.error = str(exc)
            log.warning("Coqui TTS unavailable (%s); using edge-tts instead", exc)
        return self._model

    def warm_up(self) -> bool:
        with self._lock:
            return self._load() is not None

    def wav(self, text: str) -> bytes:
        """WAV bytes for text. Raises if the model can't be loaded or synthesis fails."""
        with self._lock:
            model = self._load()
            if model is None:
                raise RuntimeError(self.error or "Coqui model not loaded")
            kwargs: dict = {}
            if self.speaker_wav:
                # ── Voice cloning hook ──────────────────────────────────────────
                # With a cloning model such as XTTS v2
                #   COQUI_MODEL=tts_models/multilingual/multi-dataset/xtts_v2
                # Coqui copies the voice in COQUI_SPEAKER_WAV (a clean 6-30 s WAV).
                # XTTS also needs a language, and it can speak Dutch ("nl"), so with
                # cloning the Dutch edge-tts route could later be dropped as well.
                # XTTS is under the Coqui Public Model License (non-commercial); accept
                # it by setting COQUI_TOS_AGREED=1 in .env, otherwise the download stops
                # to ask on the console. Expect it to be slow on CPU (several seconds
                # per sentence) — a CUDA GPU (.to("cuda")) makes it real-time.
                kwargs["speaker_wav"] = self.speaker_wav
                kwargs["language"] = "en"
            elif self.speaker:
                kwargs["speaker"] = self.speaker
            samples = model.tts(text, **kwargs)
            rate = model.synthesizer.output_sample_rate
        return to_wav(samples, rate)


def to_wav(samples, rate: int) -> bytes:
    """Float samples in [-1, 1] → 16-bit mono WAV bytes."""
    import numpy as np

    pcm = (np.clip(np.asarray(samples, dtype=np.float32), -1.0, 1.0) * 32767).astype("<i2")
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(int(rate))
        w.writeframes(pcm.tobytes())
    return buf.getvalue()


coqui: CoquiVoice | None = None
if config.TTS_ENGINE == "coqui" and CoquiVoice.installed():
    coqui = CoquiVoice(config.COQUI_MODEL, config.COQUI_SPEAKER, config.COQUI_SPEAKER_WAV)


def warm_up() -> None:
    """Load the Coqui model ahead of the first sentence (runs in a thread at startup)."""
    if coqui is not None:
        coqui.warm_up()

_DUTCH_WORDS = set("""de het een en is niet ik je jij u uw we wij zijn was dat die dit
voor met op aan te van naar ook maar nog wel al er hier daar wat wie hoe waarom
heb hebt heeft kan kunt wil wilt moet zal zou graag goed dank bedankt ja nee
meneer even nu dan omdat geen mijn jouw onze om bij zo over tot uit""".split())
_ENGLISH_WORDS = set("""the a an and is not i you we are was that this for with on at
to of from also but still here there what who how why have has can will would
should please good thanks yes no sir just now then because my your our it be""".split())


def detect_language(text: str, default: str = "en") -> str:
    words = re.findall(r"[a-zA-Zàâäéèêëïîôöüûç']+", text.lower())
    nl = sum(w in _DUTCH_WORDS for w in words)
    en = sum(w in _ENGLISH_WORDS for w in words)
    if nl == en:
        return default
    return "nl" if nl > en else "en"


def clean_for_speech(text: str) -> str:
    text = re.sub(r"```.*?```", " ", text, flags=re.S)
    text = re.sub(r"`([^`]*)`", r"\1", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)      # [label](url)
    text = re.sub(r"https?://\S+", "the link", text)
    text = re.sub(r"[*_#>|~]+", "", text)
    text = re.sub(r"^\s*[-•]\s+", "", text, flags=re.M)
    return re.sub(r"\s+", " ", text).strip()


class SentenceSplitter:
    """Collects streamed text and hands back whole sentences to speak early."""

    _END = re.compile(r"(.+?[.!?…:;])(\s+|$)", re.S)

    def __init__(self) -> None:
        self.buf = ""

    def feed(self, text: str) -> list[str]:
        self.buf += text
        out: list[str] = []
        while True:
            if "\n" in self.buf:
                head, _, rest = self.buf.partition("\n")
                if head.strip():
                    out.append(head.strip())
                self.buf = rest
                continue
            m = self._END.match(self.buf)
            # need a following space to be sure the sentence really ended
            if m and m.group(2) and len(m.group(1)) >= 12:
                out.append(m.group(1).strip())
                self.buf = self.buf[m.end():]
                continue
            break
        return out

    def flush(self) -> list[str]:
        rest, self.buf = self.buf.strip(), ""
        return [rest] if rest else []


async def synthesize(text: str, lang: str) -> tuple[bytes, str] | None:
    """(audio bytes, MIME type), or None if no voice engine worked (browser voice then)."""
    if not text.strip():
        return None
    if lang != "nl" and coqui is not None and not coqui.error:
        try:
            return await asyncio.to_thread(coqui.wav, text), "audio/wav"
        except Exception as exc:
            log.warning("Coqui TTS failed (%s); trying edge-tts", exc)
    audio = await _edge_mp3(text, lang)
    return (audio, "audio/mpeg") if audio else None


async def _edge_mp3(text: str, lang: str) -> bytes | None:
    """MP3 bytes from edge-tts, or None if the voice service can't be reached."""
    if edge_tts is None:
        return None
    voice = config.VOICE_NL if lang == "nl" else config.VOICE_EN
    try:
        com = edge_tts.Communicate(text, voice, rate=config.VOICE_RATE)
        audio = bytearray()
        async for chunk in com.stream():
            if chunk.get("type") == "audio":
                audio.extend(chunk["data"])
        return bytes(audio) or None
    except Exception as exc:
        log.warning("edge-tts failed (%s); browser voice will be used", exc)
        return None
