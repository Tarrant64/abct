# V2 Glass Theme System

## Overview

The glass & polish design language provides a frosted-glass card aesthetic for the ABCT V2 dashboard. It is scoped to the **Dashboard** section (Phase 1) and applies to dark-mode and light themes.

## CSS Custom Properties (Tokens)

Tokens are defined per-theme under `[data-theme="dark-mode"]` and `[data-theme="light"]`:

| Token | Dark Mode Value | Light Mode Value | Purpose |
|-------|----------------|-----------------|---------|
| `--glass-bg` | `rgba(15, 52, 96, 0.45)` | `rgba(255, 255, 255, 0.72)` | Translucent card fill |
| `--glass-blur` | `blur(14px) saturate(140%)` | `blur(16px) saturate(130%)` | Backdrop blur + saturation |
| `--glass-border` | `rgba(255, 255, 255, 0.08)` | `rgba(255, 255, 255, 0.72)` | Hairline top-lit edge |
| `--glass-highlight` | `linear-gradient(180deg, rgba(255,255,255,0.06) 0%, transparent 40%)` | `linear-gradient(180deg, rgba(255,255,255,0.9) 0%, transparent 50%)` | Specular top-sheen |
| `--glass-shadow` | `0 8px 24px rgba(0,0,0,0.35), inset 0 1px 0 rgba(255,255,255,0.06)` | `0 8px 24px rgba(0,0,0,0.08), inset 0 1px 0 rgba(255,255,255,0.8)` | Layered shadow (ambient + inset) |
| `--glass-radius` | `14px` | `14px` | Border radius |

## Reusable Utility: `.glass-card`

Add `class="glass-card"` to any card container to apply the glass treatment:

```html
<div class="v2-card glass-card" style="padding:20px;">
    <div class="v2-card-header">
        <span class="v2-card-title">Title</span>
    </div>
    <!-- card content -->
</div>
```

### What `.glass-card` applies:
- Translucent background from `--glass-bg`
- `backdrop-filter: blur(14px) saturate(140%)` (browser dependent)
- Hairline border from `--glass-border`
- Specular top-highlight via `::before` pseudo-element
- Layered shadow from `--glass-shadow`
- Hover lift: `translateY(-2px)` with brightened border + deepened shadow

### Specialized Overrides

For `.v2-stat-card.glass-card` and `.v2-card.glass-card`, the CSS file contains targeted overrides that ensure glass tokens take precedence over the base card/background values.

## Guardrails

The system includes three built-in accessibility guardrails:

1. **`@supports not (backdrop-filter: blur(1px))`** — Falls back to solid `--v2-bg-card` background with no blur.
2. **`prefers-reduced-transparency: reduce`** — Disables all glass effects, uses solid panels.
3. **`prefers-reduced-motion: reduce`** — Stops hover transform animations and disables the sheen effect.

## Theme Scope

- **dark-mode** (default): Glass is the new default look for dashboard cards.
- **light**: Glass tokens tuned for bright/frosted appearance.
- **ocean-depths, sunset-horizon, cypherpunk1, cypher, cypher2, cypher3**: Left AS-IS. They have their own `--v2-shadow-card` definitions but do not inherit glass tokens (no `--glass-*` vars defined).

## Usage in Later Phases

For future phases (Assets, NFTs, DeFi pages), add `class="glass-card"` to card containers. The CSS custom properties will automatically apply the dark-mode or light theme variant based on the active `[data-theme]` attribute.

## Files

- `v2.css` — All glass tokens and utility classes (Phase 1 additions start at line ~150).
- `index.html` — Dashboard HTML with glass-card class hooks on hero, stat cards, chart panel, and widget cards.
