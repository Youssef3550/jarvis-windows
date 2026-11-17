# Whisper upgrade – speech recognition

## What changed

The browser's built-in Web Speech API (Chrome only, cloud-based) has been replaced with
**OpenAI Whisper running locally** via the `faster-whisper` library.

| | Before | After |
|---|---|---|
| Engine | Chrome Web Speech API | faster-whisper (local, free) |
| Processing | Google's servers | Your laptop CPU |
| Accuracy (dialect/slang) | Weak | Much better |
| Requires Chrome | Yes (Speech API) | No (MediaRecorder works in any browser) |
| Hands-free mode | Web Speech API (unchanged) | Still Web Speech API (has built-in VAD) |
| PTT / click-to-talk | Web Speech API | Whisper via `/api/transcribe` |

## How it works

1. When you click the orb / press Space, the browser starts recording via `MediaRecorder`.
2. When you stop recording, the audio blob (WebM/Opus) is `POST`ed to `/api/transcribe`.
3. The Python server writes it to a temp file and runs faster-whisper on it.
4. The transcript comes back as JSON `{"text": "..."}` and is forwarded to Hassan.

For **hands-free mode** the Web Speech API is still used because it has built-in
voice-activity detection (VAD) that stops recording automatically on silence.
Whisper is used only in push-to-talk mode.

## Installation

Install the new Python dependencies:

```powershell
# From the jarvis-windows folder, with the venv active:
.venv\Scripts\activate
pip install faster-whisper av
```

`faster-whisper` will download the Whisper model on first use
(the default `base` model is ~74 MB).

**ffmpeg / PyAV:** `faster-whisper` uses PyAV (`av`) to decode WebM/Opus audio directly;
no separate ffmpeg installation is needed as long as `av` is installed.

## Configuration

Add to your `.env` file (optional):

```
# Whisper model size: tiny, base, small, medium, large-v3
# Larger = more accurate but slower and uses more RAM.
# "base" is a good default for everyday use.
WHISPER_MODEL=base
```

| Model | VRAM / RAM | Speed (CPU) | Notes |
|-------|-----------|-------------|-------|
| tiny | ~1 GB | Very fast | Noticeable errors |
| base | ~1 GB | Fast | Good default |
| small | ~2 GB | Medium | Better accuracy |
| medium | ~5 GB | Slow | High accuracy |
| large-v3 | ~10 GB | Very slow | Best accuracy |

For mixed Dutch/Darija conversations, `small` or `medium` will give noticeably
better results than `base`.

## API endpoints added

| Endpoint | Description |
|----------|-------------|
| `GET /api/whisper_status` | Returns `{"available": true/false, "model": "base"}` |
| `POST /api/transcribe` | Accepts `multipart/form-data` with `audio` (blob) + `lang` (`en`/`nl`). Returns `{"text": "..."}` |

## Fallback behaviour

- If `faster-whisper` is not installed, `/api/whisper_status` returns `{"available": false}`.
- The frontend detects this on startup and falls back to the Web Speech API automatically,
  so the app keeps working without any manual intervention.
