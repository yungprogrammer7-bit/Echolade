// Tiny shared state + event bus. No framework needed.
export const store = { settings: null, system: null, voices: [], languages: [], job: null };
const handlers = new Map();
export function on(evt, fn) {
  if (!handlers.has(evt)) handlers.set(evt, new Set());
  handlers.get(evt).add(fn);
}
export function emit(evt, data) { (handlers.get(evt) || []).forEach((fn) => fn(data)); }
