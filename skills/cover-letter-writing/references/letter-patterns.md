# Letter patterns

Load for a first draft, or when a draft reads as generic. All names and details are invented. Copy the moves, never the sentences.

## Three structures

Pick by what is strongest. The reader should not see the structure.

**A. Problem-led.** Use when the candidate has worked on the employer's kind of problem.

1. The operating problem, stated the way a practitioner would, and why the candidate cares about it.
2. The story: when they met this problem, what they decided, what changed.
3. What that means for this team's version of it.
4. Direction and close.

**B. Story-led.** Use when one story carries the whole argument.

1. Open inside the story, at the moment of the decision.
2. What they did and what it showed them about how they work.
3. The bridge: why that way of working belongs with this employer's work.
4. One supporting anchor, direction, close.

**C. Direction-led.** Use for a change of lane or an early-career move.

1. The honest pull toward this work, in one or two plain sentences.
2. The evidence that the pull is already acted on: the story.
3. What the previous lane adds that peers may lack.
4. What they want to learn here and what they can do on day one.

## Opening lines

The first sentence should be one that only this candidate could send to this employer.

| Weak | Why | Stronger |
|---|---|---|
| "I am excited to apply for the Backend Engineer role at Northstar." | The reader knows. It spends the best line. | "Northstar reconciles payments across ledgers that were never designed to agree. I spent last year on a smaller version of that problem." |
| "With three years of experience in data analysis, I am confident I am a strong fit." | A claim with no evidence, true of thousands. | "The most useful report I ever built was one that let a staffing lead stop waiting for me." |
| "I have always been passionate about healthcare technology." | Unverifiable, and usually untrue. | "I started paying attention to clinic scheduling when a pilot user told me she kept a paper backup of our calendar." |
| "Your job posting lists Python, SQL and cloud experience, all of which I have." | The posting read back. | Open on the work those tools were for. |

Do not open with a quotation, a rhetorical question, a dictionary definition or the candidate's name.

## Telling the story

One story, five beats, six to nine sentences:

1. Situation in one sentence: who needed what.
2. The complication: what made it hard or unclear.
3. The decision: what the candidate chose and why. This is the sentence that shows judgment.
4. The mechanism: what they built or did, in plain words.
5. The consequence: what changed, at its real level.

Then one sentence on what the story shows about how they work. Not "this taught me the value of teamwork". Something specific: "I look for the place where a system's promise and its behavior disagree, and start there."

Common faults:

- The story is a compressed resume bullet. Add the decision and the reason.
- Two stories at half depth. Cut one.
- The tools are the subject. Make the candidate's choice the subject.
- The consequence is inflated or missing. Use the evidence file's wording.

## The company-specific paragraph

Its job is to show the candidate understands the work, not that they admire the company.

Method:

1. Find one concrete fact from a first-party source: an engineering post, a product decision, documentation, a talk, the specifics of the posting's responsibilities.
2. Say what that fact implies about the work: a constraint, a trade-off, a hard part.
3. Connect it to how the candidate would approach it, using the behavior the story proved.

Weak:

> I admire Northstar's commitment to innovation and its mission to transform payments.

Stronger:

> Your engineering notes describe moving reconciliation from nightly batches to continuous matching. That shifts the hard part from throughput to deciding when a mismatch is real. Most of my work on the invoice path was that same judgment: telling a late record from a wrong one before anyone acts on it.

Rules:

- Cite only what a source actually says. Record the source in the job's Research section.
- No inference presented as fact about their internals.
- Do not explain the company to itself at length. Two or three sentences.
- If nothing specific can be found, write the paragraph about the role's stated responsibilities and the problem they imply. Do not fill the space with praise.

## Closing

The close states direction and stops.

- Say what the candidate wants to work on there, or what they would start with.
- No "I would welcome the chance to discuss", no "Thank you for your time and consideration" as the only content, no restated opening, no claim about being a fit.
- Sign-off follows the approved source or the voice file. Default: "Sincerely," and the name.

Example:

> I would like to work on the matching rules themselves, and I expect to learn a great deal from a team that has run them at your volume.

## Worked example

Thesis sentence written first: Northstar's reconciliation work depends on judging which mismatches are real, and this candidate's strongest work shows exactly that judgment on a smaller ledger.

> Northstar reconciles payments across ledgers that were never designed to agree. I spent last year on a smaller version of that problem, and it is the work I want to keep doing.
>
> At Fieldwork, finance kept finding duplicate invoices about once a week. The first explanation was a double click, and the first proposal was to block the button. I did not think that was it, because the duplicates arrived minutes apart. I traced them to a retry: when the billing provider was slow, our worker ran the whole write again. I added a key that made the write safe to repeat and a nightly job that compared our records with the provider's and flagged what did not match. The duplicates stopped, and the weekly cleanup ended with them. What stayed with me was the comparison job. It found two other mismatches nobody had been looking for.
>
> Your engineering notes describe moving from nightly batches to continuous matching. That shifts the hard part from throughput to deciding when a mismatch is real, and that is the judgment I enjoy: telling a late record from a wrong one before someone acts on it. I have also carried a pager for what I built, so I know the cost of getting that call wrong at night.
>
> I would like to work on the matching rules themselves, and I expect to learn a great deal from a team running them at your volume.
>
> Sincerely,
> Jordan Example

Why it works: the thesis is specific to this employer; one story with a visible decision; the company paragraph draws an implication from a source; one supporting anchor (operates what they build) in a single sentence; the close adds direction. About 270 words.

## If the letter still reads as generic

- Replace every adjective about the candidate with the fact that earned it.
- Find the sentence that could appear in any letter and delete it. Repeat.
- Check the story has a decision. If the candidate only followed instructions in it, choose another story.
- Ask the user the motivation question. A true small reason beats an impressive invented one.
