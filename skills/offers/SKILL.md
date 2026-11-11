---
name: offers
description: "Use when an offer arrives or pay is discussed: evaluate, negotiate."
version: 1.0.0
license: MIT
metadata:
  hermes:
    tags: [career, offer, negotiation, compensation]
    related_skills: [jobapps:jobapps, jobapps:interview-prep, jobapps:outreach]
---

# Offers and negotiation

Use from the first salary question to the signed offer. The user decides everything here. Your job is to make the facts clear, prepare the words, and keep them from giving away position by accident.

## When pay comes up early

- Recruiter asks for expectations before an offer: the user does not need to name a number first. Prepare one honest line, such as "I'd like to understand the role and the full package first; what range is budgeted?" If a number is required, give a researched range whose bottom the user would accept.
- Application forms with a required salary field: use the range from `profile/profile.md` preferences if present; otherwise ask the user. Never invent one.
- Record what was said, by whom and when, in the job's Notes.

## When an offer arrives

1. `jobapps_track(job, status="offer", note=...)` and set the next action to the response deadline with its date.
2. Write `offer.md` in the job folder with every term exactly as given: base, bonus (target and guaranteed), equity (type, amount, strike or grant value, vesting, cliff, refresh policy), sign-on, benefits, start date, location and remote policy, level and title, deadline, contingencies. Mark anything not yet in writing as "verbal".
3. List what is missing or unclear and draft the questions that get it in writing. Do not evaluate an offer from a phone summary.

## Evaluate

- Compare against the user's stated floor and preferences in `profile/profile.md`, and against other live processes from `jobapps_overview(view="jobs", stage="interviewing")`.
- Research market pay for the level, company and location with sourced figures. Give ranges and say how confident each source is. No single magic number.
- Value equity soberly: private-company equity is uncertain, state the assumptions, and show the package with equity at zero as well.
- For candidates who need work authorization, confirm sponsorship, timing and who pays, in writing, before acceptance. This can outweigh pay.
- Name the non-money terms that matter to this user: team, manager, scope, growth, location, start date.
- Present a short, plain comparison. The user chooses.

## Negotiate

- Decide the ask first: the one or two terms that matter most, a specific number for each, and the reason. Reasons that work: market data, a competing offer that really exists, scope of the role, a concrete cost the user bears. Never invent a competing offer or bluff a deadline.
- Order: express real enthusiasm, state the ask and its reason once, then stop talking. Prefer a call for the conversation and email for confirmation.
- Draft the script and the follow-up email in the user's voice (`profile/voice.md`). Keep it short and warm. Include a fallback: what the user accepts if base cannot move (sign-on, equity, start date, review at six months).
- If another process is live, help the user tell that employer the timeline, honestly, to speed it up.
- Everything agreed goes in the written offer before the user accepts. Check the final document against `offer.md` line by line.

## Close out

- Accepted: `jobapps_track(status="offer", note="Accepted ...")`, then help withdraw from other processes with brief, gracious notes, and thank everyone who helped. Close the other jobs so the pipeline is true.
- Declined: a short, appreciative note that keeps the relationship; record why in Notes.
- Either way, write what the user learned about their market value and what worked into `profile/playbook.md` under Workflow.

Drafts only. The user sends every message and signs everything.
