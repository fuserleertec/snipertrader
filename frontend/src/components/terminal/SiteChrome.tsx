"use client";

import type { Theme } from "@/hooks/useTheme";
import type { ConnectionStatus } from "@/lib/types";

const LINKS = [
  { href: "https://www.snipertrader.ai/sniper_market_forecaster.html", label: "Market Forecaster" },
  { href: "https://www.snipertrader.ai/stock_picks.html", label: "Daily Stock Picks" },
  { href: "https://www.snipertrader.ai/traderedge_chartai.html", label: "AI Chart" },
  { href: "https://www.snipertrader.ai/traderedge_preflight.html", label: "⬡ Pre-Flight Protocols" },
  { href: "https://www.snipertrader.ai/traderedge_prop_firms_command_center.html", label: "Prop Firm Center" },
  { href: "https://www.snipertrader.ai/usme_products.html", label: "Products" },
];

export function TerminalNav({ theme, onToggleTheme }: { theme: Theme; onToggleTheme: () => void }) {
  return (
    <nav className="kf-nav">
      <a href="https://www.snipertrader.ai/index.html">
        <span className="brand">
          SNIPER<b>TRADER</b>
        </span>
      </a>
      <div className="links">
        {LINKS.map((l) => (
          <a key={l.href} href={l.href}>
            {l.label}
          </a>
        ))}
      </div>
      <button type="button" className="tt-btn" onClick={onToggleTheme}>
        {theme === "dark" ? "☀️ LIGHT" : "🌙 DARK"}
      </button>
    </nav>
  );
}

export function StatusStrip({
  status,
  dataAge,
  heartbeat,
  health,
  onRefresh,
  onShare,
  onDownload,
}: {
  status: ConnectionStatus;
  dataAge: string;
  heartbeat: string;
  health: string;
  onRefresh: () => void;
  onShare: () => void;
  onDownload: () => void;
}) {
  const live = status === "live" || status === "mock";
  return (
    <div className="statusbar">
      <span className="live">
        <span className={live ? "dot" : "dot err"} />
        <b>{status === "mock" ? "MOCK" : status === "live" ? "LIVE" : status.toUpperCase()}</b>
      </span>
      <span className="live">
        Next Refresh: <b>08:00 &amp; 17:00 ET</b>
      </span>
      <span className="live">
        Data Age: <b>{dataAge}</b>
      </span>
      <span className="live">
        <span className={live ? "dot" : "dot idle"} /> Heartbeat <b>{heartbeat}</b>
      </span>
      <span className="live">
        Health <b>{health}</b>
      </span>
      <span className="spacer" />
      <button type="button" className="btn" onClick={onRefresh}>
        ↻ REFRESH
      </button>
      <button type="button" className="btn" onClick={onShare}>
        🔗 SHARE
      </button>
      <button type="button" className="btn" onClick={onDownload}>
        ⬇ DOWNLOAD
      </button>
    </div>
  );
}

export function SiteFooter() {
  return (
    <footer>
      <div className="container">
        <div className="footer-grid">
          <div>
            <a className="f-logo" href="https://www.snipertrader.ai/index.html">
              SniperTrader<span>.ai</span>
            </a>
            <p className="f-mission">
              Precision market systems &amp; algorithmic engines — calm, surgical execution for the
              disciplined trader.
            </p>
            <div className="f-status">
              <i /> System Status: Operational
            </div>
          </div>
          <div className="footer-col">
            <h4>Intelligence</h4>
            <a href="https://www.snipertrader.ai/traderedge_preflight.html">Preflight Protocol</a>
            <a href="https://www.snipertrader.ai/stock_picks.html">AI Stock Picks</a>
            <a href="https://www.snipertrader.ai/traderedge_chartai.html">AI Chart Analyzer</a>
          </div>
          <div className="footer-col">
            <h4>Proprietary Algos</h4>
            <a href="https://www.snipertrader.ai/USME_ICT_Foundation.html">USME ICT Engine</a>
            <a href="https://www.snipertrader.ai/USME_VWAP_Elite_Suite.html">USME VWAP Suite</a>
          </div>
          <div className="footer-col">
            <h4>Academy</h4>
            <a href="https://www.snipertrader.ai/USME_ICT_Foundation_Course.html">Courses</a>
            <a href="https://www.snipertrader.ai/about.html">Mentorship</a>
          </div>
          <div className="footer-col">
            <h4>Company</h4>
            <a href="https://www.snipertrader.ai/about.html">About Us</a>
            <a href="https://www.snipertrader.ai/terms.html">Terms</a>
            <a href="https://www.snipertrader.ai/privacy.html">Privacy</a>
          </div>
        </div>
        <div className="footer-bottom">
          <span>© 2026 SniperTrader.ai — All rights reserved.</span>
          <span>Calm. Precise. Deliberate.</span>
        </div>
        <p className="footer-disclaimer">
          DISCLAIMER: Trading involves substantial risk of loss and is not suitable for every
          investor. Past performance does not guarantee future results. All content on this site is
          for educational purposes only and does not constitute financial or investment advice.
        </p>
      </div>
    </footer>
  );
}
