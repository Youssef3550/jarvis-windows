"""Only let the browser reach Hassan through names we trust.

The server listens on 127.0.0.1 only, but a web page open in any browser tab on this
laptop can still send requests to http://localhost:8340, and a "DNS rebinding" site can
even pose as it. Hassan can open apps and run builds, so every HTTP and WebSocket request
must come in under a trusted host name:

  * localhost / 127.0.0.1 / [::1]                (the laptop itself)
  * this laptop's Tailscale name, e.g. laptop.tail1234.ts.net   (the phone, via `tailscale serve`)
  * anything listed in ALLOWED_HOSTS in .env

The Host header must be one of those, and so must the Origin header when the browser sends
one. Anything else gets 403. ALLOWED_HOSTS=* switches the check off.
"""
from __future__ import annotations

import asyncio
import json
import logging
import subprocess
import time
from urllib.parse import urlsplit

import config

log = logging.getLogger("jarvis.hostguard")

LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}
_RETRY_SECONDS = 30


def tailnet_name() -> str | None:
    """This machine's full Tailscale DNS name (laptop.tail1234.ts.net), or None."""
    exe = config.tailscale_exe()
    if not exe:
        return None
    try:
        out = subprocess.run([exe, "status", "--json"], capture_output=True, timeout=5,
                             creationflags=config.NO_WINDOW)
        name = json.loads(out.stdout or b"{}").get("Self", {}).get("DNSName", "")
    except (OSError, subprocess.SubprocessError, ValueError, AttributeError):
        return None
    name = name.strip().lower().rstrip(".")
    return name or None


def host_only(value: str) -> str:
    """'laptop.x.ts.net:443' -> 'laptop.x.ts.net', '[::1]:8340' -> '::1'."""
    value = value.strip().lower()
    if "://" in value:
        return (urlsplit(value).hostname or "").rstrip(".")
    try:
        return (urlsplit("//" + value).hostname or "").rstrip(".")
    except ValueError:
        return ""


class HostGuard:
    """ASGI middleware: 403 for HTTP/WebSocket requests from untrusted hosts or origins."""

    def __init__(self, app, extra_hosts: list[str] | None = None, detect=tailnet_name) -> None:
        self.app = app
        extra = config.ALLOWED_HOSTS if extra_hosts is None else extra_hosts
        self.off = "*" in extra
        self.allowed = LOCAL_HOSTS | {host_only(h) or h for h in extra}
        self.detect = detect
        self.tailnet: str | None = None
        self.next_detect = 0.0

    async def _refresh_tailnet(self) -> None:
        # Tailscale may be installed or signed in after Hassan started, so look again
        # (at most every 30 s) whenever an unknown name shows up.
        if time.monotonic() < self.next_detect:
            return
        self.next_detect = time.monotonic() + _RETRY_SECONDS
        name = await asyncio.to_thread(self.detect)
        if name and name != self.tailnet:
            log.info("Phone access allowed via Tailscale name %s", name)
            self.tailnet = name
            self.allowed.add(name)

    async def is_allowed(self, host: str) -> bool:
        if host in self.allowed:
            return True
        if host.endswith(".ts.net"):
            await self._refresh_tailnet()
        return host in self.allowed

    async def __call__(self, scope, receive, send):
        if scope["type"] not in ("http", "websocket") or self.off:
            return await self.app(scope, receive, send)
        headers = {k.decode("latin-1").lower(): v.decode("latin-1")
                   for k, v in scope.get("headers", [])}
        host = host_only(headers.get("host", ""))
        origin = headers.get("origin", "")
        ok = await self.is_allowed(host)
        if ok and origin:                                    # "null" (sandboxed page) is refused too
            ok = await self.is_allowed(host_only(origin))
        if ok:
            return await self.app(scope, receive, send)

        log.warning("Blocked request for host %r (origin %r). Add it to ALLOWED_HOSTS in .env "
                    "if it is yours.", host, origin)
        if scope["type"] == "websocket":
            await receive()                                  # websocket.connect
            await send({"type": "websocket.close", "code": 1008})
            return
        body = b"Forbidden host. See ALLOWED_HOSTS in .env."
        await send({"type": "http.response.start", "status": 403,
                    "headers": [(b"content-type", b"text/plain"),
                                (b"content-length", str(len(body)).encode())]})
        await send({"type": "http.response.body", "body": body})
