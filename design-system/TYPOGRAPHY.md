# JobApps Design System — Typography

> Source: `design-system/TOKENS.css`, `web/styles.css`

---

## Font Stack

JobApps uses **Space Grotesk** exclusively. One family for display, body, and monospace contexts.

```css
@import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;600;700&display=swap');

:root {
  --font-display: "Space Grotesk", system-ui, -apple-system,
                 BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
  --font-sans:   "Space Grotesk", system-ui, -apple-system,
                 BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
  --font-mono:   "Space Grotesk", ui-monospace, monospace;
}
```

---

## Base Metrics

```css
:root {
  --text-base:    14px;
  --leading-normal: 1.5;
}

html {
  font-size: var(--text-base);
  line-height: var(--leading-normal);
}
```

---

## Size Scale

| Token | Size | Usage |
|-------|------|-------|
| `text-xs` | 10px | Labels, metadata, eyebrow tags, status bar |
| `text-sm` | 12px | Body copy, card content, buttons, inputs |
| `text-base` | 14px | Default body text |
| `text-md` | 16px | Large body, row titles, composer input |
| `text-lg` | 20px | Header title (bar-title), view headings |
| `text-xl` | 24px | — |
| `text-2xl` | 32px | Dashboard stat values, page titles |

---

## Weight Scale

| Token | Weight | Usage |
|-------|--------|-------|
| `weight-normal` | 400 | Body text, descriptions |
| `weight-medium` | 500 | Labels, nav items, buttons, chips |
| `weight-semibold` | 600 | Titles, headings, stat values, card headers |
| `weight-bold` | 700 | Page titles, display numbers |

---

## Letter Spacing

- **Display / Headings**: `-0.02em` (tight, modern)
- **Uppercase labels / eyebrows**: `0.06em` to `0.08em` (technical, spaced)
- **Nav items**: `0.04em`
- **Body**: `0` (natural)

---

## Text Treatments

| Element | Font | Size | Weight | Color | Transform |
|---------|------|------|--------|-------|-----------|
| Page title (`h1`) | display | 32px | bold | text | — |
| Eyebrow label | mono | 10px | medium | gold | uppercase |
| Card header (`h2`) | mono | 10px | semibold | text-secondary | uppercase |
| Stat value | display | 32px | bold | text | — |
| Stat label | mono | 10px | — | text-tertiary | uppercase |
| Nav item | mono | 12px | medium | text-secondary | — |
| Nav item active | mono | 12px | medium | accent | — |
| Button | mono | 12px | medium | text-secondary | — |
| Button primary | mono | 12px | medium | gold | — |
| Input | mono | 12px | — | text | — |
| Chip | mono | 10px | medium | text-tertiary | — |
| Chip active | mono | 10px | medium | accent | — |
| Timeline title | sans | 12px | medium | text | — |
| Timeline meta | mono | 10px | — | text-tertiary | — |
| Pipeline head | mono | 10px | semibold | text-tertiary | uppercase |
| Pipe card title | sans | 12px | semibold | text | — |
| Pipe card company | sans | 12px | — | text-secondary | — |
| Badge | mono | 10px | semibold | — | lowercase |
| Bar title | display | 20px | semibold | text | — |
| Bar subtitle | mono | 10px | — | text-tertiary | uppercase |
| Bar status | mono | 10px | — | text-tertiary | lowercase |
| Composer input | mono | 16px | — | text | — |
| Message body | sans | 16px | — | text | — |
| Message prefix | mono | 16px | — | accent / gold | — |
| Tool call | mono | 10px | — | text-tertiary | — |
| Trace label | mono | 10px | — | accent | — |
| Trace detail | mono | 10px | — | text-tertiary | — |
| Agent KV key | sans | 10px | — | text-tertiary | — |
| Agent KV value | mono | 10px | medium | text-secondary | — |

---

## Role Glyphs (Chat)

```
>  user       (prefix: >, color: accent)
|  assistant  (prefix: |, color: gold)
*  tool       (prefix: *, color: accent)
.  system      (prefix: ., color: text-tertiary)
```

---

## Material Symbols

Material Symbols Outlined are used for all UI icons:

```css
@import url('https://fonts.googleapis.com/css2?family=Material+Symbols+Outlined:opsz,wght,FILL,GRAD@20..48,100..700,0..1,-50..200&display=swap');
```

Icon size: 20px in nav, 18px in buttons.
Active nav items use `FILL: 1`; inactive use `FILL: 0`.
