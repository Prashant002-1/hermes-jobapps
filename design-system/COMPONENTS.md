# JobApps Design System — Components

> Source: `web/styles.css`, `web/index.html`

---

## 1. App Shell

```
┌──────────────────────────────────────────────┐
│  [logo] JobApps    [operator mark] connected ●│  <- header .bar
├────────┬─────────────────────────────────────┤
│        │                                     │
│  Nav   │           Stage                     │
│  Rail  │    (dot grid background)            │
│  220px │                                     │
│        │                                     │
└────────┴─────────────────────────────────────┘
```

- **Header** (`<header class="bar">`): 56px height, white background, strong bottom border.
- **Nav Rail** (`<nav class="nav-rail">`): 220px wide, white background, strong right border. Icon + text labels side by side.
- **Stage** (`<main class="stage">`): Flexible width. Ivory background with 20px dot grid.

---

## 2. Header Bar

```
[logo bars] JobApps
            HERMES
```

- **Logo**: 5 vertical bars (SVG rect elements), gradient from amber (`#c45a00`) to orange (`#b72301`).
- **Title**: "JobApps" — 20px, Space Grotesk semibold, obsidian.
- **Subtitle**: "HERMES" — 10px, Space Grotesk, text-tertiary, uppercase.
- **Center**: `hermes-jobapps-mark.svg`, a minimal pixel-art JobApps wordmark.
- **Right**: Connection status text + breathing status dot (8px circle).

### Status Dot States

| State | Color | Shadow | Animation |
|-------|-------|--------|-----------|
| Connected | `#1a7a3e` (green) | soft teal glow | pulse 3s infinite |
| Thinking | `#c45a00` (amber) | amber glow | pulse 0.8s infinite |
| Disconnected | `#b72301` (orange) | red glow | none, static |

---

## 3. Nav Rail

- Items: icon (20px Material Symbols) + label side by side.
- Padding: 8px 12px per item.
- Active state: orange text, left 3px orange border, sunken background (`#e8e4e0`).
- Hover: slightly darker background (`#ede9e5`), full opacity.
- Divider: 1px border line between groups.
- Spacer pushes bottom items (Sessions, Chat) to the bottom.

---

## 4. View Header

```
EYEBROW          [Primary Button] [Button]
Page Title
```

- **Eyebrow**: 10px uppercase, amber, letter-spacing 0.08em.
- **Title**: 32px bold, Space Grotesk, obsidian, tight letter-spacing.
- **Actions**: Button group aligned to the right.

---

## 5. Buttons

### Default Button

- Height: 34px
- Padding: 0 12px
- Border: 1px `rgba(28,27,27,0.10)`
- Background: `#f5f2f0`
- Text: 12px Space Grotesk medium, text-secondary
- Hover: darker border, darker background, obsidian text
- Active: scale(0.97)

### Primary Button

- Border: amber tinted (`rgba(196,90,0,0.30)`)
- Background: amber dim (`rgba(196,90,0,0.08)`)
- Text: amber (`#c45a00`)
- Hover: amber border, amber glow background, obsidian text

### Icon Button

- 18px Material Symbols icon inside button, vertically centered.

---

## 6. Chips

- Height: 28px
- Padding: 0 12px
- Border: 1px `rgba(28,27,27,0.10)`
- Background: transparent
- Text: 10px Space Grotesk medium, text-tertiary
- Hover: darker border, text-secondary
- Active: orange border, orange text, orange dim background

---

## 7. Inputs

- Height: 38px
- Padding: 0 12px
- Border: 1px `rgba(28,27,27,0.10)`
- Background: `#f0ece8` (sunk)
- Text: 12px Space Grotesk, obsidian
- Focus: orange border, 1px orange dim glow ring
- Placeholder: text-tertiary

---

## 8. Stat Strip

```
┌──────────┬──────────┬──────────┬──────────┐
│ 0        │ 0        │ 0        │ 0        │
│ Jobs     │ Applied  │ Pending  │ Follow-… │
└──────────┴──────────┴──────────┴──────────┘
```

- Grid: 4 equal columns, 1px gap (border color), outer border.
- Each cell: white background, 16px 20px padding.
- Value: 32px bold display font.
- Label: 10px uppercase mono, text-tertiary.
- Hover: surface background.

---

## 9. Ops Bar

Same structure as stat strip (4 columns, 1px gaps):

