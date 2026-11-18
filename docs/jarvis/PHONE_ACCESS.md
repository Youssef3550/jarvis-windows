# Hassan on your phone (Tailscale)

Open Hassan from your phone's browser, anywhere, with microphone and voice. It goes over
**Tailscale**, a free private network that connects only your own devices. Hassan is never
on the public internet or your home Wi-Fi network.

## One-time setup

1. **Laptop: install Tailscale and sign in**
   ```powershell
   winget install Tailscale.Tailscale
   ```
   (or download it from https://tailscale.com/download). Open Tailscale from the tray and sign in.
2. **Phone: install the Tailscale app** (App Store / Play Store) and sign in with the **same account**.
   Switch the VPN on in the app.
3. **Turn on HTTPS for your tailnet** (phone browsers only allow the microphone on https):
   open https://login.tailscale.com/admin/dns, scroll to **HTTPS Certificates**, click **Enable HTTPS**.
4. **Publish Hassan on the tailnet** (in PowerShell, from the project folder):
   ```powershell
   powershell -ExecutionPolicy Bypass -File phone_access.ps1 on
   ```
   This runs `tailscale serve --bg 8340` and prints the address. The first time can take
   up to a minute while the certificate is made. The setting is kept after reboots;
   `start.bat` also re-applies it every time Hassan starts.

## Finding the address

It looks like `https://<laptop-name>.<tailnet>.ts.net/`. Any of these show it:

- the line `Phone: https://...` printed by `start.bat` or `phone_access.ps1 on`
- `tailscale serve status`
- the Tailscale admin console, **Machines** page (the laptop's full domain name)

Open it on the phone (Chrome on Android, Safari or Chrome on iPhone), allow the microphone
when asked, then tap the orb to talk. Add it to the home screen for one-tap access.

The laptop must be on, with Hassan running (`start.bat`) and Tailscale connected.

## Turning it off

```powershell
powershell -ExecutionPolicy Bypass -File phone_access.ps1 off    # = tailscale serve reset
```
To keep it off, also remove the `phone_access.ps1 on` line from `start.bat`.
Check what is published with `phone_access.ps1 status` (= `tailscale serve status` + `tailscale funnel status`).

## Security notes

- Hassan can open apps, use the clipboard and start builds on the laptop, so who can reach it matters.
- The server still listens on **127.0.0.1:8340 only**, never `0.0.0.0`. Your Wi-Fi/LAN cannot reach it.
  Check with `netstat -ano | findstr :8340` (only `127.0.0.1:8340` should be LISTENING).
- `tailscale serve` makes it reachable **only from devices signed in to your tailnet**.
  **Never use `tailscale funnel`**: that would put Hassan on the public internet.
  `tailscale funnel status` should say there is no funnel.
- If you share your tailnet with other people, they could open Hassan too. Keep the tailnet
  to your own devices, or restrict access with Tailscale ACLs.
- Hassan only answers requests addressed to `localhost`, `127.0.0.1` or this laptop's own
  Tailscale name (found automatically), and only from pages on those same addresses. This
  stops other websites open in your browser from driving Hassan behind your back.
  If the phone gets "Forbidden host", add the name to `.env`:
  `ALLOWED_HOSTS=<laptop-name>.<tailnet>.ts.net` and restart Hassan.

## Phone tips

- Push-to-talk uses Whisper on the laptop and works in every modern phone browser.
- Hands-free mode uses the browser's own speech recognition: works in Chrome on Android,
  patchy on iPhone. Use push-to-talk there.
- Tap the page once before the first reply so the browser allows Hassan's voice to play.
