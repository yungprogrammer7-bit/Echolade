// Starts a generation job and follows it until it finishes. The UI never blocks.
import { api } from "./api.js";
import { store, emit } from "./store.js";
import { toast } from "./ui.js";

const FINISHED = new Set(["done", "partial", "failed", "cancelled"]);
let timer = null;

function stop() { if (timer) { clearTimeout(timer); timer = null; } }

function track(job) {
  store.job = job;
  emit("job:update", job);
  stop();
  if (!FINISHED.has(job.status)) timer = setTimeout(poll, 350);
}

async function poll() {
  const job = store.job;
  if (!job) return;
  try {
    track(await api(`/api/jobs/${job.id}`));
  } catch (e) {
    if (e.status === 404) { store.job = null; emit("job:lost"); return; }
    timer = setTimeout(poll, 1500); // server briefly unreachable: keep trying
  }
}

export async function startJob(body) { track(await api("/api/jobs", { method: "POST", body })); }
export async function jobAction(action) {
  const job = store.job;
  if (!job) return;
  try { track(await api(`/api/jobs/${job.id}/${action}`, { method: "POST" })); }
  catch (e) { toast(e.message, "bad"); }
}
export const isRunning = () => store.job && !FINISHED.has(store.job.status);
