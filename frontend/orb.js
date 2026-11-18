// The orb: a rotating sphere of particles that breathes with Hassan's voice.
(() => {
  const canvas = document.getElementById("orb");
  const ctx = canvas.getContext("2d");
  const N = 1100;
  const pts = [];
  const golden = Math.PI * (3 - Math.sqrt(5));
  for (let i = 0; i < N; i++) {
    const y = 1 - (i / (N - 1)) * 2;
    const r = Math.sqrt(1 - y * y);
    const t = golden * i;
    pts.push({ x: Math.cos(t) * r, y, z: Math.sin(t) * r, j: Math.random() * Math.PI * 2 });
  }

  const COLORS = {
    idle: [79, 170, 255],
    listening: [79, 214, 255],
    thinking: [255, 181, 71],
    speaking: [120, 225, 255],
  };
  const orb = { state: "idle", level: 0, smooth: 0, rot: 0, color: [...COLORS.idle] };
  window.Orb = {
    setState(s) { orb.state = s; },
    setLevel(v) { orb.level = v; },
  };

  function resize() {
    const dpr = window.devicePixelRatio || 1;
    const rect = canvas.getBoundingClientRect();
    canvas.width = rect.width * dpr;
    canvas.height = rect.height * dpr;
  }
  window.addEventListener("resize", resize);
  resize();

  function frame(now) {
    const w = canvas.width, h = canvas.height;
    const t = now / 1000;
    ctx.clearRect(0, 0, w, h);
    const target = COLORS[orb.state] || COLORS.idle;
    for (let k = 0; k < 3; k++) orb.color[k] += (target[k] - orb.color[k]) * 0.06;
    orb.smooth += (orb.level - orb.smooth) * 0.25;

    const speed = orb.state === "thinking" ? 0.9 : orb.state === "listening" ? 0.35 : 0.18;
    orb.rot += speed / 60;
    const breathe = orb.state === "thinking" ? 0.03 * Math.sin(t * 5) : 0.015 * Math.sin(t * 1.3);
    const R = Math.min(w, h) * 0.32 * (1 + breathe + orb.smooth * 0.35);
    const cx = w / 2, cy = h / 2;
    const [cr, cg, cb] = orb.color.map(Math.round);

    // glow
    const g = ctx.createRadialGradient(cx, cy, R * 0.2, cx, cy, R * 1.6);
    g.addColorStop(0, `rgba(${cr},${cg},${cb},${0.10 + orb.smooth * 0.25})`);
    g.addColorStop(1, "rgba(0,0,0,0)");
    ctx.fillStyle = g;
    ctx.fillRect(0, 0, w, h);

    const cos = Math.cos(orb.rot), sin = Math.sin(orb.rot);
    const tilt = 0.35, ct = Math.cos(tilt), st = Math.sin(tilt);
    const dot = Math.max(1, w / 420);
    for (const p of pts) {
      const wob = 1 + orb.smooth * 0.18 * Math.sin(t * 6 + p.j);
      let x = p.x * cos - p.z * sin;
      let z = p.x * sin + p.z * cos;
      let y = p.y * ct - z * st;
      z = p.y * st + z * ct;
      const persp = 1.8 / (2.6 - z);
      const sx = cx + x * R * wob * persp;
      const sy = cy + y * R * wob * persp;
      const a = 0.18 + 0.82 * ((z + 1) / 2);
      ctx.fillStyle = `rgba(${cr},${cg},${cb},${a})`;
      ctx.fillRect(sx, sy, dot * persp, dot * persp);
    }
    requestAnimationFrame(frame);
  }
  requestAnimationFrame(frame);
})();
