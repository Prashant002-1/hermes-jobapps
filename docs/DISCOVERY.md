# Job Discovery

Hermes JobApps discovery is a removable lead feed, not an application bot.
It exists to find current candidate roles, hydrate the strongest official job
source available, run blocker preflight, and let the user choose whether to
promote the role into the normal JobApps workflow.

## Current Path

The active implementation follows the research recommendation:

1. Use Exa Search as a cheap discovery source when `EXA_API_KEY` is present.
2. Hydrate recognized ATS URLs through official public surfaces:
   - Greenhouse Job Board API:
     <https://developer.greenhouse.io/job-board.html>
   - Lever Postings API:
     <https://github.com/lever/postings-api>
   - Ashby public job postings API:
     <https://developers.ashbyhq.com/docs/public-job-posting-api>
3. Store the result as a `discovery_candidate` with source sightings.
4. Run deterministic blocker preflight for sponsorship, location, seniority,
   and obvious effort signals.
5. Promote only after a user action. Promotion writes the source breadcrumb into
   the job as a research note and application signals.

## Configuration

Discovery is controlled by `config/jobapps.default.json`:

```json
{
  "discovery": {
    "enabled": true,
    "hydrators": ["greenhouse", "lever", "ashby"],
    "exa": {
      "api_key_env": "EXA_API_KEY",
      "base_url": "https://api.exa.ai",
      "type": "auto",
      "default_num_results": 8,
      "include_domains": [
        "boards.greenhouse.io",
        "job-boards.greenhouse.io",
        "jobs.lever.co",
        "jobs.ashbyhq.com"
      ]
    }
  }
}
```

Keep the API key outside git:

```bash
export EXA_API_KEY=<exa-api-key>
```

When `EXA_API_KEY` is missing, Exa search returns a visible error and URL
hydration still works. When `discovery.enabled` is `false`, search, hydrate, and
promote actions are blocked while existing JobApps jobs remain usable.

## Removable Boundary

The removable component is intentionally narrow:

- `hermes_jobapps/discovery.py`
- discovery routes in `hermes_jobapps/server.py`
- discovery tools in `hermes_jobapps/tools.py`
- `discovery_candidates` and `discovery_sightings` tables
- the Find view in `web/index.html`, `web/app.js`, and `web/styles.css`
- discovery config under `config/`

Generated jobs, materials, research notes, application signals, progress, and
Hermes run IDs are normal JobApps state after promotion. They should not be
deleted just because the discovery component is removed later.

## Source Policy

Use official sources first. Search providers should discover URLs, not replace
the canonical source. If a search result points to Greenhouse, Lever, or Ashby,
hydrate the ATS record and treat the search result as a sighting.

Do not add LinkedIn, Indeed, anti-bot scraping, browser challenges, rotating
proxies, or form submission to this module. External actions remain disabled:
discovery may draft and record state, but it must not submit applications,
message people, or send email.

## Exa Websets And Monitors

Exa Websets and Monitors are good next adapters once the synchronous Find view
has real usage. Websets are asynchronous and are best treated as curated source
containers whose items can later be imported into `discovery_candidates`.
Monitors are a recurring-search delivery mechanism and should feed the same
candidate/sighting tables instead of creating a second discovery model.

Useful official references:

- Websets overview: <https://exa.ai/docs/websets/api/overview>
- Websets best practices: <https://exa.ai/docs/websets/best-practices>
- Websets items endpoint:
  <https://exa.ai/docs/websets/api/websets/items/list-all-items-for-a-webset>
- Monitors guide: <https://exa.ai/docs/reference/monitors-api-guide>

The rule for both is the same: Exa discovers or verifies candidates; ATS
hydration remains the authority where available.

## Networking Operator

Discovery is useful only if it leads to better action. The next layer is
networking:

1. Promote or prepare the role so the job/company context exists.
2. Use `jobapps_find_people` to search public people profiles. Cheap Exa Search
   is the default.
3. Cache returned people in the JobApps `contacts` table with source URL,
   confidence, channel, email status, and raw payload.
4. Record job-specific networking research notes when a search is tied to a job.
5. Draft outreach from the role, company needs, contact context, and active
   proof points.
6. If Gmail is requested, use `jobapps_create_gmail_draft`.

Contacts explicitly track `email_status`:

- `found` means the provider returned a concrete public email address.
- `missing` means the person/source is useful but no verified email was found.
- `unverified` is reserved for imported or human-supplied addresses that still
  need confirmation.

Websets are available for contact enrichment, including the `email` enrichment
format, but they are not the default because they are slower and more expensive.
Use `provider="auto"` or `use_websets_fallback=true` only when the normal people
search found useful contacts but no verified email and the extra cost is worth
trying.

`jobapps_create_gmail_draft` is intentionally draft-only. It invokes
`gog --gmail-no-send gmail drafts create`; JobApps has no email-send tool.
If `gog`, Gmail auth, Exa, or an API key is unavailable, the tool fails plainly
instead of inventing a fallback.
