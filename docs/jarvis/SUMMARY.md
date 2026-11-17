# Summary: Coqui TTS as Hassan's voice

Spec: `spec-2026-11-18-jarvis-windows.md` · Plan (all boxes ticked): `plan.md`.
(The earlier Whisper speech-recognition work is described in `WHISPER_UPGRADE.md`.)

## What was built

Hassan's English voice is now **Coqui TTS**, running locally on the CPU: free, offline,
no API key. Model `tts_models/en/vctk/vits`, speaker **p273** (British male; `p330` is the
other suggested one, switch with `COQUI_SPEAKER`).

How speech flows now:

1. The server cuts Hassan's answer into sentences (unchanged) and synthesizes each one as
   soon as it is ready: **English → Coqui (WAV)**, **Dutch → edge-tts (MP3)** as before.
2. The audio is pushed to the browser in the existing `say` WebSocket message, now with a
   `mime` field, so playback stays gap-free (the next sentence is made while one plays).
3. If a sentence arrives without audio, the browser asks the new **`POST /tts`** endpoint
   (prefetched immediately). The browser's own `SpeechSynthesis` voice is only the very last
   fallback.

| File | Change |
|------|--------|
| `tts.py` | `CoquiVoice` (lazy load, lock, WAV out), engine choice + fallbacks, voice-cloning hook |
| `server.py` | `POST /tts` (JSON `{text, lang}` → `audio/wav` or `audio/mpeg`), `GET /api/tts_status`, model warm-up at startup, `mime` in `say` |
| `frontend/app.js` | Plays WAV or MP3 by `mime`; `/tts` fetch for sentences without audio; interrupt cancels pending fetches |
| `config.py` | `TTS_ENGINE`, `COQUI_MODEL`, `COQUI_SPEAKER`, `COQUI_SPEAKER_WAV`, `ESPEAK_DIR` |
| `requirements.txt` | `coqui-tts[codec]`, `torch`, `torchaudio`, `six` |
| `tests/test_tts.py` | 10 unit tests (engine choice, fallbacks, cloning args, WAV format), fake model |
| `README.md`, `.env.example` | New voice settings and setup |

**Voice cloning** is prepared, not switched on: set `COQUI_MODEL=tts_models/multilingual/multi-dataset/xtts_v2`,
`COQUI_SPEAKER_WAV=<path to a clean 6–30 s WAV>` and `COQUI_TOS_AGREED=1` in `.env`. The code
path in `CoquiVoice.wav()` (comment "Voice cloning hook") already passes `speaker_wav` and
`language`. XTTS can also speak Dutch, so the edge-tts route could later be dropped too.

## How to run (PowerShell, from the project folder)

Already done on this laptop: packages installed in `.venv`, eSpeak NG installed with winget,
voice model downloaded. On another machine, once:

```powershell
.venv\Scripts\python.exe -m pip install -r requirements.txt
winget install -e --id eSpeak-NG.eSpeak-NG
```

Then start Hassan as always:

```powershell
.\start.bat
```

The log shows `Coqui voice ready (tts_models/en/vctk/vits, speaker p273)` a few seconds
after start. Check anytime: `http://localhost:8340/api/tts_status`. Try the voice directly:

```powershell
Invoke-WebRequest -Method Post -Uri http://localhost:8340/tts -ContentType 'application/json' `
  -Body '{"text":"Good evening, sir.","lang":"en"}' -OutFile "$env:TEMP\hassan.wav"
Start-Process "$env:TEMP\hassan.wav"
```

Run the tests: `.venv\Scripts\python.exe -m unittest discover -s tests -v`

## Verified

- 10/10 unit tests pass.
- Real server: `/tts` English → 200 `audio/wav` (22 050 Hz, 5.2 s of speech made in 3.9 s on
  CPU); Dutch → 200 `audio/mpeg` via edge-tts; empty text / bad JSON → 400.
- Live WebSocket: a session announcement arrived as a `say` message with Coqui WAV audio.
- Page loads in headless Edge without console errors (Node isn't installed for a syntax check).
- Not verified by ear: I can't listen, so whether p273 or p330 sounds best is for you to judge.

## Decisions and deviations from the spec

- **The old voice was edge-tts, not the browser voice.** The spec guessed SpeechSynthesis; that
  was only the fallback. Both are now behind Coqui for English.
- **`coqui-tts` instead of `pip install TTS`.** The original `TTS` package doesn't install on
  Python 3.12 (the venv's version). `coqui-tts` is the maintained fork with the same API and
  models. It needed `torch`, `torchcodec` (`[codec]` extra) and `six` added by hand.
- **eSpeak NG** (system program, installed with winget) is required by the VCTK model.
  `tts.py` adds `C:\Program Files\eSpeak NG` to PATH itself, so nothing else is needed.
- **Dutch stays on edge-tts**, because the VCTK voices only speak English and the spec
  requires Hassan to keep working as before (he answers in Dutch too).
- **Audio is still pushed over the WebSocket** rather than each sentence being fetched by the
  browser: fewer changes and no gaps. `/tts` exists and the frontend uses it whenever a
  sentence comes without audio.

## Open items

- **Disk/startup cost**: PyTorch + Coqui add roughly a gigabyte to `.venv` (estimate, PyTorch
  is most of it; not measured because `du` on the OneDrive folder was too slow), plus the
  ~150 MB voice model. Loading the model takes a few seconds in the background at start
  (2 s on the second run here, 15 s the first time); sentences spoken before that wait for it.
- **The `.venv` lives in OneDrive**: syncing a gigabyte of packages is slow and pointless.
  Consider excluding `.venv` from OneDrive, or moving the project out of the synced Desktop.
- **`start.bat` does not install eSpeak NG** on a fresh machine. Without it Hassan still
  works, just with the Microsoft voice for English (`/api/tts_status` shows why).
- **Speed on slower laptops**: VITS ran faster than real time here. If it ever lags, set
  `TTS_ENGINE=edge` in `.env`.
- The project folder is not a git repository, so there is no commit for this change.
