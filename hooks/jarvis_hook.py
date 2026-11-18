"""Claude Code hook: tells JARVIS what a session is doing.

Claude Code runs this on Notification / Stop / UserPromptSubmit / SessionStart /
SessionEnd and passes event details on stdin. It must be fast and must never
block Claude Code, so every failure is silent and the timeout is short.
"""
import json
import os
import sys
import urllib.request


def main() -> None:
    if os.environ.get("JARVIS_INTERNAL") == "1":   # JARVIS's own processes
        return
    event = sys.argv[1] if len(sys.argv) > 1 else "unknown"
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except Exception:
        payload = {}
    port = os.environ.get("JARVIS_PORT", "8340")
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}/api/hooks/{event}",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"}, method="POST")
    try:
        urllib.request.urlopen(req, timeout=1.5).read()
    except Exception:
        pass   # JARVIS isn't running: that's fine


if __name__ == "__main__":
    main()
    sys.exit(0)
