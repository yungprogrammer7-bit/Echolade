import { api } from "./api.js";
import { store, emit } from "./store.js";
import { byId, $$, confirmDialog, fmtBytes, fmtDate, h, icon, toast } from "./ui.js";
import { saveSetting, renderProfiles } from "./editor.js";
import { applyTheme } from "./theme.js";

const kv = (el, pairs) => el.replaceChildren(...pairs.flatMap(([k, v]) => [h("dt", { text: k }), h("dd", {}, v)]));
const yn = (b) => (b === true ? "Yes" : b === false ? "No" : "Unknown");

function renderProfileGrid() {
  const grid = byId("profileGrid"), sys = store.system, cur = store.settings.profile;
  grid.replaceChildren(...sys.profiles.map((p) => {
    const input = h("input", { type: "radio", name: "perfprofile", value: p.id, checked: p.id === cur });
    input.addEventListener("change", async () => {
      saveSetting({ profile: p.id });
      setTimeout(refreshSettings, 700);
    });
    return h("label", { class: "profile" }, input,
      h("div", {}, h("div", { class: "n", text: p.label }), h("div", { class: "d", text: p.description }),
        p.id === cur ? h("div", { class: "now", text: `Now using: ${sys.runtime.reason}` }) : null));
  }));
  byId("customRow").hidden = cur !== "custom";
  byId("customThreads").value = store.settings.custom_threads;
  byId("customThreads").max = sys.hardware.logical_cores;
  byId("warmup").checked = store.settings.warmup;
  const accel = sys.hardware.acceleration_providers;
  byId("accel").checked = store.settings.use_acceleration && accel.length > 0;
  byId("accel").disabled = accel.length === 0;
  byId("accelHelp").textContent = accel.length
    ? `Available: ${accel.join(", ")}. Falls back to the CPU automatically if it fails. Try it and compare in Diagnostics.`
    : "No graphics acceleration was found, so Echolade uses the CPU, which works on every computer.";
}

function renderHardware() {
  const hw = store.system.hardware, isets = Object.entries(hw.instruction_sets || {});
  kv(byId("hwList"), [
    ["Processor", hw.cpu_name || "Unknown"],
    ["Cores", `${hw.physical_cores} physical · ${hw.logical_cores} threads`],
    ["CPU features", isets.length ? isets.map(([k, v]) => `${k.toUpperCase()} ${v ? "✓" : "✗"}`).join("   ") : "Unknown"],
    ["Memory", `${(hw.ram_total_mb / 1024).toFixed(1)} GB total · ${(hw.ram_available_mb / 1024).toFixed(1)} GB free`],
    ["Free disk space", hw.disk_free_mb != null ? `${(hw.disk_free_mb / 1024).toFixed(1)} GB` : "Unknown"],
    ["Compute providers", hw.providers.join(", ") || "Unknown"],
    ["System", `${hw.os} ${hw.os_version} · ${hw.machine}`],
  ]);
}

async function renderDiagnostics() {
  const box = byId("diagBody");
  let d;
  try { d = await api("/api/diagnostics"); } catch { return; }
  if (!d.recent.length) {
    box.replaceChildren(h("p", { class: "muted", text: "Generate some audio and your measured speed appears here." }));
    return;
  }
  const num = (v, s = "") => (v == null ? "—" : `${v}${s}`);
  const head = ["When", "Profile", "Segments", "Audio", "Generated in", "RTF", "First audio", "CPU use", "Peak RAM", "Result"];
  const rows = d.recent.slice(0, 10).map((m) => h("tr", {},
    h("td", { text: m.ts.replace("T", " ").slice(5, 16) }), h("td", { text: m.profile }), h("td", { text: String(m.segments) }),
    h("td", { text: num(m.audio_s, " s") }), h("td", { text: num(m.generation_s, " s") }),
    h("td", { text: num(m.rtf) }), h("td", { text: num(m.first_audio_s, " s") }),
    h("td", { text: m.cpu_cores_avg != null ? `${m.cpu_cores_avg} cores` : "—" }),
    h("td", { text: m.peak_rss_mb ? `${m.peak_rss_mb} MB` : "—" }), h("td", { text: m.status })));
  const summary = d.summary.map((g) => h("span", { class: "badge accent", text: `${g.profile}: avg RTF ${num(g.avg_rtf)} · ${g.runs} run${g.runs === 1 ? "" : "s"}` }));
  box.replaceChildren(h("div", { class: "toolbar" }, summary),
    h("div", { class: "table-scroll" }, h("table", { class: "data" }, h("thead", {}, h("tr", {}, head.map((t) => h("th", { text: t })))), h("tbody", {}, rows))));
}

