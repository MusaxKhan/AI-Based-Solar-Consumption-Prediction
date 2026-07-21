# Solar Advisor — MVP

Tells you, right now, roughly how many watts your solar array can deliver — based on
live sun position + sky irradiance for Wah Cantt — and lets you check off appliances
to see if you're inside a safe budget for **solar-only mode**.

## What it does today (Phase 1 — physics-based, no dongle needed)

- Computes the sun's real-time elevation & azimuth using an astronomical formula (no API needed for this part).
- Pulls live irradiance (GHI/DNI/DHI), cloud cover, and temperature from Open-Meteo (free, no API key).
- Converts that into estimated plane-of-array irradiance for **your specific panel tilt and NW-facing azimuth**.
- Estimates AC-side available power, accounting for panel temperature losses and a system derate (inverter + wiring losses — defaults to 82%, tune this once you have real numbers).
- Lets you toggle appliances on/off and warns you (green/yellow/red) if your load is inside budget, inside budget but with thin margin, or over budget.
- Installable as an app (PWA) on both phone and PC home screen/desktop.
- All your appliance list and settings save locally on your device (`localStorage`) — nothing is sent anywhere except the weather lookup.

## Running it

**Option A — just open it locally**
Double-click `index.html`. Works immediately, though the "Install" button and offline caching (service worker) only activate when served over `http://` or `https://` — not `file://`.

**Option B — host it properly (recommended, needed for real install + offline support)**
Any static host works, e.g.:
```bash
# quick local test server
cd solar-advisor
python3 -m http.server 8080
# then open http://localhost:8080 on your phone/PC (same wifi network)
```
For a permanent link you can open from your phone anywhere: drag this folder into
[Vercel](https://vercel.com) or [Netlify](https://app.netlify.com) (both free, no backend needed since everything runs client-side).

## Tuning it to match reality

The **System settings** panel (bottom of the app) lets you adjust:
- Panel count / wattage — already set to 6 × 645W
- Array azimuth — set to 315° (NW). Change if you re-check your actual roof direction.
- Panel tilt — defaulted to 25°, adjust to your actual mounting angle.
- System derate — starts at 82% (typical range 75–85% for inverter conversion + wiring + dust losses). Once you have a few weeks of real readings, we'll tighten this number.
- Safety margin — how much headroom to keep below the physics estimate before it's "risky." Defaults to 15%.

## Roadmap (next phases, once you're ready)

1. **Connect the Inverterzone dongle** once you've bought/installed it — inspect its
   app traffic (or Modbus registers over the RS232 port) to pull real generation
   numbers instead of relying only on the physics estimate.
2. **Log real vs. predicted output** over a few weeks into a small database.
3. **Train a correction model** (simple scikit-learn regression is enough) on that log
   to fix systematic gaps between the physics estimate and your actual system
   (dust, shading, panel degradation, mismatched derate assumptions).
4. **Add an LLM/agent layer** so you can just ask "can I run the AC and washing
   machine right now?" in plain language instead of reading the dashboard.

## Files

- `index.html` — the entire app (UI + logic), single file for portability
- `manifest.json` — PWA metadata (name, icons, install behavior)
- `sw.js` — service worker for offline app-shell caching
- `icon-192.png`, `icon-512.png` — app icons
