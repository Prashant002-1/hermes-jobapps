// Base resume. One page, one column, real text and ordinary headings, so both
// a person and an applicant tracking system can read it.
// Keep this file as the general version. For a job, copy it into the job
// folder as "<Name> - Resume - <Company> - <Role>.typ" and edit the copy.

#let name = "Jordan Example"
#let contact = (
  "jordan@example.com",
  "(555) 010-2030",
  "Austin, TX",
  link("https://www.linkedin.com/in/jordan-example")[linkedin.com/in/jordan-example],
  link("https://github.com/jordan-example")[github.com/jordan-example],
)

#set document(title: name + " - Resume", author: name)
#set page(paper: "us-letter", margin: (x: 0.6in, top: 0.5in, bottom: 0.5in))
#set text(
  font: ("Inter", "Helvetica Neue", "Arial", "Liberation Sans", "New Computer Modern"),
  size: 11pt,
  ligatures: false,
)
#set par(leading: 0.6em)
#set list(indent: 0.4em, body-indent: 0.5em, spacing: 0.62em, marker: [•])

#let section(title) = {
  v(0.75em)
  text(weight: "bold", tracking: 0.04em, upper(title))
  v(-0.62em)
  line(length: 100%, stroke: 0.6pt)
  v(-0.2em)
}

#let entry(title, organization, dates, place: none, body) = {
  grid(
    columns: (1fr, auto),
    [*#title*, #organization],
    align(right)[#if place != none [#place, ]#dates],
  )
  v(-0.2em)
  body
  v(0.4em)
}

#align(center)[
  #text(size: 19pt, weight: "bold", name) \
  #v(-0.2em)
  #contact.join("  |  ")
]

// A summary is not required. Keep it only when it tells the reader something
// the entries below cannot: who you are for this role, in two sentences.
Software engineer who builds and runs data-heavy backend services. Most recent work: taking a nightly
reporting system to incremental loads and owning it in production.

#section("Experience")

#entry("Software Engineer", "Northstar Labs", "Jun 2024 - Present", place: "Austin, TX")[
  - Rebuilt the nightly ingestion job as incremental loads, cutting a 6-hour run to 40 minutes so analysts start the day with current data.
  - Designed the retry and dead-letter path for partner webhooks after tracing lost orders to silent timeouts; no order has been dropped since the change shipped.
  - Own the service in production: wrote the runbook, set alert thresholds from three months of incident history, and carry the pager one week in four.
  - Replaced hand-edited pricing spreadsheets with a reviewed configuration service that the finance team now updates without an engineer.
]

#entry("Software Engineering Intern", "Fieldwork Analytics", "May 2023 - Aug 2023", place: "Remote")[
  - Shipped the export feature customers had requested most, working inside the team's review and release process; it reached all accounts in the August release.
  - Found and fixed a join that double-counted refunds, so the revenue dashboard matches the ledger again, and added the regression test that guards it.
]

#entry("Peer Tutor, Data Structures", "Lakeside University", "Sep 2022 - May 2023", place: "Lakeside, TX")[
  - Ran weekly sessions for 30 students and rewrote the recursion worksheet after seeing where they stalled; the instructor adopted it for the course.
]

#section("Projects")

#entry("Trailhead", "open-source route planner for volunteer trail crews", "2023")[
  - Built a planner that orders maintenance stops by daylight and crew size; two regional crews used it for their 2023 season schedules.
  - Wrote the offline map cache after crews reported losing signal on site, so a plan made in town still works on the trail.
]

#section("Education")

#entry("B.S. Computer Science", "Lakeside University", "2020 - 2024")[
  - Senior thesis on incremental view maintenance; departmental honors.
]

#section("Skills")

- *Languages:* Python, SQL, TypeScript, Go
- *Data and backend:* PostgreSQL, Kafka, Airflow, REST and gRPC services
- *Operations:* Docker, Terraform, AWS, CI/CD, monitoring and on-call
- *Practices:* code review, incident response, test design, technical writing
