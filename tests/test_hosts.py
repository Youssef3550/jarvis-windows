"""Unit tests for hostguard.py (who may reach Hassan). No Tailscale needed: it is faked.

Run from the project folder:  .venv\\Scripts\\python.exe -m unittest discover -s tests -v
"""
import asyncio
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import hostguard  # noqa: E402

TAILNET = "laptop.tail1234.ts.net"


async def inner_app(scope, receive, send):
    if scope["type"] == "websocket":
        await receive()
        await send({"type": "websocket.accept"})
        return
    await send({"type": "http.response.start", "status": 200, "headers": []})
    await send({"type": "http.response.body", "body": b"ok"})


def call(guard, kind="http", host="localhost:8340", origin=None):
    headers = [(b"host", host.encode())]
    if origin:
        headers.append((b"origin", origin.encode()))
    scope = {"type": kind, "headers": headers, "path": "/"}
    sent = []

    async def receive():
        return {"type": "websocket.connect"} if kind == "websocket" else {"type": "http.request"}

    async def send(msg):
        sent.append(msg)

    asyncio.run(guard(scope, receive, send))
    first = sent[0]
    if first["type"] == "http.response.start":
        return first["status"]
    return "accept" if first["type"] == "websocket.accept" else "close"


class HostGuardTest(unittest.TestCase):
    def guard(self, extra=(), tailnet=TAILNET):
        self.detects = 0

        def detect():
            self.detects += 1
            return tailnet
        return hostguard.HostGuard(inner_app, extra_hosts=list(extra), detect=detect)

    def test_localhost_works_as_before(self):
        g = self.guard()
        self.assertEqual(call(g, host="localhost:8340"), 200)
        self.assertEqual(call(g, host="127.0.0.1:8340", origin="http://127.0.0.1:8340"), 200)
        self.assertEqual(call(g, "websocket", origin="http://localhost:8340"), "accept")
        self.assertEqual(self.detects, 0)            # no Tailscale lookup for local use

    def test_own_tailnet_name_allowed(self):
        g = self.guard()
        self.assertEqual(call(g, host=TAILNET, origin=f"https://{TAILNET}"), 200)
        self.assertEqual(call(g, "websocket", host=TAILNET, origin=f"https://{TAILNET}"), "accept")
        # tailscale serve may also forward with Host 127.0.0.1 and the tailnet Origin
        self.assertEqual(call(g, host="127.0.0.1:8340", origin=f"https://{TAILNET}"), 200)

    def test_other_sites_blocked(self):
        g = self.guard()
        self.assertEqual(call(g, origin="https://evil.example"), 403)
        self.assertEqual(call(g, "websocket", origin="https://evil.example"), "close")
        self.assertEqual(call(g, origin="null"), 403)
        self.assertEqual(call(g, host="evil.example"), 403)               # DNS rebinding
        self.assertEqual(call(g, host="other.tail999.ts.net"), 403)       # someone else's tailnet
        self.assertEqual(call(g, origin="https://evil.ts.net"), 403)

    def test_lookup_is_rate_limited(self):
        g = self.guard(tailnet=None)
        for _ in range(5):
            self.assertEqual(call(g, host=TAILNET), 403)
        self.assertEqual(self.detects, 1)

    def test_allowed_hosts_setting(self):
        g = self.guard(extra=["hassan.example.ts.net"], tailnet=None)
        self.assertEqual(call(g, host="hassan.example.ts.net:443"), 200)
        self.assertEqual(call(self.guard(extra=["*"]), host="anything"), 200)

    def test_host_only(self):
        self.assertEqual(hostguard.host_only("Laptop.X.ts.net:443"), "laptop.x.ts.net")
        self.assertEqual(hostguard.host_only("[::1]:8340"), "::1")
        self.assertEqual(hostguard.host_only("https://a.ts.net."), "a.ts.net")


if __name__ == "__main__":
    unittest.main()
