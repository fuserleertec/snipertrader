// /functions/v1/go?ref=CODE&to=/page — affiliate tracking redirect.
// 302-redirects to the landing page, carrying the referral code as a
// query param (st_ref) that snipertrader.ai reads, and sets a best-effort
// first-party cookie for future custom-domain use.
import { serve } from "https://deno.land/std@0.168.0/http/server.ts";

serve(async (req) => {
  const url = new URL(req.url);
  const ref = url.searchParams.get("ref") || "";
  const to = url.searchParams.get("to") || "/";

  if (!/^[A-Za-z0-9_-]{4,40}$/.test(ref)) {
    return new Response(JSON.stringify({ error: "missing or invalid ref" }), {
      status: 400,
      headers: { "Content-Type": "application/json" },
    });
  }

  const base = "https://www.snipertrader.ai";
  const target = to.startsWith("http") ? to : base + (to.startsWith("/") ? to : "/" + to);
  const sep = target.includes("?") ? "&" : "?";
  const location = target + sep + "st_ref=" + encodeURIComponent(ref);

  return new Response(null, {
    status: 302,
    headers: {
      "Location": location,
      "Set-Cookie": `st_ref=${ref}; Path=/; HttpOnly; SameSite=Lax; Max-Age=7776000`,
      "Cache-Control": "no-store",
    },
  });
});
