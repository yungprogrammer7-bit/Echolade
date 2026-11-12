// DOM helpers. All dynamic content is inserted as text nodes, never as HTML (XSS-safe).
const SVG_NS = "http://www.w3.org/2000/svg";
export const $ = (sel, root = document) => root.querySelector(sel);
export const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];
export const byId = (id) => document.getElementById(id);

export function h(tag, props = {}, ...children) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(props || {})) {
    if (v == null || v === false) continue;
    if (k === "class") el.className = v;
    else if (k === "text") el.textContent = v;
    else if (k.startsWith("on") && typeof v === "function") el.addEventListener(k.slice(2), v);
    else el.setAttribute(k, v === true ? "" : v);
  }
  for (const c of children.flat()) {
    if (c == null || c === false) continue;
    el.append(c instanceof Node ? c : document.createTextNode(String(c)));
  }
  return el;
}

export function icon(name, cls = "") {
  const svg = document.createElementNS(SVG_NS, "svg");
  svg.setAttribute("class", ("icon " + cls).trim());
  svg.setAttribute("aria-hidden", "true");
  const use = document.createElementNS(SVG_NS, "use");
  use.setAttribute("href", `#i-${name}`);
  svg.append(use);
  return svg;
}

export function setIcon(useEl, name) { useEl.setAttribute("href", `#i-${name}`); }

export function toast(message, kind = "ok", ms = 4200) {
  const box = byId("toasts");
  const t = h("div", { class: `toast ${kind}`, role: kind === "bad" ? "alert" : "status" },
    icon(kind === "bad" ? "alert" : "check"), h("span", { text: message }));
  box.append(t);
  setTimeout(() => t.remove(), kind === "bad" ? Math.max(ms, 6500) : ms);
}

export function confirmDialog({ title, text, yes = "Confirm", danger = false }) {
  const dlg = byId("confirmDialog");
  byId("confirmTitle").textContent = title;
  byId("confirmText").textContent = text || "";
  const ok = byId("confirmYes");
  ok.textContent = yes;
  ok.className = danger ? "btn btn-danger solid" : "btn btn-primary";
  return new Promise((resolve) => {
    const done = (v) => { cleanup(); dlg.close(); resolve(v); };
    const onYes = () => done(true), onNo = () => done(false), onClose = () => { cleanup(); resolve(false); };
    const cleanup = () => {
      ok.removeEventListener("click", onYes);
      byId("confirmNo").removeEventListener("click", onNo);
      dlg.removeEventListener("cancel", onClose);
    };
    ok.addEventListener("click", onYes);
    byId("confirmNo").addEventListener("click", onNo);
    dlg.addEventListener("cancel", onClose, { once: true });
    dlg.showModal();
    byId("confirmNo").focus();
  });
}

export function promptRename(current) {
  const dlg = byId("renameDialog"), input = byId("renameInput");
  input.value = current;
  return new Promise((resolve) => {
    const finish = (v) => { cleanup(); if (dlg.open) dlg.close(); resolve(v); };
    const yes = () => finish(input.value.trim() || null);
    const no = () => finish(null);
    const key = (e) => { if (e.key === "Enter") { e.preventDefault(); yes(); } };
    const cleanup = () => {
      byId("renameYes").removeEventListener("click", yes);
      byId("renameNo").removeEventListener("click", no);
      input.removeEventListener("keydown", key);
    };
    byId("renameYes").addEventListener("click", yes);
    byId("renameNo").addEventListener("click", no);
    input.addEventListener("keydown", key);
    dlg.addEventListener("cancel", () => { cleanup(); resolve(null); }, { once: true });
    dlg.showModal();
    input.select();
  });
}

export function fmtTime(sec) {
  if (!isFinite(sec) || sec < 0) sec = 0;
  const m = Math.floor(sec / 60), s = Math.floor(sec % 60);
  return `${m}:${String(s).padStart(2, "0")}`;
}
export function fmtDuration(sec) {
  sec = Math.round(sec);
  if (sec < 60) return `${sec} s`;
  const m = Math.floor(sec / 60), s = sec % 60;
  return m < 60 ? `${m} min ${s} s` : `${Math.floor(m / 60)} h ${m % 60} min`;
}
export function fmtBytes(n) {
  if (n == null) return "—";
  if (n < 1024) return `${n} B`;
  const units = ["KB", "MB", "GB"];
  let v = n / 1024, i = 0;
  while (v >= 1024 && i < 2) { v /= 1024; i++; }
  return `${v.toFixed(v < 10 ? 1 : 0)} ${units[i]}`;
}
export function fmtDate(iso) {
  try { return new Date(iso).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" }); }
  catch { return iso; }
}
export const debounce = (fn, ms) => { let t; return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); }; };
