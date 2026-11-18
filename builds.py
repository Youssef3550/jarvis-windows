"""Builds: hand a spec to a real Claude Code session and keep track of it.

Two modes:
- window:     opens a normal Claude Code window in the project. You see
              everything and approve its permission prompts yourself; the
              session watcher tells you out loud when it is waiting on you.
- background: runs `claude -p` hidden, allowed to edit files in the project
              and run a fixed list of dev commands (npm, python, git, ...).
              Progress and cost show on the dashboard.
"""
from __future__ import annotations

import asyncio
import datetime as dt
import json
import re
import subprocess
import threading
import time
import uuid
from pathlib import Path
from typing import Awaitable, Callable

import config

INDEX = config.DATA_DIR / "builds" / "index.json"
PROMPT = "Read docs/jarvis/BRIEF.md and carry out every step in it."

BACKGROUND_ALLOWED = ",".join([
    "Read", "Edit", "Write", "Glob", "Grep",
    "Bash(npm:*)", "Bash(npx:*)", "Bash(node:*)", "Bash(pnpm:*)", "Bash(yarn:*)",
    "Bash(python:*)", "Bash(py:*)", "Bash(pip:*)", "Bash(pytest:*)",
    "Bash(git init:*)", "Bash(git add:*)", "Bash(git commit:*)", "Bash(git status:*)",
    "Bash(git diff:*)", "Bash(mkdir:*)", "Bash(ls:*)", "Bash(dir:*)", "Bash(cat:*)",
    "Bash(dotnet:*)",
])

BRIEF = """# Build brief from Hassan

You are building a project on a Windows laptop. The design was agreed with the
user by voice and is written in `{spec}`. Work through these steps in order.

1. Read the spec carefully.
2. Write a plan to `docs/jarvis/plan.md`: phases with small tasks, each task a
   Markdown checkbox (`- [ ] ...`). Keep the plan concrete: files, commands, checks.
3. Review the plan against the spec. Fix anything missing or out of scope.
4. Carry out the plan task by task. After finishing each task, tick its box
   (`- [x]`) in plan.md so progress can be read from the file.
5. Test as you go where it makes sense (unit tests, running the app, a build).
6. Finish by writing `docs/jarvis/SUMMARY.md`: what was built, how to run it,
   and anything left open. Keep the user's Windows setup in mind (PowerShell,
   Windows paths).

If something in the spec is impossible or unclear, choose the simplest
reasonable option, note it in SUMMARY.md, and carry on.
"""


def _slug(text: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "-", text.strip().lower()).strip("-")
    return s[:50] or "project"


def plan_progress(path: Path) -> dict:
    plan = path / "docs" / "jarvis" / "plan.md"
    if not plan.exists():
        return {"plan": False, "done": 0, "total": 0}
    text = plan.read_text(encoding="utf-8", errors="replace")
    done = len(re.findall(r"^\s*[-*] \[[xX]\]", text, flags=re.M))
    todo = len(re.findall(r"^\s*[-*] \[ \]", text, flags=re.M))
    nxt = re.search(r"^\s*[-*] \[ \]\s*(.+)$", text, flags=re.M)
    return {"plan": True, "done": done, "total": done + todo,
            "next_task": nxt.group(1).strip()[:160] if nxt else None,
            "summary": (path / "docs" / "jarvis" / "SUMMARY.md").exists()}


