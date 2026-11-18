"""Windows control: apps, windows, screen, media keys, notifications, clipboard.

Everything goes through PowerShell or the Windows API. Inputs are handed to
PowerShell as environment variables, never pasted into the script, so names
with quotes or symbols can't break (or inject into) the command.
"""
from __future__ import annotations

import ctypes
import datetime as dt
import difflib
import json
import os
import subprocess
import tempfile
import time
from pathlib import Path

import config

_APPS_CACHE: tuple[float, list[dict]] = (0.0, [])


class NotOnWindows(RuntimeError):
    pass


def _need_windows() -> None:
    if not config.IS_WINDOWS:
        raise NotOnWindows("This only works on Windows.")


def ps(script: str, timeout: int = 20, **env: str) -> str:
    """Run a PowerShell script; values in **env are read as $env:NAME."""
    _need_windows()
    full_env = dict(os.environ)
    full_env.update({k: str(v) for k, v in env.items()})
    res = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
         "-Command", "[Console]::OutputEncoding=[Text.Encoding]::UTF8;" + script],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=timeout, env=full_env, creationflags=config.NO_WINDOW)
    if res.returncode != 0 and res.stderr.strip():
        raise RuntimeError(res.stderr.strip().splitlines()[0][:300])
    return res.stdout.strip()


def _json(out: str) -> list[dict]:
    if not out:
        return []
    data = json.loads(out)
    return data if isinstance(data, list) else [data]


# ── apps ─────────────────────────────────────────────────────────────
def installed_apps() -> list[dict]:
    global _APPS_CACHE
    if time.time() - _APPS_CACHE[0] < 600 and _APPS_CACHE[1]:
        return _APPS_CACHE[1]
    apps = _json(ps("Get-StartApps | Select-Object Name,AppID | ConvertTo-Json -Compress"))
    _APPS_CACHE = (time.time(), apps)
    return apps


_ALIASES = {"chrome": "google chrome", "word": "word", "excel": "excel",
            "vscode": "visual studio code", "vs code": "visual studio code",
            "code": "visual studio code", "explorer": "file explorer",
            "files": "file explorer", "verkenner": "file explorer",
            "rekenmachine": "calculator", "instellingen": "settings",
            "kladblok": "notepad", "terminal": "terminal"}


def open_app(name: str) -> str:
    query = _ALIASES.get(name.lower().strip(), name.lower().strip())
    apps = installed_apps()
    names = {a["Name"].lower(): a for a in apps if a.get("Name")}
    match = names.get(query)
    if not match:
        starts = [n for n in names if n.startswith(query) or query in n.split()]
        contains = [n for n in names if query in n]
        close = difflib.get_close_matches(query, list(names), n=1, cutoff=0.6)
        pick = (starts or contains or close or [None])[0]
        match = names.get(pick) if pick else None
    if not match:
        sugg = difflib.get_close_matches(query, list(names), n=5, cutoff=0.3)
        return f"No app called '{name}' found." + (
            f" Closest: {', '.join(names[s]['Name'] for s in sugg)}." if sugg else "")
    subprocess.Popen(["explorer.exe", f"shell:AppsFolder\\{match['AppID']}"],
                     creationflags=config.NO_WINDOW)
    return f"Opened {match['Name']}."


def open_url(url: str) -> str:
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    _need_windows()
    os.startfile(url)  # type: ignore[attr-defined]
    return f"Opened {url} in the default browser."


# ── windows ──────────────────────────────────────────────────────────
def list_windows() -> list[dict]:
    out = ps("Get-Process | Where-Object { $_.MainWindowTitle } | "
             "Select-Object Id,ProcessName,MainWindowTitle | ConvertTo-Json -Compress")
    return [{"pid": w["Id"], "app": w["ProcessName"], "title": w["MainWindowTitle"]}
            for w in _json(out)]


def _find_window(query: str) -> dict | None:
    q = query.lower()
    wins = list_windows()
    for w in wins:
        if q == str(w["pid"]) or q in w["title"].lower() or q == w["app"].lower():
            return w
    for w in wins:
        if q in w["app"].lower():
            return w
    return None


def focus_window(query: str) -> str:
    w = _find_window(query)
    if not w:
        return f"No open window matches '{query}'."
    ps("$s = New-Object -ComObject WScript.Shell; [void]$s.AppActivate([int]$env:PID_)",
       PID_=str(w["pid"]))
    return f"Brought '{w['title']}' to the front."


def close_window(query: str) -> str:
    w = _find_window(query)
    if not w:
        return f"No open window matches '{query}'."
    # CloseMainWindow is the same as clicking X: apps still ask to save work.
    ps("[void](Get-Process -Id ([int]$env:PID_)).CloseMainWindow()", PID_=str(w["pid"]))
    return f"Asked '{w['title']}' to close."


