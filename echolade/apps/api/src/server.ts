import express from "express";
import helmet from "helmet";
import rateLimit from "express-rate-limit";
import { env } from "./config/env.js";

const app = express();
app.disable("x-powered-by");
app.use(helmet());
app.use(express.json({ limit: "1mb" }));
app.use(rateLimit({ windowMs: 60_000, limit: 300, standardHeaders: true, legacyHeaders: false }));

app.get("/health", (_req, res) => res.json({ ok: true }));

// TODO(next step): auth middleware (Argon2id, sessions), then deny-by-default
// project authorization, then /v1/projects, /v1/segments routes.

app.listen(env.PORT, () => console.log(`API listening on :${env.PORT}`));
