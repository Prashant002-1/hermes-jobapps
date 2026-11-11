# Privacy

JobApps keeps your job search on your machine, in a folder you control.

## What is stored and where

Everything lives in the workspace folder (default `~/JobApps`): your profile, evidence, postings, documents, people and notes, as plain files. The plugin keeps no other copy and has no database.

## What leaves your machine

Nothing, unless you ask for one of these:

- **Posting lookups.** Opening a Greenhouse, Lever or Ashby link calls that site's public job API.
- **Job and people search.** These send your search words to Exa, and only when `EXA_API_KEY` is set.
- **Gmail drafts.** Created through the `gog` command in your own account. JobApps cannot send mail.

The model you run Hermes with sees whatever the agent reads from the workspace, as with any other file it works on.

## What the agent may not do

Send, submit, upload or message on your behalf. It prepares drafts and files; you send them. It tracks a person only when you ask and never guesses an email address.

## Keeping the repository clean

This repository is code only. Never commit a workspace, a legacy `data/` folder, documents, secrets or local config. `.gitignore` covers the usual locations; tests use temporary workspaces with invented data.
