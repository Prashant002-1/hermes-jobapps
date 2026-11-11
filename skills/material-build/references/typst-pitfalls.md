# Typst pitfalls

Load on a Typst build error, or when the PDF text differs from what the source appears to say. Typst markup gives meaning to characters that are ordinary in a resume. Some fail loudly. The dangerous ones compile and silently change the text.

## Characters that break or change text

| You write | What happens | Write instead |
|---|---|---|
| `C#, Java` | Error: `#` starts code | `C\#` |
| `Ranked #1 of 40` | Compiles, prints "Ranked 1 of 40" | `\#1` |
| `#urgent` | Error: unknown variable | `\#urgent` |
| `jordan@example.com` | Error: label `<example.com>` does not exist | `jordan\@example.com`, or a `link` (below) |
| `@2x load` | Error: label does not exist | `\@2x` |
| `$120k` | Error: unclosed delimiter (math mode) | `\$120k` |
| `from $5 to $10` | Error, or the text between becomes math | `\$5 to \$10` |
| `4.5* rating`, `a *bold claim` | Error: unclosed delimiter | `4.5\*` |
| `_private` or a lone `_` at a word edge | Error: unclosed delimiter | `\_private` |
| `~40 users` | Compiles, prints " 40 users": `~` is a non-breaking space | `\~40`, or "about 40" |
| `<200ms>` | Compiles, the text vanishes: it became a label | `\<200ms>` |
| `a<b` | Error: unclosed label | `a \< b` |
| `CI//CD` or any `//` | Compiles, everything after `//` on the line is dropped as a comment | `CI\/\/CD` |
| `2022 -- 2024` | Compiles as an en dash; `---` becomes an em dash | A single hyphen, or the dash the source already uses |
| `and more...` | Becomes an ellipsis character | Fine, but know it happens |
| `"quoted"` and `it's` | Become curly quotes | Fine; `#set smartquote(enabled: false)` if the source needs straight quotes |
| `Line one \\ line two` | Prints a literal backslash, no break | `\` followed by a newline, or `#linebreak()` |
| A line starting with `- `, `+ `, `= `, `/ ` or `1. ` | Becomes a list item, heading or term | Escape the first character, or reword |

No escape is needed for: `%`, `&`, a `_` or `*` inside a word (`snake_case`, `2*3`), a `<` followed by a space, and a full `https://` URL, which becomes a link by itself.

After any build, compare the extracted PDF text with the source for lines that contain `#`, `@`, `$`, `~`, `<`, `/` or `*`. The silent cases above produce no error and no warning.

## Markup, code and strings

Typst has three contexts with different rules.

- **Markup** (the body of the file, and anything inside `[ ... ]`): the special characters above apply.
- **Code** (after `#`, and inside function parentheses): values are expressions. Text must be a string `"..."` or content `[...]`.
- **Strings** (`"..."`): no markup. `"C# & *stars* $5 #1"` prints exactly that. Escape only `"` and `\` (as `\"` and `\\`).

Consequences:

- Passing a string where the template expects content is usually fine, but markup inside the string will not render: `"*bold*"` prints the asterisks.
- Passing content where the template calls a string method fails with a message such as "element text has no method `len`". Read the template's function to see which it expects, and match the existing calls in the source.
- Inside a content argument, escape as in markup: `title: [C\# Developer]`. Inside a string argument, do not: `title: "C# Developer"`.
- A stray unbalanced `[`, `]`, `(` or `)` in an argument produces an error far from its cause. Check the entry edited last.

## Variables next to text

- `#company-wide` reads as one identifier (hyphens are legal in names): unknown variable. Write `#(company)-wide`.
- `#company.` followed by a word tries field access. Write `#company;.` or `#(company).`
- `#role(s)` and `#role[s]` try to call `role` as a function. Write `#(role)\(s)` or reword.
- `#company's` is fine.

## Links

- Show short readable text and keep the full address behind it: `#link("https://northstar.example/jobs/4821")[northstar.example/jobs]`.
- Email: `#link("mailto:jordan@example.com")[jordan\@example.com]`. The address inside the string needs no escape; the visible text does.
- A bare `https://` URL in markup links itself but shows the whole address. Use `link` when the address is long.
- Check that every link in the PDF goes where the text says.

## Line breaks and spacing

- A single newline in markup is a space. A blank line starts a new paragraph.
- Force a break with `\` at the end of a line, or `#linebreak()`.
- Keep words together with `~`: `Fieldwork~Labs`. Use it only after the wording is final.
- Vertical space is `#v(6pt)`. Prefer the template's own spacing settings to scattered local `v()` calls. Negative `v()` and negative grid gutters compile cleanly and can overlap text.
- When a gap will not move, it is probably controlled elsewhere: a section helper's trailing space, a `set par(spacing: ...)`, a `set list(spacing: ...)`, or a default in an imported template. Read the surrounding helpers before editing the same line again.

## Fonts

- An unknown font is a warning, not an error: `unknown font family`. Typst falls back silently and the layout shifts. Read the warnings on every build.
- Use the font the approved source names. If it is not installed on this machine, tell the user. Do not substitute one quietly.

## Pages and exports

- Read the page count after every build. A resume that spills to a second page is a content or spacing problem, not a compiler problem.
- Exporting a multi-page document to a single fixed image name fails by design. Use a page placeholder in the output name (`resume-{p}.png`) while diagnosing, and a fixed name only once the PDF is one page.
- A PDF that builds is not a finished document. It still needs the layout and text checks.

## Template telemetry

Some resume templates wrap sections and bullets in a helper that reports each region's measured position, which lets the check attribute a layout violation to a named region and source line. If the source has such wrappers:

- Keep their identifiers stable when editing, so a violation can be followed across rounds.
- Do not strip them to simplify the source.
- Do not rewrite a stable hand-written source only to add them. The check falls back to matching rendered text against source lines.

## Reading a Typst error

- The message gives file, line and column. The real cause is usually on that line or in the entry just before it.
- `unclosed delimiter`: an unescaped `*`, `_` or `$`, or an unbalanced bracket.
- `unknown variable`: an unescaped `#`, or a variable touching text.
- `label ... does not exist`: an unescaped `@`.
- `expected function, found string`: a variable followed directly by `(` or `[`.
- `expected comma`: a missing comma between arguments.
- `has no method`: content passed where a string was expected, or the reverse.
- Fix the first error and build again. Later errors are often consequences.
