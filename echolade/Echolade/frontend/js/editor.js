// Studio: script editor, delivery/export controls and the Generate action.
import { api } from "./api.js";
import { store, on, emit } from "./store.js";
import { byId, $$, confirmDialog, debounce, fmtDuration, icon, toast } from "./ui.js";
import { startJob, isRunning } from "./jobs.js";

const DRAFT_KEY = "echolade.draft";
const CPS_KEY = "echolade.cps1";          // measured characters/second at 1.0× (from your own results)
const DEFAULT_CPS = 15;
const MAX_CHARS = 100000;
const SAMPLE = "Welcome to Echolade. Everything you hear is created on this computer, with no account and no upload.\n\nWrite a few paragraphs, choose a voice, and press Generate. Your audio will appear in the player below, ready to download.";

const script = () => byId("script");
let pending = {};

// ---------------------------------------------------------------- settings sync
const flush = debounce(async () => {
  const patch = pending; pending = {};
  try { store.settings = await api("/api/settings", { method: "PATCH", body: patch }); }
  catch (e) { toast(e.message, "bad"); }
}, 400);
export function saveSetting(patch) { Object.assign(store.settings, patch); pending = { ...pending, ...patch }; flush(); }

export function applySettingsToInputs() {
  const s = store.settings;
  byId("speed").value = s.speed; byId("volume").value = s.volume_db;
  byId("pause").value = s.paragraph_pause_ms;
  byId("bitrate").value = s.mp3_bitrate; byId("sampleRate").value = s.sample_rate; byId("channels").value = s.channels;
  $$('input[name="format"]').forEach((r) => (r.checked = r.value === s.format));
  readouts(); updateVoiceCard(); updateCounts();
}

function readouts() {
  byId("speedOut").textContent = `${Number(byId("speed").value).toFixed(2)}×`;
  const v = Number(byId("volume").value);
  byId("volumeOut").textContent = `${v > 0 ? "+" : ""}${v} dB`;
  byId("pauseOut").textContent = `${(Number(byId("pause").value) / 1000).toFixed(1)} s`;
  byId("bitrateField").hidden = $$('input[name="format"]:checked')[0]?.value !== "mp3";
}

export function updateVoiceCard() {
  const v = store.voices.find((x) => x.id === store.settings?.default_voice);
  byId("voiceName").textContent = v ? v.name : (store.settings?.default_voice || "—");
  byId("voiceSub").textContent = v ? `${v.language_label} · ${v.gender || "voice"}` : "Voice not available";
  byId("voiceAvatar").textContent = (v ? v.name : "?").slice(0, 2).toUpperCase();
}

export function renderProfiles() {
  const sel = byId("profile");
  if (!store.system) return;
  sel.replaceChildren(...store.system.profiles.map((p) => Object.assign(document.createElement("option"), { value: p.id, textContent: p.label })));
  sel.value = store.settings.profile;
  const p = store.system.profiles.find((x) => x.id === sel.value);
  byId("profileHelp").textContent = p ? `${p.description} Now: ${store.system.runtime.reason}` : "";
}

// ---------------------------------------------------------------- counts + draft
function stats(text) {
  const t = text.trim();
  return { chars: text.length, words: t ? t.split(/\s+/).length : 0, paras: t ? t.split(/\n\s*\n/).filter((p) => p.trim()).length : 0 };
}
function updateCounts() {
  const { chars, words, paras } = stats(script().value);
  byId("stWords").textContent = `${words.toLocaleString()} ${words === 1 ? "word" : "words"}`;
  const c = byId("stChars");
  c.textContent = `${chars.toLocaleString()} / ${MAX_CHARS.toLocaleString()} characters`;
  c.classList.toggle("over", chars > MAX_CHARS);
  byId("stParas").textContent = `${paras} ${paras === 1 ? "paragraph" : "paragraphs"}`;
  const cps = Number(localStorage.getItem(CPS_KEY)) || DEFAULT_CPS;
  const speed = Number(byId("speed").value) || 1;
  const secs = chars ? chars / (cps * speed) : 0;
  byId("stDur").textContent = chars ? `Estimated ≈ ${fmtDuration(secs)}` : "Estimated —";
  byId("generateBtn").disabled = isRunning() || !engineReady() || chars === 0;
}
const saveDraft = debounce(() => {
  try {
    localStorage.setItem(DRAFT_KEY, JSON.stringify({ name: byId("projectName").value, text: script().value }));
    byId("draftState").textContent = "Draft saved on this device";
  } catch { byId("draftState").textContent = "Draft could not be saved"; }
}, 400);

const engineReady = () => !!store.system?.engines?.[0]?.available;

