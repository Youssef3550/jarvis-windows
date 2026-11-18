// Hassan front end: voice in (Whisper via server, fallback Web Speech API), voice out (Coqui/edge-tts via server, browser voice as last resort), dashboard.
(() => {
  const $ = (s) => document.querySelector(s);
  const store = {
    get(k, d) { try { const v = localStorage.getItem(k); return v === null ? d : JSON.parse(v); } catch { return d; } },
    set(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch {} },
  };

  const S = {
    ws: null, busy: false, listening: false, speaking: false,
    lang: store.get("lang", "en"), handsfree: store.get("handsfree", false),
    wakeword: store.get("wakeword", false),
    mutedUpTo: 0, latestTurn: 0, bubbles: {},
    whisperAvailable: false,   // set after /api/whisper_status check
  };

  // Check whether the Whisper endpoint is ready.
  fetch("/api/whisper_status").then((r) => r.json()).then((d) => {
    S.whisperAvailable = !!d.available;
  }).catch(() => { S.whisperAvailable = false; });

  // ── connection ────────────────────────────────────────────────────
  function connect() {
    // wss:// when the page is https (phone via Tailscale), ws:// on http://localhost.
    const ws = new WebSocket(`${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/ws`);
    S.ws = ws;
    ws.onopen = () => $("#conn").classList.add("on");
    ws.onclose = () => { $("#conn").classList.remove("on"); setTimeout(connect, 1500); };
    ws.onmessage = (e) => handle(JSON.parse(e.data));
  }
  function send(obj) { if (S.ws && S.ws.readyState === 1) S.ws.send(JSON.stringify(obj)); }

  function handle(m) {
    switch (m.type) {
      case "state": S.busy = m.busy; refreshState(); break;
      case "you":
        S.latestTurn = Math.max(S.latestTurn, m.turn);
        addMsg("you", m.text);
        break;
      case "text": {
        if (m.turn <= S.mutedUpTo) break;
        const b = bubble(m.turn);
        b.text.textContent += m.text;
        scrollLog();
        break;
      }
      case "text_break": { const b = S.bubbles[m.turn]; if (b && b.text.textContent && !b.text.textContent.endsWith("\n")) b.text.textContent += "\n"; break; }
      case "tool": {
        if (m.turn <= S.mutedUpTo) break;
        const chip = document.createElement("span");
        chip.className = "chip"; chip.textContent = "⚙ " + m.name;
        bubble(m.turn).chips.appendChild(chip);
        break;
      }
      case "say":
        if (m.turn !== -1 && m.turn <= S.mutedUpTo) break;
        enqueueSpeech(m);
        break;
      case "announce": addMsg("event", m.text); break;
      case "error": addMsg("error", m.text); break;
    }
  }

  // ── conversation log ─────────────────────────────────────────────
  function addMsg(kind, text) {
    const div = document.createElement("div");
    div.className = "msg " + kind;
    div.textContent = text;
    $("#log").appendChild(div);
    scrollLog();
    return div;
  }
  function bubble(turn) {
    if (!S.bubbles[turn]) {
      const div = addMsg("jarvis", "");
      const chips = document.createElement("div");
      const text = document.createElement("div");
      div.append(chips, text);
      S.bubbles[turn] = { div, chips, text };
    }
    return S.bubbles[turn];
  }
  function scrollLog() { const l = $("#log"); l.scrollTop = l.scrollHeight; }

  // ── speech out ────────────────────────────────────────────────────
  const audioEl = new Audio();
  let actx = null, analyser = null, queue = [], fakeLevel = false;
  function ensureAudio() {
    if (!actx) {
      actx = new AudioContext();
      const src = actx.createMediaElementSource(audioEl);
      analyser = actx.createAnalyser();
      analyser.fftSize = 512;
      src.connect(analyser);
      analyser.connect(actx.destination);
    }
    if (actx.state === "suspended") actx.resume();
  }
  document.addEventListener("pointerdown", ensureAudio);
  document.addEventListener("keydown", ensureAudio);

  // The server normally sends each sentence with its audio already made (Coqui WAV for
  // English, edge-tts MP3 for Dutch). If a sentence arrives without audio, we ask the
  // server's /tts endpoint right away (so it is ready by its turn), and only if that
  // fails too do we fall back to the browser's own voice.
  let epoch = 0, blobUrl = null, ttsDownUntil = 0;
  function enqueueSpeech(item) {
    if (!item.audio && Date.now() > ttsDownUntil) item.pending = fetchTts(item, epoch);
    queue.push(item);
    if (!S.speaking) playNext();
  }
  async function fetchTts(item, ep) {
    item.ctrl = new AbortController();
    try {
      const r = await fetch("/tts", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text: item.text, lang: item.lang }), signal: item.ctrl.signal,
      });
      if (!r.ok) { if (r.status === 503) ttsDownUntil = Date.now() + 60000; return null; }
      const blob = await r.blob();
      return ep === epoch ? URL.createObjectURL(blob) : null;
    } catch (e) {
      return null;
    }
  }
  function playSrc(src, item) {
    if (blobUrl && blobUrl !== src) URL.revokeObjectURL(blobUrl);
    blobUrl = src.startsWith("blob:") ? src : null;
    audioEl.src = src;
    audioEl.play().catch(() => browserVoice(item));
  }
  function playNext() {
    const item = queue.shift();
    if (!item) { S.speaking = false; $("#caption").textContent = ""; refreshState(); afterSpeech(); return; }
    if (!S.speaking) { S.speaking = true; pauseListeningForSpeech(); refreshState(); }
    $("#caption").textContent = item.text;
    if (item.audio) {
      playSrc(`data:${item.mime || "audio/mpeg"};base64,${item.audio}`, item);
    } else if (item.pending) {
      const ep = epoch;
      item.pending.then((url) => {
        if (ep !== epoch) { if (url) URL.revokeObjectURL(url); return; }   // interrupted meanwhile
        url ? playSrc(url, item) : browserVoice(item);
      });
    } else {
      browserVoice(item);
    }
  }
  audioEl.onended = playNext;
  audioEl.onerror = playNext;

  function browserVoice(item) {
    if (!("speechSynthesis" in window)) { playNext(); return; }
    const u = new SpeechSynthesisUtterance(item.text);
    u.lang = item.lang === "nl" ? "nl-BE" : "en-GB";
    const voices = speechSynthesis.getVoices().filter((v) => v.lang.startsWith(item.lang === "nl" ? "nl" : "en-GB"));
    if (voices.length) {
      // Prefer a male voice. "Female" also contains "male", so rule it out first.
      const male = (v) => !/female|hazel|susan|libby|sonia|maisie|dena|colette|fenna/i.test(v.name)
        && /\bmale\b|ryan|george|thomas|arnaud|maarten|frank|bart/i.test(v.name);
      u.voice = voices.find(male) || voices.find((v) => !/female|hazel|susan/i.test(v.name)) || voices[0];
    }
    u.onstart = () => (fakeLevel = true);
    u.onend = u.onerror = () => { fakeLevel = false; playNext(); };
    speechSynthesis.speak(u);
  }
  function stopSpeaking() {
    epoch++;                                   // drop any /tts answers still on the way
    for (const it of queue) if (it.ctrl) it.ctrl.abort();
    queue = [];
    audioEl.pause();
    if ("speechSynthesis" in window) speechSynthesis.cancel();
    fakeLevel = false;
    const was = S.speaking;
    S.speaking = false;
    $("#caption").textContent = "";
    return was;
  }
  function interrupt() {
    const wasSpeaking = stopSpeaking();
    if (wasSpeaking || S.busy) {
      S.mutedUpTo = S.latestTurn;
      send({ type: "interrupt" });
    }
  }

  const levelBuf = new Uint8Array(512);
  (function levelLoop(t) {
    let lvl = 0;
    if (fakeLevel) lvl = 0.25 + 0.2 * Math.abs(Math.sin(t / 90));
    else if (analyser && S.speaking) {
      analyser.getByteTimeDomainData(levelBuf);
      let sum = 0;
      for (const v of levelBuf) { const d = (v - 128) / 128; sum += d * d; }
      lvl = Math.min(1, Math.sqrt(sum / levelBuf.length) * 4);
    }
    Orb.setLevel(lvl);
    requestAnimationFrame(levelLoop);
  })(0);

  // ── speech in ─────────────────────────────────────────────────────
  // Two recording paths:
  //   Whisper (PTT)       – MediaRecorder -> POST /api/transcribe -> heard()
  //   Web Speech API      – fallback for hands-free mode or when Whisper unavailable

  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  const MIC_BLOCKED = window.isSecureContext
    ? "Microphone blocked. Allow it via the icon next to the address bar (on a phone: the site settings)."
    : "The microphone only works on https:// or http://localhost. On the phone, use the https://….ts.net address.";
  const canRecord = !!(window.MediaRecorder && navigator.mediaDevices && navigator.mediaDevices.getUserMedia);
  let rec = null, resumeAfterSpeech = false;

  // ── Whisper / MediaRecorder path ──────────────────────────────────
  let mediaRec = null, audioChunks = [];

  async function startWhisperRecording(byUser = false) {
    if (S.listening) return;
    if (byUser) interrupt();
    let stream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch {
      addMsg("error", MIC_BLOCKED);
      return;
    }
    audioChunks = [];
    mediaRec = new MediaRecorder(stream);   // Chrome/Android: webm, iOS Safari: mp4
    mediaRec.ondataavailable = (e) => { if (e.data.size > 0) audioChunks.push(e.data); };
    mediaRec.onstop = async () => {
      stream.getTracks().forEach((t) => t.stop());
      S.listening = false;
      $("#caption").textContent = S.lang === "nl" ? "Transcriberen…" : "Transcribing…";
      refreshState();
      const mime = mediaRec.mimeType || "audio/webm";
      const blob = new Blob(audioChunks, { type: mime });
      const ext = /mp4|m4a|aac/.test(mime) ? "mp4" : /ogg/.test(mime) ? "ogg" : /wav/.test(mime) ? "wav" : "webm";
      const fd = new FormData();
      fd.append("audio", blob, "audio." + ext);
      fd.append("lang", S.lang);
      try {
        const resp = await fetch("/api/transcribe", { method: "POST", body: fd });
        const data = await resp.json();
        if (data.text) heard(data.text);
        else $("#caption").textContent = "";
      } catch {
        addMsg("error", "Whisper transcription failed. Check server logs.");
        $("#caption").textContent = "";
      }
      refreshState();
      if (S.handsfree && !S.speaking) setTimeout(() => S.handsfree && !S.speaking && startListening(), 300);
    };
    mediaRec.start();
    S.listening = true;
    refreshState();
  }

  function stopWhisperRecording() {
    if (mediaRec && mediaRec.state === "recording") mediaRec.stop();
  }

  // ── Web Speech API path (fallback / hands-free) ───────────────────
  function startSRListening(byUser = false) {
    if (!SR) { addMsg("error", "Speech recognition isn't available in this browser. Use push-to-talk or type."); return; }
    if (S.listening) return;
    if (byUser) interrupt();
    rec = new SR();
    rec.lang = S.lang === "nl" ? "nl-BE" : "en-GB";
    rec.interimResults = true;
    rec.continuous = S.handsfree;
    rec.onresult = (e) => {
      let interim = "";
      for (let i = e.resultIndex; i < e.results.length; i++) {
        const r = e.results[i];
        if (r.isFinal) heard(r[0].transcript);
        else interim += r[0].transcript;
      }
      $("#caption").textContent = interim;
    };
    rec.onerror = (e) => {
      if (e.error === "not-allowed") addMsg("error", MIC_BLOCKED);
      else if (e.error !== "no-speech" && e.error !== "aborted") addMsg("error", "Mic: " + e.error);
    };
    rec.onend = () => {
      S.listening = false;
      refreshState();
      if (S.handsfree && !S.speaking && !resumeAfterSpeech) setTimeout(() => S.handsfree && !S.speaking && startListening(), 300);
    };
    try { rec.start(); S.listening = true; } catch { S.listening = false; }
    refreshState();
  }

  function stopSRListening() { if (rec && S.listening) rec.stop(); }

  // ── Unified entry points ──────────────────────────────────────────
  function useWhisperNow() {
    // Use Whisper for PTT; use Web Speech API for hands-free (needs built-in VAD).
    return S.whisperAvailable && canRecord && !S.handsfree;
  }

  function startListening(byUser = false) {
    if (useWhisperNow()) startWhisperRecording(byUser);
    else startSRListening(byUser);
  }

  function stopListening() {
    if (useWhisperNow()) stopWhisperRecording();
    else stopSRListening();
  }

  function pauseListeningForSpeech() {
    if (!S.handsfree) return;
    if (S.listening) { resumeAfterSpeech = true; if (rec) rec.abort(); }
  }
  function afterSpeech() {
    if (resumeAfterSpeech || S.handsfree) { resumeAfterSpeech = false; if (S.handsfree) startListening(); }
  }

  function heard(raw) {
    let text = raw.trim();
    if (!text) return;
    if (S.wakeword) {
      const m = text.match(/\b(hasan|hassan|hasaan|hassaan|asan|hasan's)\b[,.!]?\s*(.*)$/i);
      if (!m) return;
      text = m[2].trim();
      if (!text) { $("#caption").textContent = "Yes?"; return; }
    }
    $("#caption").textContent = "";
    send({ type: "user", text, lang: S.lang });
  }

  // ── UI wiring ─────────────────────────────────────────────────────
  function refreshState() {
    const state = S.listening ? "listening" : S.speaking ? "speaking" : S.busy ? "thinking" : "idle";
    Orb.setState(state);
    $("#mic").classList.toggle("live", S.listening);
    const labels = {
      listening: S.lang === "nl" ? "Ik luister…" : "Listening…",
      speaking: "", thinking: S.lang === "nl" ? "Even denken…" : "Thinking…",
      idle: S.handsfree ? "Hands-free is on" : "Click the orb or hold Space to talk",
    };
    $("#state-label").textContent = labels[state];
  }

  function toggleMic() { S.listening ? stopListening() : startListening(true); }
  $("#orb").addEventListener("click", toggleMic);
  $("#mic").addEventListener("click", toggleMic);

  let spaceHeld = false;
  document.addEventListener("keydown", (e) => {
    if (e.code !== "Space" || e.repeat || e.target.matches("input, textarea")) return;
    e.preventDefault();
    spaceHeld = true;
    if (S.listening) interrupt(); else startListening(true);
  });
  document.addEventListener("keyup", (e) => {
    if (e.code !== "Space" || !spaceHeld) return;
    spaceHeld = false;
    if (!S.handsfree) stopListening();
  });

  $("#text-form").addEventListener("submit", (e) => {
    e.preventDefault();
    const v = $("#text-input").value.trim();
    if (!v) return;
    interrupt();
    send({ type: "user", text: v, lang: S.lang });
    $("#text-input").value = "";
  });

  function setLang(l) {
    S.lang = l; store.set("lang", l);
    document.querySelectorAll("#lang button").forEach((b) => b.classList.toggle("on", b.dataset.lang === l));
    if (S.listening) { rec.abort(); setTimeout(startListening, 200); }
    refreshState();
  }
  document.querySelectorAll("#lang button").forEach((b) => b.addEventListener("click", () => setLang(b.dataset.lang)));
  setLang(S.lang);

  $("#handsfree").checked = S.handsfree;
  $("#handsfree").addEventListener("change", (e) => {
    S.handsfree = e.target.checked; store.set("handsfree", S.handsfree);
    if (S.listening) rec.abort();
    if (S.handsfree) setTimeout(startListening, 200);
    refreshState();
  });
  $("#wakeword").checked = S.wakeword;
  $("#wakeword").addEventListener("change", (e) => { S.wakeword = e.target.checked; store.set("wakeword", S.wakeword); });

  $("#reset").addEventListener("click", () => {
    interrupt();
    $("#log").innerHTML = "";
    S.bubbles = {};
    send({ type: "reset" });
  });

  // ── tabs ──────────────────────────────────────────────────────────
  let view = "talk";
  document.querySelectorAll(".tab").forEach((t) => t.addEventListener("click", () => {
    view = t.dataset.view;
    document.querySelectorAll(".tab").forEach((x) => x.classList.toggle("active", x === t));
    document.querySelectorAll(".view").forEach((v) => v.classList.toggle("active", v.id === "view-" + view));
    refreshPanels();
  }));

  const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  function ago(ts) {
    if (!ts) return "";
    const s = Math.max(0, Date.now() / 1000 - ts);
    if (s < 60) return "just now";
    if (s < 3600) return Math.floor(s / 60) + " min ago";
    return Math.floor(s / 3600) + " h ago";
  }
  const label = (s) => s.replace("_", " ");

  async function refreshPanels() {
    try {
      const sessions = await (await fetch("/api/sessions")).json();
      const n = sessions.filter((s) => s.status === "needs_you").length;
      $("#needs-badge").hidden = !n;
      $("#needs-badge").textContent = n;
      if (view === "sessions") {
        $("#sessions").innerHTML = sessions.length ? sessions.map((s) => `
          <div class="card ${s.status}">
            <h3><span>${esc(s.project)}</span><span class="pill ${s.status}">${label(s.status)}</span></h3>
            <div class="meta">${esc(s.cwd)} · ${ago(s.since)}</div>
            ${s.last_prompt ? `<div class="meta">“${esc(s.last_prompt)}”</div>` : ""}
            ${s.status === "needs_you" && s.reason ? `<div class="reason">${esc(s.reason)}</div>` : ""}
          </div>`).join("") : `<p class="empty">No Claude Code sessions in the last 12 hours.</p>`;
      }
      if (view === "builds") {
        const builds = await (await fetch("/api/builds")).json();
        $("#builds").innerHTML = builds.length ? builds.map((b) => {
          const p = b.progress || {};
          const pct = p.total ? Math.round((100 * p.done) / p.total) : 0;
          return `<div class="card">
            <h3><span>${esc(b.project)}</span><span class="pill ${b.status}">${esc(b.status)}</span></h3>
            <div class="meta">${esc(b.path)} · ${esc(b.mode)} · ${ago(b.started)}${b.cost ? " · $" + b.cost.toFixed(2) : ""}</div>
            ${p.plan ? `<div class="bar"><span style="width:${pct}%"></span></div>
              <div class="meta">${p.done}/${p.total} tasks${p.next_task ? " · next: " + esc(p.next_task) : ""}</div>`
              : `<div class="meta">Waiting for the plan…</div>`}
            ${b.last_text ? `<div class="meta">${esc(b.last_text)}</div>` : ""}
            ${b.error ? `<div class="reason">${esc(b.error)}</div>` : ""}
          </div>`;
        }).join("") : `<p class="empty">No builds yet. Ask Hassan to build something.</p>`;
      }
      if (view === "memory") {
        const facts = await (await fetch("/api/memory")).json();
        $("#memory").innerHTML = facts.length ? facts.map((f) =>
          `<li><span>${esc(f)}</span><button data-f="${esc(f)}" title="Forget">✕</button></li>`).join("")
          : `<li class="empty">Nothing yet. Say "remember that…"</li>`;
        $("#memory").querySelectorAll("button").forEach((b) => b.addEventListener("click", async () => {
          await fetch("/api/memory/forget", { method: "POST", headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ text: b.dataset.f }) });
          refreshPanels();
        }));
      }
    } catch {}
  }
  setInterval(refreshPanels, 3000);

  connect();
  refreshPanels();
  refreshState();
  if (S.handsfree) addMsg("event", "Hands-free is on: click anywhere once to start the microphone.");
  document.addEventListener("pointerdown", () => { if (S.handsfree && !S.listening && !S.speaking) startListening(); }, { once: true });
})();
