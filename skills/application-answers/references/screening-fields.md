# Screening and logistics fields

Load when a form asks about work authorization, sponsorship, salary, years of experience, availability, location or referrals. These answers are factual statements the candidate is accountable for. Source every one from `profile/profile.md`, `settings.json` or the user in this conversation.

## Work authorization and sponsorship

Forms usually ask two separate questions. Keep them separate.

1. "Are you legally authorized to work in <country>?" This is about the present.
2. "Will you now or in the future require sponsorship?" This is about the future as well.

Procedure:

- Read Constraints in `profile/profile.md` and `rules.needs_sponsorship` in `settings.json`.
- `needs_sponsorship: false`: authorized, no sponsorship needed. `true`: answer the sponsorship question yes. `null`: unknown. Ask the user before answering either question.
- The two answers can differ: a person can be authorized today and still need sponsorship later. If the profile describes time-limited authorization, the future question is normally yes. Confirm the exact wording with the user the first time, then record their standard answers under Constraints so later forms are consistent.
- Give the yes or no the field asks for. Add explanation only in a free-text field that invites it, and then one sentence of fact: what authorization is held and until when, as the profile states it.
- Never choose "no sponsorship needed" because it seems more likely to pass a filter. A wrong answer here can end an offer.
- Do not give legal or immigration advice. If the user is unsure how their status maps to the question, say that the answer is theirs to confirm with a qualified adviser, and hold the field.
- If the posting's wording conflicts with the candidate's constraints, that is a blocker question for the operator flow, not something to smooth over in the form.

## Salary expectations

- Read Preferences in the profile for a floor or range. If none is recorded, ask. Do not invent a figure.
- If the posting states a range, answer inside it when the candidate's floor allows. If the floor is above the range, tell the user before filling anything.
- Free-text field: a range anchored on the candidate's number, with total compensation flexibility stated only if the user wants it. Example: "$115,000 to $130,000 base, flexible depending on the full package."
- Required numeric field: the single number the user chooses. Offer the midpoint of their range as a suggestion and let them decide.
- A field that is not required may be left blank if the user prefers. Say that this is a choice.
- Salary history: the user's decision whether to disclose. Never estimate or round it.
- Record the figure given in the job's Notes so later conversations with the employer stay consistent.

## Years of experience

1. Define the scope the question asks for: professional only, or including internships, research, freelance and founder work. If unclear, count what a reasonable recruiter would count and state the basis in a free-text field if one exists.
2. Take role dates from the evidence files' `start` and `end` fields.
3. Count the union of the qualifying intervals. Overlapping roles are not added together; gaps are not counted.
4. Use month precision when that is what the evidence has. Do not invent days.
5. Never round up across a threshold. Two years and ten months is "2", or "nearly 3" in free text. It is not "3+".
6. For tool-specific questions ("years of Python"), count from first real use in the evidence, and distinguish professional from academic use if the form does.
7. If a missing date changes the answer, ask.

## Start date, notice and availability

- Use the profile's stated start date or notice period. If absent, ask.
- For internships and new-graduate roles, check the graduation date and any cohort or start window in the form against the profile before anything else. A form can carry a restriction the posting did not. Raise a mismatch immediately; a yes or no question alone does not prove automatic rejection.
- State dates as the form expects them. Do not promise an earlier date than the user gave.

## Location, relocation and work mode

- Answer from Constraints and Preferences. "Willing to relocate" is yes only if the profile or the user says so.
- If the form asks for a current location, use the profile's `location` field.
- Travel percentages and on-site days: the user's stated limit, or ask.

## Referrals and "How did you hear about us?"

- Name a referrer only when the user confirms that person agreed to refer them for this role. A conversation is not a referral.
- Check `people/` for someone linked to this job. Use the name exactly as that file has it.
- "How did you hear about us?" gets the true source: the `source` field in `job.md`, the person, the board.
- Do not name an employee met through cold outreach as a referrer without their agreement.

## Previous applications and employment

- "Have you applied here before?" Search `jobs/*/job.md` for the company and check the Log. If the workspace is new or incomplete, ask.
- "Have you worked here or at an affiliate before?" From the evidence files, or ask.

## Links and uploads

- LinkedIn, GitHub and website come from the profile frontmatter, exactly.
- Provide a portfolio or project link only if it is live and matches the names used on the resume.
- The agent does not upload files. Give the user the path of the checked PDF.

## Fields the agent leaves to the user

- Demographic and self-identification questions.
- Disability and veteran status.
- Background-check consent, non-compete and other legal attestations.
- Signatures and "I certify" boxes.

List these for the user as theirs to complete. Do not suggest answers.

## Education fields

- Degree, institution, dates and GPA come from the Education section of the profile, displayed the way it specifies.
- An expected graduation date is marked expected. A completed degree is not.
- Do not convert or rescale a GPA unless the form asks and the user confirms the result.
