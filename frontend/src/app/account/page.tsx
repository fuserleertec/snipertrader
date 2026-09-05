"use client";

import { useState } from "react";
import { PageShell } from "@/components/terminal/PageShell";
import { mockLogin, mockLogout, readAuth, saveWatchlist, type AuthUser } from "@/lib/auth";

export default function AccountPage() {
  const [user, setUser] = useState<AuthUser | null>(() => (typeof window === "undefined" ? null : readAuth()));
  const [email, setEmail] = useState("trader@snipertrader.ai");
  const [watch, setWatch] = useState(user?.watchlist.join(",") ?? "BTCUSDT,ES,NVDA");
  const [note, setNote] = useState("Auth is a mock JWT in localStorage. Quant SSO/OAuth is not wired.");

  const login = () => {
    const next = mockLogin(email);
    setUser(next);
    setWatch(next.watchlist.join(","));
    setNote("Signed in (mock).");
  };

  const logout = () => {
    mockLogout();
    setUser(null);
    setNote("Signed out.");
  };

  const save = () => {
    const symbols = watch.split(",").map((s) => s.trim().toUpperCase()).filter(Boolean);
    const next = saveWatchlist(symbols);
    if (next) setUser(next);
    setNote("Watchlist saved locally.");
  };

  return (
    <PageShell>
      <div className="hero">
        <h1>
          Account <span className="tag">Preferences</span>
        </h1>
        <p className="hero-sub">{note}</p>
      </div>
      <div className="calc-grid">
        <div className="panel">
          <div style={{ fontFamily: "var(--mono)", fontSize: 13, color: "var(--dim)", marginBottom: 10 }}>
            Session
          </div>
          {user ? (
            <>
              <div className="qep-tk">{user.email}</div>
              <div className="qep-name">token {user.token.slice(0, 22)}…</div>
              <button type="button" className="btn" style={{ marginTop: 12 }} onClick={logout}>
                SIGN OUT
              </button>
            </>
          ) : (
            <>
              <div className="factor">
                <label>Email</label>
                <input value={email} onChange={(e) => setEmail(e.target.value)} />
              </div>
              <button type="button" className="tv-btn" onClick={login}>
                MOCK SIGN IN
              </button>
            </>
          )}
        </div>
        <div className="panel">
          <div style={{ fontFamily: "var(--mono)", fontSize: 13, color: "var(--dim)", marginBottom: 10 }}>
            Watchlist + chart
          </div>
          <div className="factor">
            <label>symbols (comma)</label>
            <input value={watch} onChange={(e) => setWatch(e.target.value)} disabled={!user} />
          </div>
          <button type="button" className="btn" onClick={save} disabled={!user}>
            SAVE PREFS
          </button>
          <div className="sec-sub" style={{ marginTop: 12 }}>
            Per-user alert configs live on /alerts (localStorage). Web Push is stubbed — no VAPID keys.
          </div>
        </div>
      </div>
    </PageShell>
  );
}
