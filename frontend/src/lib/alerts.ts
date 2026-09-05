import type { SetupType } from "./types";
import { SETUP_TYPES } from "./constants";

export interface AlertSettings {
  telegramToken: string;
  discordWebhook: string;
  email: string;
  minConviction: number;
  setups: SetupType[];
}

export interface AlertEvent {
  id: string;
  ts_ms: number;
  channel: "telegram" | "discord" | "email";
  status: "sent" | "delivered";
  text: string;
}

const SET_KEY = "st-alerts";
const HIST_KEY = "st-alert-history";

export function defaultAlertSettings(): AlertSettings {
  return {
    telegramToken: "",
    discordWebhook: "",
    email: "",
    minConviction: 70,
    setups: [...SETUP_TYPES],
  };
}

export function readAlertSettings(): AlertSettings {
  if (typeof window === "undefined") return defaultAlertSettings();
  try {
    const raw = window.localStorage.getItem(SET_KEY);
    return raw ? { ...defaultAlertSettings(), ...(JSON.parse(raw) as AlertSettings) } : defaultAlertSettings();
  } catch {
    return defaultAlertSettings();
  }
}

export function writeAlertSettings(next: AlertSettings): void {
  window.localStorage.setItem(SET_KEY, JSON.stringify(next));
}

export function readAlertHistory(): AlertEvent[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = window.localStorage.getItem(HIST_KEY);
    return raw ? (JSON.parse(raw) as AlertEvent[]) : seedHistory();
  } catch {
    return seedHistory();
  }
}

export function pushAlert(event: AlertEvent): AlertEvent[] {
  const next = [event, ...readAlertHistory()].slice(0, 40);
  window.localStorage.setItem(HIST_KEY, JSON.stringify(next));
  return next;
}

function seedHistory(): AlertEvent[] {
  const now = Date.now();
  return [
    { id: "al_1", ts_ms: now - 3600_000, channel: "email", status: "delivered", text: "sweep_reclaim BTCUSDT 86" },
    { id: "al_2", ts_ms: now - 7200_000, channel: "discord", status: "sent", text: "sd_extension_fade ES 73" },
  ];
}
