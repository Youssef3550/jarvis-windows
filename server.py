"""JARVIS for Windows: the local web server that ties everything together.

Run it with start.bat, then open http://localhost:8340 in Chrome.
"""
from __future__ import annotations

import asyncio
import base64
import logging
import os
import subprocess
import webbrowser
import time
from collections import deque
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles

import config
import memory_store
import tts
import whisper_stt
import winctl
from brain import Brain
from builds import BuildManager
from sessions import SessionWatcher

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s: %(message)s",
                    datefmt="%H:%M:%S")
log = logging.getLogger("jarvis")


class Hub:
    """Connects the browser, the brain, the voice and the watchers."""

    def __init__(self) -> None:
        self.clients: set[WebSocket] = set()
        self.brain = Brain(self.on_brain_event)
        self.watcher = SessionWatcher()
        self.builds = BuildManager(self.announce)
        self.turn = 0                  # id of the turn currently being answered
        self.turn_lang = "en"
        self.muted: set[int] = set()   # turns the user interrupted
        self.splitter = tts.SentenceSplitter()
        self.speech_queue: asyncio.Queue = asyncio.Queue()
        self.deferred: list[str] = []
        self.busy = False
        self.inflight: deque[tuple[int, str]] = deque()   # turns sent, oldest first
        self.memory_mtime = self._memory_mtime()

    # ── browser ──────────────────────────────────────────────────────
    async def send_all(self, msg: dict) -> None:
        dead = []
        for ws in list(self.clients):
            try:
                await ws.send_json(msg)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.clients.discard(ws)

    async def set_busy(self, busy: bool) -> None:
        self.busy = busy
        await self.send_all({"type": "state", "busy": busy})

    @staticmethod
    def _memory_mtime() -> float:
        try:
            return config.MEMORY_FILE.stat().st_mtime
        except OSError:
            return 0.0

    def _memory_update_note(self) -> str:
        """If the memory file changed outside a conversation (the sync job), pass it on."""
        mtime = self._memory_mtime()
        if mtime <= self.memory_mtime + 1:
            return ""
        self.memory_mtime = mtime
        try:
            text = config.MEMORY_FILE.read_text(encoding="utf-8")
        except OSError:
            return ""
        return ("[event] Your memory file was just synced with Claude's memory. "
                "This is the current version; it replaces what you knew before:\n"
                + text + "\n[end of memory]\n\n")

    async def user_message(self, text: str, lang: str) -> None:
        text = text.strip()
        if not text:
            return
        self.turn += 1
        lang = "nl" if lang == "nl" else "en"
        self.inflight.append((self.turn, lang))
        await self.send_all({"type": "you", "turn": self.turn, "text": text})
        await self.set_busy(True)
        note = self._memory_update_note()
        await self.brain.send(f"{note}[{lang}] {text}")

    # ── speech ───────────────────────────────────────────────────────
    def speak(self, text: str, turn: int, default_lang: str) -> None:
        clean = tts.clean_for_speech(text)
        if not clean or turn in self.muted:
            return
        lang = tts.detect_language(clean, default_lang)
        task = asyncio.create_task(tts.synthesize(clean, lang))
        self.speech_queue.put_nowait((turn, clean, lang, task))

    async def speech_worker(self) -> None:
        while True:
            turn, text, lang, task = await self.speech_queue.get()
            result = await task
            if turn in self.muted:
                continue
            audio, mime = result if result else (None, None)
            await self.send_all({"type": "say", "turn": turn, "text": text, "lang": lang,
                                 "audio": base64.b64encode(audio).decode() if audio else None,
                                 "mime": mime})

    # ── brain events ─────────────────────────────────────────────────
    async def on_brain_event(self, ev: dict) -> None:
        kind = ev["kind"]
        # The brain answers messages in order, so the oldest one sent is the one
        # this event belongs to.
        turn, self.turn_lang = self.inflight[0] if self.inflight else (self.turn, self.turn_lang)
        if kind == "done":
            # facts Hassan saved himself this turn are not news to him
            self.memory_mtime = max(self.memory_mtime, self._memory_mtime())
        if kind == "text":
            if turn not in self.muted:
                await self.send_all({"type": "text", "turn": turn, "text": ev["text"]})
            for sentence in self.splitter.feed(ev["text"]):
                self.speak(sentence, turn, self.turn_lang)
        elif kind == "block_end":
            for sentence in self.splitter.flush():
                self.speak(sentence, turn, self.turn_lang)
            await self.send_all({"type": "text_break", "turn": turn})
        elif kind == "tool":
            name = ev["name"].replace("mcp__jarvis__", "").replace("_", " ")
            await self.send_all({"type": "tool", "turn": turn, "name": name})
        elif kind == "done":
            for sentence in self.splitter.flush():
                self.speak(sentence, turn, self.turn_lang)
            if self.inflight:
                self.inflight.popleft()
            if ev.get("is_error") and ev.get("result"):
                await self.send_all({"type": "error", "text": str(ev["result"])[:300]})
            if self.brain.pending_turns == 0:
                await self.set_busy(False)
                await self.flush_deferred()
        elif kind == "exit":
            self.inflight.clear()
            self.splitter = tts.SentenceSplitter()
            await self.set_busy(False)
            if ev.get("code"):
                log.warning("brain exited with %s: %s", ev["code"], ev.get("stderr"))
                await self.send_all({"type": "error", "text":
                    "My brain process stopped. I'll restart it with your next message. "
                    + (ev.get("stderr") or "")[-300:]})

    # ── announcements (sessions, builds) ─────────────────────────────
    async def announce(self, text: str, urgent: bool) -> None:
        if not self.clients:
            try:
                await asyncio.to_thread(winctl.notify, "Hassan", text)
            except Exception as exc:
                log.info("notify failed: %s", exc)
            return
        if urgent or not self.busy:
            await self.send_all({"type": "announce", "text": text})
            self.speak(text, -1, "en")
        else:
            self.deferred.append(text)

    async def flush_deferred(self) -> None:
        if self.deferred:
            items, self.deferred = self.deferred, []
            text = " ".join(items) if len(items) < 4 else f"{len(items)} sessions finished."
            await self.send_all({"type": "announce", "text": text})
            self.speak(text, -1, "en")

    async def scan_loop(self) -> None:
        while True:
            try:
                await asyncio.to_thread(self.watcher.scan)
            except Exception:
                log.exception("session scan failed")
            await asyncio.sleep(3)