// ---------------------------------------------------------------- import
function stripMarkdown(md) {
  return md.replace(/```[\s\S]*?```/g, "").replace(/`([^`]*)`/g, "$1").replace(/!\[[^\]]*\]\([^)]*\)/g, "")
    .replace(/\[([^\]]+)\]\([^)]*\)/g, "$1").replace(/^#{1,6}\s+/gm, "").replace(/(\*\*|__)(.*?)\1/g, "$2")
    .replace(/(\*|_)(.*?)\1/g, "$2").replace(/^\s*>\s?/gm, "").replace(/^\s*([-*+]|\d+\.)\s+/gm, "").replace(/^---+$/gm, "");
}
async function importFile(file) {
  if (!file) return;
  const ext = file.name.split(".").pop().toLowerCase();
  if (!["txt", "md", "markdown"].includes(ext)) return toast("Only .txt and .md files can be imported.", "bad");
  if (file.size > 1_000_000) return toast("That file is larger than 1 MB. Split it into smaller parts.", "bad");
  let text;
  try { text = await file.text(); } catch { return toast("That file could not be read.", "bad"); }
  if (text.includes("\u0000")) return toast("That doesn’t look like a plain-text file.", "bad");
  if (script().value.trim() && !(await confirmDialog({ title: "Replace your current text?", text: "Importing will replace what is in the editor.", yes: "Replace" }))) return;
  const isMd = ext !== "txt";
  script().value = isMd ? stripMarkdown(text) : text;     // text only: never rendered as HTML
  byId("projectName").value = file.name.replace(/\.[^.]+$/, "").slice(0, 80) || "Untitled voiceover";
  updateCounts(); saveDraft();
  toast(isMd ? "Imported. Markdown formatting was removed; please review the text." : "Imported.");
}

// ---------------------------------------------------------------- generate
export async function generate() {
  if (isRunning()) return;
  const text = script().value;
  if (!text.trim()) { toast("Add some text first.", "bad"); script().focus(); return; }
  const s = store.settings;
  const body = {
    text, name: byId("projectName").value.trim() || "Untitled voiceover", engine: "kokoro",
    delivery: { voice: s.default_voice, speed: s.speed, volume_db: s.volume_db, paragraph_pause_ms: s.paragraph_pause_ms },
    export: { format: s.format, mp3_bitrate: s.mp3_bitrate, sample_rate: s.sample_rate, channels: s.channels },
  };
  try { await startJob(body); } catch (e) { toast(e.message, "bad"); updateCounts(); }
}

function setGenerateState() {
  const btn = byId("generateBtn"), running = isRunning();
  const label = byId("generateLabel");
  btn.firstElementChild?.remove();
  btn.prepend(running ? Object.assign(document.createElement("span"), { className: "spinner" }) : icon("sparkle"));
  label.textContent = running ? "Generating…" : "Generate";
  updateCounts();
}

export function initStudio() {
  try {
    const d = JSON.parse(localStorage.getItem(DRAFT_KEY) || "null");
    if (d) { script().value = d.text || ""; byId("projectName").value = d.name || "Untitled voiceover"; }
  } catch { /* ignore corrupt draft */ }

  script().addEventListener("input", () => { updateCounts(); saveDraft(); });
  byId("projectName").addEventListener("input", saveDraft);
  byId("importBtn").addEventListener("click", () => byId("importFile").click());
  byId("importFile").addEventListener("change", (e) => { importFile(e.target.files[0]); e.target.value = ""; });
  byId("sampleBtn").addEventListener("click", () => { script().value = SAMPLE; updateCounts(); saveDraft(); });
  byId("clearBtn").addEventListener("click", async () => {
    if (!script().value) return;
    if (await confirmDialog({ title: "Clear the text?", text: "This removes everything in the editor.", yes: "Clear", danger: true })) {
      script().value = ""; updateCounts(); saveDraft(); script().focus();
    }
  });
  byId("generateBtn").addEventListener("click", generate);
  byId("voiceCard").addEventListener("click", () => emit("voice:pick"));

  byId("speed").addEventListener("input", () => { readouts(); updateCounts(); saveSetting({ speed: Number(byId("speed").value) }); });
  byId("volume").addEventListener("input", () => { readouts(); saveSetting({ volume_db: Number(byId("volume").value) }); });
  byId("pause").addEventListener("input", () => { readouts(); saveSetting({ paragraph_pause_ms: Number(byId("pause").value) }); });
  $$('input[name="format"]').forEach((r) => r.addEventListener("change", () => { saveSetting({ format: r.value }); readouts(); }));
  byId("bitrate").addEventListener("change", (e) => saveSetting({ mp3_bitrate: Number(e.target.value) }));
  byId("sampleRate").addEventListener("change", (e) => saveSetting({ sample_rate: Number(e.target.value) }));
  byId("channels").addEventListener("change", (e) => saveSetting({ channels: Number(e.target.value) }));
  byId("profile").addEventListener("change", async (e) => {
    saveSetting({ profile: e.target.value });
    setTimeout(async () => { store.system = await api("/api/system"); renderProfiles(); emit("system:update"); }, 600);
  });

  on("job:update", (job) => {
    setGenerateState();
    if (job.status === "done" && job.result?.chars && job.result.duration_s > 1) {
      // learn your real speaking rate so the estimate gets more accurate over time
      const cps = (job.result.chars / job.metrics.audio_s) / store.settings.speed;
      if (isFinite(cps) && cps > 4 && cps < 40) localStorage.setItem(CPS_KEY, cps.toFixed(2));
    }
  });
  on("voice:changed", () => { updateVoiceCard(); });
  on("system:update", () => { updateCounts(); renderProfiles(); });
  applySettingsToInputs(); renderProfiles(); setGenerateState();
}

export function showSetupBanner() {
  const e = store.system?.engines?.[0];
  byId("setupBanner").hidden = !e || e.available;
  if (e && !e.available) byId("setupText").textContent = e.reason || "Run the setup script, then restart Echolade.";
}
