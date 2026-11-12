// Global dock: audio player with waveform, live generation progress, and recovery actions.
import { store, on, emit } from "./store.js";
import { byId, fmtBytes, fmtDuration, fmtTime, h, setIcon, toast } from "./ui.js";
import { jobAction } from "./jobs.js";

const audio = new Audio();
audio.preload = "metadata";
let cur = null;               // file currently loaded in the player
let prev = null;              // what was loaded before a generation started
let seg = { active: false, next: 0, waiting: false, onSegment: false };
let handledJob = null;
let startedJobId = null;
const RATES = [1, 1.25, 1.5, 2, 0.75];
let rateIdx = 0;

const dock = () => byId("dock");
const show = (id, on_) => { byId(id).hidden = !on_; };
const cssVar = (n) => getComputedStyle(document.documentElement).getPropertyValue(n).trim();

function setMode(mode) {
  dock().dataset.mode = mode;
  const ready = mode === "ready", gen = mode === "generating";
  show("dockEmpty", mode === "empty");
  show("waveWrap", ready);
  show("progressWrap", gen);
  show("dockRate", ready); show("dockLoop", ready); show("dockVol", ready); show("dockDownload", ready);
  show("dockCancel", gen);
  byId("dockPlay").disabled = mode === "empty" || (gen && !(store.job && readyCount(store.job) > 0));
  show("dockListen", gen && store.job && readyCount(store.job) > 0 && !seg.active);
  if (mode !== "generating") hideNotice(false);
}

function setPlaying(p) {
  setIcon(byId("dockPlayIcon"), p ? "pause" : "play");
  byId("dockPlay").setAttribute("aria-label", p ? "Pause" : "Play");
}

// ------------------------------------------------------------- waveform
function drawWave() {
  const canvas = byId("waveCanvas"), wrap = byId("wave");
  const dpr = window.devicePixelRatio || 1, w = wrap.clientWidth, hgt = wrap.clientHeight;
  if (!w) return;
  if (canvas.width !== Math.round(w * dpr)) { canvas.width = Math.round(w * dpr); canvas.height = Math.round(hgt * dpr); }
  const ctx = canvas.getContext("2d");
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, w, hgt);
  const peaks = cur?.peaks?.length ? cur.peaks : new Array(120).fill(8);
  const dur = cur?.duration || audio.duration || 1;
  const progress = Math.min(1, audio.currentTime / dur);
  const n = peaks.length, step = w / n, bw = Math.max(2, step * 0.62);
  const on_ = cssVar("--accent"), off = cssVar("--wave");
  for (let i = 0; i < n; i++) {
    const bh = Math.max(3, (peaks[i] / 100) * (hgt - 4));
    ctx.fillStyle = i / n < progress ? on_ : off;
    ctx.beginPath();
    ctx.roundRect(i * step + (step - bw) / 2, (hgt - bh) / 2, bw, bh, bw / 2);
    ctx.fill();
  }
  const wv = byId("wave");
  wv.setAttribute("aria-valuenow", String(Math.round(progress * 100)));
}
let raf = 0;
const queueDraw = () => { if (!raf) raf = requestAnimationFrame(() => { raf = 0; drawWave(); }); };

function updateTime() {
  byId("timeCur").textContent = fmtTime(audio.currentTime);
  queueDraw();
}

// ------------------------------------------------------------- loading audio
export function loadEntry(entry, { play = false } = {}) {
  seg.active = false; seg.onSegment = false;
  cur = { id: entry.id, name: entry.name, duration: entry.duration_s, peaks: entry.peaks };
  audio.src = `/api/history/${entry.id}/audio`;
  audio.playbackRate = RATES[rateIdx];
  byId("dockTitle").textContent = entry.name;
  byId("dockSub").textContent = `${entry.voice_name} · ${entry.format.toUpperCase()} · ${fmtBytes(entry.size_bytes)}`;
  const dl = byId("dockDownload");
  dl.href = `/api/history/${entry.id}/download`;
  byId("timeTot").textContent = fmtTime(entry.duration_s);
  byId("timeCur").textContent = "0:00";
  setMode("ready"); setPlaying(false); queueDraw();
  if (play) audio.play().catch(() => {});
}
export const playEntry = (entry) => loadEntry(entry, { play: true });

