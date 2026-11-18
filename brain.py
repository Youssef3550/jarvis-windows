"""JARVIS's brain: one long-running Claude Code process on your subscription.

We talk to it over stdin/stdout in stream-json, so it stays warm between
questions and keeps the conversation. If it dies we restart it with --resume.
"""
from __future__ import annotations

import asyncio
import json
import logging
import subprocess
import sys
import threading
from collections import deque
from typing import Awaitable, Callable

import config

log = logging.getLogger("jarvis.brain")
STATE_FILE = config.DATA_DIR / "brain_state.json"
EventCallback = Callable[[dict], Awaitable[None]]


def write_persona() -> None:
    """Render persona.md into jarvis_home/CLAUDE.md (Claude Code loads it)."""
    name = config.USER_NAME
    text = (config.ROOT / "persona.md").read_text(encoding="utf-8")
    text = (text.replace("{user}", name or "the user")
                .replace("{address}", "sir")
                .replace("{address_nl}", "Youssef (nooit \"meneer\")")
                .replace("{projects_dir}", str(config.PROJECTS_DIR)))
    (config.HOME_DIR / "CLAUDE.md").write_text(text, encoding="utf-8")
    if not config.MEMORY_FILE.exists():
        intro = f"- The user's name is {name}.\n" if name else ""
        config.MEMORY_FILE.write_text(intro, encoding="utf-8")


def write_mcp_config() -> str:
    path = config.DATA_DIR / "mcp.json"
    cfg = {"mcpServers": {"jarvis": {
        "command": sys.executable,
        "args": ["-u", str(config.ROOT / "jarvis_mcp.py")],
        "env": {"JARVIS_PORT": str(config.PORT), "PYTHONIOENCODING": "utf-8"},
    }}}
    path.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    return str(path)


class Brain:
    def __init__(self, on_event: EventCallback):
        self.on_event = on_event
        self.proc: subprocess.Popen | None = None
        self.loop: asyncio.AbstractEventLoop | None = None
        self.session_id: str | None = self._load_session()
        self.stderr_tail: deque[str] = deque(maxlen=30)
        self._streamed_ids: set[str] = set()
        self._current_msg: str | None = None
        self._write_lock = threading.Lock()
        self.pending_turns = 0

    # ── persistence ──────────────────────────────────────────────────
    @staticmethod
    def _load_session() -> str | None:
        try:
            return json.loads(STATE_FILE.read_text())["session_id"]
        except Exception:
            return None

    def _save_session(self) -> None:
        STATE_FILE.write_text(json.dumps({"session_id": self.session_id}))

    # ── lifecycle ────────────────────────────────────────────────────
    def command(self) -> list[str]:
        cmd = config.claude_command() + [
            "-p", "--input-format", "stream-json", "--output-format", "stream-json",
            "--verbose", "--include-partial-messages",
            "--model", config.BRAIN_MODEL,
            "--setting-sources", "project",
            "--strict-mcp-config", "--mcp-config", write_mcp_config(),
            "--tools", "WebSearch,WebFetch",
            "--allowedTools", "mcp__jarvis,WebSearch,WebFetch",
            "--permission-mode", "dontAsk",
        ]
        if self.session_id:
            cmd += ["--resume", self.session_id]
        return cmd

    def alive(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    def start(self) -> None:
        if self.alive():
            return
        if self.loop is None:
            self.loop = asyncio.get_running_loop()
        write_persona()
        cmd = self.command()
        log.info("starting brain: %s", " ".join(cmd[:3]) + " ...")
        self._streamed_ids.clear()
        self.proc = subprocess.Popen(
            cmd, cwd=str(config.HOME_DIR), env=config.child_env(),
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding="utf-8", errors="replace", bufsize=1,
            creationflags=config.NO_WINDOW)
        threading.Thread(target=self._read_stdout, args=(self.proc,), daemon=True).start()
        threading.Thread(target=self._read_stderr, args=(self.proc,), daemon=True).start()

    def stop(self) -> None:
        if self.proc and self.proc.poll() is None:
            try:
                self.proc.stdin.close()
            except Exception:
                pass
            try:
                self.proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.proc.kill()
        self.proc = None
        self.pending_turns = 0

    def reset(self) -> None:
        """Forget the conversation (memory files stay)."""
        self.stop()
        self.session_id = None
        STATE_FILE.unlink(missing_ok=True)
        self.start()

    async def send(self, text: str) -> None:
        if not self.alive():
            self.start()
        line = json.dumps({"type": "user", "message": {"role": "user", "content": text}})
        proc = self.proc

        def _write() -> None:
            with self._write_lock:
                proc.stdin.write(line + "\n")
                proc.stdin.flush()

        self.pending_turns += 1
        try:
            await asyncio.to_thread(_write)
        except (BrokenPipeError, OSError, ValueError):
            # The process died between the check and the write: restart once.
            self.stop()
            self.start()
            self.pending_turns = 1
            await asyncio.to_thread(lambda: (self.proc.stdin.write(line + "\n"),
                                             self.proc.stdin.flush()))

    # ── reading ──────────────────────────────────────────────────────
    def _emit(self, event: dict) -> None:
        if self.loop:
            asyncio.run_coroutine_threadsafe(self.on_event(event), self.loop)

    def _read_stderr(self, proc: subprocess.Popen) -> None:
        for line in proc.stderr:
            line = line.rstrip()
            if line:
                self.stderr_tail.append(line)
                log.debug("brain stderr: %s", line)

    def _read_stdout(self, proc: subprocess.Popen) -> None:
        for line in proc.stdout:
            line = line.strip()
            if not line:
                continue
            try:
                ev = json.loads(line)
            except json.JSONDecodeError:
                continue
            try:
                self._handle(ev)
            except Exception:
                log.exception("bad brain event")
        code = proc.wait()
        if proc is self.proc:
            self.pending_turns = 0
            self._emit({"kind": "exit", "code": code,
                        "stderr": "\n".join(list(self.stderr_tail)[-8:])})

    def _handle(self, ev: dict) -> None:
        t = ev.get("type")
        if t == "system" and ev.get("subtype") == "init":
            sid = ev.get("session_id")
            if sid and sid != self.session_id:
                self.session_id = sid
                self._save_session()
            return
        if t == "stream_event":
            inner = ev.get("event", {})
            it = inner.get("type")
            if it == "message_start":
                self._current_msg = inner.get("message", {}).get("id")
            elif it == "content_block_delta":
                delta = inner.get("delta", {})
                if delta.get("type") == "text_delta" and delta.get("text"):
                    if self._current_msg:
                        self._streamed_ids.add(self._current_msg)
                    self._emit({"kind": "text", "text": delta["text"]})
            elif it == "content_block_stop":
                self._emit({"kind": "block_end"})
            return
        if t == "assistant":
            msg = ev.get("message", {})
            streamed = msg.get("id") in self._streamed_ids
            for block in msg.get("content", []):
                if block.get("type") == "tool_use":
                    self._emit({"kind": "tool", "name": block.get("name", ""),
                                "input": block.get("input", {})})
                elif block.get("type") == "text" and not streamed and block.get("text"):
                    self._emit({"kind": "text", "text": block["text"]})
                    self._emit({"kind": "block_end"})
            return
        if t == "result":
            self.pending_turns = max(0, self.pending_turns - 1)
            sid = ev.get("session_id")
            if sid and sid != self.session_id:
                self.session_id = sid
                self._save_session()
            self._emit({"kind": "done", "is_error": bool(ev.get("is_error")),
                        "result": ev.get("result", ""),
                        "cost": ev.get("total_cost_usd")})
