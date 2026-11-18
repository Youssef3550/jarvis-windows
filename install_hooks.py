"""Add (or remove) the JARVIS hooks in your Claude Code user settings.

    python install_hooks.py            install
    python install_hooks.py --remove   uninstall

A backup of settings.json is written next to it first. Hooks you already have
are kept; only entries pointing at jarvis_hook.py are added or removed.
"""
import json
import shutil
import sys
import time
from pathlib import Path

EVENTS = ["Notification", "Stop", "UserPromptSubmit", "SessionStart", "SessionEnd"]
HOOK = Path(__file__).resolve().parent / "hooks" / "jarvis_hook.py"
SETTINGS = Path.home() / ".claude" / "settings.json"


def command(event: str) -> str:
    # Forward slashes work in both cmd and the Git Bash shell Claude Code uses.
    py = Path(sys.executable).as_posix()
    return f'"{py}" "{HOOK.as_posix()}" {event}'


def is_ours(entry: dict) -> bool:
    return any("jarvis_hook.py" in h.get("command", "") for h in entry.get("hooks", []))


def main() -> None:
    remove = "--remove" in sys.argv
    SETTINGS.parent.mkdir(parents=True, exist_ok=True)
    settings = {}
    if SETTINGS.exists():
        raw = SETTINGS.read_text(encoding="utf-8")
        settings = json.loads(raw) if raw.strip() else {}
        backup = SETTINGS.with_name(f"settings.backup-{time.strftime('%Y%m%d-%H%M%S')}.json")
        shutil.copy2(SETTINGS, backup)
        print(f"Backup saved: {backup}")
    hooks = settings.setdefault("hooks", {})
    for event in EVENTS:
        entries = [e for e in hooks.get(event, []) if not is_ours(e)]
        if not remove:
            entries.append({"hooks": [{"type": "command", "command": command(event), "timeout": 5}]})
        if entries:
            hooks[event] = entries
        else:
            hooks.pop(event, None)
    if not hooks:
        settings.pop("hooks")
    SETTINGS.write_text(json.dumps(settings, indent=2), encoding="utf-8")
    print("JARVIS hooks removed." if remove else
          f"JARVIS hooks installed in {SETTINGS}. Restart open Claude Code sessions to pick them up.")


if __name__ == "__main__":
    main()
