import { createHash } from "node:crypto";
import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";
import { env } from "../config/env.js";

/** Dev-only storage. Swap for an S3-compatible adapter with the same shape in production. */
export async function putObject(key: string, data: Buffer) {
  // Keys are generated server-side; still guard against path traversal.
  const root = path.resolve(env.LOCAL_STORAGE_DIR);
  const full = path.resolve(root, key);
  if (!full.startsWith(root + path.sep)) throw new Error("Invalid storage key.");
  await mkdir(path.dirname(full), { recursive: true });
  await writeFile(full, data);
  return { key, sizeBytes: data.length, sha256: createHash("sha256").update(data).digest("hex") };
}
