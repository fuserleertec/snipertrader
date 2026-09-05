import type { Metadata } from "next";
import { Orbitron, Space_Mono, Syne } from "next/font/google";
import "./globals.css";

const orbitron = Orbitron({
  subsets: ["latin"],
  variable: "--font-orbitron",
});

const spaceMono = Space_Mono({
  weight: ["400", "700"],
  subsets: ["latin"],
  variable: "--font-space",
});

const syne = Syne({
  subsets: ["latin"],
  variable: "--font-syne",
});

export const metadata: Metadata = {
  title: "Market Simulation & Conviction Terminal | SniperTrader.ai",
  description:
    "Quantitative Market Intelligence Conviction Terminal — Kronos overlays, Quantum Ensemble picks, and setup_signals.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html
      lang="en"
      className={`${orbitron.variable} ${spaceMono.variable} ${syne.variable}`}
    >
      <body>{children}</body>
    </html>
  );
}