# ── screen ───────────────────────────────────────────────────────────
_SCREENSHOT = r"""
Add-Type -AssemblyName System.Windows.Forms,System.Drawing
Add-Type -TypeDefinition 'using System.Runtime.InteropServices; public class JDpi { [DllImport("user32.dll")] public static extern bool SetProcessDPIAware(); }'
[void][JDpi]::SetProcessDPIAware()
$b = [System.Windows.Forms.SystemInformation]::VirtualScreen
$bmp = New-Object System.Drawing.Bitmap $b.Width, $b.Height
$g = [System.Drawing.Graphics]::FromImage($bmp)
$g.CopyFromScreen($b.Left, $b.Top, 0, 0, $bmp.Size)
$max = [int]$env:MAXW
if ($bmp.Width -gt $max) {
  $h = [int]($bmp.Height * $max / $bmp.Width)
  $small = New-Object System.Drawing.Bitmap $max, $h
  $g2 = [System.Drawing.Graphics]::FromImage($small)
  $g2.InterpolationMode = 'HighQualityBicubic'
  $g2.DrawImage($bmp, 0, 0, $max, $h)
  $bmp = $small
}
$bmp.Save($env:OUT, [System.Drawing.Imaging.ImageFormat]::Jpeg)
"""


def screenshot(max_width: int = 1600) -> bytes:
    out = Path(tempfile.gettempdir()) / f"jarvis_shot_{os.getpid()}.jpg"
    ps(_SCREENSHOT, OUT=str(out), MAXW=str(max_width))
    data = out.read_bytes()
    out.unlink(missing_ok=True)
    return data


# ── media & system ───────────────────────────────────────────────────
_KEYS = {"play_pause": 0xB3, "next": 0xB0, "previous": 0xB1, "stop": 0xB2,
         "volume_up": 0xAF, "volume_down": 0xAE, "mute": 0xAD}


def _tap(vk: int, times: int = 1) -> None:
    _need_windows()
    user32 = ctypes.windll.user32  # type: ignore[attr-defined]
    for _ in range(times):
        user32.keybd_event(vk, 0, 0, 0)
        user32.keybd_event(vk, 0, 2, 0)   # KEYEVENTF_KEYUP


def media_key(key: str, times: int = 1) -> str:
    if key not in _KEYS:
        return f"Unknown key. Use one of: {', '.join(_KEYS)}."
    _tap(_KEYS[key], max(1, min(int(times), 50)))
    return f"Pressed {key.replace('_', ' ')}."


def set_volume(percent: int) -> str:
    percent = max(0, min(100, int(percent)))
    _tap(_KEYS["volume_down"], 50)          # each press is 2%
    _tap(_KEYS["volume_up"], round(percent / 2))
    return f"Volume set to about {percent} percent."


class _PowerStatus(ctypes.Structure):
    _fields_ = [("ACLineStatus", ctypes.c_byte), ("BatteryFlag", ctypes.c_byte),
                ("BatteryLifePercent", ctypes.c_byte), ("SystemStatusFlag", ctypes.c_byte),
                ("BatteryLifeTime", ctypes.c_ulong), ("BatteryFullLifeTime", ctypes.c_ulong)]


def system_status() -> dict:
    now = dt.datetime.now()
    info: dict = {"local_time": now.strftime("%A %d %B %Y, %H:%M")}
    if config.IS_WINDOWS:
        st = _PowerStatus()
        if ctypes.windll.kernel32.GetSystemPowerStatus(ctypes.byref(st)):  # type: ignore[attr-defined]
            pct = st.BatteryLifePercent & 0xFF
            info["battery_percent"] = None if pct == 255 else pct
            info["charging"] = st.ACLineStatus == 1
    return info


def lock_screen() -> str:
    _need_windows()
    ctypes.windll.user32.LockWorkStation()  # type: ignore[attr-defined]
    return "Screen locked."


def clipboard_get() -> str:
    return ps("Get-Clipboard -Raw")[:4000]


def clipboard_set(text: str) -> str:
    ps("Set-Clipboard -Value $env:CLIP", CLIP=text)
    return "Copied to the clipboard."


_TOAST = r"""
[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] > $null
$t = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent([Windows.UI.Notifications.ToastTemplateType]::ToastText02)
$x = $t.GetElementsByTagName('text')
[void]$x.Item(0).AppendChild($t.CreateTextNode($env:TTITLE))
[void]$x.Item(1).AppendChild($t.CreateTextNode($env:TBODY))
$app = '{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\WindowsPowerShell\v1.0\powershell.exe'
[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier($app).Show([Windows.UI.Notifications.ToastNotification]::new($t))
"""


def notify(title: str, body: str) -> str:
    ps(_TOAST, TTITLE=title[:120], TBODY=body[:400])
    return "Notification shown."
