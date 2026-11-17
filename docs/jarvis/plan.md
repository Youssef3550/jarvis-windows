# Plan: Coqui TTS as Hassan's voice

Spec: `docs/jarvis/spec-2026-11-18-jarvis-windows.md`.
(The previous plan for the Whisper upgrade is finished; it is described in `WHISPER_UPGRADE.md`.)

Findings that shape this plan:
- Current voice is **edge-tts** (server side, `tts.py`, MP3 pushed to the browser in
  `say` WebSocket messages). Browser `SpeechSynthesis` is only the fallback in `frontend/app.js`.
- The venv runs Python 3.12. The original `TTS` package stops at Python 3.11, so we use the
  maintained fork **`coqui-tts`** (same import: `from TTS.api import TTS`).
- Hassan also answers in Dutch. VCTK is English-only, so Dutch keeps using edge-tts.

Plan review against the spec: steps 1–7 and all acceptance criteria are covered.
Deliberate choice: the server keeps synthesizing each sentence as soon as it is ready and pushes
the audio (smooth, no gaps, minimal change); the frontend calls `/tts` whenever a sentence
arrives without audio, and the browser voice is only the very last fallback. Out of scope and
not planned: replacing the Dutch voice, a GPU setup, actually cloning a voice.

## Phase 1 – Install and try Coqui

- [x] Install into the venv: `.venv\Scripts\python.exe -m pip install coqui-tts`
- [x] Smoke test in a scratch script: load `tts_models/en/vctk/vits`, synthesize one sentence
      with speakers `p273` and `p330` to WAV, check it runs on CPU and time it
- [x] If phonemizer / espeak is missing, resolve it (or pick a model that does not need it)

## Phase 2 – Server

- [x] `config.py`: add `TTS_ENGINE` (`coqui` | `edge`, default `coqui`), `COQUI_MODEL`
      (default `tts_models/en/vctk/vits`), `COQUI_SPEAKER` (default `p273`),
      `COQUI_SPEAKER_WAV` (empty; voice cloning, later)
- [x] `tts.py`: add a Coqui engine — lazy model load, a lock (model not thread-safe),
      synthesis in a worker thread, WAV bytes out; `warm_up()` to load at startup
- [x] `tts.py`: `synthesize(text, lang)` returns `(audio_bytes, mime)`; English → Coqui,
      Dutch or Coqui failure → edge-tts (as before), else `None` (browser voice)
- [x] `tts.py`: voice-cloning hook — code path + comments for XTTS v2 with `COQUI_SPEAKER_WAV`
- [x] `server.py`: pass `mime` in `say` messages; preload Coqui in the background at startup
- [x] `server.py`: add `POST /tts` (JSON `{text, lang}`) → audio response (`audio/wav` or `audio/mpeg`)
- [x] `requirements.txt`: add `coqui-tts`

## Phase 3 – Frontend

- [x] `app.js`: play pushed audio using its `mime` (WAV, not hard-coded MP3)
- [x] `app.js`: when a `say` has no audio, fetch `POST /tts` first; browser voice only as last resort
- [x] `app.js`: keep queue/interrupt behaviour (stop clears queue, aborts in-flight fetch)

## Phase 4 – Tests and checks

- [x] `tests/test_tts.py`: unit tests for engine selection / fallback with a fake Coqui model
      (no model download); run `.venv\Scripts\python.exe -m pytest tests -q`
- [x] Run the real server, `POST /tts` with English and Dutch text, check status + content type
      + WAV header (the WebSocket `say` path calls the same `tts.synthesize`)
- [x] JS check: Node is not installed, so the page was loaded in headless Edge instead (no console errors)

## Phase 5 – Docs

- [x] `.env.example` + `README.md`: new voice settings
- [x] `docs/jarvis/SUMMARY.md`: what was built, how to run (PowerShell), open items
