# Echolade

AI voice and audio production platform. Flagship: **Echolade Assurance** (segment-level tracking, pronunciation rules, script-to-audio verification, change-aware regeneration).

## Status (foundation slice)
Built: monorepo, Docker services, first Prisma schema, provider-neutral TTS contract, ElevenLabs adapter (with-timestamps, seed, context stitching, pronunciation dictionary locators), BullMQ generation worker, API skeleton.
Not built yet: auth, authorization, project/segment routes, web app, STT, Assurance checks.

## Setup
```bash
pnpm install
cp .env.example .env        # add ELEVENLABS_API_KEY
docker compose up -d
pnpm db:generate
pnpm db:migrate
pnpm dev:api                # terminal 1
pnpm dev:worker             # terminal 2
```

## Known items to verify against the live API
- `request-id` response header name used for stitching (`providerRequestId`).
- Pricing, rate limits, and commercial-use terms per voice/plan.
- ElevenLabs allows max 3 pronunciation dictionaries per request; the Production Bible needs a merge step.

## Rules baked in
- Provider keys are server-side only. No silent provider fallback.
- Usage stored as `estimatedQuantity`; `actualQuantity` only from reconciled provider data.
- Worker is idempotent: READY versions are never regenerated on retry.
