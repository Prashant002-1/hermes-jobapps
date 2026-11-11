---
name: cover-letter-writing
description: "Use when writing or revising a cover letter. A letter adds what the resume cannot: a through-line, real motivation and judgment, proven by one concrete story in the candidate's voice."
version: 1.0.0
license: MIT
metadata:
  hermes:
    tags: [career, cover-letter, writing, voice]
    related_skills: [jobapps:jobapps, jobapps:resume-writing, jobapps:material-build, jobapps:outreach]
---

# Cover letter writing

A cover letter is not a prose resume and not a requirement-by-requirement compliance table. It answers one question: why does this person's way of working make sense for this employer's actual work, and why is this the right next step for them? If the company name can be swapped without changing the argument, the letter fails.

## The thesis comes first

Before drafting, write one sentence that connects:

1. the employer's real work or operating problem,
2. the candidate's honest reason for choosing it,
3. the behavior their strongest evidence proves.

"The role requires X and the candidate has X" is not a thesis. Keep working until the sentence could only be about this candidate and this employer.

The motivation must be real. Look for it in `profile/profile.md` (target direction), the job's Notes, and what the user has said in this conversation. Do not manufacture a personal discovery, a lifelong passion or a product habit the candidate does not have. If no true reason is on record, ask one question before writing: "What made you stop on this role rather than the similar ones?" Write the answer into the job's Notes. If the user wants a draft anyway, build the thesis on the work itself and keep the motivation plain and small.

## What goes in

- **One primary story**, told with mechanism and consequence: the situation, the decision the candidate made and why, what they did, what changed. Choose the story that proves the thesis, not the most impressive one. The letter should show how they think; the resume already lists what they did.
- **At most two supporting anchors**, one sentence each, and only when each answers a different concern (works inside a team, operates what they build, communicates with non-specialists).
- **The company-specific paragraph**: one concrete thing about the employer's work (a product decision, a constraint of their domain, something the team published) and what it means for how the candidate would work there. Never praise, never the posting read back. Use the Research section of `job.md`; if it is empty, read one or two first-party sources and stop.
- **Direction**: what they can contribute now and where they want to grow. Stated once.

Leave out: a tour of every employer, technology lists, restated resume bullets, a gap inventory, anything the reader has to take on trust. A number belongs only when it changes the reader's sense of scope or rigor.

## Voice

Write from `profile/voice.md` and the playbook sections `All documents` and `Cover letter`; they override the defaults here. Defaults: first person, short declarative sentences, plain words, prose paragraphs with no headings or bullets. Ambition shows through choices and actions, not adjectives. When the user supplies their own draft or skeleton, keep their idea order, phrasing and cadence; fix grammar and clarity, trim redundancy, and do not restructure.

Banned unless the voice file asks for them: "I am excited/thrilled to apply", "I believe I am a strong fit", "innovative", "passionate", "fast-paced", "I would welcome the chance", "leverage", consulting language, and praise of the company's mission in general terms.

## A change of direction

When the candidate's recent lane differs from the target, do not hide it and do not apologize for it. State the pull toward the target work, name the recent lane plainly, show the target-relevant behavior already present in the strongest evidence, and say what the recent lane adds. Never open with what is missing. Claim intentions (a degree, a field change) only when the user has stated them now; an old letter is not a source of current plans.

## Length, format and file

- Length is diagnostic, not a target. A finished letter usually lands between 250 and 400 words. Much shorter: the story is missing its mechanism. Much longer: motivation is repeated or a second story crept in.
- One page. Three to five paragraphs whose order follows the thought.
- Start from the candidate's approved letter source (an earlier job folder, else `templates/`). Preserve its format, header, typography and sign-off. Match the contact block of the current resume. Do not redesign because another template exists.
- File: `<Name> - Cover Letter - <Company> - <Role>.typ` or `.tex`, in the job folder.
- Address the team or hiring manager only by a name the posting or a verified source gives. Otherwise use a team salutation. Leave the date out if it will go stale.

Structures, openings, closes and a worked example: `references/letter-patterns.md`. Load it for a first draft or when the draft reads as generic.

## Workflow

1. `jobapps_brief(job, purpose="cover_letter")`. Read the resume in the job folder if one exists, so the letter adds to it.
2. Write the thesis sentence. Choose the primary story and any supporting anchors from the evidence.
3. Draft the whole letter in one pass. Then run the review below once and make one consolidated repair.
4. `jobapps_check(path)`. Repair findings, at most three rounds; layout issues go to `jobapps:material-build`.
5. Give the user the PDF path. Update `jobapps_track` only if the next action changed.

## Review before the check

- Would the argument survive swapping in a competitor's name? If yes, the company paragraph is not specific.
- Does the story show a decision and its consequence, or only a list of tools?
- Does the letter tell the reader something the resume does not?
- Is the motivation true, specific and stated at its real intensity?
- Is every fact in the evidence? Is any weakness raised that the reader had not asked about?
- Does the close add direction, or repeat the opening?
- Read it aloud in the candidate's voice. Cut any sentence they would not say.

## Revisions

Repair what was named. "Too dense" is a layout request: keep the approved text and fix spacing through `jobapps:material-build`. "Shorter" means trim repeated motivation and explanation first, keeping the story's mechanism and consequence. Outreach copy is not a letter: a message earns a reply, a letter makes the full argument.
