// Base cover letter. One page. Copy into the job folder as
// "<Name> - Cover Letter - <Company> - <Role>.typ" and edit the copy.

#let name = "Jordan Example"
#let contact = ("jordan@example.com", "(555) 010-2030", "Austin, TX")
#let company = "Northstar Labs"
#let role = "Backend Engineer"

#set document(title: name + " - Cover Letter - " + company, author: name)
#set page(paper: "us-letter", margin: (x: 1in, y: 0.9in))
#set text(
  font: ("Inter", "Helvetica Neue", "Arial", "Liberation Sans", "New Computer Modern"),
  size: 11pt,
  ligatures: false,
)
#set par(leading: 0.7em, spacing: 1.15em)

#text(size: 16pt, weight: "bold", name) \
#contact.join("  |  ")

#v(1.2em)
#datetime.today().display("[month repr:long] [day], [year]")

#v(0.6em)
Hiring team, #company \
Re: #role

#v(0.4em)
Dear #company team,

Open with the reason this role and you belong together, in one or two plain sentences. Name the
problem the team is hiring to solve and the experience that makes you the person for it.

Tell one story the resume cannot: the situation, the decision you made, how it worked, and what
changed because of it. Keep the detail that shows judgment and drop the rest.

Say one specific, true thing about the company that connects to that story: a product decision, a
published problem, a direction you want to work on. No flattery and nothing copied from the posting.

Close briefly: what you would like to do next, and thanks.

#v(0.6em)
Sincerely, \
#name
