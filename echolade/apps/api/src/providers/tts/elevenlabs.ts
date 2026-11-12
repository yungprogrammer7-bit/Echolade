import {
  ProviderError,
  type TtsCapabilities,
  type TtsProvider,
  type TtsSegmentRequest,
  type TtsSegmentResult,
} from "@echolade/types";

const MAX_DICTIONARIES = 3;
const MAX_STITCH_IDS = 3;

interface ElevenLabsTimestampResponse {
  audio_base64: string;
  alignment?: {
    characters: string[];
    character_start_times_seconds: number[];
    character_end_times_seconds: number[];
  } | null;
}

export interface ElevenLabsOptions {
  apiKey: string;
  baseUrl?: string;
  timeoutMs?: number;
  fetchImpl?: typeof fetch;
}

const FORMAT_CONTENT_TYPES: Record<string, string> = {
  mp3: "audio/mpeg",
  pcm: "audio/L16",
  opus: "audio/ogg",
  ulaw: "audio/basic",
  alaw: "audio/basic",
};

export class ElevenLabsTtsProvider implements TtsProvider {
  readonly id = "elevenlabs";
  private readonly baseUrl: string;
  private readonly timeoutMs: number;
  private readonly fetchImpl: typeof fetch;

  constructor(private readonly opts: ElevenLabsOptions) {
    this.baseUrl = (opts.baseUrl ?? "https://api.elevenlabs.io").replace(/\/$/, "");
    this.timeoutMs = opts.timeoutMs ?? 60_000;
    this.fetchImpl = opts.fetchImpl ?? fetch;
  }

  capabilities(): TtsCapabilities {
    return {
      charTimestamps: true,
      contextText: true,
      requestStitching: true,
      pronunciationDictionaries: { supported: true, maxPerRequest: MAX_DICTIONARIES },
      seed: true,
    };
  }

  /** Build the JSON body. Exported for tests; no network. */
  buildBody(req: TtsSegmentRequest): Record<string, unknown> {
    const dicts = req.pronunciationDictionaries ?? [];
    if (dicts.length > MAX_DICTIONARIES) {
      throw new ProviderError(
        `ElevenLabs allows at most ${MAX_DICTIONARIES} pronunciation dictionaries per request; got ${dicts.length}. Merge dictionaries first.`,
        "invalid_request", false,
      );
    }
    const prevIds = req.previousRequestIds ?? [];
    const nextIds = req.nextRequestIds ?? [];
    if (prevIds.length > MAX_STITCH_IDS || nextIds.length > MAX_STITCH_IDS) {
      throw new ProviderError(`At most ${MAX_STITCH_IDS} previous/next request ids are supported.`, "invalid_request", false);
    }
    if (req.seed !== undefined && (!Number.isInteger(req.seed) || req.seed < 0 || req.seed > 4294967295)) {
      throw new ProviderError("seed must be an integer between 0 and 4294967295.", "invalid_request", false);
    }

    const body: Record<string, unknown> = { text: req.text, model_id: req.modelId };
    if (req.languageCode) body.language_code = req.languageCode;
    if (req.seed !== undefined) body.seed = req.seed;
    if (req.voiceSettings) {
      const v = req.voiceSettings;
      body.voice_settings = {
        stability: v.stability,
        similarity_boost: v.similarityBoost,
        style: v.style,
        use_speaker_boost: v.useSpeakerBoost,
      };
    }
    if (dicts.length) {
      body.pronunciation_dictionary_locators = dicts.map((d) => ({
        pronunciation_dictionary_id: d.id,
        ...(d.versionId ? { version_id: d.versionId } : {}),
      }));
    }
    // Per provider docs, request ids take precedence over text when both are sent,
    // so we send only one form per direction to keep stored provenance unambiguous.
    if (prevIds.length) body.previous_request_ids = prevIds;
    else if (req.previousText) body.previous_text = req.previousText;
    if (nextIds.length) body.next_request_ids = nextIds;
    else if (req.nextText) body.next_text = req.nextText;
    return body;
  }

  async generate(req: TtsSegmentRequest, signal?: AbortSignal): Promise<TtsSegmentResult> {
    const outputFormat = req.outputFormat ?? "mp3_44100_128";
    const url = `${this.baseUrl}/v1/text-to-speech/${encodeURIComponent(req.voiceId)}/with-timestamps?output_format=${encodeURIComponent(outputFormat)}`;
    const body = this.buildBody(req);

    const timeout = AbortSignal.timeout(this.timeoutMs);
    const combined = signal ? AbortSignal.any([signal, timeout]) : timeout;

    let res: Response;
    try {
      res = await this.fetchImpl(url, {
        method: "POST",
        headers: { "Content-Type": "application/json", "xi-api-key": this.opts.apiKey },
        body: JSON.stringify(body),
        signal: combined,
      });
    } catch (err) {
      if (timeout.aborted) throw new ProviderError("ElevenLabs request timed out.", "timeout", true);
      throw new ProviderError(`ElevenLabs network error: ${(err as Error).message}`, "upstream", true);
    }

    if (!res.ok) throw await this.normalizeError(res);

    const json = (await res.json()) as ElevenLabsTimestampResponse;
    if (!json.audio_base64) {
      throw new ProviderError("ElevenLabs returned no audio.", "upstream", true, res.status);
    }
    const audio = Buffer.from(json.audio_base64, "base64");
    if (audio.length === 0) throw new ProviderError("ElevenLabs returned empty audio.", "upstream", true, res.status);

    const family = outputFormat.split("_")[0] ?? "mp3";
    return {
      audio,
      contentType: FORMAT_CONTENT_TYPES[family] ?? "application/octet-stream",
      // TODO(verify): confirm header name against a live response before relying on stitching.
      providerRequestId: res.headers.get("request-id"),
      alignment: json.alignment
        ? {
            characters: json.alignment.characters,
            startSeconds: json.alignment.character_start_times_seconds,
            endSeconds: json.alignment.character_end_times_seconds,
          }
        : null,
      estimatedUsage: { characters: req.text.length },
    };
  }

  private async normalizeError(res: Response): Promise<ProviderError> {
    let detail = "";
    try { detail = (await res.text()).slice(0, 500); } catch { /* ignore */ }
    const msg = `ElevenLabs ${res.status}${detail ? `: ${detail}` : ""}`;
    if (res.status === 401 || res.status === 403) return new ProviderError(msg, "auth", false, res.status);
    if (res.status === 429) return new ProviderError(msg, "rate_limit", true, res.status);
    if (res.status === 400 || res.status === 404 || res.status === 422) return new ProviderError(msg, "invalid_request", false, res.status);
    if (res.status >= 500) return new ProviderError(msg, "upstream", true, res.status);
    return new ProviderError(msg, "upstream", false, res.status);
  }
}
