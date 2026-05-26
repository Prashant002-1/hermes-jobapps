# Hermes JobApps Branding

JobApps is a career-operator cockpit built on the Hermes agent framework. It should feel like a technical workbench — signal, clarity, urgency.

## Brand Relationship

- **Parent framework**: Hermes — agent runtime, memory, tool dispatch, chat.
- **Product layer**: JobApps adds opportunity ingestion, blocker preflight, evidence mapping, LaTeX materials, networking, and follow-up state.
- **Naming**: Use `JobApps` as the product name in the header, with `HERMES` as the parent-runtime subtitle. The center header mark is a minimal pixel-art JobApps wordmark; do not use duplicate runtime text such as `jobapps · jobapps`.

## Visual Tokens

Use `design-system/TOKENS.css` as the baseline:

| Token | Value | Usage |
|-------|-------|-------|
| `--bg` | `#fcf9f8` | Main app background |
| `--bg-raised` | `#ffffff` | Cards, panels, nav, header |
| `--bg-sunk` | `#f0ece8` | Inputs, recessed surfaces |
| `--text` | `#1c1b1b` | Primary text — obsidian |
| `--text-secondary` | `#4a4745` | Labels, metadata |
| `--text-tertiary` | `#8a8580` | Muted info, placeholders |
| `--accent` | `#b72301` | Active states, links, focus rings, decisions |
| `--gold` | `#c45a00` | Eyebrows, secondary highlights, primary buttons |
| `--good` | `#1a7a3e` | Success, ready, healthy |
| `--bad` | `#b72301` | Error, blocked, skip |
| `--warn` | `#c45a00` | Review needed, thinking |
| `--border` | `rgba(28,27,27,0.10)` | Default borders |
| `--border-strong` | `rgba(28,27,27,0.35)` | Header, nav rail, panel separators |
| `--font-sans` / `--font-display` / `--font-mono` | `"Space Grotesk"` | All typography |

## Design Principles

- **Technical brutalism**: Hard 1px borders, 0px border-radius, no decorative shadows.
- **Signal over decoration**: Orange means action. Green means go. Amber means wait. Obsidian means read.
- **Work surfaces, not cards**: Panels are drafting tables. The dot grid on the stage reinforces this.
- **Single font family**: Space Grotesk for everything. No mixing display and mono families.
- **Spare copy**: Use operational language. No marketing slogans.

## Interface Voice

Keep product copy spare and operational:

- `State` — dashboard view
- `Brain` — memory view
- `Find` — discovery/research view
- `Jobs` — opportunities list
- `Materials` — generated artifacts
- `Network` — contacts and outreach
- `Events` — activity log
- `Rules` — blocker criteria
- `Sessions` — conversation history
- `Chat` — Hermes runtime

Avoid: "Get started", "Your journey", "AI-powered", "Supercharge".

## Layout Feel

- Dense but breathable. 8px base grid, 4px micro-grid.
- The header is a thin chrome line — 56px, white, strong bottom border.
- The nav rail is a tool palette — 220px, white, strong right border, icon + label.
- The stage is a drafting surface — ivory, dot grid, max 1440px content.
- Chat should show Hermes as an active operator, not a hidden backend.
- Status and evidence should be visible before long drafts.
- LaTeX artifacts should feel inspectable and reproducible.

## Customization Path

Start from the Amber Signal tokens in `TOKENS.css`, then add JobApps-specific aliases in `web/styles.css`. If a real theme picker appears later, follow `design-system/SKIN_SYSTEM.md` and keep every visual property overridable with safe fallbacks.

## Theme Name

**Amber Signal** — ivory background, safety orange accents, warm amber highlights, sharp corners, hard borders, dot grid stage.
