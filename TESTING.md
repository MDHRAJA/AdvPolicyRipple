# Testing PolicyForge

This checklist validates the model contract, browser experience, and deployment configuration without treating synthetic outputs as real-world predictions.

## Automated checks

### Backend

From `backend`:

```powershell
.\.venv\Scripts\Activate.ps1
python -m pytest
```

The suite includes:

- deterministic 10,000-agent simulations;
- policy and parameter validation;
- one-time policy application semantics;
- aggregate, income-group, and ward simulation outputs;
- paired seeded range calculations;
- policy intake and outside-catalogue routing;
- water-restoration interpretation;
- budget/cost recognition, including lakh, crore, INR, and rupee formats;
- Gemini request and fallback contracts without calling the real API;
- access-password enforcement and token flow;
- Census-informed synthetic scenario boundaries.

### Frontend production build

From `frontend`:

```powershell
npm ci
npm run build
```

This checks TypeScript and the production Next.js build. It does not call Gemini.

## Manual browser checklist

### Access and navigation

- [ ] With `POLICYFORGE_ACCESS_PASSWORD` set, opening the site first shows the password screen.
- [ ] An incorrect password is rejected; the shared password opens the app.
- [ ] Removing the variable and redeploying removes the gate.
- [ ] Navigation includes AI Planner, Simulator, Results, Scenarios, Chennai Data, Ward Map, and About. Learning content appears inside About.

### AI Planner and results

- [ ] A supported request, such as “Reduce household water availability by 25% in Chennai”, opens Results automatically.
- [ ] A water-restoration request, such as “Current water cut is 15%; increase available water by 15%”, is interpreted as restoration, not a new 15% cut.
- [ ] An outside-catalogue request remains a Census-informed synthetic scenario and is not relabelled as a preset policy.
- [ ] The selected policy, no-policy baseline, outcome chart, income-group effects, trajectory, and limitations are visible together in Results.
- [ ] Results describe the seeded range as model variation, not a confidence interval.

### Budget and delivery

- [ ] “Under 2 crores” displays a stated amount of `₹2,00,00,000`.
- [ ] “₹25 lakh”, “65 lakhs”, and “INR 65,00,000” display normalised rupee amounts.
- [ ] “Heavy cost” or “strict cost” displays a cost/funding consideration even without an amount.
- [ ] A question with no money language is the only case that displays “No explicit budget constraint supplied.”
- [ ] The AI funding approach does not claim an invented funding cut or numeric simulator effect.

### Ward targeting

- [ ] Search for a valid ward number (for example, 92) selects it and adds it to the target.
- [ ] Clicking additional polygons adds/removes wards from the selected target.
- [ ] **Select all Chennai** clears ward-specific targeting and makes the policy citywide.
- [ ] Ward overlays remain labelled as synthetic simulation output rather than observed ward outcomes.

### Report export

- [ ] Select **Export presentation report (PDF)** from Results.
- [ ] The print window opens with a centred full-page PolicyForge cover.
- [ ] The AI proposal, budget, charts, group effects, assumptions, and limitations begin on the subsequent pages.
- [ ] Use the browser print dialog’s **Save as PDF** option and inspect for clipped text or broken tables.

### Vercel

- [ ] Both frontend and backend deploy from the root `vercel.json`.
- [ ] `/health` returns a healthy response.
- [ ] The frontend can call same-origin `/api/*`; `NEXT_PUBLIC_API_URL` is unset.
- [ ] Gemini variables are set only on the backend service.
- [ ] No API key appears in source control, frontend variables, screenshots, or logs.
