# Solar Advisor — MVP

Tells you, right now, roughly how many watts your solar array can deliver — based on
live sun position + sky irradiance for Wah Cantt — and lets you check off appliances
to see if you're inside a safe budget for **solar-only mode**.

## What it does today

- Computes the sun's real-time elevation & azimuth using an astronomical formula (no API needed for this part).
- Pulls **satellite-observed** irradiance (Himawari-9, ~10-30 min old) as the primary live data source — this actually sees the cloud/storm over your roof, not a weather model's prediction. Falls back to the forecast model if satellite data is briefly unavailable.
- Converts that into estimated AC-side available power for **your specific panel tilt and azimuth**, with temperature-loss correction.
- Manual override button for the gap between satellite updates ("sky darker than shown? tap to override").
- Appliance checklist with green/yellow/red budget status.
- **Test history logging** — tap "Log what happened" after trying something, pick Held / Flickered / Tripped, and it's saved locally. Export as CSV or JSON any time — this is your own ground-truth dataset, no dongle required to start collecting it.
- **Seasonal outlook** — loads a real year of historical weather for Wah Cantt (ERA5 reanalysis, free, back to 1940) and shows a monthly available-watts chart, so you can see winter vs. summer without waiting for winter.
- **Chat agent** (optional, needs the small backend below) — ask "can I run the AC and washing machine right now?" in plain language. The agent calls a deterministic tool to check the real numbers; it never guesses wattage math itself.
- Installable as an app (PWA) on both phone and PC home screen/desktop.
- All appliance list, settings, and logs save locally on your device (`localStorage`) — nothing is sent anywhere except weather lookups and, if you set it up, your own chat backend.

## Running it

**Option A — just open it locally**
Double-click `index.html`. Works immediately, though the "Install" button and offline caching (service worker) only activate when served over `http://` or `https://` — not `file://`.

