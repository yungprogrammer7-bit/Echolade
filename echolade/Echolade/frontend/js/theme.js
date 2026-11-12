import { emit } from "./store.js";
import { setIcon, byId } from "./ui.js";

const ICON = { system: "monitor", light: "sun", dark: "moon" };

export function applyTheme(theme) {
  const root = document.documentElement;
  if (theme === "light" || theme === "dark") root.setAttribute("data-theme", theme); else root.removeAttribute("data-theme");
  try { localStorage.setItem("echolade.theme", theme); } catch { /* storage unavailable */ }
  setIcon(byId("themeIcon"), ICON[theme] || "monitor");
  byId("themeBtn").title = `Theme: ${theme}`;
  emit("theme:changed", theme);
}
