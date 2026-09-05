"use client";

import { useState } from "react";
import { PageShell } from "@/components/terminal/PageShell";
import { SETUP_TYPES } from "@/lib/constants";
import {
  defaultAlertSettings,
  pushAlert,
  readAlertHistory,
  readAlertSettings,
  writeAlertSettings,
  type AlertEvent,
  type AlertSettings,
} from "@/lib/alerts";
import type { SetupType } from "@/lib/types";

export default function AlertsPage() {
  const [settings, setSettings] = useState<AlertSettings>(() =>
    typeof window === "undefined" ? defaultAlertSettings() : readAlertSettings(),
  );
  const [history, setHistory] = useState<AlertEvent[]>(() =>
    typeof window === "undefined" ? [] : readAlertHistory(),
  );
  const [note, setNote] = useState("Mock alerts API — Quant has no alerts endpoint yet.");

  const save = () => {
    writeAlertSettings(settings);
    setNote("Saved locally (mock).");
  };

  const test = () => {
    const ev = pushAlert({
      id: `al_${Date.now()}`,
      ts_ms: Date.now(),
      channel: settings.discordWebhook ? "discord" : settings.telegramToken ? "telegram" : "email",
      status: "sent",
      text: `test · minConviction ${settings.minConviction} · ${settings.setups.join(",")}`,
    });
    setHistory(ev);
    setNote("Test alert queued (mock).");
  };

  const toggleSetup = (s: SetupType) => {
    setSettings((prev) => ({
      ...prev,
      setups: prev.setups.includes(s) ? prev.setups.filter((x) => x !== s) : [...prev.setups, s],
    }));
  };

  return (
    <PageShell>
      <div className="hero">
        <h1>
          Alert <span className="tag">Management</span>
        </h1>
        <p className="hero-sub">{note}</p>
      </div>
      <div className="calc-grid">
        <div className="panel">
          <div style={{ fontFamily: "var(--mono)", fontSize: 13, color: "var(--dim)", marginBottom: 10 }}>
            Channels
          </div>
          <div className="factor">
            <label>Telegram token</label>
            <input value={settings.telegramToken} onChange={(e) => setSettings({ ...settings, telegramToken: e.target.value })} />
          </div>
          <div className="factor">
            <label>Discord webhook</label>
            <input value={settings.discordWebhook} onChange={(e) => setSettings({ ...settings, discordWebhook: e.target.value })} />
          </div>
          <div className="factor">
            <label>Email</label>
            <input value={settings.email} onChange={(e) => setSettings({ ...settings, email: e.target.value })} />
          </div>
          <div className="factor">
            <div className="flabel">
              <span>min conviction</span>
              <b>{settings.minConviction}</b>
            </div>
            <input
              type="range"
              min={0}
              max={100}
              value={settings.minConviction}
              onChange={(e) => setSettings({ ...settings, minConviction: Number(e.target.value) })}
            />
          </div>
          <div className="filters">
            {SETUP_TYPES.map((s) => (
              <button
                key={s}
                type="button"
                className={`ftab${settings.setups.includes(s) ? " active" : ""}`}
                onClick={() => toggleSetup(s)}
              >
                {s}
              </button>
            ))}
          </div>
          <div className="pick-btns">
            <button type="button" className="tv-btn" onClick={save}>
              SAVE
            </button>
            <button type="button" className="sim-btn" onClick={test}>
              TEST ALERT
            </button>
          </div>
        </div>
        <div className="panel">
          <div style={{ fontFamily: "var(--mono)", fontSize: 13, color: "var(--dim)", marginBottom: 10 }}>
            History (sent / delivered)
          </div>
          {history.length === 0 && <div className="note">No alerts yet.</div>}
          {history.map((h) => (
            <div key={h.id} className="ssig">
              <span className="nm">{h.channel}</span>
              <span className="qep-name">{h.text}</span>
              <span className="vl">{h.status}</span>
            </div>
          ))}
        </div>
      </div>
    </PageShell>
  );
}
