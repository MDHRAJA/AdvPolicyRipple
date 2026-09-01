# Vercel deployment

**Live deployment:** [https://policy-forge-nu.vercel.app/](https://policy-forge-nu.vercel.app/)

PolicyForge deploys as one public Vercel project. The Next.js interface and FastAPI API share this domain, so browser requests use `/api/*` without cross-origin configuration.

| Service | Repository root | Public route |
| --- | --- | --- |
| Next.js interface | `frontend` | `/` |
| FastAPI simulation API | `backend` | `/api/*` |

The root `vercel.json` declares this layout.

## Configure a deployment

1. In Vercel, choose **Add New → Project** and import `MDHRAJA/AdvPolicyRipple`.
2. Keep **Root Directory** as `./`; Vercel reads the root `vercel.json`.
3. Add these environment variables to Production, Preview, and Development:
   - `POLICYFORGE_SESSION_ONLY=true`
   - `POLICYFORGE_AI_MODE=gemini`
   - `GEMINI_API_KEY` — set this only in Vercel; never commit it.
   - `GEMINI_MODEL=gemini-3.6-flash`
   - `GEMINI_FALLBACK_MODEL_1=gemini-3.5-flash`
   - `GEMINI_FALLBACK_MODEL_2=gemini-3.5-flash-lite`
   - `GEMINI_FALLBACK_MODEL_3=gemini-3.1-flash-lite`
4. Deploy. The health endpoint is available at `/health`.

Do not set `NEXT_PUBLIC_API_URL` for Vercel: the app uses its shared deployment domain automatically. The deployment is intentionally public and has no application password gate.

## Local development

For session-only local development, set `POLICYFORGE_SESSION_ONLY=true`. Leave `NEXT_PUBLIC_API_URL` unset to use `http://localhost:8001` automatically.
