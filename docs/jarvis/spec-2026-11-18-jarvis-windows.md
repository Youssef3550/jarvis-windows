# Goal
Finish the phone-access setup for Hassan (FastAPI server in server.py, port 8340) using Tailscale. An earlier Claude Code session did most of the code work and then its window was closed. Continue from where it stopped, do not redo finished work.

# First
Run `git status` and `git log` and read docs/jarvis/ (especially any PHONE_ACCESS.md or plan) to see what is already done. Check that the server still runs on http://localhost:8340 and is still bound to 127.0.0.1 only.

# Remaining work
1. Check whether Tailscale is installed (`tailscale version`, or C:\Program Files\Tailscale). If missing, tell the user to run `winget install Tailscale.Tailscale` (or download from tailscale.com), then sign in. Do not sign in on their behalf.
2. Ask the user to install the Tailscale app on their phone and sign in with the same account.
3. Ask the user to enable HTTPS certificates in the Tailscale admin console (DNS page, Enable HTTPS).
4. Run `tailscale serve --bg 8340` (never `tailscale funnel`) and report the resulting https address.
5. Make sure start.bat or a helper script re-applies the serve config when Hassan starts, if Tailscale is installed.
6. Make sure docs/jarvis/PHONE_ACCESS.md exists with setup steps, how to find the address, how to turn it off (`tailscale serve reset`) and security notes.

# Security
- Server stays bound to 127.0.0.1. No 0.0.0.0, no funnel. Only the user's own tailnet may reach Hassan.

# Acceptance checks
- localhost:8340 still works.
- `tailscale serve status` shows 8340 over HTTPS, funnel off.
- The https address opens on the phone, the mic prompt appears, and a spoken message gets a spoken reply.
- Commit changes to git with a clear message, never commit .env.
- Ask the user before every step that needs them. Speak plainly, the user is not very technical with networking.