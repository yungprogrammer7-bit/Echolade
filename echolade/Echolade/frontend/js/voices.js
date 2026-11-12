// Voice library: browse, search, filter, preview (generated locally), favourite, choose.
import { api } from "./api.js";
import { store, emit } from "./store.js";
import { byId, h, icon, toast } from "./ui.js";
import { saveSetting } from "./editor.js";

const previewAudio = new Audio();
let previewingId = null, previewBtn = null;

function resetPreviewBtn() {
  if (previewBtn) { previewBtn.replaceChildren(icon("play")); previewBtn.setAttribute("aria-label", "Preview voice"); }
  previewingId = null; previewBtn = null;
}
previewAudio.addEventListener("ended", resetPreviewBtn);

async function preview(v, btn) {
  if (previewingId === v.id) { previewAudio.pause(); resetPreviewBtn(); return; }
  previewAudio.pause(); resetPreviewBtn();
  previewingId = v.id; previewBtn = btn;
  btn.replaceChildren(h("span", { class: "spinner" }));
  btn.disabled = true;
  try {
    const { url } = await api(`/api/voices/${v.engine}/${v.id}/preview`, { method: "POST" });
    if (previewingId !== v.id) return;
    previewAudio.src = url;
    await previewAudio.play();
    btn.replaceChildren(icon("pause")); btn.setAttribute("aria-label", "Stop preview");
  } catch (e) { resetPreviewBtn(); toast(e.message || "Preview failed.", "bad"); }
  finally { btn.disabled = false; }
}

export function chooseVoice(v) {
  saveSetting({ default_voice: v.id });
  emit("voice:changed", v);
}

function toggleFav(v) {
  const favs = new Set(store.settings.favourites);
  favs.has(v.id) ? favs.delete(v.id) : favs.add(v.id);
  saveSetting({ favourites: [...favs] });
}

function row(v, ctx) {
  const selected = store.settings.default_voice === v.id;
  const isFav = store.settings.favourites.includes(v.id);
  const limited = v.description.includes("limited");
  const pv = h("button", { class: "btn btn-ghost btn-icon btn-sm", "aria-label": "Preview voice", title: "Preview" }, icon("play"));
  pv.addEventListener("click", (e) => { e.stopPropagation(); preview(v, pv); });
  const fav = h("button", { class: `btn btn-ghost btn-icon btn-sm fav${isFav ? " on" : ""}`, "aria-pressed": String(isFav), "aria-label": isFav ? "Remove favourite" : "Add favourite", title: "Favourite" }, icon("star"));
  fav.addEventListener("click", (e) => { e.stopPropagation(); toggleFav(v); ctx.render(); });
  const use = h("button", { class: `btn btn-sm${selected ? "" : " btn-primary"}`, text: selected ? "Selected" : "Use", disabled: selected });
  use.addEventListener("click", (e) => { e.stopPropagation(); chooseVoice(v); ctx.render(); ctx.onUse?.(v); });
  return h("div", { class: `row${selected ? " selected" : ""}` },
    h("span", { class: "avatar" }, v.name.slice(0, 2).toUpperCase()),
    h("div", {},
      h("div", { class: "title" }, h("span", { class: "t", text: v.name }),
        limited ? h("span", { class: "badge warn", title: "Pronunciation support is more limited for this language in this build.", text: "Limited" }) : null),
      h("div", { class: "meta" }, h("span", { text: `${v.language_label} · ${v.gender || "voice"}` }), h("span", { class: "mono", text: v.id }))),
    h("div", { class: "row-actions" }, pv, fav, use));
}

export function mountVoiceBrowser(root, { onUse } = {}) {
  const state = { q: "", lang: "", favOnly: false };
  const search = h("input", { type: "search", placeholder: "Search voices", "aria-label": "Search voices" });
  const langSel = h("select", { "aria-label": "Language" });
  const favBtn = h("button", { class: "btn", "aria-pressed": "false" }, icon("star"), "Favourites");
  const list = h("div", {});
  root.replaceChildren(
    h("div", { class: "toolbar" }, h("div", { class: "search" }, icon("search"), search), langSel, favBtn), list);

  const ctx = { render, onUse };
  function fill() {
    langSel.replaceChildren(h("option", { value: "", text: "All languages" }),
      ...store.languages.map((l) => h("option", { value: l.code, text: `${l.label} (${l.count})` })));
    langSel.value = state.lang;
  }
  function render() {
    const q = state.q.toLowerCase().trim();
    const vs = store.voices.filter((v) =>
      (!state.lang || v.language === state.lang) &&
      (!state.favOnly || store.settings.favourites.includes(v.id)) &&
      (!q || `${v.name} ${v.id} ${v.language_label} ${v.gender}`.toLowerCase().includes(q)));
    list.replaceChildren();
    if (!store.voices.length) {
      list.append(h("div", { class: "card empty" }, h("div", { class: "badge-icon" }, icon("voices")),
        h("h3", { text: "No voices available" }),
        h("p", { text: "The speech model isn’t installed yet. Run the setup script, then restart Echolade." })));
      return;
    }
    if (!vs.length) {
      list.append(h("div", { class: "card empty" }, h("h3", { text: "No voices match" }), h("p", { text: "Try a different search or language." })));
      return;
    }
    const section = (title, items) => {
      if (!items.length) return;
      list.append(h("div", { class: "group-title", text: title }), h("div", { class: "card list" }, items.map((v) => row(v, ctx))));
    };
    if (!q && !state.lang && !state.favOnly) {
      section("Favourites", vs.filter((v) => store.settings.favourites.includes(v.id)));
      const recent = store.settings.recent_voices.map((id) => vs.find((v) => v.id === id)).filter(Boolean).slice(0, 4);
      section("Recently used", recent);
    }
    const byLang = new Map();
    vs.forEach((v) => { if (!byLang.has(v.language_label)) byLang.set(v.language_label, []); byLang.get(v.language_label).push(v); });
    for (const [label, items] of byLang) section(label, items);
  }
  search.addEventListener("input", () => { state.q = search.value; render(); });
  langSel.addEventListener("change", () => { state.lang = langSel.value; render(); });
  favBtn.addEventListener("click", () => {
    state.favOnly = !state.favOnly; favBtn.setAttribute("aria-pressed", String(state.favOnly));
    favBtn.classList.toggle("btn-primary", state.favOnly); render();
  });
  fill(); render();
  return { render: () => { fill(); render(); } };
}

export function initVoices() {
  const page = mountVoiceBrowser(byId("voicePage"), { onUse: () => toast("Voice selected for Studio.") });
  let picker = null;
  const dlg = byId("voiceDialog");
  byId("voiceClose").addEventListener("click", () => dlg.close());
  dlg.addEventListener("close", () => { previewAudio.pause(); resetPreviewBtn(); });
  dlg.addEventListener("click", (e) => { if (e.target === dlg) dlg.close(); });
  return {
    refreshPage: page.render,
    openPicker() {
      picker = mountVoiceBrowser(byId("voicePicker"), { onUse: () => dlg.close() });
      dlg.showModal();
    },
    refreshPicker: () => picker?.render(),
  };
}
