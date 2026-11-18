"""Watches every Claude Code session on this laptop.

Two sources:
- Hooks (installed by install_hooks.py) tell us the moment a session starts
  working, finishes, or stops at a permission prompt.
- A scan of ~/.claude/projects finds sessions started before JARVIS was
  running and notices when a blocked session moves on again.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import config

RECENT_HOURS = 12


def _project_name(cwd: str) -> str:
    return Path(cwd).name if cwd else "unknown project"


def _tail_info(path: Path) -> dict:
    """cwd and last user prompt from the end of a transcript file."""
    info: dict = {}
    try:
        with path.open("rb") as fh:
            fh.seek(0, 2)
            size = fh.tell()
            fh.seek(max(0, size - 65536))
            lines = fh.read().decode("utf-8", "replace").splitlines()
    except OSError:
        return info
    for raw in reversed(lines):
        try:
            ev = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if "cwd" not in info and ev.get("cwd"):
            info["cwd"] = ev["cwd"]
        if "prompt" not in info and ev.get("type") == "user":
            content = ev.get("message", {}).get("content")
            if isinstance(content, str) and not content.startswith("<"):
                info["prompt"] = content[:200]
        if "cwd" in info and "prompt" in info:
            break
    return info


class SessionWatcher:
    def __init__(self) -> None:
        self.sessions: dict[str, dict] = {}

    def _get(self, sid: str, payload: dict) -> dict:
        s = self.sessions.get(sid)
        if s is None:
            s = {"session_id": sid, "status": "idle", "reason": "", "since": time.time(),
                 "last_prompt": "", "cwd": "", "transcript": ""}
            self.sessions[sid] = s
        if payload.get("cwd"):
            s["cwd"] = payload["cwd"]
        if payload.get("transcript_path"):
            s["transcript"] = payload["transcript_path"]
        s["project"] = _project_name(s["cwd"])
        return s

    def _set(self, s: dict, status: str, reason: str = "") -> None:
        s["status"], s["reason"], s["since"] = status, reason, time.time()

    def handle_hook(self, event: str, payload: dict) -> dict | None:
        """Update state; return an announcement dict when the user should hear it."""
        sid = payload.get("session_id")
        if not sid or self._is_jarvis(payload.get("cwd", "")):
            return None
        s = self._get(sid, payload)
        if event == "UserPromptSubmit":
            s["last_prompt"] = (payload.get("prompt") or "")[:200]
            self._set(s, "working")
        elif event == "Notification":
            msg = payload.get("message") or ""
            kind = payload.get("notification_type") or ""
            if kind == "permission_prompt" or "permission" in msg.lower():
                self._set(s, "needs_you", msg or "permission prompt")
                return {"urgent": True, "session": dict(s),
                        "text": f"The {s['project']} session needs you: {msg or 'a permission prompt'}."}
            if kind == "idle_prompt" or "waiting for your input" in msg.lower():
                if s["status"] != "finished":
                    self._set(s, "waiting", "waiting for your next message")
            elif kind in ("elicitation_dialog",) or "question" in msg.lower():
                self._set(s, "needs_you", msg)
                return {"urgent": True, "session": dict(s),
                        "text": f"The {s['project']} session has a question for you."}
        elif event == "Stop":
            was_working = s["status"] in ("working", "needs_you", "idle")
            self._set(s, "finished", "finished its turn")
            if was_working:
                return {"urgent": False, "session": dict(s),
                        "text": f"{s['project']} finished."}
        elif event == "SessionStart":
            self._set(s, "idle")
        elif event == "SessionEnd":
            self._set(s, "gone", payload.get("reason") or "")
        return None

    @staticmethod
    def _is_jarvis(cwd: str) -> bool:
        try:
            return bool(cwd) and Path(cwd).resolve() == config.HOME_DIR.resolve()
        except OSError:
            return False

    def scan(self) -> None:
        root = config.CLAUDE_HOME / "projects"
        if not root.exists():
            return
        cutoff = time.time() - RECENT_HOURS * 3600
        seen = set()
        for path in root.glob("*/*.jsonl"):
            try:
                mtime = path.stat().st_mtime
            except OSError:
                continue
            if mtime < cutoff:
                continue
            sid = path.stem
            seen.add(sid)
            s = self.sessions.get(sid)
            if s is None:
                info = _tail_info(path)
                if self._is_jarvis(info.get("cwd", "")):
                    continue
                s = self._get(sid, {"cwd": info.get("cwd", ""), "transcript_path": str(path)})
                s["last_prompt"] = info.get("prompt", "")
                fresh = time.time() - mtime < 20
                self._set(s, "working" if fresh else "idle")
                s["since"] = mtime
            s["mtime"] = mtime
            # A blocked session whose transcript moved on has been answered.
            if s["status"] == "needs_you" and mtime > s["since"] + 2:
                self._set(s, "working")
        for sid, s in list(self.sessions.items()):
            if sid not in seen and time.time() - s["since"] > RECENT_HOURS * 3600:
                del self.sessions[sid]

    def listing(self) -> list[dict]:
        order = {"needs_you": 0, "working": 1, "waiting": 2, "finished": 3, "idle": 4, "gone": 5}
        items = [s for s in self.sessions.values() if s["status"] != "gone"
                 or time.time() - s["since"] < 600]
        return sorted(items, key=lambda s: (order.get(s["status"], 9), -s["since"]))
