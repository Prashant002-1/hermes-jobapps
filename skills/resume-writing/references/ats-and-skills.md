# ATS vocabulary and the Skills section

Load when building the Skills section, when the check reports weak requirement coverage, or when the user asks about ATS or keywords.

## What actually matters

Most applicant tracking systems parse the PDF into text, then a recruiter searches or skims. Two things follow:

1. The text layer must parse cleanly: single column, real text, standard section names.
2. The posting's exact terms must appear where they are true, because recruiters search for the words they wrote.

There is no hidden score to game. Keyword stuffing reads badly to the human who makes the decision.

## Extract the vocabulary

From the posting in the brief, list:

- Hard terms: languages, frameworks, platforms, methods, certifications, domain nouns.
- The title and its close variants.
- Verbs for the core work: "on-call", "code review", "experiment design", "stakeholder reporting".
- The spelling the posting uses: "PostgreSQL" or "Postgres", "CI/CD", "A/B testing".

Sort each term into one of three bins:

| Bin | Meaning | Action |
|---|---|---|
| Supported | The evidence shows hands-on use | Use the posting's exact spelling. Place it in the bullet where it happened, or in Skills. |
| Adjacent | The evidence shows a close relative (a different cloud, a sibling framework) | Name what was actually used. Do not swap in the posting's term. |
| Unsupported | Nothing in the evidence or profile | Leave it out. If it is central to the role, ask the user once whether they have used it. |

A user's question about an unfamiliar tool is not confirmation that they have used it.

## Where terms go

- In a bullet, when the term is part of the mechanism and the sentence would be unclear without it.
- In Skills, for everything else that is true.
- In the title line or summary, only as part of a truthful identity.

Never write a bullet whose purpose is to carry a keyword. If removing the term leaves nothing, the bullet fails the gate.

When the posting and the evidence use different names for the same thing, use the posting's spelling once and keep it consistent. Where a recruiter may search either form, write both once: "Amazon Web Services (AWS)".

## Skills section

- Ordinary categories a practitioner would recognize: `Languages`, `Frameworks`, `Data`, `Cloud and infrastructure`, `Tools`. Three to five rows.
- Never invent a category to mirror the posting, and never expand a name to match its phrasing ("Git Version Control", "Command-Line Tools").
- Practitioner spellings: `Git`, `C++`, `PostgreSQL`, `scikit-learn`.
- Order within a row: the role's core first, then the rest of the truthful inventory from `profile/profile.md`.
- Each row fits on one rendered line. Trim the least relevant items rather than wrapping.
- Cut generic filler that the bullets already prove: "Problem Solving", "Data Quality", "Communication", "Workflow Management".
- Soft skills do not belong in Skills. Show them in a bullet through what was done.
- Keep breadth the user asked to keep. Do not silently drop languages to make space.
- No proficiency bars, star ratings or self-assigned levels.

## Parse-safe structure

- Single column for the body. Dates may sit right-aligned on the same line as the role.
- Standard headings: Experience, Education, Projects, Skills.
- Real text for everything: no text inside images, no icon fonts standing in for words such as "email" or "phone".
- Contact details in the body of the page, not in a header or footer region.
- One consistent date format. Month and year, with a plain hyphen between them unless the playbook says otherwise.
- Links as short readable text with the full URL behind them.
- Ordinary bullet characters.

## Verify the final PDF text

The source is not the proof. After the build, read the extracted PDF text (the check reports coverage; `pdftotext` shows the raw layer) and confirm:

- Each supported key term appears, spelled as the posting spells it.
- Special characters survived: `C#`, `C++`, `.NET`, `Node.js`, `CI/CD`. Markup languages can swallow `#`, `$`, `@`, `*` or `//` silently.
- Reading order is sensible: title, then company and dates, then bullets, for each role.
- No stray text: template placeholders, comments, notes to self, internal labels.
- The name, email and phone match `profile/profile.md` exactly.

A term missing from the PDF text after appearing in the source is a build defect: see `jobapps:material-build`.

## Coverage is a floor, not the goal

Requirement coverage tells you whether the reader will find what they search for. It does not tell you the resume is good. When coverage is low because the candidate lacks the experience, leave it low. Report which requirements have no supporting evidence in one neutral line, ask whether any evidence is missing from the workspace, and do not pad.
