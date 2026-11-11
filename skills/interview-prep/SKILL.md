---
name: interview-prep
description: "Use when preparing for or debriefing a job interview. Builds a prep pack in the job folder: the round, sourced research, a story bank from evidence, likely questions, questions to ask, logistics, and the debrief."
version: 1.0.0
license: MIT
metadata:
  hermes:
    tags: [career, interview, preparation, stories, debrief]
    related_skills: [jobapps:jobapps, jobapps:outreach, jobapps:application-answers]
---

# Interview preparation

The output is not a generic question bank. It is a grounded model of what the team does, what this round tests, what the interviewers have already read, and how the candidate can explain their real experience under pressure without overselling or underselling. Understanding comes before scripting.

## Scope the request

Prepare the layer the user asked for: understanding the company, understanding the role, positioning, likely questions, rehearsal, or logistics. A question about what the team does is not a request for a full pack. Work one step at a time and stop after each; a complete pack is built only when asked or when the interview is close. Rehearsal and discussion stay in chat. Write the pack file when the user wants something to keep.

## Lock the facts

1. `jobapps_brief(job, purpose="interview")`. It returns the posting, notes, materials, evidence and the playbook `Interview` section, which overrides the defaults here.
2. Establish from `job.md` and the user: the round, format, length, date and time zone, and who is interviewing (a named interviewer, not the scheduler). Ask for the invitation text if these are missing.
3. Read what the employer received: the resume, letter and `answers.md` in the job folder. List every number, title, date and claim an interviewer could probe. The candidate must be able to explain each one. If a submitted document framed something the user now dislikes, do not pretend it was not sent: prepare a spoken version that shifts emphasis without contradicting it.

## What each round tests

| Round | Tests | Prepare |
|---|---|---|
| Recruiter screen | Motivation, logistics, clear communication, no red flags | A 60 to 90 second introduction, why this role, salary and availability answers, questions about process |
| Hiring manager | Ownership, judgment, how they would work on this team | Three or four stories, the role's real problems, questions about the work |
| Technical | Problem solving aloud, fundamentals, depth in claimed skills | Practice in the stated format, deep review of everything on the resume |
| System design | Structuring ambiguity, trade-offs, scale reasoning | A method for the first five minutes, two designs from their domain, their own systems as examples |
| Behavioral | Past behavior as evidence: conflict, failure, influence, ambiguity | The story bank, mapped to themes |
| Take-home | Finished, readable work under a time limit | Scope control, a written rationale, the follow-up discussion |
| Onsite or panel | Consistency across people, stamina | Different stories for different interviewers, a question for each |

Detail by question type: `references/question-types.md`. Load it when drafting likely questions or practicing a specific round.

## Research, narrow and sourced

Research the work, not the mission statement. Stop when the role can be explained through one realistic day and one realistic failure. Use first-party sources first: the posting, the team's own writing, product documentation, talks, public code. For each responsibility in the posting recover: the thing owned, the people on the other side, what normal work looks like, what breaks and who notices. Ask why each tool in the posting is there.

Label every statement in the pack:

- **Verified**: stated in a current first-party source, with the link.
- **Inference**: supported by the posting plus public material; the private workflow is not public.
- **Scenario**: an illustration to make the work concrete, not a claim about their process.

For a named interviewer, read their public professional writing only. Separate what they said from what they shared. Do not infer a private rubric or coach a personality to please them. Candidate reports of the process count only with role, stage and date; say so when none can be verified.

## Map experience honestly

For each major responsibility, fill one row: target responsibility, direct evidence, transferable mechanism, new layer. State the new layer once, plainly, then spend the answer on the mechanism: "The platform is new to me; the diagnosis work is what I did on X." Never "I have not done this but I learn fast", and never "I built something similar so I know yours". Keep the user's chosen identity for each piece of work: a project stays a project, a pilot stays a pilot.

## Stories and answers

Build the story bank from evidence files: situation, decision, mechanism, consequence, what the candidate would change. Five or six strong stories cover most rounds. Outline answers as spoken beats in the candidate's voice (`profile/voice.md`), not scripts to memorize. Method and templates: `references/story-bank.md`. Load it when building or rehearsing stories.

Pressure points (a gap, a short tenure, a missing requirement, a change of lane) get one prepared answer each: the fact, stated once without apology, then the relevant strength. Authorization and salary answers come from `profile/profile.md` and follow `jobapps:application-answers`; never guess a status, and do not volunteer detail the interviewer did not ask for.

## Questions to ask them

Offer three or four, recommend two, plus one about next steps. Fit each to what that interviewer can answer: a recruiter knows process and priorities, a manager knows the team's problems, a peer knows the daily work. Each should be a question the candidate wants answered. Pattern: ask, listen, add one connected sentence at most. Not a planted question that launches another pitch.

## The pack

Write `interview-prep.md` in the job folder with these sections, omitting any that are not needed yet. It is working notes, not a checked document: do not run `jobapps_check` on it.

`Round and logistics` / `The role in plain words` / `What they have read` / `Research` (labeled) / `Experience map` / `Stories` / `Likely questions` / `Pressure points` / `Questions to ask` / `Plan`

Logistics: date, time and time zone, format and link, interviewer names and roles, what to have open (resume as sent, the posting, notes), and for remote rounds a check of camera, microphone and screen sharing.

When the interview is soon, the plan is time-boxed:

- **Tonight or tomorrow**: the introduction aloud three times, the two stories most likely to be asked, the claims on the resume, two questions, logistics. Nothing else.
- **Two to four days**: add the role model, the full story bank, one timed practice in the round's format.
- **A week or more**: add deeper research, weak-area review, a full mock, and a second pass on answers that ran long.

## After the interview

1. Capture in `job.md` Notes while fresh: questions asked, what went well, what stumbled, anything promised, names, and the stated next step and date.
2. A story or answer that worked, or a fact the user corrected, goes back into the evidence file. A reusable lesson goes in the playbook `Interview` section, in place.
3. Thank-you notes through `jobapps:outreach`. Drafts only.
4. `jobapps_track` with the next action and its date: the follow-up if a decision date was given, otherwise a check-in.

## Ready when

- Every claim in the submitted documents can be explained aloud.
- The role is understood as concrete work and failure modes, with inference labeled, and each major responsibility has a truthful parallel and a named new layer.
- The main stories fit in two minutes each, spoken.
- Pressure points are answered once, without self-disqualification, and logistics are confirmed.
