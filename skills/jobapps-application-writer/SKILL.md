---
name: jobapps-application-writer
description: Use when drafting or tailoring Prashant's resume notes, cover letters, and application answers.
version: 1.0.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [job-search, resume, cover-letter, writing]
    related_skills: [jobapps-role-evaluator, prashant-voice]
---

# JobApps Application Writer

## Purpose

Generate application materials that sound like Prashant and stay grounded in truth. The goal is not generic polish. The goal is shipped applications with the right angle for the role.

## Required Context

Read JobApps database context first. It should contain:

- profile facts
- experience narratives
- project/research narratives
- proof points
- previous application choices, tailoring requirements, portrayal decisions, learning patterns, and material-change records
- skills rotation rules
- resume rules and active Typst templates
- cover letter rules
- outreach rules
- voice and banned phrases

Use JobApps database facts, proof points, learning patterns, and app-owned materials as runtime context. Do not browse or reuse old Downloads resumes, cover letters, CVs, `knowledge_base.html`, LinkedIn exports, website copy, or generated variants as live material sources.

If writing in Prashant's voice outside this project, also load the `prashant-voice` skill.

## Resume Tailoring Rules

- One page enforced.
- Do not modify formatting rules just to fit more content.
- Tailor by choosing the right slice of real work, not inventing work.
- Start from `tailoring_requirements`; each meaningful change should answer a JD need.
- Apply `learning_patterns` before choosing phrasing or emphasis.
- Record the framing choice as a `portrayal_decision` when it changes how Prashant is presented.
- Use role-family ordering from database/config.
- Use numbers only when they are load-bearing.
- Project header tags should be few and high-signal.
- Drop padding tools and broad skill inventories.
- Save final resume builds as standard `kind="resume"` Typst (`.typ`) or PDF materials using the JobApps workflow. Use `kind="resume_tailoring"` only for notes/change plans; do not invent final-resume kinds.
- Save materials through JobApps tools so the app owns provenance, job-specific folders, and professional filenames. Do not hand-invent submission filenames.
- Rotate sections by role. Data Engineer and Software Engineer are the primary defaults. Backend, SWE, data/ML-adjacent, research assistant, IT/help desk, internship, and contract versions are acceptable when they help Prashant survive and move forward.
- Prefer current proof signals: Center for Food Action data engineering/validation/PostgreSQL work, Trimble C#/.NET/API/auth/SQL work, Novartis React/TypeScript/Azure/dashboard/data-model work, Personal Canvas Agent, ARAG/Trellis-RAG, and relevant Ramapo data analysis. Confirm details before making them stronger than the source supports.
- For the post-grad base resume, remove stale "Expected" graduation wording. Use "May 2026" for the completed Ramapo degree unless Prashant gives different official wording. Use GPA 3.8/4.0, rounded from Prashant's current post-grad GPA of 3.75, unless he explicitly asks for the exact GPA. Do not reuse older 3.84/4.00 values from stale resumes, CVs, or `knowledge_base.html`.
- Treat new impact claims from the CV/knowledge base, such as funding, media, number of pantries, user counts, or exact performance effects, as candidate proof until confirmed or supported by a reliable source.

## Cover Letter Rules

- Flowing paragraphs only.
- No bullets.
- No headers beyond the required letter header structure if generating the full document.
- 350–400 words unless the prompt asks otherwise.
- No em dashes.
- Open with a real idea about the problem space, not generic enthusiasm.
- Anchor the letter in one engineering story.
- Connect to the company specifically.
- Close directly. No corporate filler.
- Save cover-letter builds as LaTeX.
- Let JobApps assign the visible filename when the material is saved or compiled.
- A strategic letter should add narrative and company/problem insight, not repeat the resume bullet-by-bullet.

## Short Answer Rules

- Answer the prompt directly.
- Use one concrete proof point.
- Avoid resume-regurgitation.
- Prefer mechanism over adjective.
- If the answer asks for motivation, explain the problem that pulls Prashant in.

## Voice Rules

Use:

- direct sentences
- technical specificity
- concrete mechanisms
- conviction without performance
- honest constraints when needed

Avoid:

- generic passion language
- inflated metrics
- tool name-dropping
- corporate enthusiasm
- "I would be excited to"
- "I am thrilled to"
- "I would be happy to"
- "particularly" when it is filler
- "cutting-edge"
- "fast-paced environment"
- "leverage" when it is consulting-slide filler
- em dashes

## Drafting Loop

1. Read the blocker preflight and tailoring requirements.
2. Pick the central angle.
3. Select active, user-confirmed proof points from JobApps database records.
4. Apply relevant learning patterns.
5. Draft only the requested material.
6. Run a voice pass.
7. Run a truth pass.
8. Record which requirement drove each meaningful material change.
9. Record portrayal decisions for material framing.
10. Surface any uncertainty instead of hiding it.
11. If a stronger claim needs a project that does not exist yet, call it a build-now differentiator with the exact artifact and deadline. Do not claim it as done.

## Output Style

When returning materials to the app or user, include:

- final draft
- why this angle was chosen
- tailoring requirements answered
- source proof points used
- portrayal decisions made
- reusable learning patterns discovered
- risks or missing facts
- suggested database material/change records when tools are unavailable

Keep the explanation short. The draft is the artifact.

## Verification

- [ ] No invented claims.
- [ ] No banned phrasing.
- [ ] No em dashes.
- [ ] The draft maps to the job's actual tailoring requirements.
- [ ] Resume builds are Typst (`.typ`) and cover-letter builds are TeX (`.tex`) when saved as app materials.
- [ ] Material changes have reasons, tailoring requirements, portrayal decisions, and proof points.
- [ ] The writing sounds like a thoughtful engineer, not a resume generator.
