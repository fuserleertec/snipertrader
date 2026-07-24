# AGENTS.md — SniperTrader.ai

You are an engineering / growth copilot for **SniperTrader.ai**, an AI-powered
trading-education and tools business. This repository **is** the live website.

## What this repo is
- **Static site, no build step.** Plain HTML files served by **GitHub Pages**
  from the `main` branch.
- Live domain: `snipertrader.ai` (see `CNAME`). Every push to `main` deploys to
  production automatically — there is no separate "staging" deploy step.
- ~52 HTML pages. Each page is **self-contained**: inline `<style>` and inline
  `<script>`. There is **no shared CSS, JS, or template system** yet — EXCEPT the
  new canonical theme at `assets/theme.css` (see "Theme unification" below).
- **Kronos dashboard:** `kronos_foundation.html` + inference backend `api/server.js`
  (`POST /api/kronos/forecast`). Real OHLCV via Binance/CoinGecko/CSV. See the
  `kronos-foundation` skill.

## Critical operating rules
- 🚫 **NEVER push to `main` without explicit user confirmation.** A push = a
  live deploy to snipertrader.ai in front of customers. Local edits and local
  commits are fine; only `git push origin main` when the user says so.
- Links between pages use **absolute paths** (`href="/page.html"`). These only
  resolve on the apex domain, not a subpath — keep this convention unless the
  user asks to change deployment structure.
- Each page has a **dark/light theme toggle** driven by a `body.light` /
  `body.light-mode` class plus CSS variables. Preserve both modes.
- Pages load fonts from Google Fonts (Orbitron, Space Mono, Inter, Syne). Keep
  the CDN `<link>` tags; don't inline fonts.

## Product surface (what lives here)
- **Course pages:** USME/ICT Foundation, VWAP Suite/Elite, Prop Firm MasterPlan,
  30-Day Funded Challenge, workshops.
- **AI product pages:** `traderedge_*` (AI sentiment, chart AI, baseline,
  guardrails, review loop, prop-firm command center) and `ai_vision*`,
  `Ai_Vision.html`.
- **Tools:** `P&L_tracker.html`, `sniper_pl_widget.html`, `USME_ICT_Calculator`.
- **Commerce/admin:** `checkout.html`, `admin.html`, `ebook.html`, `sentinel_*`.
- **Legal/info:** `terms.html`, `privacy.html`, `disclaimer.html`, `about.html`.
- **Extras:** a packaged `USME_ICT_Calculator.app` and course audio `.mp3`.

## Known architecture issues (fix opportunistically, propose before doing)
1. **Three divergent design systems (in progress).** Index/USME pages use one
   token set (`--bg`, `--cyan`, `--gold`, Inter). The `traderedge_*` pages use a
   green-cyan set (`--obs`, `--emerald`, Syne). The P&L widget uses a third
   (green-blue, Space Grotesk). **Unification started:** a canonical
   `assets/theme.css` now defines the unified dark (green-cyan) + light palette,
   fonts, and a shared `.kf-nav` / `.kf-panel` primitive. `kronos_foundation.html`
   is migrated to it. **Migrate other pages incrementally** — do NOT blast-convert
   50 files in one unreviewed pass; one page per reviewed change.
2. **Nav duplication.** The same nav/footer is hand-copied into every file
   (~50 references to `/traderedge_guardrails.html`, etc.). A shared partial or
   a tiny build/include step would remove the maintenance drag. `assets/theme.css`
   ships a `.kf-nav` primitive to adopt as pages are migrated.
3. **No DRY.** Repeating a brand color or adding a page means editing many files
   by hand. Suggest templating before large site-wide changes.

## Theme unification (canonical = `assets/theme.css`)
- Dark mode = traderedge green-cyan family (the AI-product look). Light mode
  preserves both palettes' light variants.
- To migrate a page: (a) add `<link rel="stylesheet" href="/assets/theme.css">`
  in `<head>`; (b) delete its inline `:root`/`body.light-mode` token blocks;
  (c) optionally swap its nav markup for `.kf-nav`. Verify visually before pushing.
- Keep brand-critical tokens (`--emerald`, `--cyan`, `--gold`, `--red`, `--obs*`)
  defined ONLY in `assets/theme.css` going forward. Page-specific overrides are OK
  but should be minimal.

## How to help (the "engine" role)
- **Content ops:** add/edit product & course pages; keep nav/footer consistent.
- **AI features:** the `traderedge_*` / `ai_vision*` pages are AI product
  surfaces — extend them, wire real APIs, build the sentiment/guardrail logic.
- **Design consistency:** propose unifying the two theme systems; verify with
  screenshots (`browser` toolset) before declaring a visual change done.
- **Safe deploys:** stage + commit locally, then ASK before pushing.

## Local workflow
```bash
cd ~/snipertrader
git status                       # what changed
git add -A && git commit -m "…"  # local only
# only after explicit user OK:
git push origin main             # → live deploy
```