// ------------------------------------------------------------- segment playback while generating
const readyCount = (job) => { let n = 0; for (const c of job.chunks) { if (c.status === "done") n++; else break; } return n; };

function playNextSegment() {
  const job = store.job;
  if (!seg.active || !job) return;
  const ready = readyCount(job);
  if (seg.next < ready) {
    audio.src = `/api/jobs/${job.id}/segments/${seg.next}`;
    audio.playbackRate = RATES[rateIdx];
    audio.play().catch(() => {});
    seg.onSegment = true; seg.waiting = false;
    byId("dockSub").textContent = `Playing segment ${seg.next + 1} of ${job.progress.total}`;
    seg.next++;
  } else if (["queued", "running"].includes(job.status)) {
    seg.waiting = true;
  } else {
    seg.active = false; seg.onSegment = false; setPlaying(false);
  }
}
function startListening() { seg = { active: true, next: 0, waiting: false, onSegment: false }; show("dockListen", false); playNextSegment(); }

// ------------------------------------------------------------- progress rendering
function drawStrip(job) {
  const c = byId("segStrip"), dpr = window.devicePixelRatio || 1;
  const w = c.clientWidth, hgt = c.clientHeight;
  if (!w) return;
  c.width = Math.round(w * dpr); c.height = Math.round(hgt * dpr);
  const ctx = c.getContext("2d"); ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  const n = job.chunks.length, cell = w / n, gap = cell > 5 ? 1.5 : 0;
  const colors = { done: cssVar("--accent"), pending: cssVar("--wave"), failed: cssVar("--danger"), running: cssVar("--text-3") };
  job.chunks.forEach((ch, i) => { ctx.fillStyle = colors[ch.status] || colors.pending; ctx.fillRect(i * cell, 0, Math.max(1, cell - gap), hgt); });
}

function progressText(job) {
  const p = job.progress, pct = Math.round(p.fraction * 100);
  if (job.status === "queued") return "Waiting to start…";
  if (job.phase === "loading_model") return "Loading the speech model… the first run takes a few seconds.";
  if (job.phase === "exporting") return "Finishing and saving your file…";
  if (job.cancelling) return "Stopping after the current segment…";
  const eta = job.eta_s != null ? ` · about ${fmtDuration(job.eta_s)} left` : "";
  const cur_ = Math.min(p.done + 1, p.total);
  return `Segment ${cur_} of ${p.total} · ${pct}%${eta}`;
}

function renderProgress(job) {
  setMode("generating");
  byId("dockTitle").textContent = job.name;
  byId("dockSub").textContent = seg.onSegment ? byId("dockSub").textContent : `${fmtDuration(job.elapsed_s)} elapsed`;
  byId("progressText").textContent = progressText(job);
  drawStrip(job);
  show("dockListen", readyCount(job) > 0 && !seg.active);
  byId("dockPlay").disabled = readyCount(job) === 0;
  byId("dockCancel").disabled = job.cancelling;
  if (seg.waiting) playNextSegment();
}

// ------------------------------------------------------------- notices (cancel / failures)
function hideNotice(clear = true) { show("notice", false); if (clear) byId("noticeActions").replaceChildren(); }
function showNotice(msg, kind, actions) {
  byId("noticeMsg").textContent = msg;
  byId("notice").className = `notice ${kind}`;
  byId("noticeActions").replaceChildren(...actions);
  show("notice", true);
}
const btn = (label, fn, cls = "btn btn-sm") => h("button", { class: cls, onclick: fn, text: label });

