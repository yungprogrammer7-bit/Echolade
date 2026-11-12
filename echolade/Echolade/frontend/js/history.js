import { api } from "./api.js";
import { byId, confirmDialog, fmtDate, fmtBytes, fmtTime, h, icon, promptRename, toast } from "./ui.js";
import { playEntry } from "./player.js";

let items = [];

function entryRow(e) {
  const play = h("button", { class: "btn btn-icon btn-primary", "aria-label": `Play ${e.name}`, disabled: e.file_missing }, icon("play"));
  play.addEventListener("click", () => playEntry(e));
  const badges = [];
  if (e.status === "partial") badges.push(h("span", { class: "badge warn", title: `${e.missing_segments.length} segment(s) missing`, text: "Partial" }));
  if (e.file_missing) badges.push(h("span", { class: "badge bad", text: "File missing" }));
  const dl = h("a", { class: "btn btn-ghost btn-icon btn-sm", href: `/api/history/${e.id}/download`, download: "", "aria-label": "Download", title: "Download" }, icon("download"));
  if (e.file_missing) { dl.removeAttribute("href"); dl.setAttribute("aria-disabled", "true"); dl.classList.add("disabled"); }
  const ren = h("button", { class: "btn btn-ghost btn-icon btn-sm", "aria-label": "Rename", title: "Rename" }, icon("pencil"));
  ren.addEventListener("click", async () => {
    const name = await promptRename(e.name);
    if (!name || name === e.name) return;
    try { await api(`/api/history/${e.id}`, { method: "PATCH", body: { name } }); refreshHistory(); }
    catch (err) { toast(err.message, "bad"); }
  });
  const del = h("button", { class: "btn btn-ghost btn-icon btn-sm btn-danger", "aria-label": "Delete", title: "Delete" }, icon("trash"));
  del.addEventListener("click", async () => {
    if (!(await confirmDialog({ title: `Delete “${e.name}”?`, text: "The audio file will be permanently removed from this computer.", yes: "Delete", danger: true }))) return;
    try { await api(`/api/history/${e.id}`, { method: "DELETE" }); toast("Deleted."); refreshHistory(); }
    catch (err) { toast(err.message, "bad"); }
  });
  return h("div", { class: "row" }, play,
    h("div", {}, h("div", { class: "title" }, h("span", { class: "t", text: e.name }), ...badges),
      h("div", { class: "meta" }, h("span", { text: e.voice_name }), h("span", { text: `${e.format.toUpperCase()}${e.bitrate ? ` ${e.bitrate} kbps` : ""}` }),
        h("span", { text: fmtTime(e.duration_s) }), h("span", { text: fmtBytes(e.size_bytes) }), h("span", { text: fmtDate(e.created_at) }))),
    h("div", { class: "row-actions" }, dl, ren, del));
}

function render() {
  const q = byId("historySearch").value.toLowerCase().trim();
  const shown = items.filter((e) => !q || `${e.name} ${e.voice_name}`.toLowerCase().includes(q));
  byId("historyCount").textContent = items.length ? `${items.length} ${items.length === 1 ? "item" : "items"}` : "";
  const box = byId("historyList");
  if (!shown.length) {
    box.replaceChildren(h("div", { class: "card empty" }, h("div", { class: "badge-icon" }, icon("history")),
      h("h3", { text: items.length ? "Nothing matches your search" : "No audio yet" }),
      h("p", { text: items.length ? "Try a different word." : "Audio you generate is listed here, so you can replay, rename, or download it later." }),
      items.length ? null : h("a", { class: "btn btn-primary", href: "#/studio", text: "Go to Studio" })));
    return;
  }
  box.replaceChildren(h("div", { class: "card list" }, shown.map(entryRow)));
}

export async function refreshHistory() {
  try { items = (await api("/api/history")).items; } catch (e) { toast(e.message, "bad"); return; }
  render();
}
export function initHistory() { byId("historySearch").addEventListener("input", render); }
