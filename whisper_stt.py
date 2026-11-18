"""Local speech-to-text using faster-whisper (CPU, free).

The model is loaded lazily on the first transcription call so the server
starts up quickly. Subsequent calls reuse the loaded model.
"""
from __future__ import annotations

import logging
import os
import tempfile

import config

log = logging.getLogger("jarvis.whisper")

try:
    from faster_whisper import WhisperModel as _WhisperModel
    _AVAILABLE = True
except ImportError:
    _WhisperModel = None  # type: ignore[assignment]
    _AVAILABLE = False

_model: "_WhisperModel | None" = None


def available() -> bool:
    return _AVAILABLE


def _get_model() -> "_WhisperModel":
    global _model
    if _model is None:
        size = config.WHISPER_MODEL
        log.info("Loading Whisper model '%s' (first call, may take a moment)…", size)
        _model = _WhisperModel(size, device="cpu", compute_type="int8")
        log.info("Whisper model '%s' ready.", size)
    return _model


def transcribe(audio_bytes: bytes, lang_hint: str = "en", suffix: str = ".webm") -> str:
    """Transcribe raw audio bytes to text.

    audio_bytes: any format that ffmpeg / PyAV can decode (WebM/Opus, WAV, MP4…).
    lang_hint:   "nl" or "en" – passed to Whisper to bias the decoder.
    suffix:      file extension of the upload (".webm" from Chrome, ".mp4" from iPhone Safari).
    Returns the recognised text, or "" on failure.
    """
    model = _get_model()

    # Write to a temp file; faster-whisper needs a file path.
    if suffix not in (".webm", ".mp4", ".m4a", ".ogg", ".wav"):
        suffix = ".webm"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as fh:
        fh.write(audio_bytes)
        tmp = fh.name

    try:
        language = lang_hint if lang_hint in ("nl", "en") else None
        segments, _info = model.transcribe(
            tmp,
            language=language,
            beam_size=5,
            vad_filter=False,         # browser PTT sends only when mic is held; no VAD needed
        )
        return " ".join(s.text for s in segments).strip()
    except Exception as exc:
        log.error("Whisper transcription failed: %s", exc)
        return ""
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass
