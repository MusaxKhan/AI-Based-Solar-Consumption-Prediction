// growatt-proxy — Supabase Edge Function (free tier, Deno runtime)
//
// Why this exists: Growatt's Open API (openapi.growatt.com) does not send
// CORS headers, so a browser calling it directly from index.html is blocked.
// This function just relays the request server-side, where CORS doesn't
// apply. Nothing here costs money — Supabase's free tier includes 500,000
// edge function calls/month, far more than a personal or small-fleet app
// will ever use.
//
// The user's Growatt API token is sent per-request from the browser (it's
// generated free from Settings > Account Management > API Key in the
// ShinePhone app, or the Growatt web dashboard) and is never stored here —
// this function is stateless. If you want it remembered across sessions,
// store it in your existing Supabase `sites` table (RLS already protects it
// per-user) and have the frontend read it from there before calling this.
//
// Deploy (one-time, free):
//   1. Install the Supabase CLI: https://supabase.com/docs/guides/cli
//   2. supabase login
//   3. supabase link --project-ref <your-project-ref>
//   4. supabase functions deploy growatt-proxy --no-verify-jwt
//   5. Your endpoint is:
//      https://<your-project-ref>.supabase.co/functions/v1/growatt-proxy
//      (find <your-project-ref> in your Supabase dashboard URL, or run
//      `supabase status` — it's the same ref you used in `supabase link`)
//
// Regions: Growatt has separate servers per region. Pakistan installs
// typically register on the "rest of world" server. If plant_list comes
// back empty, try the alternate GROWATT_BASE values commented below.

const GROWATT_BASE = "https://openapi.growatt.com"; // rest of world (try this first)
// const GROWATT_BASE = "https://openapi-cn.growatt.com"; // China
// const GROWATT_BASE = "https://openapi-us.growatt.com"; // North America

const CORS_HEADERS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
};

Deno.serve(async (req: Request) => {
  if (req.method === "OPTIONS") {
    return new Response("ok", { headers: CORS_HEADERS });
  }

  try {
    const { token, action, plantId, deviceSn } = await req.json();

    if (!token) {
      return json({ error: "Missing Growatt API token" }, 400);
    }

    let path: string;
    switch (action) {
      case "plant_list":
        // Every plant registered to this account.
        path = "/v1/plant/list";
        break;
      case "plant_detail":
        // Current generation + today's/total energy for one plant.
        if (!plantId) return json({ error: "plantId required for plant_detail" }, 400);
        path = `/v1/plant/data?plant_id=${encodeURIComponent(plantId)}`;
        break;
      case "device_data":
        // Live device-level readout: AC power, battery SoC, charge/discharge
        // status. deviceSn comes from plant_detail's device list.
        if (!deviceSn) return json({ error: "deviceSn required for device_data" }, 400);
        path = `/v1/device/mix/mix_last_data?device_sn=${encodeURIComponent(deviceSn)}`;
        break;
      default:
        return json({ error: `Unknown action '${action}'. Use plant_list, plant_detail, or device_data.` }, 400);
    }

    const growattRes = await fetch(`${GROWATT_BASE}${path}`, {
      headers: { "token": token },
    });

    const body = await growattRes.text();
    // Growatt returns JSON; pass it through as-is so the frontend can parse it.
    return new Response(body, {
      status: growattRes.status,
      headers: { ...CORS_HEADERS, "Content-Type": "application/json" },
    });
  } catch (err) {
    return json({ error: String(err) }, 500);
  }
});

function json(obj: unknown, status = 200) {
  return new Response(JSON.stringify(obj), {
    status,
    headers: { ...CORS_HEADERS, "Content-Type": "application/json" },
  });
}