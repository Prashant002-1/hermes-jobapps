# Cockpit design

The cockpit displays the state of the search in an organized way. It does not direct. Acting is the user's job; the interface shows what there is to act on and stays out of the way.

## Principles

- **Display, do not direct.** No instructions, hints, advice or nagging in the interface. Labels are short nouns. An empty state is one neutral phrase.
- **No urgency theater.** A date is a plain date. A date in the past is set in the accent color and nothing more. No counters of days overdue, no snooze, no quick-action buttons in lists.
- **Hierarchy before density.** Each page leads with the few things that matter. Everything else sits behind a disclosure and opens on request. Forms appear only when asked for.
- **Type and space, not boxes.** Sections and rows are separated by whitespace and typography. Borders belong to controls and the app shell. A subtle fill marks selection.
- **One primary action per page at most.** Everything secondary is a quiet text button.

## Visual language: Amber Signal

Warm ivory surfaces, near-black text, one safety-orange accent, square corners, fine rules, a narrow navigation rail. Hanken Grotesk throughout, bundled with the plugin so nothing loads from the network.

| Use | Size |
|---|---|
| Page title | 32px |
| Section title | 20px |
| Body | 14px |
| Metadata | 12px |
| Eyebrow label | 10px, uppercase, letter-spaced |

Spacing follows a 4px rhythm, with more space between groups than within them. No shadows, no rounded cards, no decorative color.

Tokens are custom properties on `.jobapps-root` in `dashboard/dist/style.css`. Every rule is scoped under that class, so the stylesheet cannot affect the Hermes dashboard around it. Dark mode follows the system setting.

## Pages

| Page | Shows |
|---|---|
| Overview | Four plain counts, the one job to continue with, what is up next, and disclosures for the rest. |
| Jobs | A list grouped by stage beside one focused job: status, next step, materials, and the record behind disclosures. |
| People | The people being tracked, with status and next touch. Editing opens a form. |
| Leads | Postings found by search, with links to open, shortlist, start or dismiss. |
| Insights | The funnel in plain numbers and simple tables. |
| Library | Profile, voice, playbook and evidence, rendered for reading. |

Standalone, the cockpit has a top bar and a collapsible navigation rail. Inside the Hermes dashboard it drops both and uses one quiet row of tabs, because the dashboard supplies its own chrome.

## Engineering rules

- One framework-free script (`dashboard/dist/index.js`) and one stylesheet. No build step, no dependencies, no network requests for assets.
- Data is never inserted as HTML. The Markdown renderer builds DOM nodes and only links http, https and mailto targets.
- All requests go through one injected API client, so the same script runs standalone (`python3 -m hermes_jobapps ui`) and as a Hermes dashboard tab.
- Real buttons for anything clickable, labelled controls, visible focus, keyboard-operable rows and disclosures, reduced motion respected, usable down to 390px wide.
- `python3 scripts/ui_preview.py` serves the cockpit over invented sample data for review.