**Option B — host it properly (recommended, needed for real install + offline support)**
Any static host works, e.g.:
```bash
cd solar-advisor
python3 -m http.server 8080
# then open http://localhost:8080 on your phone/PC (same wifi network)
```
For a permanent link you can open from your phone anywhere: drag this folder into
[Vercel](https://vercel.com) or [Netlify](https://app.netlify.com) (both free, no backend needed for the core app).

## Agent backend (optional — for the chat feature)

The chat button needs a tiny local server that calls Claude on your behalf. Your API key
never touches the browser.

```bash
cd agent-backend
pip install -r requirements.txt
cp .env.example .env        # then paste your Anthropic API key into .env
export $(cat .env | xargs)  # or use a tool like python-dotenv / direnv
uvicorn main:app --reload --port 8787
```
Then in the app, tap the 💬 button and hit "Connect" (default URL `http://localhost:8787`
already filled in). If you're testing from your phone, use your PC's LAN IP instead of
`localhost` (e.g. `http://192.168.1.x:8787`) and make sure both devices are on the same
WiFi.

Get an API key at [console.anthropic.com](https://console.anthropic.com) — this uses
paid API credits (a few conversation turns cost a fraction of a cent), separate from any
Claude.ai subscription.

**Why it's built this way:** the LLM never does the wattage arithmetic itself — it calls
a `check_combo` tool that runs plain Python math against the exact numbers the app already
computed. The model's job is only to reason and explain in natural language. This keeps
the safety-critical part deterministic and the AI part genuinely useful, instead of asking
an LLM to do something a calculator already does better.

## Cross-device sync (accounts)

By default the app works standalone on one device (data in `localStorage`). To let anyone
who opens the app sync their settings, appliances, test logs, and trained risk model across
devices, wire up one Supabase project — you do this once, as the developer; users just log in.

1. Go to [supabase.com](https://supabase.com), sign up free, create a new project.
2. In your project, open **SQL Editor → New query**, paste the contents of
   `supabase_setup.sql` (included in this folder), and run it. This creates one table,
   locked down with Row Level Security so every user can only ever see their own row —
   this is what keeps data private between users, not which project it's in.
3. Go to **Project Settings → API**. Copy the **Project URL** and the **anon public** key.
4. Optional but recommended: **Authentication → Providers → Email** → turn off "Confirm
   email", so signing up logs a user in immediately instead of requiring an email click.
5. In the repo root, create a `.env` file (gitignored — never committed):
   ```
   PROJECT_URL=https://xxxxx.supabase.co
   ANON_KEY=eyJhbGciOi...
   ```
6. Run `node scripts/build-config.js`. This generates `config.js` (also gitignored) from
   your `.env`. Re-run it any time you change `.env`.
7. Open the app. New users now land straight on **"Set up sync" → sign up** — no URL/key
   entry needed, since it's baked in. Tapping **"Skip — use this device only"** still works
   for anyone who wants local-only mode.

**Deploying** (Vercel/Netlify/etc.): set `PROJECT_URL` and `ANON_KEY` as environment
variables in your host's dashboard (free on every major static host) and set
`node scripts/build-config.js` as the build command, so `config.js` regenerates fresh on
every deploy instead of you needing to remember to run it locally.

A Supabase anon key is safe to ship in the frontend by design — Row Level Security is what
actually protects each user's data, not the key being secret. Never put a `service_role`
key anywhere client-side.

## Live inverter link (optional — Growatt)


By default the app is a pure physics estimate (sun + satellite/forecast sky data). If
you or a customer has a **Growatt** inverter, you can optionally connect it to show real
generation and battery charge alongside the estimate — no new hardware to buy, and it's
free:

1. Growatt's API doesn't allow direct calls from a browser, so you need a small free
   relay. Deploy the included Edge Function (uses your existing Supabase project from
   Cross-device sync above, no new account needed):
   ```
   supabase functions deploy growatt-proxy --no-verify-jwt
   ```
   Full deploy steps are in the comment at the top of `supabase/functions/growatt-proxy/index.ts`.
2. Generate a free API token from the Growatt account: ShinePhone app or web dashboard →
   **Settings → Account Management → API Key**.
3. In the app, open **System settings → Live inverter link (optional)**, paste in your
   Edge Function URL and the token, tap **Find plants** to auto-fill the plant/device IDs,
   then **Save & connect**.
4. The main screen will now show a live "Live inverter reading" line next to the physics
   estimate, along with battery charge % if the inverter is a hybrid/SPH model.

This is entirely optional — leave these fields blank and the app behaves exactly as
before.

## Tuning it to match reality

The **System settings** panel (bottom of the app) lets you adjust:
- Panel count / wattage — already set to 6 × 645W
- Array azimuth — set to 315° (NW). Change if you re-check your actual roof direction.
- Panel tilt — defaulted to 25°, adjust to your actual mounting angle.
- System derate — starts at 82% (typical range 75–85% for inverter conversion + wiring + dust losses). Once you have a few weeks of real readings, we'll tighten this number.
- Safety margin — how much headroom to keep below the physics estimate before it's "risky." Defaults to 15%.

## Roadmap (next, once you're ready)

1. ~~Connect a real inverter for ground-truth generation data~~ — done via the
   **Growatt live link** above (free, no dongle purchase needed for Growatt-brand
   systems). The Inverterzone dongle route is still worth doing later for non-Growatt
   inverters or if you want raw Modbus access.
2. Once you've got a couple dozen logged entries (from the "Log what happened" button),
   **train a correction model** (simple scikit-learn regression is enough) on predicted vs.
   actual outcomes to fix systematic gaps — dust, shading, your specific derate.
3. Feed that correction model's output back into the physics estimate, so the number
   the app shows gets more accurate the longer you use it.

## Files

- `index.html` — the entire frontend app (UI + logic), single file for portability
- `manifest.json` — PWA metadata (name, icons, install behavior)
- `sw.js` — service worker for offline app-shell caching
- `icon-192.png`, `icon-512.png` — app icons
- `supabase_setup.sql` — one-time SQL to run in Supabase for cross-device sync
- `agent-backend/` — optional FastAPI server for the chat feature (runs on Ollama, free/local)
  - `main.py` — the agent: tool definitions, system prompt, chat endpoint
  - `requirements.txt`