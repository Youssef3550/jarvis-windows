# Goal
Make Hassan (the FastAPI server in server.py, port 8340) usable from the user's phone browser, including microphone and voice, from anywhere, using Tailscale (free). Only the user's own devices may reach it.

# Design (keep it secure)
- Hassan can control the laptop (open apps, start builds, clipboard), so it must NOT be exposed to the LAN or public internet.
- Keep the server bound to 127.0.0.1. Use `tailscale serve` to publish http://127.0.0.1:8340 as HTTPS on the user's tailnet only (NOT `tailscale funnel`). HTTPS is required because phone browsers only allow the microphone on secure origins.
- Do not use 0.0.0.0 binding.

# Tasks
1. Inspect server.py, config.py and frontend/app.js. Find anything that would break when the page is loaded from a https://<machine>.<tailnet>.ts.net address instead of http://localhost:8340: hard-coded localhost URLs, CORS or allowed-origin or host checks, WebSocket URLs (must use wss:// when the page is https), MediaRecorder / Web Speech API assumptions. Fix them with relative URLs / protocol-aware URLs. Optionally add an ALLOWED_HOSTS or extra-origin setting in config.py / .env for the tailnet hostname.
2. Check whether Tailscale is installed (`tailscale version`, or C:\Program Files\Tailscale). If not, tell the user to install it (winget install Tailscale.Tailscale, or tailscale.com/download) and sign in; also install the Tailscale app on the phone and sign in with the same account. Do not attempt to sign in on the user's behalf. Pause and ask the user to do this.
3. Once Tailscale is up and HTTPS certificates are enabled for the tailnet (admin console, DNS page, Enable HTTPS), run `tailscale serve --bg 8340` and report the resulting https address.
4. Update start.bat (or add a helper script) so that the serve configuration is applied when Hassan starts, if Tailscale is installed.
5. Write docs/jarvis/PHONE_ACCESS.md with the setup steps, how to find the address, how to turn it off (`tailscale serve reset`), and the security notes.

# Acceptance checks
- http://localhost:8340 still works exactly as before.
- Server is still bound to 127.0.0.1 only (verify with netstat).
- `tailscale serve status` shows 8340 proxied over HTTPS and funnel is off.
- Opening the https tailnet address from the phone loads the Hassan page, the mic permission prompt appears, and a spoken message gets a spoken reply.
- Commit the changes to git with a clear message. Do not commit .env.
- Ask the user before any step that needs them (installing, signing in, admin console).