---
name: outreach
description: "Use when drafting networking or recruiter messages. Covers who to contact for a role, first-contact messages, referral asks, follow-ups, recruiter replies, thank-you notes and logging touches. Drafts only."
version: 1.0.0
license: MIT
metadata:
  hermes:
    tags: [career, networking, outreach, referrals, follow-up]
    related_skills: [jobapps:jobapps, jobapps:interview-prep, jobapps:job-search, jobapps:application-answers]
---

# Outreach

A message gets a reply when the recipient can see in ten seconds why it came to them, that the sender is credible, and what small thing is being asked. Everything here serves that. The agent drafts; the user sends.

## Who to contact, in order

Warmth first, then proximity to the role. Recommend one or two people, not a list to blast.

1. **People who already know the user.** Search `people/` for the company, and ask whether anyone they know works there or can introduce them. A warm introduction beats every cold message.
2. **The hiring manager or team lead** for the exact team, when the posting or a first-party source identifies them.
3. **The recruiter attached to the requisition**, or one whose stated scope matches the role family and location.
4. **A peer on the team** with the same or an adjacent title, who can describe the work or point to the right person.
5. **A shared-background contact** at the company (same school, former employer, community), even in another function. They are a router: ask who handles the role.

After an employee has referred the candidate, their part is done. Do not route status questions back through them unless the referral failed or they offered more.

## Finding and verifying

1. `jobapps_find_people(job=...)`, or `company` or `query`. It saves nothing.
2. Verify each person before recommending them. Search results can attach the requested company to anyone, and namesakes collide.
   - Current employer and title: from their current position on a public profile or the company's own page, not from a search snippet.
   - Shared background: from their education or work history, not from a keyword match.
   - Connection to this requisition: confirmed only if the posting or a first-party source names them. Otherwise label it "likely" and say why.
3. Report for each: current title, why they are relevant, role type (manager, recruiter, peer, router), what is unconfirmed, the public profile link, and an email only if a public source displays it. Never derive an address from a naming pattern.
4. If a contact does not clearly belong to the search, keep the message honest with a conditional: "If this sits with you, ...; if not, I would be grateful for a pointer."

## Anatomy of a first message

Three parts, in this order, and nothing else:

1. **Why them.** One specific, verifiable reason: something they wrote, built or said, their team's work, the shared background. Not flattery.
2. **One line of proof.** The single fact about the candidate most relevant to their work, from the evidence files. Not a biography.
3. **One small ask.** Something answerable in two minutes: a specific question, a pointer to the right person, or fifteen minutes. Name the role. Give an easy way to decline.

Limits: under about 110 words for a LinkedIn message, 60 to 150 for an email with a subject that names the role or the reason. A connection-request note is far shorter (a few hundred characters; check the form): reason plus ask only. Voice from `profile/voice.md`; playbook sections `All documents` and `Outreach` override these defaults.

Never: "I hope this finds you well", "pick your brain", "I know you are busy", "any advice would be appreciated", an attached resume nobody asked for, a request for a job, or a status question to a stranger.

Templates and worked examples for each situation: `references/message-patterns.md`. Load it when drafting.

## Referral asks

Ask for a referral only from someone who knows the candidate's work, or after a real conversation. With a stranger, ask about the team; if they offer to refer, accept. Make a yes effortless: the role link, a three-line blurb they can paste, the resume PDF path for the user to attach. Always include a graceful out. Someone who says "let me check whether I can help" is on hold: prepare, do not push.

## Follow-ups and when to stop

- Timing comes from `settings.json` follow-up settings; `jobapps_overview` lists people and applications that are due.
- One follow-up after the configured gap, in the same thread, three sentences at most, adding something new: a result, the submitted application, a sharper question. Never "just bumping this".
- At most one more, about a week later. Then stop: set the person to `paused`. Silence is an answer and the relationship may matter later.
- If they named a date, wait until it has passed. A thank-you with no question needs no reply and no follow-up.
- For an application gone quiet, one check-in to the recruiter or coordinator after the configured gap: role, date applied, continued interest, one new fact if there is one.

## Replies, recruiters and thank-you notes

- Recruiter reaches out: answer what they asked, in their order. Give availability as two or three concrete windows with a time zone. Take logistics from `profile/profile.md`; for salary and authorization follow `jobapps:application-answers`. For a role the user does not want, decline in two sentences and leave the door open.
- Thank-you after an interview: within a day, under 90 words, one specific thing from the conversation and one thing it adds (a thought, the answer promised). No re-pitch. Separate notes for separate interviewers, each different.
- Warm introductions: read the whole thread first. Note for each named person what they offered, what they already did, and whether direct contact is permitted. Write forwardable notes for the introducer to send; do not write to anyone whose willingness is still pending.

## Saving, logging, drafts

- Save drafts in the job folder's `outreach.md` under `## <Person> - <channel> - <date>`. Chat only means no file. `jobapps_check` lints an outreach file as a single message (stock openers, length, a missing ask), so its length finding is meaningful only when the file holds one draft.
- `jobapps_person` only when the user asks to track someone. Once tracked, log every touch the user reports sending (status `contacted`, then `follow_up` or `replied`) and set `next_touch`. A draft is not a touch.
- `jobapps_gmail_draft` only when the user asks for a Gmail draft. It cannot send, and neither can the agent. For LinkedIn and forms, give copy-ready plain text.
- Deliver the message as plain text in a fenced block with nothing else inside it.

## Check before delivery

- Could this message go to anyone else unchanged? Then the first line is not specific.
- Is the ask one thing, small, and obvious on a phone screen?
- Is every fact about the recipient verified, and every fact about the candidate in the evidence?
- Is it free of implied endorsement, implied referral, or a claim that the recipient owns the role when that is unconfirmed?
