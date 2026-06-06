# Glass Phase 1 — Screenshot Guide

Take these screenshots before reviewing/merging the `feature/glass-polish` branch.

## Setup
1. Ensure the branch `feature/glass-polish` is checked out on the ABCT dashboard server
2. Start the backend: `cd /home/ccata/Claude/ABCT/dashboard && python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000`
   OR deploy via `deploy-from-git.sh` on Unraid
3. Open the dashboard in browser: `http://127.0.0.1:8000/next/`

## Screenshots Required

### Dark Mode (default)
| # | Resolution | View | File Path |
|---|-----------|------|-----------|
| 1 | 1440px | Dashboard full page, dark-mode theme | `screenshots/glass-phase1/dark-1440.png` |
| 2 | 1024px | Dashboard full page, dark-mode theme | `screenshots/glass-phase1/dark-1024.png` |
| 3 | 1440px | Zoom on stat cards showing glass blur | `screenshots/glass-phase1/dark-statcards-1440.png` |
| 4 | 1440px | Chart panel with glass effect | `screenshots/glass-phase1/dark-chart-1440.png` |

### Light Mode
| # | Resolution | View | File Path |
|---|-----------|------|-----------|
| 5 | 1440px | Dashboard full page, light theme | `screenshots/glass-phase1/light-1440.png` |
| 6 | 1024px | Dashboard full page, light theme | `screenshots/glass-phase1/light-1024.png` |

### Cross-theme sweep (verify unchanged)
| # | Theme | Check | File Path |
|---|-------|-------|-----------|
| 7 | ocean-depths | Cards look normal (no glass) | `screenshots/glass-phase1/ocean-depths.png` |
| 8 | sunset-horizon | Cards look normal (no glass) | `screenshots/glass-phase1/sunset-horizon.png` |
| 9 | cypherpunk1 | Cards look normal (no glass, no neon over-glow) | `screenshots/glass-phase1/cypherpunk1.png` |

### Accessibility
| # | Setting | Check | File Path |
|---|---------|-------|-----------|
| 10 | prefers-reduced-transparency | Panels are solid (no blur) | `screenshots/glass-phase1/reduced-transparency.png` |
| 11 | prefers-reduced-motion | No hover lift animation | `screenshots/glass-phase1/reduced-motion.png` |

## How to set reduced-transparency / reduced-motion in browser DevTools
1. Open DevTools (F12)
2. Press Ctrl+Shift+P (Cmd+Shift+P on Mac)
3. Type "Rendering" to open Rendering panel
4. Check "Emulate CSS media feature prefers-reduced-transparency" or "prefers-reduced-motion"

## Verification Criteria
- [ ] Glass blur visible on stat cards (frosted background behind them)
- [ ] Specular highlight visible at top of cards
- [ ] Hover lift is smooth (translateY(-2px))
- [ ] Chart panel has glass treatment
- [ ] Hero section has glass treatment
- [ ] Heatmap card has glass treatment
- [ ] Other sections (Assets, NFTs, etc.) NOT affected
- [ ] Light mode: frosted white glass, not dark
- [ ] Ocean/sunset/cypherpunk: unchanged
- [ ] No layout shift or clipping
- [ ] Chart.js chart renders on top of glass panel correctly
