import { Queue } from "bullmq";
import { Redis } from "ioredis";
import { env } from "../config/env.js";

export const connection = new Redis(env.REDIS_URL, { maxRetriesPerRequest: null });

export interface GenerationJobData { versionId: string }

export const generationQueue = new Queue<GenerationJobData>("generation", {
  connection,
  defaultJobOptions: {
    attempts: 4,
    backoff: { type: "exponential", delay: 2000 },
    removeOnComplete: 1000,
    removeOnFail: false, // keep failures for inspection / dead-letter review
  },
});