hub: Hub


def open_browser() -> None:
    url = f"http://localhost:{config.PORT}"
    if config.IS_WINDOWS:
        # Speech recognition needs Chrome, so prefer it over the default browser.
        for base in (os.environ.get("PROGRAMFILES"), os.environ.get("PROGRAMFILES(X86)"),
                     os.environ.get("LOCALAPPDATA")):
            chrome = os.path.join(base or "", "Google", "Chrome", "Application", "chrome.exe")
            if base and os.path.exists(chrome):
                subprocess.Popen([chrome, url])
                return
    webbrowser.open(url)


@asynccontextmanager
async def lifespan(app: FastAPI):
    global hub
    hub = Hub()
    hub.builds.loop = asyncio.get_running_loop()
    try:
        hub.brain.start()
    except FileNotFoundError:
        log.error("Claude Code was not found. Install it and run `claude` once to log in.")
    tasks = [asyncio.create_task(hub.speech_worker()), asyncio.create_task(hub.scan_loop()),
             asyncio.create_task(asyncio.to_thread(tts.warm_up))]   # load Coqui voice early
    log.info("JARVIS is ready at http://localhost:%s", config.PORT)
    if os.environ.get("OPEN_BROWSER") == "1":
        asyncio.get_running_loop().call_later(1.0, open_browser)
    yield
    for t in tasks:
        t.cancel()
    hub.brain.stop()


app = FastAPI(lifespan=lifespan)


@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    await ws.accept()
    hub.clients.add(ws)
    await ws.send_json({"type": "state", "busy": hub.busy, "user": config.USER_NAME})
    try:
        while True:
            msg = await ws.receive_json()
            t = msg.get("type")
            if t == "user":
                await hub.user_message(msg.get("text", ""), msg.get("lang", "en"))
            elif t == "interrupt":
                hub.muted.update(t for t, _ in hub.inflight)
                hub.muted.add(hub.turn)
                hub.muted.add(-1)
                # announcements are muted only until the next one arrives
                asyncio.get_running_loop().call_later(0.5, hub.muted.discard, -1)
            elif t == "reset":
                hub.muted.update(t for t, _ in hub.inflight)
                hub.inflight.clear()
                await asyncio.to_thread(hub.brain.reset)
                await hub.set_busy(False)
                await ws.send_json({"type": "announce", "text": "New conversation started."})
    except WebSocketDisconnect:
        pass
    finally:
        hub.clients.discard(ws)


