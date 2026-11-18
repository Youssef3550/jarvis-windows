# Hassan: a voice assistant for Windows

A voice assistant on top of the Claude Code you already pay for. You talk, he
talks back with a British voice (in English or Dutch), and he can control your
laptop, build software projects, and tell you out loud when one of your Claude
Code sessions needs you.

Everything runs on your own laptop. The brain is Claude Code on your Claude
subscription (no API key). The English voice is a local Coqui TTS voice (free,
offline); Dutch uses Microsoft's free neural voices.

## What you need

- Windows 10 or 11
- Google Chrome (the microphone uses Chrome's built-in speech recognition)
- Claude Code installed and logged in (you can run `claude` in a terminal)
- Python 3.10 or newer. If you don't have it: `winget install Python.Python.3.12`

## Start

1. Double-click **start.bat**. The first run installs what it needs (about a minute).
2. Chrome opens at http://localhost:8340. Allow the microphone when asked.
3. Click the orb or **hold Space** and talk. Release Space when you're done.

Optional, once: double-click **install_hooks.bat** so Hassan can see what your
other Claude Code sessions are doing. It backs up `%USERPROFILE%\.claude\settings.json`
first and keeps your existing hooks. To remove it: `install_hooks.bat --remove`.

## Controls

| | |
|---|---|
| Hold **Space** / click the orb | Talk (talking also interrupts him) |
| **EN / NL** | Language the microphone listens for. He answers in the language you speak. |
| **Hands-free** | Mic stays on; pauses while he speaks so he doesn't hear himself |
| **Only after "Jarvis"** | In hands-free, only react to sentences starting with "Jarvis" |
| **New conversation** | Fresh conversation (memory is kept) |

## Things to say

- "Open Spotify" · "Open YouTube" · "Close Notepad" · "Switch to Chrome"
- "Pause the music" · "Next song" · "Set the volume to 30"
- "What's on my screen?" · "Copy that to my clipboard"
- "How's my battery?" · "Lock my laptop"
- "Remember that my sister's practice is H.M Thuisverpleging"
- "What's the weather in Hasselt?" · "Latest news about AI"
- "Which of my Claude sessions needs me?"
- "I want to build a booking page for my burger truck" → he asks questions one at
  a time, proposes options, and after your yes starts a Claude Code build.
- In Dutch: "Open Spotify", "Zet het volume op dertig", "Wat staat er op mijn scherm?"

## Builds

When you agree on a project, Hassan writes the spec to
`<project>\docs\jarvis\` and starts Claude Code on it:

- **window** (default): a normal Claude Code window opens. You approve its
  permission prompts yourself; Hassan tells you when it's waiting.
- **background** (say "run it in the background"): hidden, may edit files in the
  project and run common dev commands (npm, python, pip, git, dotnet). No
  deleting outside the project, no other commands.

New projects go in `%USERPROFILE%\JarvisProjects` (change `PROJECTS_DIR` in `.env`).
The **Builds** tab shows progress from each project's `plan.md` checkboxes.

## Settings (`.env`)

Your name, the Claude model (sonnet / opus / haiku), the voices and the projects
folder. To see all voices: `.venv\Scripts\edge-tts --list-voices`.
Good options: `en-GB-RyanNeural`, `en-GB-ThomasNeural`, `nl-BE-ArnaudNeural`,
`nl-NL-MaartenNeural`.

### Local English voice (Coqui TTS)

English is spoken by Coqui TTS on your own laptop (`TTS_ENGINE=coqui`, the default).
One-time setup in PowerShell, from this folder:

```powershell
.venv\Scripts\python.exe -m pip install -r requirements.txt
winget install -e --id eSpeak-NG.eSpeak-NG
```

The first start downloads the voice model (about 150 MB). Settings: `COQUI_SPEAKER`
(`p273` or `p330` sound British male; any VCTK speaker `p225`–`p376` works),
`COQUI_MODEL`, and `TTS_ENGINE=edge` to go back to the Microsoft voice. Voice cloning
is prepared (`COQUI_SPEAKER_WAV`, see the comments in `tts.py`). Check the voice at
`http://localhost:8340/api/tts_status`.

## Safety

- The brain can only use Hassan's own tools plus web search. It can't run
  shell commands or edit files on its own.
- Closing a window works like clicking X, so apps still ask to save.
- Nothing listens unless the mic button is lit or Hands-free is on.
- Speech recognition runs through Google (that's how Chrome does it); the English
  voice is made locally; Dutch speech goes through Microsoft's text-to-speech service. Conversations go to Claude
  like any Claude Code session.

## Troubleshooting

- **No voice, only text**: the free voice service couldn't be reached, so
  Chrome's built-in voice is used. Check your internet connection.
- **English voice is Microsoft's, not Coqui**: open `/api/tts_status`; `coqui_error`
  says why. Usually eSpeak NG is missing (install it, or set `ESPEAK_DIR` in `.env`).
- **"Claude Code was not found"**: set `CLAUDE_PATH` in `.env` to the full path
  of `claude.exe` (run `where claude` in a terminal to find it).
- **Microphone blocked**: click the icon on the left of Chrome's address bar
  and allow the microphone for localhost.
- **Session alerts don't arrive**: run `install_hooks.bat`, then restart your
  open Claude Code sessions.

## Files

`server.py` web server · `brain.py` Claude Code process · `persona.md` his
personality and rules (edit freely) · `jarvis_mcp.py` his tools · `winctl.py`
Windows control · `tts.py` voice · `sessions.py` session watcher ·
`builds.py` builds · `frontend\` the page · `jarvis_home\memory\MEMORY.md`
what he remembers.
