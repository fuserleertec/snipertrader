// /functions/v1/postback — server-side conversion tracking.
// POST { referral_code, customer_email, product_slug, amount_cents, transaction_id }
// Looks up the affiliate, computes the direct commission via the shared engine,
// and inserts a referral + commission using the service-role key (bypasses RLS).
import { serve } from "https://deno.land/std@0.168.0/http/server.ts";
import { computeDirect } from "../_shared/engine.ts";

serve(async (req) => {
  if (req.method !== "POST") {
    return new Response(JSON.stringify({ error: "POST only" }), { status: 405, headers: { "Content-Type": "application/json" } });
  }

  const POSTBACK_SECRET = Deno.env.get("POSTBACK_SECRET");
  if (!POSTBACK_SECRET || req.headers.get("x-webhook-secret") !== POSTBACK_SECRET) {
    return new Response(JSON.stringify({ error: "unauthorized" }), { status: 401, headers: { "Content-Type": "application/json" } });
  }

  const SUPABASE_URL = Deno.env.get("SUPABASE_URL")!;
  const SR = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!;
  const auth = { apikey: SR, Authorization: `Bearer ${SR}` };

  let body: any;
  try { body = await req.json(); } catch { return new Response(JSON.stringify({ error: "invalid JSON" }), { status: 400, headers: { "Content-Type": "application/json" } }); }

  const { referral_code, customer_email, product_slug, amount_cents, transaction_id } = body;
  if (!referral_code || !product_slug || !amount_cents) {
    return new Response(JSON.stringify({ error: "referral_code, product_slug, amount_cents required" }), { status: 400, headers: { "Content-Type": "application/json" } });
  }

  // lookup affiliate by referral_code
  const affRes = await fetch(
    `${SUPABASE_URL}/rest/v1/sentinel_affiliates?referral_code=eq.${encodeURIComponent(referral_code)}&select=*&limit=1`,
    { headers: auth },
  );
  if (!affRes.ok) return new Response(JSON.stringify({ error: "lookup failed", status: affRes.status }), { status: 502, headers: { "Content-Type": "application/json" } });
  const affiliates = await affRes.json();
  if (!affiliates.length) return new Response(JSON.stringify({ error: "unknown referral_code" }), { status: 404, headers: { "Content-Type": "application/json" } });
  const aff = affiliates[0];

  const c = computeDirect(aff.tier, Math.floor(Number(amount_cents)));

  const rh = { ...auth, "Content-Type": "application/json", "Prefer": "return=representation" };

  const refRes = await fetch(`${SUPABASE_URL}/rest/v1/sentinel_referrals`, {
    method: "POST",
    headers: rh,
    body: JSON.stringify({
      affiliate_id: aff.id,
      customer_email: customer_email || null,
      product_slug,
      conversion_at: new Date().toISOString(),
      status: "approved",
      metadata: { transaction_id: transaction_id || null },
    }),
  });
  if (!refRes.ok) return new Response(JSON.stringify({ error: "referral insert failed", detail: await refRes.text() }), { status: 502, headers: { "Content-Type": "application/json" } });
  const ref = (await refRes.json())[0];

  const comRes = await fetch(`${SUPABASE_URL}/rest/v1/sentinel_commissions`, {
    method: "POST",
    headers: rh,
    body: JSON.stringify({
      referral_id: ref.id,
      affiliate_id: aff.id,
      type: "direct",
      amount_cents: c.cents,
      status: "approved",
      rule_snapshot: c.rule,
    }),
  });
  if (!comRes.ok) return new Response(JSON.stringify({ error: "commission insert failed", detail: await comRes.text() }), { status: 502, headers: { "Content-Type": "application/json" } });
  const com = (await comRes.json())[0];

  return new Response(JSON.stringify({ ok: true, affiliate_id: aff.id, tier: aff.tier, referral_id: ref.id, commission_cents: com.amount_cents, rate: c.rule.rate }), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });
});
