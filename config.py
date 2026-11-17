"""Settings for JARVIS for Windows, read from .env next to this file."""
from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def _load_env() -> None:
    env_file = ROOT / ".env"
    if not env_file.exists():
        return
    for raw in env_file.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        value = value.split(" #")[0].strip().strip('"').strip("'")
        os.environ.setdefault(key.strip(), value)


_load_env()

PORT = int(os.environ.get("JARVIS_PORT", "8340"))
USER_NAME = os.environ.get("USER_NAME", "").strip()
BRAIN_MODEL = os.environ.get("JARVIS_BRAIN_MODEL", "sonnet").strip()
BUILD_MODEL = os.environ.get("JARVIS_BUILD_MODEL", "sonnet").strip()

VOICE_EN = os.environ.get("VOICE_EN", "en-GB-RyanNeural").strip()
VOICE_NL = os.environ.get("VOICE_NL", "nl-BE-ArnaudNeural").strip()
VOICE_RATE = os.environ.get("VOICE_RATE", "+4%").strip()

# Local Coqui TTS voice for English ("coqui"), or "edge" for the old Microsoft voice.
# Dutch always uses VOICE_NL above, because the Coqui VCTK voices are English-only.
TTS_ENGINE = os.environ.get("TTS_ENGINE", "coqui").strip().lower()
COQUI_MODEL = os.environ.get("COQUI_MODEL", "tts_models/en/vctk/vits").strip()
COQUI_SPEAKER = os.environ.get("COQUI_SPEAKER", "p273").strip()   # p273 / p330: British male
# Voice cloning (later): set COQUI_MODEL=tts_models/multilingual/multi-dataset/xtts_v2
# and point this at a clean 6-30 second WAV of the voice to copy. See tts.py.
COQUI_SPEAKER_WAV = os.environ.get("COQUI_SPEAKER_WAV", "").strip()
# Folder with espeak-ng.exe (needed by the VCTK voice). Found automatically if installed
# with: winget install -e --id eSpeak-NG.eSpeak-NG
ESPEAK_DIR = os.environ.get("ESPEAK_DIR", r"C:\Program Files\eSpeak NG").strip()

WHISPER_MODEL = os.environ.get("WHISPER_MODEL", "base").strip()

PROJECTS_DIR = Path(os.path.expandvars(os.path.expanduser(
    os.environ.get("PROJECTS_DIR", "~/JarvisProjects")))).resolve()

# Where Claude Code keeps its transcripts (one folder per project).
CLAUDE_HOME = Path(os.path.expanduser("~/.claude"))

DATA_DIR = ROOT / "data"
HOME_DIR = ROOT / "jarvis_home"          # the brain's working folder
MEMORY_FILE = HOME_DIR / "memory" / "MEMORY.md"
FRONTEND_DIR = ROOT / "frontend"

for _d in (DATA_DIR, HOME_DIR / "memory", DATA_DIR / "builds"):
    _d.mkdir(parents=True, exist_ok=True)

IS_WINDOWS = sys.platform == "win32"


def claude_command() -> list[str]:
    """The command that starts Claude Code, as a list."""
    override = os.environ.get("CLAUDE_PATH", "").strip()
    if override:
        return [override]
    for name in ("claude.exe", "claude.cmd", "claude"):
        found = shutil.which(name)
        if found:
            return [found]
    return ["claude"]


def child_env(**extra: str) -> dict[str, str]:
    """Environment for Claude Code processes we start.

    API keys are removed so everything runs on your Claude subscription login,
    and JARVIS_INTERNAL marks the process so our own hooks ignore it.
    """
    env = {k: v for k, v in os.environ.items()
           if not k.startswith("ANTHROPIC_") and not k.startswith("CLAUDE_CODE_")
           and k != "CLAUDECODE"}
    env["JARVIS_INTERNAL"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    env.update(extra)
    return env


NO_WINDOW = 0x08000000 if IS_WINDOWS else 0          # CREATE_NO_WINDOW
NEW_CONSOLE = 0x00000010 if IS_WINDOWS else 0        # CREATE_NEW_CONSOLE
