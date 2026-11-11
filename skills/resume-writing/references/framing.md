# Re-angling the same work for a different lane

Load when the candidate's history reads as one lane and the target is another, or when one piece of work must serve several different applications. The example is invented.

## The rule

A resume is a selection, and selection is honest. Fabrication is not.

| May change | May not change |
|---|---|
| Which true slice of the work is shown | What was done and who did it |
| The order of bullets and roles within a section | Numbers, dates, employers, statuses |
| Which consequence leads | The scale and maturity of the thing |
| Vocabulary, at the level the reader uses | The cause of a result |
| The title, among truthful alternatives | The employment relationship |

Test for every re-angled bullet: would the candidate's manager or teammate at the time read it and agree without hesitation?

## Method

1. List every fact the evidence file holds for the work: users, problem, decisions, parts built, tests, operation, results.
2. Mark the facts the target lane cares about, using `role-families.md`.
3. Choose the lead from the marked facts. The lead is the hardest thing done that this reader values.
4. Write the bullets from marked facts only. Unmarked facts drop to a clause or disappear.
5. Carry the same consequence if it is still the true consequence of the slice shown. If it belongs to a different slice, find the consequence that belongs to this one.
6. Check what the page now implies. If the selection suggests a scope the candidate did not have, add the limiting fact (team size, pilot stage, internal use).

## Worked example

Evidence, all from one file: at Northstar Logistics the candidate built an internal tool that lets depot supervisors reassign delivery stops when a driver calls out. Before it, dispatch handled call-outs by phone and spreadsheet. Facts recorded: a board where supervisors drag stops between drivers; a rule check on vehicle capacity and driver hours; a nightly import from the order system that sets aside malformed stops; three rounds of feedback with six supervisors at two depots; tests replaying 60 past call-out days; reassignment time went from about 40 minutes to under 10 according to the supervisors' own logs.

**Backend lane**

> Built the reassignment service behind the depot call-out tool: a rule check on vehicle capacity and driver hours rejects invalid swaps before they reach dispatch, and a nightly order import sets aside malformed stops instead of failing the run.
>
> Verified the rules by replaying 60 past call-out days; supervisors at two depots now reassign a call-out in under 10 minutes, down from about 40.

**Frontend lane**

> Designed and built the board supervisors use during a call-out: drag a stop to another driver, see capacity and hours conflicts before saving, undo a mistake. Shaped over three feedback rounds with six supervisors.
>
> Replaced phone-and-spreadsheet dispatch at two depots; a reassignment that took about 40 minutes now takes under 10.

**Data lane**

> Built the nightly import that feeds call-out reassignment from the order system, with validation that sets aside malformed stops for review rather than passing them to supervisors.
>
> Replayed 60 past call-out days to test the reassignment rules and measure the change: about 40 minutes per call-out before, under 10 after.

**Support and operations lane**

> Worked with six depot supervisors to replace phone-and-spreadsheet call-out handling: mapped how reassignments were really decided, then built and refined the tool over three feedback rounds until both depots ran on it.
>
> Cut the time to cover a driver call-out from about 40 minutes to under 10, by the supervisors' own logs.

What changed across the four: the slice, the lead, the vocabulary. What stayed fixed: six supervisors, two depots, 60 replayed days, 40 minutes to under 10, an internal tool.

What would be dishonest here:

- Calling it a "logistics platform" or a "real-time routing engine".
- Implying a company-wide rollout.
- Attaching the time saving to the import alone in the data lane, as if the import caused it.
- Presenting the work as team leadership when it was built alone, or as solo work if others built parts.

## When the lanes are far apart

For a move such as product engineering to research computing, or engineering to customer-facing work:

- Lead with the evidence that already is the target work, however small, at full strength.
- Use the home-lane evidence as support for a different concern: reliability, delivery, diagnosis, communication.
- Do not open with a deficit, and do not impersonate the domain. Frame the contribution at the real interface between what the candidate does and what the team does.
- State the new layer once, in the cover letter or an interview, not on the resume.

## When one employer has several openings

Separate requisitions get separate selections when the user asks for them. Do not swap the title on a shared document. Leave a finished package unchanged when adding a second role.
