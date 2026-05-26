# JobApps Design System

A living reference for the Hermes JobApps visual language. This design system documents the web dashboard only.

---

## Surface Coverage

| Surface | Technology | Source |
|---------|-----------|--------|
| **Web Dashboard** | Vanilla CSS custom properties | `design-system/TOKENS.css`, `web/styles.css` |

---

## File Reference

```
design-system/
├── README.md         <- This file. Quick start & overview.
├── COLORS.md         <- Amber Signal color palette
├── TYPOGRAPHY.md     <- Space Grotesk stack, sizes, text styles
├── COMPONENTS.md     <- Layout, panels, status bar, composer, cards, buttons
├── TOKENS.css        <- Drop-in CSS file with all custom properties
├── ASCII_ART.md      <- Logo bar motif and brand strings
└── SKIN_SYSTEM.md    <- YAML skin schema for pluggable theming
```

---

## Quick Start

Drop in the CSS:

```html
<link rel="stylesheet" href="design-system/TOKENS.css">
```

Then use the custom properties anywhere:

```css
.my-header {
  color: var(--accent);
  font-family: var(--font-sans);
}
```

---

## Visual Identity Summary

```
Background:      #fcf9f8  (ivory)
Text:            #1c1b1b  (obsidian)
Primary accent:  #b72301  (safety orange)
Secondary:       #c45a00  (warm amber)
Border:          rgba(28,27,27,0.10)
Good:            #1a7a3e  (green)
Bad:             #b72301  (orange-red)
Warn:            #c45a00  (amber)

Prompt symbol:   >
Tool prefix:     |
```

---

## Key Design Principles

1. **Orange on ivory** — Safety orange and warm amber against an ivory background. The palette suggests signal, clarity, and urgency without noise.

2. **Technical brutalism** — Hard 1px borders, 0px border-radius, no decorative shadows. Surfaces are work areas, not decorative cards.

3. **Semantic color by role** — Every UI element has a predictable color mapping. Orange = active/primary, green = ok, amber = warn, obsidian = text.

4. **Single font family** — Space Grotesk for everything: display, body, and monospace contexts. No mixing.

5. **One theme mode** — Light only (Amber Signal). No dark mode toggle.

6. **Dot grid texture** — The main stage uses a subtle 20px dot grid (`radial-gradient`) to suggest drafting paper / planning surface.

---

## Version

Amber Signal design language — May 2026.
