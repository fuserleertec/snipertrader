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
  title: "SniperTrader Dashboard",
  description: "Phase 1 chart + VWAP bands + session levels + live signal table",
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
