# Private Vercel deployment

PolicyForge is deployed as two **private Vercel projects** from the same repository:

| Project | Vercel Root Directory | Purpose |
| --- | --- | --- |
| `policyforge-web` | `frontend` | Next.js interface |
| `policyforge-api` | `backend` | FastAPI simulation API |

This arrangement keeps the frontend and API independently deployable while both remain on Vercel.

## 1. Create the Neon database

In Vercel, open **Storage** or the Marketplace and create a Neon Postgres database. Copy its pooled connection string. Do not commit it to the repository.

## 2. Import the API

1. In Vercel, choose **Add New → Project** and import `MDHRAJA/AdvPolicyRipple`.
2. Set **Root Directory** to `backend`.
3. In **Environment Variables**, add:
   - `DATABASE_URL`: the Neon connection string.
   - `CORS_ORIGINS`: the private web deployment URL, for example `https://policyforge-web.vercel.app`.
   - `POLICYFORGE_AI_MODE`: `rule_based`, or `gemini` if AI interpretation is wanted.
   - `GEMINI_API_KEY` and `GEMINI_MODEL` only if using the Gemini option.
4. Deploy. The health check is available at `/health`.

The database table is created automatically on first API start.

## 3. Import the web interface

1. Create a second Vercel project from the same GitHub repository.
2. Set **Root Directory** to `frontend`.
3. Add `NEXT_PUBLIC_API_URL` with the API project’s complete HTTPS URL, without a trailing slash.
4. Deploy.

`NEXT_PUBLIC_API_URL` is safe to expose because it contains only the API address. Never put `GEMINI_API_KEY` in the web project.

## 4. Make both deployments private

For **both** Vercel projects:

1. Open **Settings → Deployment Protection**.
2. Enable **Password Protection**.
3. Apply it to **All Deployments**, including Production.
4. Set one strong shared password and give it only to intended teammates.

Do this before sharing the deployment URL. Teammates can use the site from any computer after entering the password; the password-protection feature must be available on the selected Vercel plan.

## Local development

Leave `DATABASE_URL` unset. PolicyForge uses the existing local SQLite database automatically, so local commands remain unchanged.
