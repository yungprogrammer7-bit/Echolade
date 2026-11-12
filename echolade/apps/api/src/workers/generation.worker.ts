import { Worker, UnrecoverableError } from "bullmq";
import { ProviderError } from "@echolade/types";
import { prisma } from "../lib/prisma.js";
import { connection, type GenerationJobData } from "../queues/generation.js";
import { getTtsProvider } from "../providers/tts/registry.js";
import { putObject } from "../storage/local.js";

/**
 * Generates one GenerationSegmentVersion. Idempotent: a version that is already
 * READY is skipped, so retries never produce duplicate audio or double provider calls.
 */
new Worker<GenerationJobData>(
  "generation",
  async (job) => {
    const version = await prisma.generationSegmentVersion.findUnique({
      where: { id: job.data.versionId },
      include: { segment: true },
    });
    if (!version) throw new UnrecoverableError("Version not found.");
    if (version.status === "READY") return;

    await prisma.generationSegmentVersion.update({ where: { id: version.id }, data: { status: "GENERATING" } });

    const config = version.config as Record<string, any>;
    try {
      const provider = getTtsProvider(version.provider);
      const result = await provider.generate({
        text: version.segment.text,
        voiceId: version.voiceId,
        modelId: version.modelId,
        seed: version.seed ?? undefined,
        languageCode: config.languageCode,
        voiceSettings: config.voiceSettings,
        previousText: config.previousText,
        nextText: config.nextText,
        previousRequestIds: config.previousRequestIds,
        nextRequestIds: config.nextRequestIds,
        pronunciationDictionaries: config.pronunciationDictionaries,
      });

      const stored = await putObject(`segments/${version.segmentId}/${version.id}.mp3`, result.audio);
      await prisma.$transaction([
        prisma.generationSegmentVersion.update({
          where: { id: version.id },
          data: {
            status: "READY",
            audioKey: stored.key,
            audioSha256: stored.sha256,
            audioSizeBytes: stored.sizeBytes,
            providerRequestId: result.providerRequestId,
            alignment: result.alignment as any,
            error: null,
          },
        }),
        prisma.providerUsage.create({
          data: {
            versionId: version.id,
            provider: version.provider,
            unit: "characters",
            // Estimate only. Reconcile against actual provider billing separately.
            estimatedQuantity: result.estimatedUsage.characters,
          },
        }),
      ]);
    } catch (err) {
      const message = (err as Error).message;
      await prisma.generationSegmentVersion.update({ where: { id: version.id }, data: { status: "FAILED", error: message } });
      if (err instanceof ProviderError && !err.retryable) throw new UnrecoverableError(message);
      throw err;
    }
  },
  { connection, concurrency: 4 },
);
