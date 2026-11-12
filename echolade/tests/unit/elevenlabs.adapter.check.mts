import { ElevenLabsTtsProvider } from "/home/claude/echolade/apps/api/src/providers/tts/elevenlabs";
import { ProviderError } from "@echolade/types";
const calls: any[] = [];
const fake = (async (url: string, init: any) => {
  calls.push({ url, body: JSON.parse(init.body), headers: init.headers });
  return new Response(JSON.stringify({ audio_base64: Buffer.from("abc").toString("base64"),
    alignment: { characters: ["a"], character_start_times_seconds: [0], character_end_times_seconds: [0.1] } }),
    { status: 200, headers: { "request-id": "req_1" } });
}) as any;
const p = new ElevenLabsTtsProvider({ apiKey: "k", fetchImpl: fake });
const r = await p.generate({ text: "Hi", voiceId: "v", modelId: "m", seed: 5, previousRequestIds: ["a"], previousText: "ignored", nextText: "next",
  pronunciationDictionaries: [{ id: "d", versionId: "1" }] });
console.log(r.providerRequestId, r.alignment?.characters, calls[0].body);
try { p.buildBody({ text: "x", voiceId: "v", modelId: "m", pronunciationDictionaries: [1,2,3,4].map(i => ({ id: String(i) })) }); }
catch (e) { console.log("cap enforced:", e instanceof ProviderError, (e as ProviderError).retryable); }
const bad = new ElevenLabsTtsProvider({ apiKey: "k", fetchImpl: (async () => new Response("no", { status: 429 })) as any });
try { await bad.generate({ text: "x", voiceId: "v", modelId: "m" }); } catch (e) { console.log("429 ->", (e as ProviderError).kind, (e as ProviderError).retryable); }
