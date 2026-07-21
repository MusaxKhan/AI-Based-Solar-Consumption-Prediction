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

## Tuning it to match reality

The **System settings** panel (bottom of the app) lets you adjust:
- Panel count / wattage — already set to 6 × 645W
- Array azimuth — set to 315° (NW). Change if you re-check your actual roof direction.
- Panel tilt — defaulted to 25°, adjust to your actual mounting angle.
- System derate — starts at 82% (typical range 75–85% for inverter conversion + wiring + dust losses). Once you have a few weeks of real readings, we'll tighten this number.
- Safety margin — how much headroom to keep below the physics estimate before it's "risky." Defaults to 15%.

## Roadmap (next, once you're ready)

1. **Connect the Inverterzone dongle** once you've bought/installed it — inspect its
   app traffic (or Modbus registers over the RS232 port) to pull real generation
   numbers instead of relying only on the physics estimate.
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
- `agent-backend/` — optional FastAPI server for the chat feature
  - `main.py` — the agent: tool definitions, system prompt, chat endpoint
  - `requirements.txt`, `.env.example`
