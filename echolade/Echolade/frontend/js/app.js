import { api } from "./api.js";
import { store, on } from "./store.js";
import { byId, $$, toast } from "./ui.js";
import { applyTheme } from "./theme.js";
import { initStudio, applySettingsToInputs, generate, saveSetting, showSetupBanner, renderProfiles } from "./editor.js";
import { initPlayer, togglePlay } from "./player.js";
import { initVoices } from "./voices.js";
import { initHistory, refreshHistory } from "./history.js";
import { initSettings, refreshSettings } from "./settings.js";
import { isRunning } from "./jobs.js";

const VIEWS = { studio: "Studio", voices: "Voice library", history: "Audio history", settings: "Settings", help: "Help" };
let voices;

function route() {
  const name = (location.hash.match(/^#\/(\w+)/) || [])[1];
  const view = VIEWS[name] ? name : "studio";
  $$(".view").forEach((v) => (v.hidden = v.dataset.view !== view));
  $$(".nav a").forEach((a) => (a.dataset.nav === view ? a.setAttribute("aria-current", "page") : a.removeAttribute("aria-current")));
  byId("viewTitle").textContent = VIEWS[view];
  document.title = `${VIEWS[view]} · Echolade`;
  byId("content").scrollTop = 0;
  if (view === "voices") voices.refreshPage();
  if (view === "history") refreshHistory();
  if (view === "settings") refreshSettings();
}

function updateEngineStatus() {
  const e = store.system?.engines?.[0], dot = byId("engineDot"), text = byId("engineText");
  let cls = "", label = "Checking…";
  if (isRunning()) { cls = "busy"; label = "Generating…"; }
  else if (!e) { cls = "bad"; label = "Not connected"; }
  else if (!e.available) { cls = "bad"; label = "Model not installed"; }
  else if (e.loaded) { cls = "ok"; label = `${e.name} · ready`; }
  else { cls = "ok"; label = `${e.name} · loads on first use`; }
  dot.className = `dot ${cls}`; text.textContent = label;
}

async function refreshSystem() {
  try { store.system = await api("/api/system"); } catch { store.system = null; }
  updateEngineStatus(); showSetupBanner();
}

async function init() {
  try {
    const [settings, system, catalogue] = await Promise.all([api("/api/settings"), api("/api/system"), api("/api/voices")]);
    store.settings = settings; store.system = system;
    store.voices = catalogue.voices; store.languages = catalogue.languages;
  } catch (e) {
    toast(e.message, "bad", 10000);
    byId("engineText").textContent = "Not connected"; byId("engineDot").className = "dot bad";
    return;
  }
  applyTheme(store.settings.theme);
  byId("themeBtn").addEventListener("click", () => {
    const order = ["system", "light", "dark"];
    const next = order[(order.indexOf(store.settings.theme) + 1) % 3];
    applyTheme(next); saveSetting({ theme: next });
  });

  initPlayer(); initStudio(); initHistory(); initSettings();
  voices = initVoices();
  on("voice:pick", () => voices.openPicker());
  on("voice:changed", () => { voices.refreshPage(); voices.refreshPicker(); });
  on("job:update", updateEngineStatus);
  on("job:update", (j) => { if (["done", "partial", "failed", "cancelled"].includes(j.status)) refreshSystem(); });
  showSetupBanner(); updateEngineStatus(); renderProfiles(); applySettingsToInputs();

  window.addEventListener("hashchange", route);
  route();
  setInterval(refreshSystem, 15000);

  document.addEventListener("keydown", (e) => {
    const t = e.target, typing = t.matches?.("input, textarea, select, [contenteditable]");
    if ((e.ctrlKey || e.metaKey) && e.key === "Enter") { e.preventDefault(); generate(); }
    else if (e.key === " " && !typing && !t.matches?.("button, a, [role=slider]") && !document.querySelector("dialog[open]")) {
      e.preventDefault(); togglePlay();
    }
  });
}
init();