function finished(job) {
  if (handledJob === job.id + job.status) return;
  handledJob = job.id + job.status;
  seg.active = false; seg.onSegment = false;
  const p = job.progress;

  if (job.result) {
    loadEntry(job.result);
    emit("history:changed");
  } else if (prev) {
    cur = prev; setMode("ready");
    byId("dockTitle").textContent = prev.name;
  } else {
    setMode("empty"); byId("dockTitle").textContent = "No audio yet";
    byId("dockSub").textContent = "";
  }

  if (job.status === "done") { toast("Your audio is ready."); return; }
  const actions = [];
  if (job.can_retry) actions.push(btn(job.status === "cancelled" ? "Resume" : "Retry failed", () => jobAction("retry"), "btn btn-sm btn-primary"));
  if (job.can_finalize && !job.result) actions.push(btn("Export finished segments", () => jobAction("finalize")));
  actions.push(btn("Dismiss", () => hideNotice()));
  let msg = job.error || "Something went wrong.";
  if (job.status === "cancelled") msg = `Cancelled. ${p.done} of ${p.total} segments were finished and kept.`;
  showNotice(msg, job.status === "failed" ? "bad" : "warn", actions);
}

on("job:update", (job) => {
  if (["queued", "running"].includes(job.status)) {
    if (job.id !== startedJobId) { startedJobId = job.id; prev = cur; }
    if (!seg.active) audio.pause();
    handledJob = null;
    hideNotice();
    renderProgress(job);
  } else {
    finished(job);
  }
});

// ------------------------------------------------------------- init + controls
export function initPlayer() {
  byId("dockPlay").addEventListener("click", togglePlay);
  byId("dockListen").addEventListener("click", startListening);
  byId("dockCancel").addEventListener("click", () => jobAction("cancel"));
  byId("dockRate").addEventListener("click", () => {
    rateIdx = (rateIdx + 1) % RATES.length; audio.playbackRate = RATES[rateIdx];
    byId("dockRate").textContent = `${RATES[rateIdx]}×`;
  });
  byId("dockLoop").addEventListener("click", (e) => {
    audio.loop = !audio.loop; e.currentTarget.setAttribute("aria-pressed", String(audio.loop));
    e.currentTarget.classList.toggle("btn-primary", audio.loop);
  });
  byId("dockVol").addEventListener("input", (e) => { audio.volume = Number(e.target.value); });

  const wave = byId("wave");
  const seek = (clientX) => {
    const r = wave.getBoundingClientRect();
    const dur = cur?.duration || audio.duration;
    if (dur) audio.currentTime = Math.min(1, Math.max(0, (clientX - r.left) / r.width)) * dur;
  };
  wave.addEventListener("pointerdown", (e) => { wave.setPointerCapture(e.pointerId); seek(e.clientX); wave.onpointermove = (m) => seek(m.clientX); });
  wave.addEventListener("pointerup", () => { wave.onpointermove = null; });
  wave.addEventListener("keydown", (e) => {
    if (e.key === "ArrowRight") { audio.currentTime += 5; e.preventDefault(); }
    if (e.key === "ArrowLeft") { audio.currentTime = Math.max(0, audio.currentTime - 5); e.preventDefault(); }
  });

  audio.addEventListener("timeupdate", updateTime);
  audio.addEventListener("play", () => setPlaying(true));
  audio.addEventListener("pause", () => setPlaying(false));
  audio.addEventListener("ended", () => { if (seg.active) playNextSegment(); else setPlaying(false); });
  audio.addEventListener("error", () => { if (audio.src && !seg.onSegment) toast("That audio file could not be played.", "bad"); });
  window.addEventListener("resize", () => { queueDraw(); if (store.job && dock().dataset.mode === "generating") drawStrip(store.job); });
  on("theme:changed", queueDraw);
  setMode("empty");
}

export function togglePlay() {
  if (dock().dataset.mode === "generating") {
    if (!seg.active) return startListening();
  } else if (dock().dataset.mode !== "ready") return;
  if (audio.paused) audio.play().catch(() => {}); else audio.pause();
}
