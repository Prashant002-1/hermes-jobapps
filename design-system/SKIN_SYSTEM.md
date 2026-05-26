# JobApps Design System — Skin System

> Source: `design-system/TOKENS.css`, `web/styles.css`

The skin system lets users customize the entire visual appearance via YAML files — no code changes needed. If your app wants a pluggable theme system, mirror this schema.

---

## Overview

```
Data flow:
  YAML skin file  ->  SkinConfig  ->  CSS custom properties
                            |
                   merge with defaults (missing fields inherit)
```

Skins are stored in `~/.hermes/skins/<name>.yaml`. Built-in presets include:
- `amber-signal` — Ivory background, safety orange accents, sharp borders (JobApps default)

---

## Skin YAML Schema

All fields are optional. Missing values inherit from the `amber-signal` skin.

```yaml
# Required: skin identity
name: mytheme
description: A custom theme

# ── Colors ──────────────────────────────────────────────────────
colors:
  # Base surfaces
  bg: "#fcf9f8"
  bg_raised: "#ffffff"
  bg_sunk: "#f0ece8"
  surface: "#f5f2f0"
  surface_hover: "#ede9e5"
  surface_active: "#e8e4e0"

  # Text
  text: "#1c1b1b"
  text_secondary: "#4a4745"
  text_tertiary: "#8a8580"
  text_disabled: "#b5b0ab"

  # Primary accent — Safety Orange
  accent: "#b72301"
  accent_dim: "rgba(183, 35, 1, 0.08)"
  accent_glow: "rgba(183, 35, 1, 0.15)"
  accent_container: "#d42a00"

  # Secondary accent — Warm Amber
  gold: "#c45a00"
  gold_dim: "rgba(196, 90, 0, 0.08)"
  gold_glow: "rgba(196, 90, 0, 0.15)"
  gold_container: "#a34a00"

  # Semantic
  good: "#1a7a3e"
  good_dim: "rgba(26, 122, 62, 0.08)"
  bad: "#b72301"
  bad_dim: "rgba(183, 35, 1, 0.08)"
  warn: "#c45a00"
  warn_dim: "rgba(196, 90, 0, 0.08)"

  # Borders
  border: "rgba(28, 27, 27, 0.10)"
  border_hover: "rgba(28, 27, 27, 0.22)"
  border_strong: "rgba(28, 27, 27, 0.35)"
  border_accent: "rgba(183, 35, 1, 0.30)"
  border_gold: "rgba(196, 90, 0, 0.30)"

  # Status bar
  status_bar_text: "#8a8580"
  status_bar_strong: "#b72301"
  status_bar_good: "#1a7a3e"
  status_bar_warn: "#c45a00"
  status_bar_bad: "#b72301"

# ── Typography ────────────────────────────────────────────────────
fonts:
  display: "Space Grotesk, system-ui, -apple-system, sans-serif"
  sans: "Space Grotesk, system-ui, -apple-system, sans-serif"
  mono: "Space Grotesk, ui-monospace, monospace"
  symbols: "Material Symbols Outlined"

# ── Spacing ─────────────────────────────────────────────────────
spacing:
  base_grid: 4         # px
  header_height: 56    # px
  nav_width: 220       # px

# ── Radii ─────────────────────────────────────────────────────
radii:
  sm: 0    # px
  md: 0    # px
  lg: 0    # px
  xl: 0    # px

# ── Branding ────────────────────────────────────────────────────
branding:
  product_name: "JobApps"
  subtitle: "HERMES"
  center_mark: "hermes-jobapps-mark.svg"
  prompt_symbol: ">"
  tool_prefix: "|"

# ── Layout ──────────────────────────────────────────────────────
layout:
  max_content_width: 1440   # px
  dot_grid_size: 20         # px spacing
  dot_grid_opacity: 0.05    # dot opacity
```

---

## Mapping: Skin Colors -> CSS Custom Properties

| Skin Key | CSS Variable |
|----------|--------------|
| `bg` | -> `--bg` |
| `bg_raised` | -> `--bg-raised` |
| `bg_sunk` | -> `--bg-sunk` |
| `surface` | -> `--surface` |
| `surface_hover` | -> `--surface-hover` |
| `surface_active` | -> `--surface-active` |
| `text` | -> `--text` |
| `text_secondary` | -> `--text-secondary` |
| `text_tertiary` | -> `--text-tertiary` |
| `text_disabled` | -> `--text-disabled` |
| `accent` | -> `--accent` |
| `accent_dim` | -> `--accent-dim` |
| `accent_glow` | -> `--accent-glow` |
| `gold` | -> `--gold` |
| `gold_dim` | -> `--gold-dim` |
| `gold_glow` | -> `--gold-glow` |
| `good` | -> `--good` |
| `good_dim` | -> `--good-dim` |
| `bad` | -> `--bad` |
| `bad_dim` | -> `--bad-dim` |
| `warn` | -> `--warn` |
| `warn_dim` | -> `--warn-dim` |
| `border` | -> `--border` |
| `border_hover` | -> `--border-hover` |
| `border_strong` | -> `--border-strong` |
| `border_accent` | -> `--border-accent` |
| `border_gold` | -> `--border-gold` |

---

## Usage Pattern in Your App

```typescript
// Load skin config (YAML -> JSON in your app)
const skin = loadSkin('mytheme')

// Merge with defaults
const tokens = {
  '--bg': skin.colors?.bg ?? '#fcf9f8',
  '--accent': skin.colors?.accent ?? '#b72301',
  '--font-sans': skin.fonts?.sans ?? '"Space Grotesk", sans-serif',
  // ... map each field
}

// Inject into root
Object.entries(tokens).forEach(([k, v]) => {
  document.documentElement.style.setProperty(k, v)
})
```

For a YAML format, follow the schema above. For JSON, simply use the same key names.
