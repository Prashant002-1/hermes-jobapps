# JobApps is installed

Start a new session and say **"Set up my JobApps workspace"**. Hermes will create `~/JobApps`, fill in your profile and build your evidence files from an existing resume.

- `/jobapps` shows what needs attention.
- `python3 -m hermes_jobapps ui` (from this plugin's folder) opens the cockpit.
- `python3 -m hermes_jobapps doctor` lists optional tools: Typst for resumes, `EXA_API_KEY` for search, `gog` for Gmail drafts.

Your data stays in the workspace folder. Set `JOBAPPS_HOME` to put it somewhere else.