- Label: 10px uppercase mono, text-tertiary.
- Value: 16px semibold mono, obsidian.

---

## 10. Cards

- Border: 1px `rgba(28,27,27,0.10)`
- Background: white
- Hover: darker border
- No border-radius (0px)
- No shadow

### Card Head

- Padding: 12px 20px
- Bottom border: 1px separator
- Title (`h2`): 10px uppercase semibold, text-secondary
- Kicker: 10px lowercase, text-tertiary

---

## 11. Pipeline

- 5 columns: New, Applied, Interview, Offer, Closed.
- Column header: 10px uppercase semibold, text-tertiary, bottom border.
- Cards inside columns:
  - Padding: 8px 12px
  - Border: 1px default + 3px left border (default color)
  - Background: surface
  - Hover: darker border, orange left border, translateX(2px)

---

## 12. Timeline

- Vertical line: 1px border color, positioned absolutely.
- Items: 18px icon column + content column.
- Dot: 7px circle, text-tertiary by default.
  - Event dot: orange
  - Run dot: amber
  - Material dot: green
- Title: 12px medium, obsidian.
- Meta: 10px mono, text-tertiary.

---

## 13. Discovery Cards

- Grid: content + side metadata.
- Left border: 3px, color changes by status:
  - `ready`: green
  - `needs_review`: amber
  - `blocked`: orange
  - `prepared`: orange
  - `approved`: amber

---

## 14. Criteria Cards

- Full-width card with left border indicator:
  - `blocker`: orange
  - `flag`: amber
  - `clear`: green

---

## 15. Chat Layout

```
┌────────────────────────┬──────────────┐
│                        │              │
│   Transcript           │  Agent       │
│                        │  Panel       │
│   > user msg           │  260px       │
│   | assistant msg      │              │
│   * tool call          │              │
│                        │              │
├────────────────────────┤              │
│ [input box]      [send]│              │
└────────────────────────┴──────────────┘
```

### Messages

- Grid: 20px prefix column + content column.
- Prefix characters: `>` (user, orange), `|` (assistant, amber), `*` (tool, orange), `.` (system, muted).
- Body: 16px, Space Grotesk, obsidian.
- Inline code: surface background, orange text.
- Code blocks: surface background, muted text, no border-radius.

### Composer

- Textarea: flexible height (42px to 180px), sunk background, orange focus ring.
- Send button: 42px square, orange border, orange dim background, orange icon.

### Agent Panel

- 260px wide, left border, white background.
- KV grid: 70px label + value.
- Usage grid: 2-column, 1px gap, border color.
- Events: scrollable list of event kind + detail.

---

## 16. Badges

| Variant | Text Color | Background |
|---------|-----------|--------------|
| `badge-apply` | `#1a7a3e` | `rgba(26,122,62,0.08)` |
| `badge-skip` | `#b72301` | `rgba(183,35,1,0.08)` |
| `badge-pending` | `#8a8580` | `#f5f2f0` |
| `badge-review` | `#c45a00` | `rgba(196,90,0,0.08)` |

Height: 20px, padding: 0 4px, 10px mono semibold, lowercase.

---

## 17. Animations

```css
@keyframes fade-in {
  from { opacity: 0; }
  to   { opacity: 1; }
}

@keyframes slide-up {
  from { opacity: 0; transform: translateY(8px); }
  to   { opacity: 1; transform: translateY(0); }
}

@keyframes pulse-lamp {
  0%, 100% { opacity: 0.6; }
  50%      { opacity: 1; }
}

@keyframes breathe {
  0%, 100% { opacity: 0.5; }
  50%      { opacity: 0.9; }
}
```

---

## 18. Layout & Spacing

Base grid: 4px

```css
--space-1:  4px;
--space-2:  8px;
--space-3: 12px;
--space-4: 16px;
--space-5: 20px;
--space-6: 24px;
--space-8: 32px;
--space-10: 40px;
--space-12: 48px;
--space-16: 64px;
```

Radii:
```css
--radius-sm:  0px;
--radius-md:  0px;
--radius-lg:  0px;
--radius-xl:  0px;
--radius-full: 9999px;  /* status dots only */
```

Max content width: 1440px
Header height: 56px
Nav width: 220px

---

## 19. Scrollbar

```css
::-webkit-scrollbar { width: 6px; height: 6px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: rgba(28,27,27,0.35); border-radius: 0px; }
::-webkit-scrollbar-thumb:hover { background: #8a8580; }
```
