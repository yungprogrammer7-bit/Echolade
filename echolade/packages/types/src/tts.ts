/** Provider-neutral TTS contract. Adapters declare what they can really do. */

export interface TtsCapabilities {
  /** Returns per-character timing with the audio. */
  charTimestamps: boolean;
  /** Accepts previous/next text for context-aware generation. */
  contextText: boolean;
  /** Accepts IDs of neighbouring generations for stitching continuity. */
  requestStitching: boolean;
  pronunciationDictionaries: { supported: boolean; maxPerRequest: number };
  /** Accepts a seed (best-effort reproducibility, not a guarantee). */
  seed: boolean;
}

export interface PronunciationDictionaryRef {
  id: string;
  versionId?: string;
}

export interface TtsSegmentRequest {
  text: string;
  voiceId: string;
  modelId: string;
  outputFormat?: string; // e.g. "mp3_44100_128"
  languageCode?: string;
  seed?: number;
  voiceSettings?: {
    stability?: number;
    similarityBoost?: number;
    style?: number;
    useSpeakerBoost?: boolean;
  };
  previousText?: string;
  nextText?: string;
  previousRequestIds?: string[];
  nextRequestIds?: string[];
  pronunciationDictionaries?: PronunciationDictionaryRef[];
}

export interface CharAlignment {
  characters: string[];
  startSeconds: number[];
  endSeconds: number[];
}

export interface TtsSegmentResult {
  audio: Buffer;
  contentType: string;
  /** Provider's id for this generation, used for stitching. May be null if not returned. */
  providerRequestId: string | null;
  alignment: CharAlignment | null;
  /** Billable units reported by us (characters sent), NOT an actual provider charge. */
  estimatedUsage: { characters: number };
}

export interface TtsProvider {
  readonly id: string;
  capabilities(): TtsCapabilities;
  generate(req: TtsSegmentRequest, signal?: AbortSignal): Promise<TtsSegmentResult>;
}

export type ProviderErrorKind =
  | "auth" | "rate_limit" | "invalid_request" | "quota" | "upstream" | "timeout" | "unsupported";

export class ProviderError extends Error {
  constructor(
    message: string,
    public readonly kind: ProviderErrorKind,
    public readonly retryable: boolean,
    public readonly status?: number,
  ) {
    super(message);
    this.name = "ProviderError";
  }
}
