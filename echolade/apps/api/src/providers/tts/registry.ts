import type { TtsProvider } from "@echolade/types";
import { env } from "../../config/env.js";
import { ElevenLabsTtsProvider } from "./elevenlabs.js";

const providers = new Map<string, TtsProvider>();

if (env.ELEVENLABS_API_KEY) {
  providers.set("elevenlabs", new ElevenLabsTtsProvider({ apiKey: env.ELEVENLABS_API_KEY, baseUrl: env.ELEVENLABS_BASE_URL }));
}

/** Never falls back silently: an unknown or unconfigured provider is an explicit error. */
export function getTtsProvider(id: string): TtsProvider {
  const p = providers.get(id);
  if (!p) throw new Error(`TTS provider "${id}" is not configured.`);
  return p;
}
