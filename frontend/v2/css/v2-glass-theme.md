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
<div class="v2-card glass-card">
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

For `.v2-stat-card.glass-card` and `.v2-card.glass-card`, the CSS file contains targeted overrides that ensure glass tokens take precedence over the base card/background values. Explicit `padding` is set on each specialized rule to prevent inheritance gaps from the base class.

## Padding & Spacing Scale

The dashboard uses a 6-step spacing scale (data-dense, professional):

| Token | Value | Usage |
|-------|-------|-------|
| `--v2-space-xs` | `4px` | Micro margins (label-to-value) |
| `--v2-space-sm` | `8px` | Tight gaps between small elements |
| `--v2-space-md` | `12px` | Card padding, table cell padding, stat card padding, card header margins |
| `--v2-space-lg` | `16px` | Standard card padding, chart container padding |
| `--v2-space-xl` | `20px` | Hero padding, content padding, section top-level padding |
| `--v2-space-2xl` | `24px` | Section-to-section margins |

### Applied values (Phase 1 refine):

| Element | Padding/Gap | Notes |
|---------|------------|-------|
| `.v2-content` | `20px` | Main content area |
| `.v2-hero` | `20px` | Hero card internal padding (fixes overflow bug) |
| `.v2-stat-card` | `12px` | Stat card internal padding |
| `.v2-stat-card.glass-card` | `12px` | Explicit override to prevent inheritance gap |
| `.v2-card` | `16px` | Standard card padding |
| `.v2-card.glass-card` | `16px` | Explicit override to prevent inheritance gap |
| `.v2-chart-container` | `16px` | Chart panel padding |
| `.v2-chart-container.glass-card` | inherits from base | Already sets padding in base |
| `.v2-table th/td` | `8px 12px` | Cell padding (reduced from 10/16) |
| `.v2-footer` | `16px 20px` | Footer padding |
| `.v2-stats-grid` | `gap: 12px` | Reduced from 16px |
| `.v2-card-header` / `.v2-chart-header` / `.v2-table-header` | `margin-bottom: 12px` | Reduced from 16px |
| `.v2-hero-change` | `margin-top: 4px` | Reduced from 6px |
| `.v2-hero-sub` | `gap: 12px; margin-top: 6px` | Reduced from gap 16, margin 8 |
| `.v2-stat-label` | `margin-bottom: 4px` | Reduced from 6px |

### Inline-styled grid override

The dashboard uses inline `style="grid-template-columns:1fr 1fr;gap:20px"` for the donut+holdings section. CSS attribute selector `[style*="grid-template-columns:1fr 1fr"]` overrides this to `gap: var(--v2-space-md)` (12px).

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

- `v2.css` — All glass tokens, spacing scale, and utility classes.
- `index.html` — Dashboard HTML with glass-card class hooks on hero, stat cards, chart panel, and widget cards.
