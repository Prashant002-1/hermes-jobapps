# TeX letters

Load when a cover letter's approved source is `.tex`. Keep that source's class, packages, fonts and spacing. This note covers building it and the mistakes that most often break or disfigure a letter.

## Engine

- `jobapps_check(path)` builds `.tex` files with the configured compiler and leaves the PDF beside the source.
- A source that loads `fontspec` needs a Unicode engine (Tectonic, XeLaTeX or LuaLaTeX). With pdfLaTeX it fails outright. If the error mentions `fontspec` and the engine, the wrong compiler ran: report it instead of rewriting the preamble.
- System fonts are named exactly as installed: `\setmainfont{Font Name}`. A missing font is an error in TeX, unlike Typst. Tell the user which font the source asks for. Do not substitute one.
- With a Unicode engine, type accented letters and typographic quotes directly. Do not add `inputenc` or `fontenc` to a `fontspec` document.

## Characters to escape

| Character | Write |
|---|---|
| `&` | `\&` |
| `%` | `\%` (unescaped, it comments out the rest of the line, silently) |
| `$` | `\$` |
| `#` | `\#` |
| `_` | `\_` |
| `{` `}` | `\{` `\}` |
| `~` | `\textasciitilde{}` (a bare `~` is a non-breaking space) |
| `^` | `\textasciicircum{}` |
| `\` | `\textbackslash{}` |

Other habits:

- Quotes: two backticks to open and two apostrophes to close, or typographic quotes typed directly under a Unicode engine. A straight `"` can print the wrong glyph.
- `--` is an en dash and `---` an em dash. Use what the approved source uses for ranges.
- A blank line ends a paragraph. `\\` forces a line break and belongs in address blocks and the signature, not between paragraphs.
- An unescaped `%` in "grew 40% in a year" deletes the rest of that source line from the PDF with no error. After every build, search the extracted text for each sentence that contains a percentage.

## Hyphenation and overfull lines

Letters look wrong with hyphenated words at line ends.

- Turn hyphenation off the way the source already does. Common forms: `\usepackage[none]{hyphenat}`, or `\hyphenpenalty=10000 \exhyphenpenalty=10000`.
- With hyphenation off, a long word or URL can run past the margin. The log reports `Overfull \hbox`. Fix by rewording the sentence, or by allowing a little stretch (`\emergencystretch=1em`). Do not ignore it: the text is outside the margin.
- Keep a name or a number with its unit together with `~`: `Northstar~Labs`, `40~minutes`.
- Break a long visible URL by showing short text instead: `\href{https://northstar.example/jobs/4821}{northstar.example/jobs}`.

## Layout

- One page. Read the page count after every build.
- The usual controls, in the order to try them: paragraph spacing (`\parskip`), line spacing (`\linespread`), the gaps around the header, address block and signature, then margins (`geometry`). Change one, build, look.
- If only the signature spills to page two, trim repeated sentences in the body first, then tighten the gap before the closing. Never reduce the font size to pull it back.
- If the letter feels dense, widen paragraph spacing before touching the text. Slightly wider side margins can make a full page read less like a block.
- A large empty area at the bottom of a full letter means the spacing is too tight overall. Rebalance; do not add words.
- Use `\pagestyle{empty}` so no page number appears on a one-page letter.
- Keep the header and contact line identical to the resume's: same name, same order, same links.
- An employer and role block above the greeting, with a clear gap before "Dear ...", reads as a letter. Leave the date out when it would go stale, unless the source or the user wants it.
- Avoid decorative rules if they crowd the page.

## Build hygiene

- Auxiliary files (`.aux`, `.log`, `.out`) do not belong in the job folder. The check builds in a temporary location and keeps only the PDF. If you build by hand, use an output directory outside the job folder and copy back only the PDF.
- Read the log for `Overfull`, `Underfull` in the body text, `Missing character` (a glyph the font lacks) and `undefined`. A PDF can be produced with any of these present.
- `Missing character` means a symbol silently vanished from the PDF. Replace the symbol, or use a font that has it.

## Verify

1. One page.
2. Extracted text contains the company name, the role, every sentence with a `%`, `&`, `#` or `$`, and the signature.
3. No broken words from hyphenation, no text beyond the right margin.
4. No template placeholders ("Company Name", "Hiring Manager" when a name was intended), no comments, no notes to self.
5. One look at the rendered page: separate paragraphs, balanced margins, signature placed, nothing touching.

## Longer academic documents

An academic CV for a research audience may stay in TeX and run two or three pages; the one-page rule is for resumes. It still gets the same build, text and visual checks, and every publication is stated at its exact status: submitted, under review, accepted, presented or published.
