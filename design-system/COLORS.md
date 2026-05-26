# JobApps Design System — Colors

> Source: `design-system/TOKENS.css`, `web/styles.css`

---

## Amber Signal Palette

The canonical JobApps web palette. Orange and amber on ivory.

### Base Surfaces

| Token | Hex | Usage |
|-------|-----|-------|
| `bg` | `#fcf9f8` | Main background / stage base |
| `bg-raised` | `#ffffff` | Cards, panels, nav rail, header |
| `bg-sunk` | `#f0ece8` | Input fields, recessed surfaces |
| `surface` | `#f5f2f0` | List rows, hoverable items |
| `surface-hover` | `#ede9e5` | Hover state |
| `surface-active` | `#e8e4e0` | Active / pressed state |

### Text

| Token | Hex | Usage |
|-------|-----|-------|
| `text` | `#1c1b1b` | Primary body text — obsidian |
| `text-secondary` | `#4a4745` | Secondary labels, metadata |
| `text-tertiary` | `#8a8580` | Muted info, placeholders, disabled |
| `text-disabled` | `#b5b0ab` | Disabled states |

### Primary Accent — Safety Orange

| Token | Hex | Usage |
|-------|-----|-------|
| `accent` | `#b72301` | Active nav, primary buttons, focus rings, links |
| `accent-dim` | `rgba(183,35,1,0.08)` | Subtle accent backgrounds |
| `accent-glow` | `rgba(183,35,1,0.15)` | Hover accent backgrounds |
| `accent-container` | `#d42a00` | Stronger orange for fills |

### Secondary Accent — Warm Amber

| Token | Hex | Usage |
|-------|-----|-------|
| `gold` | `#c45a00` | Eyebrow labels, secondary highlights |
| `gold-dim` | `rgba(196,90,0,0.08)` | Subtle amber backgrounds |
| `gold-glow` | `rgba(196,90,0,0.15)` | Hover amber backgrounds |
| `gold-container` | `#a34a00` | Stronger amber for fills |

### Semantic Colors

| Token | Hex | Usage |
|-------|-----|-------|
| `good` | `#1a7a3e` | Success, healthy status, ready indicators |
| `good-dim` | `rgba(26,122,62,0.08)` | Subtle green backgrounds |
| `bad` | `#b72301` | Errors, failures, blocked states |
| `bad-dim` | `rgba(183,35,1,0.08)` | Subtle error backgrounds |
| `warn` | `#c45a00` | Warnings, review needed, thinking state |
| `warn-dim` | `rgba(196,90,0,0.08)` | Subtle warning backgrounds |

### Borders and Outlines

| Token | Value | Usage |
|-------|-------|-------|
| `border` | `rgba(28,27,27,0.10)` | Default card / panel borders |
| `border-hover` | `rgba(28,27,27,0.22)` | Hover border elevation |
| `border-strong` | `rgba(28,27,27,0.35)` | Header bottom, nav rail right, agent panel left |
| `border-accent` | `rgba(183,35,1,0.30)` | Accent-bordered elements |
| `border-gold` | `rgba(196,90,0,0.30)` | Primary button borders |

### Surfaces

| Token | Value | Usage |
|-------|-------|-------|
| `selectionBg` | `#e8e4e0` | Selected / highlighted rows |
| `sessionLabel` | `#8a8580` | Session info labels |
| `sessionBorder` | `#8a8580` | Session ID dim text |

---

## CSS Custom Properties

```css
:root {
  --bg:                        #fcf9f8;
  --bg-raised:                 #ffffff;
  --bg-sunk:                   #f0ece8;
  --surface:                   #f5f2f0;
  --surface-hover:             #ede9e5;
  --surface-active:            #e8e4e0;

  --text:                      #1c1b1b;
  --text-secondary:            #4a4745;
  --text-tertiary:             #8a8580;
  --text-disabled:             #b5b0ab;

  --accent:                    #b72301;
  --accent-dim:                rgba(183, 35, 1, 0.08);
  --accent-glow:               rgba(183, 35, 1, 0.15);
  --accent-container:          #d42a00;

  --gold:                      #c45a00;
  --gold-dim:                  rgba(196, 90, 0, 0.08);
  --gold-glow:                 rgba(196, 90, 0, 0.15);
  --gold-container:            #a34a00;

  --good:                      #1a7a3e;
  --good-dim:                  rgba(26, 122, 62, 0.08);
  --bad:                       #b72301;
  --bad-dim:                   rgba(183, 35, 1, 0.08);
  --warn:                      #c45a00;
  --warn-dim:                  rgba(196, 90, 0, 0.08);

  --border:                    rgba(28, 27, 27, 0.10);
  --border-hover:              rgba(28, 27, 27, 0.22);
  --border-strong:             rgba(28, 27, 27, 0.35);
  --border-accent:             rgba(183, 35, 1, 0.30);
  --border-gold:               rgba(196, 90, 0, 0.30);
}
```

---

## Dot Grid Background

The main stage uses a drafting-paper dot grid:

```css
.stage {
  background-color: var(--bg);
  background-image: radial-gradient(circle, rgba(28, 27, 27, 0.05) 1px, transparent 1px);
  background-size: 20px 20px;
}
```

---

## Noise Texture

A very subtle SVG noise overlay is applied globally at `0.015` opacity and `0.025` on `.noise` elements. This prevents the ivory from feeling too flat without adding visual clutter.
