"use client";

import { useCallback, useEffect, useState } from "react";

export type Theme = "dark" | "light";

export function useTheme(): { theme: Theme; toggle: () => void } {
  const [theme, setTheme] = useState<Theme>("light");

  useEffect(() => {
    const stored = window.localStorage.getItem("st-theme");
    const next: Theme = stored === "dark" ? "dark" : "light";
    apply(next);
    if (next !== "light") {
      queueMicrotask(() => setTheme(next));
    }
  }, []);

  const toggle = useCallback(() => {
    setTheme((prev) => {
      const next: Theme = prev === "dark" ? "light" : "dark";
      window.localStorage.setItem("st-theme", next);
      apply(next);
      return next;
    });
  }, []);

  return { theme, toggle };
}

function apply(theme: Theme): void {
  const light = theme === "light";
  document.body.classList.toggle("light", light);
  document.body.classList.toggle("light-mode", light);
  document.documentElement.classList.toggle("light", light);
  document.documentElement.classList.toggle("light-mode", light);
}
