# Story bank

Load when building or rehearsing interview stories. The example is invented.

## Why a bank and not a script

Interviewers ask the same few things in many wordings. Five or six well-understood stories, each usable for several themes, serve better than twenty memorized answers. A story the candidate understands can be shortened, extended or re-angled on the spot. A script breaks at the first follow-up.

## Selecting stories

Source: the evidence files, especially Facts and Approved wording. Never build a story from a fact the evidence does not hold; ask the user to confirm and record it first.

Choose stories so that together they cover:

| Theme | The interviewer is checking |
|---|---|
| Technical depth | Can they go three levels down on something they claim? |
| Diagnosis | How do they find a cause when it is not obvious? |
| Ownership | Do they finish, including the dull parts? |
| Judgment and trade-off | Did they choose, and can they say what they gave up? |
| Disagreement or conflict | Can they disagree usefully and stay in the relationship? |
| Failure | Do they see their own part, and did behavior change? |
| Working with non-specialists | Can they translate both ways? |
| Ambiguity | What do they do when nobody defines the task? |
| Learning something new fast | Evidence, not the claim |

One story usually covers two or three themes. Mark them. Check the map for holes; a missing failure story is the most common hole and the most damaging.

Prefer stories that are recent, where the candidate made a real decision, and that they enjoy telling. Avoid stories where they only carried out instructions.

## The five beats

Write each story as beats, not prose. The candidate speaks from beats.

1. **Situation**: who needed what, in one or two sentences. Only the context the listener needs.
2. **Decision**: what the candidate chose, what the alternatives were, and why. This is the beat that scores.
3. **Mechanism**: what they did, in plain words, at the depth the interviewer can follow.
4. **Consequence**: what changed, at its real level, with the number if the evidence has one.
5. **What I would change**: one honest thing. Not a disguised boast.

Timing when spoken: situation 20 seconds, decision 30, mechanism 40, consequence 15, change 15. About two minutes. If the situation runs past 30 seconds the story is losing the listener.

Use "I" for what the candidate did and "we" for what the team did. Interviewers listen for the difference.

## Template for the pack

```
### <Short name>
Source: evidence/<slug>.md
Themes: <two or three>
Situation:
Decision:
Mechanism:
Consequence:
Would change:
Depth ready: <the two follow-ups most likely, with the answer in a line each>
Numbers to know: <each figure in the story and where it comes from>
30-second version: <two sentences>
```

## Example

```
### The duplicate invoices
Source: evidence/fieldwork-billing.md
Themes: diagnosis, ownership, working with non-specialists
Situation: Finance at Fieldwork found duplicate invoices about once a week and cleaned them up by hand.
Decision: The proposed fix was to block double clicks. I did not accept that, because the duplicates were minutes apart. I chose to trace one end to end before changing anything.
Mechanism: Found that when the billing provider was slow, our worker retried the whole write. Added a key so a repeated write is harmless, and a nightly job comparing our records with the provider's.
Consequence: Duplicates stopped. The weekly cleanup ended. The comparison job later caught two unrelated mismatches.
Would change: I would have asked finance for timestamps on day one. I spent two days on the wrong theory before I looked at them.
Depth ready: "Why not make the provider call idempotent instead?" It was, the problem was our write around it. "How did you test the retry?" Injected delay in staging and replayed a week of traffic.
Numbers to know: about weekly (finance's log); two other mismatches (job output).
30-second version: Finance kept finding duplicate invoices. I traced them to a retry in our own worker, made the write safe to repeat, and added a nightly comparison that has since caught other problems.
```

## Re-angling one story

The same story answers different questions by changing which beat leads:

- "Tell me about a hard bug": lead with the decision to trace before fixing.
- "Tell me about working with another team": lead with finance's cleanup and how the timestamps came from them.
- "Tell me about a mistake": lead with the two days on the wrong theory.

Do not change the facts between angles. Interviewers on a panel compare notes.

## The introduction

Sixty to ninety seconds, three moves:

1. Who the candidate is now, in one sentence, in the identity the submitted resume used.
2. Two pieces of evidence chosen for this role, one sentence each.
3. Why this role, in one true sentence. Then stop.

It is not a chronological walk through the resume. Rehearse it aloud; it is the one answer worth knowing nearly by heart.

## Failure and weakness answers

- Choose a real failure with a real cost, where the candidate's own decision contributed.
- Spend one third on what happened and two thirds on what changed afterwards, with one later example of the changed behavior.
- A weakness answer names something true and current, how it shows up, and what the candidate does about it. "I work too hard" and "I am a perfectionist" fail.

## Rehearsal

- Say each story aloud once, timed. Reading silently does not count.
- After each, ask the two most likely follow-ups and answer them aloud.
- Shorten what ran long by cutting situation, never the decision.
- When the agent plays interviewer: one question at a time, wait for the answer, then give two pieces of feedback at most, one to keep and one to change. Do not rewrite the candidate's answer into the agent's phrasing; adjust their own words.
- Stop when the stories are fluent. Over-rehearsed answers sound recited.

## Keeping the bank

Stories that worked, with their final beats, belong in the evidence file's Approved wording or Facts so the next interview starts from them. A story the user retires gets removed there, not left to resurface.
