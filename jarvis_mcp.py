"""The brain's tools, served to Claude Code as an MCP server over stdio.

Written without the MCP SDK on purpose: the protocol needed here is small and
this way an SDK upgrade can never break JARVIS.
"""
from __future__ import annotations

import base64
import json
import os
import sys
import traceback
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import memory_store  # noqa: E402
import winctl  # noqa: E402

PORT = os.environ.get("JARVIS_PORT", "8340")
BASE = f"http://127.0.0.1:{PORT}"


def api(method: str, path: str, body: dict | None = None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return {"error": exc.read().decode("utf-8", "replace")[:300]}


def _s(desc: str, **props) -> dict:
    required = [k for k, v in props.items() if not v.pop("optional", False)]
    return {"description": desc,
            "inputSchema": {"type": "object", "properties": props, "required": required}}


STR = lambda d, **kw: {"type": "string", "description": d, **kw}  # noqa: E731
INT = lambda d, **kw: {"type": "integer", "description": d, **kw}  # noqa: E731

TOOLS: dict[str, dict] = {
    "open_app": _s("Open an installed Windows app by name (Chrome, Spotify, Word, VS Code, Settings...).",
                   name=STR("App name as the user said it")),
    "open_url": _s("Open a website in the default browser.", url=STR("URL or domain")),
    "list_windows": _s("List open windows with their app and title."),
    "focus_window": _s("Bring a window to the front.", query=STR("Part of the window title or app name")),
    "close_window": _s("Close a window gracefully (like clicking X; apps still ask to save). Confirm with the user first.",
                       query=STR("Part of the window title or app name")),
    "screenshot": _s("Take a screenshot of the screen to see what the user is looking at."),
    "media_key": _s("Press a media key.", key=STR("Which key", enum=[
        "play_pause", "next", "previous", "stop", "volume_up", "volume_down", "mute"]),
        times=INT("How many presses (volume steps are 2% each)", optional=True)),
    "set_volume": _s("Set the system volume.", percent=INT("0 to 100")),
    "system_status": _s("Local date and time, battery level and charging state."),
    "lock_screen": _s("Lock the Windows screen."),
    "clipboard_get": _s("Read the text on the clipboard."),
    "clipboard_set": _s("Put text on the clipboard.", text=STR("Text to copy")),
    "notify": _s("Show a Windows notification.", title=STR("Title"), body=STR("Message")),
    "remember": _s("Save a durable fact about the user to long-term memory.", fact=STR("One short fact")),
    "forget": _s("Remove memory items containing this text.", text=STR("Text to match")),
    "list_memory": _s("List everything in long-term memory."),
    "list_sessions": _s("List the user's Claude Code sessions and whether each is working, finished, or waiting on the user."),
    "start_build": _s(
        "Start building a software project with Claude Code from an agreed spec. Only call after the user said yes.",
        project_name=STR("Short project name, or the full path of an existing folder"),
        spec=STR("Complete Markdown spec: goal, features, tech stack, structure, acceptance checks"),
        mode=STR("window = visible Claude Code window (default); background = hidden", enum=["window", "background"], optional=True)),
    "list_builds": _s("List recent builds and their progress."),
    "build_status": _s("Progress of one build: plan tasks done, next task, status.",
                       project=STR("Project name or build id")),
    "stop_build": _s("Stop a background build.", project=STR("Project name or build id")),
}


def call(name: str, a: dict) -> list[dict]:
    text = lambda v: [{"type": "text", "text": v if isinstance(v, str)  # noqa: E731
                       else json.dumps(v, ensure_ascii=False, indent=1)}]
    if name == "open_app":
        return text(winctl.open_app(a["name"]))
    if name == "open_url":
        return text(winctl.open_url(a["url"]))
    if name == "list_windows":
        return text(winctl.list_windows())
    if name == "focus_window":
        return text(winctl.focus_window(a["query"]))
    if name == "close_window":
        return text(winctl.close_window(a["query"]))
    if name == "screenshot":
        return [{"type": "image", "mimeType": "image/jpeg",
                 "data": base64.b64encode(winctl.screenshot()).decode()}]
    if name == "media_key":
        return text(winctl.media_key(a["key"], a.get("times", 1)))
    if name == "set_volume":
        return text(winctl.set_volume(a["percent"]))
    if name == "system_status":
        return text(winctl.system_status())
    if name == "lock_screen":
        return text(winctl.lock_screen())
    if name == "clipboard_get":
        return text(winctl.clipboard_get() or "(clipboard is empty)")
    if name == "clipboard_set":
        return text(winctl.clipboard_set(a["text"]))
    if name == "notify":
        return text(winctl.notify(a["title"], a["body"]))
    if name == "remember":
        return text(memory_store.remember(a["fact"]))
    if name == "forget":
        return text(memory_store.forget(a["text"]))
    if name == "list_memory":
        return text(memory_store.list_facts() or "Memory is empty.")
    if name == "list_sessions":
        sessions = api("GET", "/api/sessions")
        slim = [{k: s.get(k) for k in ("project", "status", "reason", "last_prompt", "cwd")}
                for s in sessions] if isinstance(sessions, list) else sessions
        return text(slim or "No Claude Code sessions in the last 12 hours.")
    if name == "start_build":
        return text(api("POST", "/api/builds", {"project": a["project_name"], "spec": a["spec"],
                                               "mode": a.get("mode", "window")}))
    if name == "list_builds":
        return text([{k: b.get(k) for k in ("id", "project", "mode", "status", "progress")}
                     for b in api("GET", "/api/builds")])
    if name == "build_status":
        return text(api("GET", "/api/builds/" + urllib.parse.quote(a["project"], safe="")))
    if name == "stop_build":
        return text(api("POST", "/api/builds/" + urllib.parse.quote(a["project"], safe="") + "/stop"))
    raise ValueError(f"Unknown tool {name}")


def respond(msg_id, result=None, error=None) -> None:
    out = {"jsonrpc": "2.0", "id": msg_id}
    if error is not None:
        out["error"] = error
    else:
        out["result"] = result
    sys.stdout.write(json.dumps(out) + "\n")
    sys.stdout.flush()


def main() -> None:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue
        method, msg_id = msg.get("method"), msg.get("id")
        if msg_id is None:          # notification: nothing to answer
            continue
        if method == "initialize":
            version = msg.get("params", {}).get("protocolVersion", "2025-06-18")
            respond(msg_id, {"protocolVersion": version,
                             "capabilities": {"tools": {"listChanged": False}},
                             "serverInfo": {"name": "jarvis", "version": "1.0"}})
        elif method == "tools/list":
            respond(msg_id, {"tools": [{"name": n, **spec} for n, spec in TOOLS.items()]})
        elif method == "tools/call":
            p = msg.get("params", {})
            try:
                content = call(p.get("name", ""), p.get("arguments") or {})
                respond(msg_id, {"content": content, "isError": False})
            except Exception as exc:
                detail = f"{type(exc).__name__}: {exc}"
                print(traceback.format_exc(), file=sys.stderr)
                respond(msg_id, {"content": [{"type": "text", "text": detail}], "isError": True})
        elif method == "ping":
            respond(msg_id, {})
        else:
            respond(msg_id, error={"code": -32601, "message": f"Unknown method {method}"})


if __name__ == "__main__":
    main()
