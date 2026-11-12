import { z } from "zod";

const schema = z.object({
  NODE_ENV: z.enum(["development", "test", "production"]).default("development"),
  PORT: z.coerce.number().default(4000),
  DATABASE_URL: z.string().url(),
  REDIS_URL: z.string().url(),
  ELEVENLABS_API_KEY: z.string().min(1).optional(),
  ELEVENLABS_BASE_URL: z.string().url().default("https://api.elevenlabs.io"),
  LOCAL_STORAGE_DIR: z.string().default(".storage"),
});

export const env = schema.parse(process.env);
