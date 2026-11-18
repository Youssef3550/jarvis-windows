# Plan: Hassan on the phone via Tailscale (spec 2026-11-18)

Goal: open Hassan from the phone over HTTPS on the user's own tailnet (`tailscale serve`,
never `funnel`). The server stays bound to 127.0.0.1:8340.

## Phase 1: Make the page work from https://<machine>.<tailnet>.ts.net
- [x] `frontend/app.js`: WebSocket URL follows the page protocol (`wss://` on https, `ws://` on http)
- [x] `frontend/app.js`: MediaRecorder upload uses the real container type (iOS Safari records `audio/mp4`, not webm); fall back to Web Speech API if MediaRecorder is missing
- [x] `frontend/app.js`: mic error text not Chrome-only (phone browsers)
- [x] `whisper_stt.py` + `server.py`: temp file suffix taken from the uploaded file name (`.webm` / `.mp4` / `.ogg` / `.wav`)
- [x] Check: no other hard-coded `localhost` URLs in the frontend (all `fetch` calls are relative already); no CORS/host middleware to break
- [x] `config.py`: `ALLOWED_HOSTS` setting (.env, comma-separated) plus auto-detection of this machine's tailnet name via `tailscale status --json`
- [x] `server.py`: host/origin guard: reject requests whose `Host` or `Origin` is not localhost / 127.0.0.1 / the tailnet name / `ALLOWED_HOSTS` (blocks DNS rebinding and other websites driving Hassan through the browser). `ALLOWED_HOSTS=*` turns it off
- [x] `.env.example`: document `ALLOWED_HOSTS`
- [x] Tests: `tests/test_hosts.py` (guard allows localhost + tailnet origin, rejects foreign Host/Origin, WebSocket too); run with `.venv\Scripts\python -m unittest discover -s tests -v` (16/16 pass)

## Phase 2: Tailscale
- [x] Check install: `tailscale version`, `C:\Program Files\Tailscale\tailscale.exe` → not installed (2026-11-18; re-checked in the follow-up session: still not installed. Tests 16/16 pass, server still 127.0.0.1:8340 only)
- [x] If missing: ask the user to install (`winget install Tailscale.Tailscale`), sign in, install the phone app with the same account, and enable HTTPS in the admin console (DNS page). Pause until done (user did it: Tailscale 1.104.7, iPhone online, HTTPS on)
- [x] Run `tailscale serve --bg 8340`; report the https address → https://<laptop>.<tailnet>.ts.net/ (run phone_access.ps1 status to see yours)
- [x] Check `tailscale serve status` (HTTPS → http://127.0.0.1:8340) and `tailscale funnel status` (off: "tailnet only")

## Phase 3: Start-up
- [x] `start.bat`: if Tailscale is installed, run `tailscale serve --bg 8340` before starting the server and print the phone address; skip quietly if not installed
- [x] Helper script `phone_access.ps1 on|off|status` (one script instead of two .bat files; `off` = `tailscale serve reset`). Fixed: the `Phone:` line never printed (empty ExitCode without a cached process handle)

## Phase 4: Docs, checks, commit
- [x] `docs/jarvis/PHONE_ACCESS.md`: setup steps, finding the address, turning it off, security notes
- [x] Acceptance: `http://localhost:8340` page, `/api/status`, WebSocket still work (tested on a second instance, port 8341, with the fake Claude: page, chat reply with voice, mp4 Whisper upload; foreign Host/Origin → 403)
- [x] Acceptance: `netstat -ano | findstr :8340` shows only `127.0.0.1:8340` listening
- [ ] Acceptance (user): phone opens the https address, mic prompt appears, spoken question gets a spoken reply
- [x] `docs/jarvis/SUMMARY.md`
- [x] Commit (not `.env`)