async function renderStorage() {
  let u;
  try { u = await api("/api/storage"); } catch { return; }
  const clear = h("button", { class: "btn", text: "Clear temporary files" });
  clear.addEventListener("click", async () => {
    if (!(await confirmDialog({ title: "Clear temporary files?", text: "Removes voice previews and unfinished-job data. Your finished audio is not touched.", yes: "Clear" }))) return;
    try { const r = await api("/api/storage/clear-cache", { method: "POST" }); toast(`Freed ${fmtBytes(r.freed_bytes)}.`); renderStorage(); }
    catch (e) { toast(e.message, "bad"); }
  });
  const body = byId("storageBody");
  body.replaceChildren(h("dl", { class: "kv" },
    h("dt", { text: "Finished audio" }), h("dd", { text: `${fmtBytes(u.outputs_bytes)} in the “${u.outputs_dir}” folder` }),
    h("dt", { text: "Speech models" }), h("dd", { text: fmtBytes(u.models_bytes) }),
    h("dt", { text: "Temporary files" }), h("dd", { text: fmtBytes(u.cache_bytes) }),
    h("dt", { text: "Settings & history" }), h("dd", { text: fmtBytes(u.data_bytes + u.logs_bytes) })),
    h("div", { class: "toolbar" }, clear));
}

function renderPrivacyAbout() {
  const s = store.system, e = s.engines[0];
  kv(byId("privacyList"), [
    ["Server address", `${s.network.bind_host}:${s.network.port} (this computer only)`],
    ["Reachable from other devices", "No"],
    ["Internet needed to generate", yn(s.network.internet_required)],
    ["Analytics or telemetry", "None"],
    ["Where audio is saved", "The “outputs” folder next to the app"],
  ]);
  kv(byId("aboutList"), [
    ["Version", `${s.app.name} ${s.app.version}`],
    ["Speech engine", `${e.name} — ${e.available ? (e.loaded ? `loaded (${e.provider}${e.load_seconds ? `, ${e.load_seconds}s to load` : ""})` : "installed, loads on first use") : "not installed"}`],
    ["Pitch / emphasis / styles", "Not supported by this engine, so no controls are shown"],
    ["MP3 & format conversion", s.ffmpeg ? "FFmpeg available" : "FFmpeg missing — WAV 24 kHz mono only"],
    ["Licenses", "See THIRD_PARTY_NOTICES.md in the app folder"],
  ]);
}

export async function refreshSettings() {
  try { [store.settings, store.system] = await Promise.all([api("/api/settings"), api("/api/system")]); }
  catch (e) { toast(e.message, "bad"); return; }
  $$('input[name="theme"]').forEach((r) => (r.checked = r.value === store.settings.theme));
  renderProfileGrid(); renderHardware(); renderPrivacyAbout(); renderProfiles(); emit("system:update");
  renderDiagnostics(); renderStorage();
}

export function initSettings() {
  $$('input[name="theme"]').forEach((r) => r.addEventListener("change", () => { applyTheme(r.value); saveSetting({ theme: r.value }); }));
  byId("customThreads").addEventListener("change", (e) => {
    const v = Math.max(1, Math.min(Number(e.target.value) || 1, store.system.hardware.logical_cores));
    e.target.value = v; saveSetting({ custom_threads: v }); setTimeout(refreshSettings, 700);
  });
  byId("warmup").addEventListener("change", (e) => saveSetting({ warmup: e.target.checked }));
  byId("accel").addEventListener("change", (e) => { saveSetting({ use_acceleration: e.target.checked }); setTimeout(refreshSettings, 700); });

  byId("benchBtn").addEventListener("click", async (ev) => {
    const b = ev.currentTarget, out = byId("benchResult");
    b.disabled = true; b.replaceChildren(h("span", { class: "spinner" }), "Measuring…");
    out.hidden = true;
    try {
      const r = await api("/api/benchmark", { method: "POST" });
      const rows = r.results.map((x) => h("tr", {}, h("td", { text: `${x.threads} thread${x.threads === 1 ? "" : "s"}` }),
        h("td", { text: x.ok ? String(x.rtf) : "failed" }),
        h("td", {}, x.threads === r.recommended_threads ? h("span", { class: "badge ok", text: "Recommended" }) : "")));
      out.replaceChildren(h("div", { class: "table-scroll" }, h("table", { class: "data" }, h("thead", {}, h("tr", {}, h("th", { text: "Setting" }), h("th", { text: "RTF (lower is faster)" }), h("th"))), h("tbody", {}, rows))),
        h("p", { class: "help", text: r.note + " The recommendation is now used by the Automatic profile." }));
      out.hidden = false;
      await refreshSettings();
    } catch (e) { toast(e.message, "bad"); }
    finally { b.disabled = false; b.replaceChildren("Run benchmark"); }
  });

  byId("verifyBtn").addEventListener("click", async (ev) => {
    const b = ev.currentTarget; b.disabled = true;
    try {
      const r = await api("/api/models/verify", { method: "POST" });
      byId("verifyResult").replaceChildren(h("div", { class: "toolbar" }, r.results.map((x) =>
        h("span", { class: `badge ${x.ok ? "ok" : "bad"}`, text: `${x.file}: ${!x.present ? "missing" : x.ok ? "verified" : "does not match"}` }))));
    } catch (e) { toast(e.message, "bad"); } finally { b.disabled = false; }
  });
}
