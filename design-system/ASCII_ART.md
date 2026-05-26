# JobApps Design System — ASCII Art & Brand Assets

> Source: `web/index.html` (logo bars), `web/styles.css`

---

## 1. Header Logo — Bar Motif

The JobApps header uses a geometric bar motif (5 vertical bars of varying heights) rendered as inline SVG. It evokes signal bars, drafting marks, and wing feathers.

### SVG Structure

```svg
<svg viewBox="0 0 28 28" fill="none">
  <rect x="1"  y="6"  width="3" height="16" rx="1.5"/>
  <rect x="7"  y="9"  width="3" height="13" rx="1.5"/>
  <rect x="13" y="3"  width="3" height="22" rx="1.5"/>
  <rect x="19" y="7"  width="3" height="15" rx="1.5"/>
  <rect x="25" y="10" width="3" height="13" rx="1.5"/>
</svg>
```

### Color Mapping

| Bar | Position | Fill (odd) | Fill (even) |
|-----|----------|------------|-------------|
| 1 | x=1 | `#a34a00` (gold-container) | — |
| 2 | x=7 | — | `#c45a00` (gold) |
| 3 | x=13 | — | `#b72301` (accent) |
| 4 | x=19 | — | `#c45a00` (gold) |
| 5 | x=25 | `#a34a00` (gold-container) | — |

Odd-indexed bars: `var(--gold-container)` — darker amber.
Even-indexed bars: `var(--gold)` — warm amber, with the center bar using `var(--accent)` — safety orange.

### Favicon

Same bar motif, 28x28, encoded as data URI SVG:

```html
<link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 28 28'>...bars...</svg>">
```

---

## 2. Brand Identity Strings

```typescript
const BRAND = {
  name:       "JobApps",
  subtitle:   "HERMES",
  parent:     "Hermes",
  prompt:     ">",
  tool:       "|",
  center_mark: "hermes-jobapps-mark.svg",
}
```

### Header Layout

```
[bar motif] JobApps             [pixel JobApps wordmark]
            HERMES
```

- Product name: "JobApps" — 20px, Space Grotesk semibold.
- Context label: "HERMES" — 10px, Space Grotesk, text-tertiary, uppercase.
- Center mark: a minimal pixel-art JobApps SVG wordmark.

---

## 3. CSS Gradient Reference

For web/display contexts where you want the gradient pattern:

```css
.jobapps-logo-gradient {
  background: linear-gradient(
    180deg,
    #a34a00 0%,      /* gold-container — outer bars */
    #c45a00 33%,     /* gold — inner bars */
    #b72301 66%,     /* accent — center bar */
    #c45a00 100%     /* gold — inner bars */
  );
  -webkit-background-clip: text;
  background-clip: text;
  color: transparent;
}
```

---

## 4. Status Indicator Emoji

The status bar uses a simple colored dot rather than emoji faces:

| State | Visual |
|-------|--------|
| Connected | Green circle, breathing pulse |
| Thinking | Amber circle, fast pulse |
| Disconnected | Red circle, static |

---

## 5. Chat Role Prefixes

```
>  user       (prefix: >,  color: accent)
|  assistant  (prefix: |,  color: gold)
*  tool       (prefix: *,  color: accent)
.  system      (prefix: .,  color: text-tertiary)
```

These render as 20px-wide prefix columns in the transcript grid, using Space Grotesk at 16px.
