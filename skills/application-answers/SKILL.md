---
name: application-answers
description: "Use when answering application form questions. Covers short answers such as Why us and project questions, character-limited boxes, and screening fields: work authorization, salary, start date, referral."
version: 1.0.0
license: MIT
metadata:
  hermes:
    tags: [career, application, short-answers, forms]
    related_skills: [jobapps:jobapps, jobapps:cover-letter-writing, jobapps:resume-writing]
---

# Application answers

Answer the question that was asked, in the box it was asked in. A narrative question gets a specific reason, judgment or story. A factual field gets the fact. Neither gets a resume recital.

## Classify the question first

| Kind | Examples | The answer is |
|---|---|---|
| Motivation | "Why us?", "Why this role?" | One real reason tied to the employer's actual work, plus the evidence that the reason is acted on |
| Proof | "Tell us about a project", "Describe a hard problem", "Something you are proud of" | One story: situation, decision, mechanism, consequence |
| Character | "In your own words", "What do you want next?", "How do you work?" | A pattern in how the candidate works, shown through one or two moments. Not employer names and tools |
| Screening | Authorization, sponsorship, salary, start date, location, years of experience | The fact, stated directly. See `references/screening-fields.md` |
| Administrative | "How did you hear about us?", referral name, links, "Anything else?" | The literal truth, short. "Anything else" may stay empty |

Read the exact wording. "Why do you want to work here?" and "Why should we hire you?" are different questions. A question with two parts gets both parts answered, in order.

## Writing narrative answers

1. `jobapps_brief(job, purpose="application_answers")` once for the set. It returns the playbook sections `All documents` and `Application answers`; they override the defaults here.
2. Search earlier answers before writing: native search over `jobs/*/answers.md` for the question's key words. Reuse a strong approved answer as the skeleton, then re-specify everything that names the employer or the role. Never paste an answer that mentions another company.
3. Give each answer one job. In a set, no two answers lean on the same story; spread the evidence so the set shows range.
4. Lead with the answer. The first sentence should work alone if the reader stops there.
5. Use one concrete detail only this candidate would write: a habit, a decision, a failure, a trade-off, something a user said. Achievements serve the point; they are not the point.
6. Connect to the employer's real work with a fact, not praise and not the posting read back. If the motivation is not on record (profile target direction, job Notes, this conversation), ask one question instead of inventing a reason.
7. Voice from `profile/voice.md`. Defaults: first person, short plain sentences, no "I am excited", no "strong fit", no consulting language, no fake humility.
8. For proof questions, state prototype work as a prototype and team work as team work, with the candidate's part exact.

## Limits

- Find the limit before writing: words or characters, and whether the form states it. Record limits in the job's Notes ("Why us: 600 characters").
- `jobapps_check(path, max_chars=<limit>)` measures the whole file. If `answers.md` holds only that answer, check it directly. Otherwise write the one answer to a scratch file in the job folder (`answer-check.txt`), check it, move the passing text into `answers.md`, then delete the scratch file and its `qa/` report. Characters include spaces and punctuation; leave a small margin, since some forms count a line break as two.
- With no stated limit, match the box: a single-line field gets a phrase or sentence, a small text area 60 to 120 words, a large one up to 200. Longer only if the question demands a story.
- When a limit arrives after drafting, cut immediately and return the corrected text without commentary. Cut repeated setup and bolted-on lists first; keep the one mechanism that makes the answer specific.
- "More concise" means trim within the user's own structure. Keep their idea order and phrasing.

## Honesty on screening and logistics

These fields are legal and practical statements. Answer them from `profile/profile.md` (Constraints, Preferences) and `settings.json` (`rules.needs_sponsorship`), never from assumption.

- If the needed fact is absent or `null`, ask the user. Do not guess, and do not choose the answer that looks most acceptable.
- Never round up a number to clear a threshold (years of experience, GPA, salary history).
- Answer exactly what the field asks. Do not volunteer detail a yes or no field did not request.
- Demographic and self-identification questions, legal attestations and signatures are the user's alone. Leave them for the user and say so.

Load `references/screening-fields.md` when the form includes authorization, sponsorship, salary, years-of-experience, availability, relocation or referral fields.

## Saving and delivery

- Save to `answers.md` in the job folder: one `## <Question>` section per field, the question verbatim as the heading, the answer as plain text beneath. Update a section in place when revised; never keep two versions of one answer.
- Deliver in chat as plain text the user can paste, each answer in its own fenced block with no language tag and nothing else inside it. No Markdown inside answers: forms show asterisks and pound signs literally. Use line breaks, and plain hyphens only if a list is truly needed.
- If the user asks for plain text in chat, no block, or chat only, the latest delivery instruction wins. Chat only also means do not save.
- A correction turn delivers the corrected text first. Do not make the user wait on bookkeeping.
- The agent never fills or submits a form. The user pastes and submits.

## Final check

- Does the first sentence answer the question asked?
- Is there one specific, true reason or story, and no resume recital?
- Is every fact, number and date in the evidence or profile?
- Does the answer name the right company and role, and nothing from another application?
- Is it within the limit, in plain text, in the channel the user last asked for?
- Would the candidate say this aloud in an interview without flinching? They may be asked to.
