# Private Vercel deployment

PolicyForge deploys as **one private Vercel Services project** with a single shareable URL:

| Service | Repository root | Public route |
| --- | --- | --- |
| Next.js interface | `frontend` | `/` |
| FastAPI simulation API | `backend` | `/api/*` |

The root `vercel.json` declares this layout. Vercel Services builds both applications together and applies password protection once to the shared deployment.

## 1. Import and configure PolicyForge

1. In Vercel, choose **Add New → Project** and import `MDHRAJA/AdvPolicyRipple`.
2. Keep **Root Directory** as `./`; Vercel reads the root `vercel.json` to identify both services.
3. In **Environment Variables**, add:
   - `POLICYFORGE_SESSION_ONLY`: `true`.
   - `POLICYFORGE_AI_MODE`: `gemini`.
   - `GEMINI_API_KEY`: the Gemini key, entered only in Vercel.
   - `GEMINI_MODEL`: `gemini-3.7-flash`.
4. Apply every variable to Production, Preview, and Development.
5. Deploy. The API health check will be at `/health`.

The browser automatically calls `/api/*` on the same password-protected PolicyForge domain. Do not set `NEXT_PUBLIC_API_URL` in Vercel.

## 2. Protect teammate access

1. Open **Settings → Deployment Protection**.
2. Enable **Password Protection**.
3. Apply it to **All Deployments**, including Production.
4. Set one strong shared password and give it only to intended teammates.

Teammates can open the single deployment URL on any computer, enter the password, and use PolicyForge. Password protection availability depends on the selected Vercel plan.

## Local development

For the same no-save behavior locally, set `POLICYFORGE_SESSION_ONLY=true`. Leave `NEXT_PUBLIC_API_URL` unset to use `http://localhost:8000` automatically.
