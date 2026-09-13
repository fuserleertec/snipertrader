# Design Tokens — Command Portal

**Source of truth:** `/index.html` (the canonical "Precision Over Prediction"
homepage). The Command Portal's token layer is a faithful extraction of that
design system into a shared, reusable file so the portal reads as a native
extension of the marketing site rather than a disconnected internal tool.

**File:** `assets/css/tokens.css` (linked first in `admin.html`, before
`admin.css`, which consumes every value via `var(--…)`).

> Note on repo history: the site has two earlier token sets — the green-cyan
> `assets/theme.css` (traderedge/AI-product look) and the index inline
> `:root` block. `index.html` intentionally diverged from `theme.css` (its own
> comment: "intentionally diverges from the green-cyan canonical theme").
> Per the user's direction that `index.html` is the canonical visual reference,
> `tokens.css` upstreams the **index** palette — gold-first, sage/emerald
> secondary, glassmorphism — into a shared file for the portal.

## Color tokens

### Dark (default `:root`)
| Token | Value | Role |
|---|---|---|
| `--bg` | `#020408` | page background (obsidian) |
| `--bg2` | `#06090F` | raised section background |
| `--bg3` | `#0A1018` | form inputs, wells |
| `--ink` | `#020408` | footer background |
| `--card` | `rgba(255,255,255,.03)` | card surface |
| `--card2` | `rgba(255,255,255,.055)` | card hover / raised |
| `--glass` | `rgba(10,16,24,.66)` | glassmorphism surface |
| `--text` | `#FFFFFF` | primary text |
| `--text2` | `#DCE8F2` | secondary text |
| `--text3` | `#9BB5C8` | muted text |
| `--text4` | `#5A7888` | labels / captions |
| `--emerald` | `#00E5A0` | positive / "sage" accent |
| `--gold` | `#F0C040` | primary accent (CTA, highlights) |
| `--gold2` | `#C9A84C` | gold gradient end |
| `--red` | `#FF4455` | negative / breach / danger |
| `--cyan` | `#00D4FF` | informational accent |
| `--cyan2` | `#00A8CC` | cyan gradient end |
| `--amber` | `#FF9F43` | warning accent |
| `--border` | `rgba(0,229,160,.13)` | hairline border |
| `--border2` | `rgba(0,229,160,.26)` | emphasized border |
| `--border-soft` | `rgba(255,255,255,.07)` | row dividers |
| `--nav-bg` | `rgba(2,4,8,.94)` | sticky header bg |
| `--shadow` | `0 30px 80px rgba(0,0,0,.55)` | modal/dropdown elevation |
| `--shadow-soft` | `0 12px 34px rgba(0,0,0,.30)` | card elevation |

### Light (`body.light`)
The same keys invert to a light-grey system (light-grey panels + dark text, per
the canonical light mode — **not** black "window" blocks):

```css
--bg:#F0F4F8; --bg2:#E4EBF2; --bg3:#D8E2EC; --ink:#FFFFFF;
--card:rgba(255,255,255,.6); --card2:rgba(255,255,255,.82); --glass:rgba(255,255,255,.55);
--text:#070E18; --text2:#12243A; --text3:#2A4460; --text4:#4A6278;
--emerald:#008F6A; --gold:#9A6E00; --gold2:#7A5A00; --red:#C02030;
--cyan:#0080AA; --cyan2:#0077AA; --amber:#C07020;
--border:rgba(0,150,110,.18); --border2:rgba(0,150,110,.35); --nav-bg:rgba(240,244,248,.96);
```

> Note: light-mode `--red` is `#C02030` and dims use the `-dim` variants; the
> table above is illustrative — the authoritative block lives in `tokens.css`.

Light-mode SVG adaptation (so illustrative strokes/fills re-tint):
`body.light [stroke="#DCE8F2"]{stroke:#12243A;}` and matching rules for
`#00E5A0`, `#F0C040`, `#FF4455`.

## Typography scale

| Token | Stack | Use |
|---|---|---|
| `--ff-d` | `'Playfair Display', serif` | headings, logo, large numerals |
| `--ff-b` | `'Plus Jakarta Sans', sans-serif` | body, UI copy |
| `--ff-m` | `'Space Mono', monospace` | data tags, labels, ticker, small caps |

Loads via a single Google Fonts `<link>` with `preconnect` (never inlined).
`Orbitron` and `Syne` are **retired** across the brand — do not reintroduce.

## Spacing & radii

- Radii: `--r-lg:22px` (banners/modal), `--r-md:16px` (panels/cards),
  `--r-sm:12px` (inputs/buttons), `--r-pill:24px` (tags/toggles/CTAs).
- Spacing scale: `--sp-1:4px … --sp-7:48px` (4/8/12/16/24/32/48).

## Motion

- Easing: `--ease:cubic-bezier(.22,.61,.36,1)`.
- Durations: `--dur-fast:.18s` (hover/focus), `--dur:.22s` (transitions),
  `--dur-slow:.35s` (panel entry).
- Section entry: `.panel.active` fades/slides in (`panelIn`, 300ms).
- Ticker: `scrollTick` 48s linear infinite, pauses on hover.
- Reduced motion: `@media (prefers-reduced-motion:reduce)` collapses all
  animation/transition durations and disables the ticker marquee.

## Shared primitives (in `tokens.css`)

`.container`, `.eyebrow`, `.btn` (`.btn-primary` / `.btn-outline` / `.btn-ghost` /
`.btn-danger`), `.tag` (`.gold` / `.sage` / `.red` / `.cyan`), `.glass`,
`.live-dot`, `.reveal`, `:focus-visible`, `.skip-link`, `.sr-only`.

## Where tokens are consumed

- `assets/css/admin.css` — every portal component references `var(--…)` only.
- `assets/js/admin.js` — renderers inject `var(--emerald)`, `var(--red)`,
  `var(--gold)`, `var(--cyan)` for dynamic values (P&L, status, bias).
- No component hard-codes a hex in the portal; new surface should add a token,
  not a raw color.