# ── API used by the dashboard, the hooks and the brain's tools ───────
@app.get("/api/status")
async def api_status():
    return {"brain_alive": hub.brain.alive(), "session_id": hub.brain.session_id,
            "model": config.BRAIN_MODEL, "busy": hub.busy, "user": config.USER_NAME,
            "projects_dir": str(config.PROJECTS_DIR), "time": time.time()}


@app.get("/api/sessions")
async def api_sessions():
    return hub.watcher.listing()


@app.post("/api/hooks/{event}")
async def api_hook(event: str, request: Request):
    try:
        payload = await request.json()
    except Exception:
        payload = {}
    ann = hub.watcher.handle_hook(event, payload)
    if ann:
        await hub.announce(ann["text"], ann["urgent"])
    return {"ok": True}


@app.get("/api/builds")
async def api_builds():
    return hub.builds.listing()


@app.get("/api/builds/{key}")
async def api_build(key: str):
    return hub.builds.status(key)


@app.post("/api/builds")
async def api_start_build(request: Request):
    body = await request.json()
    try:
        b = hub.builds.start(body["project"], body["spec"], body.get("mode", "window"))
    except (KeyError, ValueError, OSError) as exc:
        raise HTTPException(400, str(exc))
    return b


@app.post("/api/builds/{key}/stop")
async def api_stop_build(key: str):
    return {"message": hub.builds.stop(key)}


@app.get("/api/memory")
async def api_memory():
    return memory_store.list_facts()


@app.post("/api/memory/forget")
async def api_forget(request: Request):
    body = await request.json()
    return {"message": memory_store.forget(body.get("text", ""))}


@app.get("/api/whisper_status")
async def api_whisper_status():
    return {"available": whisper_stt.available(), "model": config.WHISPER_MODEL}


@app.post("/api/transcribe")
async def api_transcribe(request: Request):
    content_type = request.headers.get("content-type", "")
    if "multipart/form-data" in content_type:
        form = await request.form()
        audio_field = form.get("audio")
        if audio_field is None:
            raise HTTPException(400, "Missing 'audio' field")
        audio_bytes = await audio_field.read()
        lang = str(form.get("lang", "en"))
    else:
        audio_bytes = await request.body()
        lang = request.query_params.get("lang", "en")

    if not audio_bytes:
        raise HTTPException(400, "Empty audio")
    if not whisper_stt.available():
        raise HTTPException(503, "faster-whisper is not installed. "
                            "Run: pip install faster-whisper av")
    try:
        text = await asyncio.to_thread(whisper_stt.transcribe, audio_bytes, lang)
    except Exception as exc:
        log.error("Whisper error: %s", exc)
        raise HTTPException(500, f"Transcription failed: {exc}")
    return {"text": text}


@app.post("/tts")
async def api_tts(request: Request):
    """Text in ({"text": ..., "lang": "en"|"nl"}), audio out (audio/wav from Coqui,
    audio/mpeg from edge-tts). 503 if no voice engine works: use the browser voice."""
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(400, 'Send JSON: {"text": "...", "lang": "en"}')
    text = tts.clean_for_speech(str(body.get("text", "")))[:2000]
    if not text:
        raise HTTPException(400, "Empty text")
    lang = body.get("lang") or tts.detect_language(text)
    result = await tts.synthesize(text, "nl" if lang == "nl" else "en")
    if not result:
        raise HTTPException(503, "No voice engine available")
    audio, mime = result
    return Response(content=audio, media_type=mime, headers={"Cache-Control": "no-store"})


@app.get("/api/tts_status")
async def api_tts_status():
    c = tts.coqui
    return {"engine": config.TTS_ENGINE, "coqui_installed": tts.CoquiVoice.installed(),
            "coqui_ready": bool(c and c._model is not None), "coqui_error": c.error if c else None,
            "model": config.COQUI_MODEL, "speaker": c.speaker if c else None}


@app.get("/")
async def index():
    return FileResponse(config.FRONTEND_DIR / "index.html",
                        headers={"Cache-Control": "no-store"})


app.mount("/static", StaticFiles(directory=config.FRONTEND_DIR), name="static")


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=config.PORT, log_level="warning")
