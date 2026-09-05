"use client";

import { useTheme } from "@/hooks/useTheme";
import { AppNav } from "./AppNav";
import { SiteFooter, TerminalNav } from "./SiteChrome";

export function PageShell({ children }: { children: React.ReactNode }) {
  const { theme, toggle } = useTheme();
  return (
    <div>
      <TerminalNav theme={theme} onToggleTheme={toggle} />
      <AppNav />
      <div className="wrap">{children}</div>
      <SiteFooter />
    </div>
  );
}
