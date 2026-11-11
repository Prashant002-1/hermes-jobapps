# Layout repair

Load when `jobapps_check` reports layout violations on a resume, or when a page is over or under filled. The check measures the rendered PDF. Treat its numbers as the truth about the page, and repair from `layout.repair_plan`.

## Principles

1. Finish the writing first. Layout work on unfinished text is wasted.
2. One cause, one edit. A defect repeated across the page lives in a shared style; fix it there once. A defect on one line is fixed on that line.
3. Preserve meaning. A rewrite to reclaim a line keeps every claim, number and name.
4. Never buy space with smaller type, tighter leading than the source, narrower margins or negative spacing.
5. Know the direction. An over-full page and an under-full page need opposite repairs. Read `bottom_whitespace_in` and the violation's `direction` before touching anything.
6. Measure again after every edit. Compare the new report with the last one.

## Repair plan actions

| Action | Meaning | Do |
|---|---|---|
| `refit_document` | Wrong page count, or the page is over or under filled | Use the tactics under "Too long" or "Too short" below |
| `correct_page_setup` | Paper size, margins or body font differ from what is required | Fix the page or text setting before any content change. Do not shrink the font to get under a limit |
| `rewrite_short_final_lines` | Listed bullets or paragraphs end with one or two words on their own line | See "Short last lines" |
| `adjust_shared_list_style` | Bullet spacing is inconsistent or bullets touch | Change the shared list setting once (`list.spacing`, `par.leading`). Do not patch bullets individually |
| `adjust_shared_row_style` | Rows or lines sit too close | Raise the shared row leading or spacing once |
| `normalize_wrapped_line_leading` | A wrapped line sits at a different distance from its neighbors | Restore normal paragraph leading and remove the one local spacer responsible |
| `separate_spacing_hierarchy` | The gap inside an entry is nearly as large as the gap between sections | Make the two gaps clearly different through the template's spacing settings, not another local `v()` |

## Violation types

| Type | What was measured | Usual cause |
|---|---|---|
| `page_count` | More or fewer pages than required | Too much content, or a stray page break |
| `bottom_whitespace_out_of_range` | The distance from the lowest content to the page edge is outside the accepted range | Too much or too little content. Configured margins are not the measure; rendered content is |
| `short_final_line` | The last line of a bullet, paragraph or row holds very few words | Wording a few characters too long for the line |
| `text_line_collision`, `bullet_item_overlap`, `cross_block_text_collision` | Lines or blocks overlap | Negative spacing, leading set too tight, a spacer pulling a block upward |
| `near_collision` | Lines are closer than the minimum gap | The same, milder |
| `inconsistent_intra_item_leading` | Lines within one item are unevenly spaced | A local override, an inline element taller than the line |
| `inconsistent_inter_item_gap` | Gaps between like items differ | Per-item spacers instead of one shared setting |
| `weak_spacing_hierarchy` | Internal gaps rival section gaps | Spacing values too similar |
| `text_out_of_bounds` | Text runs past the page or margin | A long unbreakable string, a row too wide |
| `body_font_below_minimum`, `body_font_mismatch` | Body type is smaller than allowed, or not the required font | A size was reduced to fit, or the font is missing and a fallback was used |
| `page_size` | The page is not the required paper size | Wrong paper setting |
| `missing_exported_text` | The PDF has no text layer | Text was rendered as shapes or images. ATS cannot read it |
| `verification_unavailable`, `source_unavailable` | The measurement could not run | A missing tool or file. Report it; do not treat it as a pass |

## Too long

Work down this list and stop as soon as the page fits.

1. Reclaim lines from short last lines. Each bullet tightened by a few words returns a full line.
2. Cut the weakest bullet on the page: the one that fails the bullet gate, or duplicates another's proof.
3. Tighten wordy bullets: remove the manufactured ending, the restated context, the second mechanism.
4. Trim Skills to one line per category by dropping the least relevant items.
5. Shorten the summary if it has one, or cut a sentence that restates the page.
6. Remove the least relevant project or the oldest, weakest entry. Tell the user what went.
7. Only then consider a shared spacing value, and only within what the approved source allows.

Do not delete a substantive role to make room for decoration, and do not make bullets cryptic.

## Too short

An under-filled page usually means strong evidence was left out.

1. Check the evidence files and the candidate's earlier resumes for relevant material that was dropped. Restore it.
2. Complete bullets that stop before their consequence, or that lack the mechanism. One or two rendered lines of real substance.
3. Add a relevant project with a concrete descriptor.
4. Expand a compressed role back into separate bullets where each has its own mechanism and consequence.
5. If the page is only a few points outside the range, adjust section spacing slightly through the shared setting.

Never pad with filler, generic skills, or large gaps. If there is not enough true material, say so and leave the white space.

## Short last lines

The report lists each one with its text and source line.

- **Page over-full or within range**: shorten the bullet by a few words so the last line disappears. Cut filler first: "in order to", "successfully", "various", a repeated noun.
- **Page under-full**: do the reverse. Complete the line with supported substance (the mechanism, the product's purpose, the consequence) so the last line carries real content. Shortening would make the under-fill worse.
- Reordering a clause can move the break without changing length.
- After the edit, build and look at the same bullet again. A new break can leave a different word alone.
- Fix only the listed lines. Do not tighten the whole document to solve a local wrap.
- For a wrapped Skills or header row, drop or reorder items so the row fits one line.

## Spacing that will not move

When changing a value has no visible effect, the gap is controlled somewhere else. Find every source before editing again:

1. The section helper's trailing space.
2. The entry helper's internal space after its heading or grid.
3. Paragraph and list settings (`par.leading`, `par.spacing`, `list.spacing`).
4. Local `v()` calls.
5. Defaults inside an imported template.

Then change the one that owns the gap. Keep the last working version as a baseline: if an experiment causes overlap, revert to it before trying something else. Do not rebuild a stable block as a new grid or macro to move a few points.

When two neighboring gaps both look wrong (for example above and below a summary), adjust them as a pair and check for collisions on both sides.

## Letters

Letters are not measured against the resume's numeric thresholds. Judge them against their approved template.

- "Too dense" is a spacing problem. Keep the text. Adjust paragraph spacing and leading within the template, then check the header, address block, greeting and closing, since paragraph spacing moves all of them.
- If only the closing spills onto a second page, first remove repeated motivation or repeated explanation from the body (with the writing skill's rules), then tighten the gap before the signature. Do not shrink the font.
- A large empty block at the bottom of a full letter is a layout defect: rebalance spacing. Do not add words to fill it.
- Check for a wall of text: paragraphs must be visibly separate even when the page count passes.
- Remove a one-word last line by editing that sentence, then build and look again.

## When to stop

Stop after three rounds, or sooner when a round removes nothing or introduces a new violation it cannot remove. Report the remaining violations with their measurements and the latest PDF path. A page that looks acceptable in a screenshot but fails measurement is still failing.
