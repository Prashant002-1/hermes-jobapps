# Academic / PhD CV workflow

Use this reference when the user needs a one-off academic CV for PI outreach, PhD applications, research assistant roles, fellowships, or lab opportunities. This is an exception to the normal JobApps resume-default: academic CVs may stay in LaTeX and may be 2–3 pages when the audience is a professor or admissions/research reader.

## Decision pattern

- Treat the CV as a research narrative, not a job resume.
- Keep the academic structure: Research Interests, Education/Honors, Research Experience, Manuscripts/Presentations, Technical/Applied Systems, Teaching/Leadership, Skills.
- Put research before internships when the target is a PI/lab.
- Use the old CV/source as structure and extraction material, not as authoritative final copy if facts are stale.
- For interdisciplinary PhD leads, do not pretend the applicant has the target lab's full domain background. Position confirmed technical depth as a contribution to the target domain.

## Content rules

- Claim papers only at their confirmed status. If a manuscript is submitted, write `Manuscript submitted for conference review`; do not imply acceptance, publication, or peer-reviewed status.
- Tie older research to the current arc when truthful. Example: gamification research can support later AI learning-system / tutoring-system work through motivation, feedback timing, objective alignment, and human-centered system design.
- Convert software projects into academic systems language when useful: durable state, provenance, retrieval, evaluation, human-agent workflows, semantic memory, typed tool use, data models, and learning-system design.
- Avoid internal JobApps/Hermes operational language in candidate-facing prose: no workflow scaffolding, learned preferences, approval-state labels, application-status language, or meta instructions.

## Build workflow

1. Back up the user-provided CV source before rewriting.
2. Read the old source and any relevant paper/project source directly when available.
3. Rewrite as an academic CV rather than compressing into a one-page resume.
4. Use Tectonic/XeTeX with a temp output directory; copy back only the final PDF.
5. For macOS typography, `fontspec` with Avenir Next can work well for a modern academic CV if the font is available.
6. Add manual page breaks only after rendering shows they improve section flow.

## Verification checklist

- Compile succeeds with no LaTeX errors; grep compile logs for errors/undefined/overfull when possible.
- Confirm page count. For PhD/PI CVs, 3 pages is acceptable when the content is research-heavy and visually controlled.
- Extract text with `pdftotext` and verify key claims survived.
- Scan for stale education phrasing such as `Expected` after graduation.
- Scan for contamination/internal language such as `approval gate`, `review_status`, `tailoring`, `learned preference`, `JD-specific`, or operational-state prose.
- Verify submitted/accepted/published wording explicitly.
- Render pages (`pdftoppm`, `qlmanage`, or equivalent) and visually inspect section breaks, spacing, cropping, and readability.
- Final report should include source path, PDF path, backup path, page count, and the factual-status checks.
