# Summary: Hassan on the phone via Tailscale (2026-11-18)

Spec: `docs/jarvis/spec-2026-11-18-jarvis-windows.md` · Plan and progress: `docs/jarvis/plan.md`
(The previous Whisper work is summarised in `docs/jarvis/WHISPER_UPGRADE.md` and git history.)

## What was built

**Page works from `https://<laptop>.<tailnet>.ts.net`** (`frontend/app.js`)
- WebSocket uses `wss://` when the page is https, `ws://` on `http://localhost` (this was the one
  thing that would have broken: `ws://` from an https page is blocked).
- Push-to-talk uploads the format the browser really records: webm on Chrome/Android,
  **mp4 on iPhone Safari** (was always labelled webm). `whisper_stt.py` / `server.py` use the
  matching file extension. Tested: an AAC/mp4 clip transcribed correctly.
- Falls back to the browser's speech recognition if MediaRecorder is missing; mic error texts
  no longer assume desktop Chrome and explain the https requirement.
- All other URLs were already relative. There was no CORS or host check to break.

**Host/origin guard** (`hostguard.py`, wired into `server.py`; `ALLOWED_HOSTS` in `config.py`, `.env.example`)
- Hassan answers only when the `Host` (and `Origin`, if sent) is localhost / 127.0.0.1 / ::1,
  this laptop's own Tailscale name (read from `tailscale status --json`, re-checked at most every
  30 s so it works even if Tailscale is set up after Hassan started), or a name in `ALLOWED_HOSTS`.
- Blocks other websites in your browser, DNS-rebinding sites and other tailnets from driving
  Hassan. `ALLOWED_HOSTS=*` switches it off.
- Tests: `tests/test_hosts.py` (6 tests).

**Start-up** (`phone_access.ps1`, `start.bat`)
- `phone_access.ps1 on|off|status`: runs `tailscale serve --bg 8340` and prints the phone
  address / `tailscale serve reset` / serve + funnel status. Skips quietly if Tailscale is not
  installed or not signed in, and gives up after 20 s (with the admin-console link) if HTTPS
  is not enabled yet, so it never blocks Hassan from starting.
- `start.bat` calls `phone_access.ps1 on` before starting the server.

**Docs**: `docs/jarvis/PHONE_ACCESS.md` (setup, finding the address, turning it off, security notes).

Not changed: the server still binds to `127.0.0.1` only; no `0.0.0.0`, no `tailscale funnel`.

## How to run

```powershell
cd "C:\Users\youss\OneDrive\Desktop\jarvis-windows\jarvis-windows"
.\start.bat                                                         # Hassan + phone access (if Tailscale is set up)
powershell -ExecutionPolicy Bypass -File phone_access.ps1 status    # what is published
powershell -ExecutionPolicy Bypass -File phone_access.ps1 off       # stop phone access
.venv\Scripts\python -m unittest discover -s tests -v               # tests (16 pass)
```

## Checks done

- Unit tests: 16/16 pass.
- A second instance on port 8341 (fake Claude, so no real brain was used) with the new code:
  page loads in Chrome with no console errors, typed message gets a reply with voice audio,
  WebSocket with a foreign Origin refused, foreign Host/Origin get 403, mp4 Whisper upload works.
- `netstat`: only `127.0.0.1:8340` / `127.0.0.1:8341` listening.
- The Hassan already running on 8340 was **not restarted** (it is running the old code until you restart it).

## Phone access status (follow-up session, 2026-11-18)

- Tailscale 1.104.7 installed and signed in; iPhone on the same tailnet; HTTPS certificates on.
- `tailscale serve --bg 8340` applied. Phone address: **https://<laptop>.<tailnet>.ts.net/ (run phone_access.ps1 status to see yours)**
- `tailscale serve status` / `tailscale funnel status`: proxy to http://127.0.0.1:8340, **tailnet only** (no funnel).
- Checked from the laptop: the https address returns the Hassan page (200); the server still listens on 127.0.0.1:8340 only.
- Fixed `phone_access.ps1`: the `Phone: https://...` line was never printed (PowerShell leaves
  `ExitCode` empty unless the process handle is cached).

## Left open (needs you)

1. **Restart Hassan** (close the Hassan window, double-click `start.bat`). The running copy was
   started before the phone-access code, so the host/origin guard is not active yet.
2. **Phone test**: on the iPhone (Tailscale app on), open the address above in Safari, allow the
   microphone, hold the orb to talk (push-to-talk), and check you hear the reply.

## Notes / choices

- One PowerShell helper instead of separate on/off batch files; `start.bat` stays a .bat.
- Hands-free mode on iPhone relies on Safari's own speech recognition, which is unreliable;
  push-to-talk (Whisper) is the recommended way on the phone.
- Pre-existing, not fixed (out of scope): switching language or hands-free while recording with
  push-to-talk calls `rec.abort()` on the Web Speech object, which is unset in Whisper mode.
