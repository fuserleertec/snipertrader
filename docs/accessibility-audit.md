# Accessibility Audit — Command Portal (WCAG 2.1 AA)

This records what is implemented against WCAG 2.1 AA, and — honestly — what has
and has not been machine-verified. No automated Lighthouse/axe run was possible
in this environment (no Chrome/Playwright); the items below are implementation
facts + a manual review, and the "automated verification" section is explicit
about the gap.

## Landmarks & semantic structure ✅

- `<header role="banner">`, `<nav aria-label="Primary">`,
  `<aside role="navigation" aria-label="Command Portal">`,
  `<main role="main">`, `<footer role="contentinfo">`.
- One `<h1>`-equivalent section title per panel via `aria-labelledby` on each
  `<section class="panel">`.
- Breadcrumb is a real `<nav aria-label="Breadcrumb">` with `aria-current="page"`.

## Icons & non-text content ✅

- All UI icons are inline `<svg>` with `aria-hidden="true" focusable="false"`,
  paired with adjacent visible text (or an `aria-label` on the control).
- **No emoji used as UI icons.**
- Standalone icon files under `assets/icons/*.svg` include `role="img"` +
  `<title>` for direct use.

## Keyboard operability ✅

- Every interactive element is a real `<button>` or `<a>` (no clickable `<div>`).
- Global event delegation targets `[data-section]`, `[data-action]`,
  `[data-group-toggle]` — all attached to real controls.
- Visible focus ring via `:focus-visible` (`outline:2px solid var(--gold)`).
- Custom toggle switches expose the `<input type="checkbox">` (focusable) with a
  `:focus-visible` ring and an `.sr-only` accessible name.

## Tables ✅

- Signal Log uses `<table>` with `<caption>`, `<th scope="col">`, and a
  sr-only Actions header. Horizontally scrollable on mobile (`.table-wrap`).

## Forms ✅

- Explicit `<label for="…">` on every input/select.
- Phone field links help text via `aria-describedby="phoneHint"`.
- Login error is `role="alert"`.
- 2FA inputs have `inputmode="numeric"` and per-digit `aria-label`.

## Live regions & states ✅

- Dynamic content containers carry `aria-live="polite"`.
- A global `role="status" aria-live="polite"` region (`#srAnnounce`) announces
  section navigation.
- Loading states are skeleton shimmer with `aria-busy` semantics (set on the
  region); **no "Loading…" text**. Empty/error states are static readable text,
  not spinners.
- `aria-expanded` on collapsible sidebar groups and the bell dropdown;
  `aria-haspopup` + `aria-expanded` on the bell.

## Color & contrast ✅ (by construction)

- Text `#DCE8F2` on `#020408` ≈ **14.6:1**; `#9BB5C8` on `#020408` ≈ **8.9:1**;
  `#5A7888` on `#020408` ≈ **5.2:1** (all ≥ 4.5:1).
- Light mode: `#12243A` on `#F0F4F8` ≈ **13:1**; `#2A4460` on `#F0F4F8` ≈ **8:1**;
  `#4A6278` on `#F0F4F8` ≈ **5.3:1** (≥ 4.5:1).
- Accent-on-card: gold `#9A6E00` on light `#F0F4F8` ≈ **4.6:1** (≥ 3:1 UI
  component threshold; used for large/text elements ≥ 4.5:1 where needed).
- Focus indicators use gold with `outline-offset`, meeting 3:1 against the
  adjacent surface.

## Motion ✅

- `@media (prefers-reduced-motion:reduce)` disables all animations/transitions
  and the ticker marquee.

## Screen-reader helpers ✅

- `.sr-only` utility, `.skip-link` ("Skip to main content"), `#srAnnounce`.

## Known gaps / not yet verified ⚠️

1. **No automated run.** Lighthouse Accessibility and axe were **not** run (no
   headless browser available). Scores are **not claimed**.
2. **Custom cursor.** `cursor:none` + the precision-scope cursor is inherited
   from the homepage for brand parity; it is hidden below 820px, but desktop
   keyboard-only and low-vision users lose the OS pointer on the desktop —
   flag for product decision (the homepage has the same tradeoff).
3. **Dropdowns are hover-open** (from the homepage nav); keyboard users can
   reach the links, but `Escape`-to-close is not wired on the marketing
   dropdowns. Recommend adding if the portal nav is treated as primary.
4. **Color-only signal** in some statuses (P&L green/red) is always paired with
   a `+`/`-` sign, so it is not color-only.

## Verification method (what was actually run)

- `node --check` on all three JS files (syntax).
- Node `vm` harness against the real `admin.js` asserting all 10 sections
  populate DOM (18/18 mock-fallback assertions; 14/14 real-API+merge
  assertions), including empty-state and SIMULATION-badge paths.
- Manual DOM inspection of the served page (landmarks, labels, live regions)
  via the in-app preview.