class BuildManager:
    def __init__(self, announce: Callable[[str, bool], Awaitable[None]]):
        self.announce = announce
        self.loop: asyncio.AbstractEventLoop | None = None
        self.procs: dict[str, subprocess.Popen] = {}
        self.builds: dict[str, dict] = {}
        try:
            self.builds = json.loads(INDEX.read_text(encoding="utf-8"))
            for b in self.builds.values():          # anything "running" died with us
                if b["status"] == "running" and b["mode"] == "background":
                    b["status"] = "interrupted"
        except Exception:
            pass

    def _save(self) -> None:
        INDEX.write_text(json.dumps(self.builds, indent=1), encoding="utf-8")

    def _resolve(self, project: str) -> Path:
        p = Path(project).expanduser()
        if p.is_absolute():
            if not p.exists():
                raise ValueError(f"Folder {p} does not exist.")
            return p.resolve()
        return (config.PROJECTS_DIR / _slug(project)).resolve()

    def start(self, project: str, spec: str, mode: str = "window") -> dict:
        self.loop = self.loop or asyncio.get_event_loop()
        path = self._resolve(project)
        docs = path / "docs" / "jarvis"
        docs.mkdir(parents=True, exist_ok=True)
        date = dt.date.today().isoformat()
        spec_file = docs / f"spec-{date}-{_slug(path.name)}.md"
        spec_file.write_text(spec, encoding="utf-8")
        rel_spec = spec_file.relative_to(path).as_posix()
        (docs / "BRIEF.md").write_text(BRIEF.format(spec=rel_spec), encoding="utf-8")

        bid = uuid.uuid4().hex[:8]
        build = {"id": bid, "project": path.name, "path": str(path), "mode": mode,
                 "status": "running", "started": time.time(), "ended": None,
                 "spec": rel_spec, "cost": None, "last_text": "", "error": ""}
        self.builds[bid] = build
        claude = config.claude_command()
        if mode == "background":
            log_path = config.DATA_DIR / "builds" / f"{bid}.jsonl"
            proc = subprocess.Popen(
                claude + ["-p", PROMPT, "--output-format", "stream-json", "--verbose",
                          "--model", config.BUILD_MODEL, "--permission-mode", "acceptEdits",
                          "--allowedTools", BACKGROUND_ALLOWED],
                cwd=str(path), env=config.child_env(), stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                encoding="utf-8", errors="replace", creationflags=config.NO_WINDOW)
            self.procs[bid] = proc
            threading.Thread(target=self._follow, args=(bid, proc, log_path), daemon=True).start()
        else:
            env = config.child_env()
            env.pop("JARVIS_INTERNAL", None)      # we *want* hooks to watch this one
            subprocess.Popen(claude + [PROMPT], cwd=str(path), env=env,
                             creationflags=config.NEW_CONSOLE)
            build["status"] = "opened"
        self._save()
        return build

    def _follow(self, bid: str, proc: subprocess.Popen, log_path: Path) -> None:
        b = self.builds[bid]
        with log_path.open("w", encoding="utf-8") as log:
            for line in proc.stdout:
                log.write(line)
                try:
                    ev = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if ev.get("type") == "assistant":
                    for block in ev.get("message", {}).get("content", []):
                        if block.get("type") == "text" and block.get("text", "").strip():
                            b["last_text"] = block["text"].strip()[:300]
                elif ev.get("type") == "result":
                    b["cost"] = ev.get("total_cost_usd")
                    if ev.get("is_error"):
                        b["error"] = str(ev.get("result", ""))[:300]
        code = proc.wait()
        self.procs.pop(bid, None)
        if b["status"] == "running":
            b["status"] = "done" if code == 0 and not b["error"] else "failed"
        b["ended"] = time.time()
        self._save()
        if self.loop and b["status"] in ("done", "failed"):
            msg = (f"The {b['project']} build has finished." if b["status"] == "done"
                   else f"The {b['project']} build failed.")
            asyncio.run_coroutine_threadsafe(self.announce(msg, b["status"] == "failed"), self.loop)

    def _find(self, key: str) -> dict | None:
        if key in self.builds:
            return self.builds[key]
        k = key.lower()
        matches = [b for b in self.builds.values() if k in b["project"].lower()]
        return max(matches, key=lambda b: b["started"]) if matches else None

    def status(self, key: str) -> dict:
        b = self._find(key)
        if not b:
            return {"error": f"No build matching '{key}'."}
        return {**b, "progress": plan_progress(Path(b["path"]))}

    def stop(self, key: str) -> str:
        b = self._find(key)
        if not b:
            return f"No build matching '{key}'."
        proc = self.procs.get(b["id"])
        if not proc:
            return ("That build runs in its own window; close the window to stop it."
                    if b["mode"] == "window" else "That build is not running.")
        b["status"] = "stopped"
        proc.terminate()
        self._save()
        return f"Stopped the {b['project']} build."

    def listing(self) -> list[dict]:
        out = []
        for b in sorted(self.builds.values(), key=lambda b: -b["started"])[:30]:
            out.append({**b, "progress": plan_progress(Path(b["path"]))})
        return out
