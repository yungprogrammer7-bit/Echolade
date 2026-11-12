// Runs before first paint so the chosen theme never flashes.
try {
  var t = localStorage.getItem("echolade.theme");
  if (t === "light" || t === "dark") document.documentElement.setAttribute("data-theme", t);
} catch (e) { /* storage unavailable: follow the system theme */ }
