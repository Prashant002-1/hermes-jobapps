/* JobApps cockpit.
   One framework-free file for both hosts: the standalone page
   (dashboard/dist/index.html) and the Hermes dashboard tab.
   It displays the state of the search; it does not direct it. */
(function () {
  "use strict";

  const global = typeof window !== "undefined" ? window : globalThis;

  const STAGES = ["new", "ready", "applied", "interviewing", "offer", "rejected", "closed", "skipped"];
  const STAGE_LABELS = {
    new: "New",
    ready: "Ready",
    applied: "Applied",
    interviewing: "Interviewing",
    offer: "Offer",
    rejected: "Rejected",
    closed: "Closed",
    skipped: "Skipped",
  };
  const JOB_GROUPS = [
    { key: "progress", label: "In progress", stages: ["new", "ready"] },
    { key: "applied", label: "Applied", stages: ["applied"] },
    { key: "interviewing", label: "Interviewing", stages: ["interviewing", "offer"] },
    { key: "aside", label: "Set aside", stages: ["rejected", "closed", "skipped"] },
  ];
  const STAGE_TONES = { new: "warn", ready: "warn", applied: "good", interviewing: "good", offer: "good" };
  const PERSON_STATUSES = ["to_contact", "follow_up", "contacted", "replied", "paused"];
  const PERSON_LABELS = {
    to_contact: "To contact",
    follow_up: "Follow up",
    contacted: "Contacted",
    replied: "Replied",
    paused: "Paused",
  };
  const PERSON_TONES = { to_contact: "warn", follow_up: "warn", contacted: "good" };
  const MATERIAL_LABELS = {
    resume: "Resume",
    cover_letter: "Cover letter",
    application_answers: "Answers",
    outreach: "Outreach",
  };
  const MATERIAL_STATES = { pass: "Checked", review: "Needs attention", fail: "Needs attention", stale: "Changed since check" };
  const CHECKABLE_FORMATS = ["typ", "tex", "md", "txt"];
  const PRIORITIES = [
    { value: "high", label: "High" },
    { value: "normal", label: "Normal" },
    { value: "low", label: "Low" },
  ];
  const DECISION_LABELS = { apply: "Apply", pending: "Pending", skip: "Skip" };
  const LEAD_CHIPS = { skip: "Blocked", pending: "Check" };
  const CHANNEL_LABELS = { referral: "Referral", cold: "Cold" };
  const NAV = [
    { group: "Daily workspace", view: "overview", label: "Overview", icon: "overview" },
    { group: "Daily workspace", view: "jobs", label: "Jobs", icon: "jobs" },
    { group: "Daily workspace", view: "people", label: "People", icon: "people" },
    { group: "Explore", view: "leads", label: "Leads", icon: "leads" },
    { group: "Explore", view: "insights", label: "Insights", icon: "insights" },
    { group: "Reference", view: "library", label: "Library", icon: "library" },
  ];
  const VIEWS = NAV.map(function (item) {
    return item.view;
  });
  const HASH_ALIASES = { today: "overview", pipeline: "jobs", job: "jobs" };
  const PROFILE_DOCS = [
    { path: "profile/profile.md", label: "Profile" },
    { path: "profile/voice.md", label: "Voice" },
    { path: "profile/playbook.md", label: "Playbook" },
  ];
  const GROUP_LIMIT = 20;
  const WAITING_LIMIT = 12;
  const UP_NEXT_LIMIT = 5;
  const REFRESH_MS = 20000;
  const EMPTY = "Nothing here yet";
  const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  const MONTH_NAMES = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];
  const WEEKDAYS = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"];

  function hasOwn(object, key) {
    return Object.prototype.hasOwnProperty.call(object, key);
  }

  function lookup(table, key) {
    return typeof key === "string" && hasOwn(table, key) ? table[key] : undefined;
  }

  // ── Dates: plain calendar dates, nothing counted ─────────────────────

  function pad2(value) {
    return value < 10 ? "0" + value : String(value);
  }

  function localISODate(date) {
    const d = date || new Date();
    return d.getFullYear() + "-" + pad2(d.getMonth() + 1) + "-" + pad2(d.getDate());
  }

  function parseDay(value) {
    const match = /^(\d{4})-(\d{2})-(\d{2})/.exec(String(value == null ? "" : value));
    if (!match || Number(match[2]) < 1 || Number(match[2]) > 12) return null;
    return { y: Number(match[1]), m: Number(match[2]), d: Number(match[3]) };
  }

  function formatDate(iso, today) {
    const day = parseDay(iso);
    if (!day) return "";
    const base = MONTHS[day.m - 1] + " " + day.d;
    const now = parseDay(today);
    return now && now.y === day.y ? base : base + ", " + day.y;
  }

  function longDate(iso) {
    const day = parseDay(iso);
    if (!day) return "";
    const weekday = WEEKDAYS[new Date(day.y, day.m - 1, day.d).getDay()];
    return weekday + ", " + MONTH_NAMES[day.m - 1] + " " + day.d;
  }

  /* A date as text, and whether it lies before today. The past is shown by
     color alone at the point of use: no counters, no warnings. */
  function dateInfo(iso, today) {
    const text = formatDate(iso, today);
    if (!text) return null;
    const day = String(iso).slice(0, 10);
    return { text: text, past: !!parseDay(today) && day < String(today).slice(0, 10) };
  }

  function plural(count, word) {
    return count + " " + word + (count === 1 ? "" : "s");
  }

  // ── Labels ───────────────────────────────────────────────────────────

  function humanize(value) {
    const text = String(value == null ? "" : value).replace(/[_-]+/g, " ").trim();
    return text ? text.charAt(0).toUpperCase() + text.slice(1) : "";
  }

  function stageLabel(stage) {
    return lookup(STAGE_LABELS, stage) || humanize(stage);
  }

  function stageTone(stage) {
    return lookup(STAGE_TONES, stage) || "neutral";
  }

  function personLabel(status) {
    return lookup(PERSON_LABELS, status) || humanize(status);
  }

  function personTone(status) {
    return lookup(PERSON_TONES, status) || "neutral";
  }

  function leadChip(preflight) {
    return lookup(LEAD_CHIPS, String(preflight == null ? "" : preflight).trim().toLowerCase()) || "";
  }

  function decisionLabel(value) {
    const key = String(value == null ? "" : value).trim().toLowerCase();
    return key ? lookup(DECISION_LABELS, key) || humanize(value) : "";
  }

  function materialLabel(material) {
    const item = material || {};
    const label = lookup(MATERIAL_LABELS, item.kind);
    return label ? { label: label, file: String(item.name || "") } : { label: String(item.name || ""), file: "" };
  }

  /* A word only when there is something to say; never-checked says nothing. */
  function materialState(qa) {
    return lookup(MATERIAL_STATES, qa) || "";
  }

  // ── Overview ─────────────────────────────────────────────────────────

  function overviewCounts(counts) {
    const value = counts || {};
    return JOB_GROUPS.map(function (group) {
      return {
        key: group.key,
        label: group.label,
        value: group.stages.reduce(function (sum, stage) {
          return sum + (Number(value[stage]) || 0);
        }, 0),
      };
    });
  }

  function byRecent(a, b) {
    const left = String(a.updated_on || "");
    const right = String(b.updated_on || "");
    return left < right ? 1 : left > right ? -1 : 0;
  }

  /* The one job to continue with: an interview or offer first, then the
     ready job touched most recently, then the newest work in progress. */
  function continueJob(jobs) {
    const list = jobs || [];
    const pick = function (stages) {
      return list
        .filter(function (job) {
          return stages.indexOf(job.stage) !== -1;
        })
        .sort(byRecent)[0];
    };
    return pick(["interviewing", "offer"]) || pick(["ready"]) || pick(["new"]) || null;
  }

  function upNext(rows, limit, today) {
    const anchor = parseDay(today || localISODate()) || parseDay(localISODate());
    const recent = localISODate(new Date(anchor.y, anchor.m - 1, anchor.d - 14));
    return (rows || [])
      .filter(function (row) {
        return !!parseDay(row.due);
      })
      .map(function (row, index) {
        return { row: row, index: index };
      })
      .sort(function (a, b) {
        const staleA = a.row.due < recent ? 1 : 0;
        const staleB = b.row.due < recent ? 1 : 0;
        if (staleA !== staleB) return staleA - staleB;
        if (a.row.due !== b.row.due) return (a.row.due < b.row.due ? -1 : 1) * (staleA ? -1 : 1);
        return a.index - b.index;
      })
      .slice(0, limit == null ? UP_NEXT_LIMIT : limit)
      .map(function (item) {
        return item.row;
      });
  }

  function waitingJobs(jobs) {
    return (jobs || [])
      .filter(function (job) {
        return job.stage === "applied";
      })
      .map(function (job, index) {
        return { job: job, index: index };
      })
      .sort(function (a, b) {
        const left = String(a.job.applied_on || "");
        const right = String(b.job.applied_on || "");
        if (left !== right) return left < right ? 1 : -1;
        return a.index - b.index;
      })
      .map(function (item) {
        return item.job;
      });
  }

  // ── Jobs ─────────────────────────────────────────────────────────────

  function filterJobs(jobs, query) {
    const words = String(query == null ? "" : query).toLowerCase().split(/\s+/).filter(Boolean);
    if (!words.length) return (jobs || []).slice();
    return (jobs || []).filter(function (job) {
      const haystack = [job.company, job.title, job.location, job.job].join(" ").toLowerCase();
      return words.every(function (word) {
        return haystack.indexOf(word) !== -1;
      });
    });
  }

  function groupStages(filter) {
    const group = JOB_GROUPS.filter(function (item) {
      return item.key === filter;
    })[0];
    return group ? group.stages : STAGES;
  }

  /* The list beside the detail: one group per stage, in stage order,
     skipping empty stages. */
  function groupJobs(jobs, query, filter) {
    const matched = filterJobs(jobs, query);
    const buckets = {};
    STAGES.forEach(function (stage) {
      buckets[stage] = [];
    });
    matched.forEach(function (job) {
      (lookup(buckets, job.stage) || buckets.new).push(job);
    });
    return groupStages(filter)
      .filter(function (stage) {
        return buckets[stage].length;
      })
      .map(function (stage) {
        return { stage: stage, label: stageLabel(stage), jobs: buckets[stage] };
      });
  }

  function jobRowMeta(job, today) {
    return [job.location, formatDate(job.applied_on || job.created_on || job.updated_on, today)].filter(Boolean).join(" · ");
  }

  function trackRoute(jobId) {
    return "/jobs/" + encodeURIComponent(jobId) + "/track";
  }

  /* The one track body for the next-step form, or null when nothing changed.
     Clearing the text clears its date on the server, so no date is sent then. */
  function nextActionBody(saved, text, due) {
    const before = saved || {};
    const body = {};
    if (text !== String(before.next_action || "")) body.next_action = text;
    if (due !== String(before.due || "") && !(hasOwn(body, "next_action") && !text)) body.due = due;
    return Object.keys(body).length ? body : null;
  }

  function jobRef(job) {
    return (job.company || "the company") + ", " + (job.title || "the role") + " (job " + job.job + ")";
  }

  function jobPrompts(job) {
    const ref = jobRef(job);
    return [
      { label: "Plan my application", text: "Plan my application for " + ref + "." },
      { label: "Tailor my resume", text: "Tailor my resume for " + ref + "." },
      { label: "Write the cover letter", text: "Write the cover letter for " + ref + "." },
      { label: "Draft outreach", text: "Draft outreach for " + ref + "." },
      { label: "Prepare for the interview", text: "Help me prepare for the interview at " + ref + "." },
    ];
  }

  function personPrompt(person) {
    const at = [person.role, person.company].filter(Boolean).join(" at ");
    return "Draft a note to " + person.name + (at ? ", " + at : "") + " (person " + person.person + ").";
  }

  /* What a check found, as one flat list: the rule in words, the excerpt, the fix. */
  function checkFindings(result) {
    const value = result || {};
    if (value.ok === false) {
      return { state: "Not checked", items: [{ rule: "Check", excerpt: String(value.error || ""), fix: "" }], more: 0 };
    }
    const build = value.build || {};
    const layout = value.layout || {};
    const content = value.content || {};
    const items = [];
    if (build.error) items.push({ rule: "Build", excerpt: String(build.error), fix: "" });
    (build.integrity_errors || []).forEach(function (item) {
      items.push({ rule: humanize(item), excerpt: "", fix: "" });
    });
    (build.contamination || []).forEach(function (item) {
      items.push({ rule: "Leftover text", excerpt: String(item), fix: "" });
    });
    (layout.violations || []).forEach(function (item) {
      let rule = humanize(item.type) || "Layout";
      if (item.page != null) rule += ", page " + item.page;
      items.push({ rule: rule, excerpt: String(item.text || ""), fix: String(item.fix || "") });
    });
    (content.findings || []).forEach(function (item) {
      const rule = humanize(item.rule) || humanize(item.severity) || "Writing";
      items.push({ rule: item.where ? rule + ", " + item.where : rule, excerpt: String(item.excerpt || ""), fix: String(item.fix || "") });
    });
    const hidden = Math.max(0, (Number(layout.violations_total) || 0) - (layout.violations || []).length) + (Number(content.findings_truncated) || 0);
    return { state: materialState(value.status) || "Checked", items: items, more: hidden };
  }

  function addJobOutcome(result) {
    const value = result || {};
    const job = value.job || {};
    const name = [job.company, job.title].filter(Boolean).join(", ");
    if (value.ok && value.duplicate) {
      return { kind: "duplicate", jobId: job.job || "", lines: ["Already here: " + (name || job.job || "this job")] };
    }
    if (value.ok && job.job) {
      const preflight = value.preflight || {};
      const lines = ["Added " + (name || job.job)];
      const decision = String(preflight.decision || "").toLowerCase();
      if (decision && decision !== "apply") {
        const found = (preflight.blockers || [])
          .map(function (item) {
            return [humanize(item.area), item.evidence].filter(Boolean).join(": ");
          })
          .filter(Boolean)
          .join("; ");
        lines.push("Blocker check: " + decisionLabel(decision) + (found ? ". " + found : ""));
      }
      return { kind: "created", jobId: job.job, lines: lines };
    }
    const needs = [].concat(value.needs || []).map(function (item) {
      return String(item).replace(/_/g, " ");
    });
    const lines = [needs.length ? "Missing: " + needs.join(" and ") : "Not added"];
    if (value.error) lines.push(String(value.error));
    return { kind: "needs", jobId: "", lines: lines };
  }

  // ── People and leads ─────────────────────────────────────────────────

  function peopleCounts(people) {
    const list = people || [];
    const of = function (status) {
      return list.filter(function (person) {
        return person.status === status;
      }).length;
    };
    return [
      { label: "People", value: list.length },
      { label: "To contact", value: of("to_contact") },
      { label: "Follow up", value: of("follow_up") },
      { label: "Contacted", value: of("contacted") },
    ];
  }

  function filterPeople(people, query, status) {
    const words = String(query == null ? "" : query).toLowerCase().split(/\s+/).filter(Boolean);
    return (people || []).filter(function (person) {
      if (status && person.status !== status) return false;
      const haystack = [person.name, person.company, person.role].join(" ").toLowerCase();
      return words.every(function (word) {
        return haystack.indexOf(word) !== -1;
      });
    });
  }

  /* The text under a `## heading` of a record, without italic placeholders. */
  function sectionText(body, heading) {
    const lines = String(body == null ? "" : body).replace(/\r\n?/g, "\n").split("\n");
    const wanted = String(heading).toLowerCase();
    const kept = [];
    let inside = false;
    for (let i = 0; i < lines.length; i += 1) {
      const match = /^##[ \t]+(.+?)[ \t]*$/.exec(lines[i]);
      if (match) {
        if (inside) break;
        inside = match[1].toLowerCase() === wanted;
      } else if (inside) {
        kept.push(lines[i]);
      }
    }
    const text = kept.join("\n").trim();
    return /^_[^\n]*_$/.test(text) ? "" : text;
  }

  // ── Insights ─────────────────────────────────────────────────────────

  function tally(value) {
    const number = Number(value);
    return number > 0 && isFinite(number) ? Math.round(number) : 0;
  }

  function percent(part, whole) {
    const top = Number(part);
    const bottom = Number(whole);
    if (!(top > 0) || !(bottom > 0)) return 0;
    return Math.min(100, Math.round((top / bottom) * 100));
  }

  function monthLabel(month) {
    const text = String(month == null ? "" : month);
    const match = /^(\d{4})-(\d{2})$/.exec(text);
    if (match && Number(match[2]) >= 1 && Number(match[2]) <= 12) return MONTHS[Number(match[2]) - 1] + " " + match[1];
    return text === "undated" ? "No date" : text;
  }

  function insightRows(rows, key) {
    const list = (rows || []).map(function (row) {
      const raw = row[key];
      let label = humanize(raw) || "Unlabelled";
      if (key === "month") label = monthLabel(raw);
      if (key === "channel") label = lookup(CHANNEL_LABELS, String(raw)) || label;
      return {
        label: label,
        applied: tally(row.applied),
        interviews: tally(row.interviews),
        rejected: tally(row.rejected),
        no_reply: tally(row.no_reply),
      };
    });
    const most = list.reduce(function (max, row) {
      return Math.max(max, row.applied);
    }, 0);
    list.forEach(function (row) {
      row.bar = percent(row.applied, most);
    });
    return list;
  }

  function insightFigures(stats) {
    const value = stats || {};
    const median = value.median_days_to_outcome;
    return {
      sent: tally(value.applied),
      figures: [
        { label: "Sent", value: tally(value.applied) },
        { label: "Interviews", value: tally(value.interviews) },
        { label: "Offers", value: tally(value.offers) },
        { label: "Rejected", value: tally(value.rejected) },
        { label: "No reply", value: tally(value.no_reply) },
      ],
      rate: value.interview_rate ? String(value.interview_rate) + " reached an interview" : "",
      median: typeof median === "number" && median > 0 ? "Median " + plural(median, "day") + " to an outcome" : "",
    };
  }

  // ── Links and routes ─────────────────────────────────────────────────

  function safeHref(value) {
    const url = String(value == null ? "" : value).trim();
    if (/^https?:\/\/[^\s]+$/i.test(url)) return url;
    if (/^mailto:[^\s@]+@[^\s@]+$/i.test(url)) return url;
    return null;
  }

  function mailtoHref(email) {
    const address = String(email == null ? "" : email).trim();
    return /^[^\s@<>]+@[^\s@<>]+$/.test(address) ? "mailto:" + address : null;
  }

  function linkedinHref(value) {
    const text = String(value == null ? "" : value).trim();
    if (!text) return null;
    if (/^https?:\/\//i.test(text)) return safeHref(text);
    if (/^(www\.)?linkedin\.com\/[^\s]+$/i.test(text)) return "https://" + text;
    return null;
  }

  /* #/overview, #/jobs, #/jobs/<id>, #/people, #/leads, #/insights and
     #/library/<path>. The earlier #/today, #/pipeline and #/job/<id> still open. */
  function parseHash(hash) {
    const parts = String(hash == null ? "" : hash).replace(/^#/, "").split("/").filter(Boolean);
    let decoded;
    try {
      decoded = parts.map(decodeURIComponent);
    } catch (err) {
      return { view: "overview" };
    }
    const view = lookup(HASH_ALIASES, decoded[0]) || decoded[0];
    if (view === "jobs") return decoded[1] ? { view: "jobs", job: decoded[1] } : { view: "jobs" };
    if (view === "library") {
      const path = decoded.slice(1).join("/");
      return path ? { view: "library", path: path } : { view: "library" };
    }
    return VIEWS.indexOf(view) !== -1 ? { view: view } : { view: "overview" };
  }

  function formatHash(route) {
    const view = route && VIEWS.indexOf(route.view) !== -1 ? route.view : "overview";
    if (view === "jobs" && route.job) return "#/jobs/" + encodeURIComponent(route.job);
    if (view === "library" && route.path) {
      return "#/library/" + String(route.path).split("/").filter(Boolean).map(encodeURIComponent).join("/");
    }
    return "#/" + view;
  }

  // ── Markdown ─────────────────────────────────────────────────────────

  const MD_FENCE = /^ {0,3}(`{3,}|~{3,})[ \t]*([^`\s]*)[^`]*$/;
  const MD_HEADING = /^ {0,3}(#{1,4})[ \t]+(.*?)(?:[ \t]+#+)?[ \t]*$/;
  const MD_RULE = /^ {0,3}([-*_])(?:[ \t]*\1){2,}[ \t]*$/;
  const MD_BULLET = /^([ \t]*)[-*+][ \t]+(.*)$/;
  const MD_NUMBER = /^([ \t]*)(\d{1,9})[.)][ \t]+(.*)$/;
  const IN_CODE = /`([^`\n]+)`/y;
  const IN_LINK = /\[([^\]\n]+)\]\([ \t]*([^()\s]+)[ \t]*\)/y;
  const IN_STRONG = /\*\*(?=\S)([^\n]*?\S)\*\*/y;
  const IN_EM_STAR = /\*(?=[^\s*])([^*\n]*?[^\s*])\*(?!\*)/y;
  const IN_EM_UNDER = /_(?=[^\s_])([^_\n]*?[^\s_])_(?![A-Za-z0-9_])/y;
  const IN_URL = /https?:\/\/[^\s<>"'`\\]+/y;

  function trimUrl(url) {
    let text = url;
    for (;;) {
      const last = text.charAt(text.length - 1);
      if (/[.,;:!?*_]/.test(last)) {
        text = text.slice(0, -1);
      } else if (last === ")" && text.split(")").length > text.split("(").length) {
        text = text.slice(0, -1);
      } else if (last === "]" && text.split("]").length > text.split("[").length) {
        text = text.slice(0, -1);
      } else {
        return text;
      }
    }
  }

  function parseInline(text, inLink) {
    const source = String(text == null ? "" : text);
    const out = [];
    let buffer = "";
    let i = 0;

    function flush() {
      if (buffer) out.push({ type: "text", text: buffer });
      buffer = "";
    }
    function at(pattern) {
      pattern.lastIndex = i;
      return pattern.exec(source);
    }
    function wrap(type, match) {
      flush();
      out.push({ type: type, children: parseInline(match[1], inLink) });
      i += match[0].length;
    }

    while (i < source.length) {
      const ch = source.charAt(i);
      const prev = i > 0 ? source.charAt(i - 1) : "";
      let match = null;
      if (ch === "\n") {
        flush();
        out.push({ type: "break" });
        i += 1;
      } else if (ch === "\\" && /[\\`*_[\]()#+\-.!>]/.test(source.charAt(i + 1))) {
        buffer += source.charAt(i + 1);
        i += 2;
      } else if (ch === "`" && (match = at(IN_CODE))) {
        flush();
        out.push({ type: "code", text: match[1] });
        i += match[0].length;
      } else if (ch === "[" && !inLink && (match = at(IN_LINK))) {
        const href = safeHref(match[2]);
        if (href) {
          flush();
          out.push({ type: "link", href: href, children: parseInline(match[1], true) });
        } else {
          buffer += match[0];
        }
        i += match[0].length;
      } else if (ch === "*" && source.charAt(i + 1) === "*" && (match = at(IN_STRONG))) {
        wrap("strong", match);
      } else if (ch === "*" && prev !== "*" && (match = at(IN_EM_STAR))) {
        wrap("em", match);
      } else if (ch === "_" && !/[A-Za-z0-9_]/.test(prev) && (match = at(IN_EM_UNDER))) {
        wrap("em", match);
      } else if (ch === "h" && !inLink && !/[A-Za-z0-9]/.test(prev) && (match = at(IN_URL)) && safeHref(trimUrl(match[0]))) {
        const url = trimUrl(match[0]);
        flush();
        out.push({ type: "link", href: url, children: [{ type: "text", text: url }] });
        i += url.length;
      } else {
        buffer += ch;
        i += 1;
      }
    }
    flush();
    return out;
  }

  function listMarker(line) {
    let match = MD_BULLET.exec(line);
    if (match) return { indent: match[1].replace(/\t/g, "    ").length, ordered: false, start: 1, text: match[2] };
    match = MD_NUMBER.exec(line);
    if (match) return { indent: match[1].replace(/\t/g, "    ").length, ordered: true, start: Number(match[2]), text: match[3] };
    return null;
  }

  function startsBlock(line) {
    return MD_FENCE.test(line) || MD_HEADING.test(line) || MD_RULE.test(line) || !!listMarker(line);
  }

  function readList(lines, start, blocks) {
    const first = listMarker(lines[start]);
    const base = first.indent;
    const items = [];
    let item = null;
    let target = null;
    let i = start;
    while (i < lines.length) {
      const line = lines[i];
      if (!line.trim()) {
        let next = i + 1;
        while (next < lines.length && !lines[next].trim()) next += 1;
        if (next >= lines.length || MD_RULE.test(lines[next]) || !listMarker(lines[next])) break;
        i = next;
        continue;
      }
      if (MD_RULE.test(line) || MD_FENCE.test(line) || MD_HEADING.test(line)) break;
      const marker = listMarker(line);
      if (marker && item && marker.indent >= base + 2) {
        if (!item.list) item.list = { ordered: marker.ordered, start: marker.start, items: [] };
        target = { text: marker.text };
        item.list.items.push(target);
      } else if (marker) {
        if (marker.ordered !== first.ordered) break;
        item = { text: marker.text, list: null };
        target = item;
        items.push(item);
      } else if (/^[ \t]+\S/.test(line) && target) {
        target.text += "\n" + line.trim();
      } else {
        break;
      }
      i += 1;
    }
    blocks.push({
      type: "list",
      ordered: first.ordered,
      start: first.start,
      items: items.map(function (entry) {
        return {
          children: parseInline(entry.text),
          list: entry.list
            ? {
                type: "list",
                ordered: entry.list.ordered,
                start: entry.list.start,
                items: entry.list.items.map(function (child) {
                  return { children: parseInline(child.text), list: null };
                }),
              }
            : null,
        };
      }),
    });
    return i;
  }

  function parseMarkdown(text) {
    const lines = String(text == null ? "" : text).replace(/\r\n?/g, "\n").split("\n");
    const blocks = [];
    let i = 0;
    while (i < lines.length) {
      const line = lines[i];
      let match;
      if (!line.trim()) {
        i += 1;
      } else if ((match = MD_FENCE.exec(line))) {
        const fence = match[1];
        const body = [];
        i += 1;
        while (i < lines.length) {
          const close = /^ {0,3}(`{3,}|~{3,})[ \t]*$/.exec(lines[i]);
          if (close && close[1].charAt(0) === fence.charAt(0) && close[1].length >= fence.length) break;
          body.push(lines[i]);
          i += 1;
        }
        i += 1;
        blocks.push({ type: "code", lang: match[2] || "", text: body.join("\n") });
      } else if ((match = MD_HEADING.exec(line))) {
        blocks.push({ type: "heading", level: match[1].length, children: parseInline(match[2]) });
        i += 1;
      } else if (MD_RULE.test(line)) {
        blocks.push({ type: "rule" });
        i += 1;
      } else if (listMarker(line)) {
        i = readList(lines, i, blocks);
      } else {
        const paragraph = [line.trim()];
        i += 1;
        while (i < lines.length && lines[i].trim() && !startsBlock(lines[i])) {
          paragraph.push(lines[i].trim());
          i += 1;
        }
        blocks.push({ type: "paragraph", children: parseInline(paragraph.join("\n")) });
      }
    }
    return blocks;
  }

  function appendInline(parent, nodes, doc) {
    nodes.forEach(function (node) {
      let el;
      if (node.type === "text") {
        parent.appendChild(doc.createTextNode(node.text));
        return;
      }
      if (node.type === "break") {
        el = doc.createElement("br");
      } else if (node.type === "code") {
        el = doc.createElement("code");
        el.textContent = node.text;
      } else if (node.type === "link") {
        el = doc.createElement("a");
        el.setAttribute("href", node.href);
        el.setAttribute("target", "_blank");
        el.setAttribute("rel", "noopener noreferrer");
        appendInline(el, node.children, doc);
      } else {
        el = doc.createElement(node.type === "strong" ? "strong" : "em");
        appendInline(el, node.children, doc);
      }
      parent.appendChild(el);
    });
  }

  function renderList(list, doc) {
    const el = doc.createElement(list.ordered ? "ol" : "ul");
    if (list.ordered && list.start !== 1) el.setAttribute("start", String(list.start));
    list.items.forEach(function (item) {
      const li = doc.createElement("li");
      appendInline(li, item.children, doc);
      if (item.list) li.appendChild(renderList(item.list, doc));
      el.appendChild(li);
    });
    return el;
  }

  function renderMarkdown(text, doc) {
    const target = doc || global.document;
    const fragment = target.createDocumentFragment();
    parseMarkdown(text).forEach(function (block) {
      let el;
      if (block.type === "heading") {
        el = target.createElement("h" + (block.level + 2));
        el.className = "ja-md-h" + block.level;
        appendInline(el, block.children, target);
      } else if (block.type === "code") {
        el = target.createElement("pre");
        const code = target.createElement("code");
        code.textContent = block.text;
        el.appendChild(code);
      } else if (block.type === "rule") {
        el = target.createElement("hr");
      } else if (block.type === "list") {
        el = renderList(block, target);
      } else {
        el = target.createElement("p");
        appendInline(el, block.children, target);
      }
      fragment.appendChild(el);
    });
    return fragment;
  }

  // ── API clients ──────────────────────────────────────────────────────

  function queryString(query) {
    const parts = [];
    Object.keys(query || {}).forEach(function (key) {
      if (query[key] != null) parts.push(encodeURIComponent(key) + "=" + encodeURIComponent(query[key]));
    });
    return parts.length ? "?" + parts.join("&") : "";
  }

  function errorText(body, status) {
    let payload = null;
    try {
      payload = body ? JSON.parse(body) : null;
    } catch (err) {
      payload = null;
    }
    if (payload && typeof payload.error === "string" && payload.error) return payload.error;
    if (payload && typeof payload.detail === "string" && payload.detail) return payload.detail;
    return "The request failed (" + status + ").";
  }

  function blobUrlFrom(response) {
    if (!response.ok) {
      return response.text().then(function (body) {
        throw new Error(errorText(body, response.status));
      });
    }
    return response.blob().then(function (blob) {
      return global.URL.createObjectURL(blob);
    });
  }

  function createApiClient(options) {
    const settings = options || {};
    const base = String(settings.base == null ? "/api" : settings.base).replace(/\/+$/, "");
    const fetchFn =
      settings.fetch ||
      function (url, init) {
        return global.fetch(url, init);
      };

    function request(url, init) {
      return fetchFn(url, init).catch(function () {
        throw new Error("The cockpit server is not answering. Is it still running?");
      });
    }
    function json(url, init) {
      return request(url, init).then(function (response) {
        return response.text().then(function (body) {
          if (!response.ok) throw new Error(errorText(body, response.status));
          return body ? JSON.parse(body) : null;
        });
      });
    }
    return {
      get: function (route, query) {
        return json(base + route + queryString(query), { headers: { Accept: "application/json" } });
      },
      post: function (route, body) {
        return json(base + route, {
          method: "POST",
          headers: { Accept: "application/json", "Content-Type": "application/json" },
          body: JSON.stringify(body || {}),
        });
      },
      fileBlobUrl: function (path) {
        return request(base + "/file" + queryString({ path: path })).then(blobUrlFrom);
      },
    };
  }

  /* Inside the Hermes dashboard every request goes through the SDK:
     fetchJSON for JSON routes and authedFetch for file bytes. Both attach
     the dashboard's own authentication. */
  function createHermesApiClient(sdk, base) {
    const prefix = String(base || "/api/plugins/jobapps").replace(/\/+$/, "");

    function normalize(err) {
      const message = String((err && err.message) || err || "The request failed.");
      const legacy = /^(\d{3}): ([\s\S]*)$/.exec(message);
      throw new Error(legacy ? errorText(legacy[2], legacy[1]) : message);
    }
    function authed(url) {
      if (typeof sdk.authedFetch === "function") return sdk.authedFetch(url);
      const token = global.__HERMES_SESSION_TOKEN__;
      return global.fetch(url, {
        credentials: "include",
        headers: token ? { "X-Hermes-Session-Token": token } : {},
      });
    }
    return {
      get: function (route, query) {
        return sdk.fetchJSON(prefix + route + queryString(query)).catch(normalize);
      },
      post: function (route, body) {
        return sdk
          .fetchJSON(prefix + route, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(body || {}),
          })
          .catch(normalize);
      },
      fileBlobUrl: function (path) {
        return authed(prefix + "/file" + queryString({ path: path })).then(blobUrlFrom);
      },
    };
  }

  // ── DOM ──────────────────────────────────────────────────────────────

  const PROPERTY_KEYS = ["value", "checked", "disabled", "selected", "hidden"];
  const SVG_NS = "http://www.w3.org/2000/svg";
  const ICONS = {
    overview: [
      ["rect", { x: 3.5, y: 3.5, width: 7, height: 17 }],
      ["rect", { x: 13.5, y: 3.5, width: 7, height: 7 }],
      ["rect", { x: 13.5, y: 13.5, width: 7, height: 7 }],
    ],
    jobs: [
      ["rect", { x: 3.5, y: 7.5, width: 17, height: 12 }],
      ["path", { d: "M9 7.5V4.5h6v3" }],
    ],
    people: [
      ["circle", { cx: 9, cy: 8.5, r: 3 }],
      ["path", { d: "M3.5 19.5c0-3 2.5-5.5 5.5-5.5s5.5 2.5 5.5 5.5" }],
      ["path", { d: "M15.5 5.8a3 3 0 0 1 0 5.4" }],
      ["path", { d: "M17 14.3c2 .8 3.5 2.8 3.5 5.2" }],
    ],
    leads: [
      ["circle", { cx: 11, cy: 11, r: 6.5 }],
      ["path", { d: "M16 16l4.5 4.5" }],
    ],
    insights: [
      ["path", { d: "M3.5 17.5l5.5-6 4 3.5 7.5-8.5" }],
      ["path", { d: "M15.5 6.5h5v5" }],
    ],
    library: [
      ["path", { d: "M6 3.5h8.5l4 4v13H6z" }],
      ["path", { d: "M14.5 3.5v4h4" }],
      ["path", { d: "M9 12.5h6M9 16h6" }],
    ],
    rail: [
      ["rect", { x: 3.5, y: 4.5, width: 17, height: 15 }],
      ["path", { d: "M9.5 4.5v15" }],
    ],
    plus: [["path", { d: "M12 5.5v13M5.5 12h13" }]],
  };
  const LOGO_BARS = [
    { x: 1, y: 6, height: 16, tone: "amber" },
    { x: 7, y: 9, height: 13, tone: "accent" },
    { x: 13, y: 3, height: 22, tone: "accent" },
    { x: 19, y: 7, height: 15, tone: "amber" },
    { x: 25, y: 10, height: 13, tone: "accent" },
  ];

  function makeH(doc) {
    function append(el, child) {
      if (child == null || child === false || child === true) return;
      if (Array.isArray(child)) {
        child.forEach(function (item) {
          append(el, item);
        });
      } else if (typeof child === "string" || typeof child === "number") {
        el.appendChild(doc.createTextNode(String(child)));
      } else {
        el.appendChild(child);
      }
    }
    return function h(tag, props) {
      const el = doc.createElement(tag);
      Object.keys(props || {}).forEach(function (key) {
        const value = props[key];
        if (value == null || value === false) return;
        if (key === "class") el.className = value;
        else if (key === "text") el.textContent = String(value);
        else if (key.slice(0, 2) === "on" && typeof value === "function") el.addEventListener(key.slice(2), value);
        else if (PROPERTY_KEYS.indexOf(key) !== -1) el[key] = value;
        else el.setAttribute(key, value === true ? "" : String(value));
      });
      for (let i = 2; i < arguments.length; i += 1) append(el, arguments[i]);
      return el;
    };
  }

  function makeSvg(doc) {
    function node(tag, attrs) {
      const el = doc.createElementNS(SVG_NS, tag);
      Object.keys(attrs).forEach(function (key) {
        el.setAttribute(key, String(attrs[key]));
      });
      return el;
    }
    return {
      icon: function (name) {
        const svg = node("svg", { class: "ja-icon", viewBox: "0 0 24 24", "aria-hidden": "true", focusable: "false" });
        (ICONS[name] || []).forEach(function (shape) {
          svg.appendChild(node(shape[0], shape[1]));
        });
        return svg;
      },
      logo: function () {
        const svg = node("svg", { class: "ja-logo", viewBox: "0 0 28 28", "aria-hidden": "true", focusable: "false" });
        LOGO_BARS.forEach(function (bar) {
          svg.appendChild(node("rect", { class: "ja-logo-" + bar.tone, x: bar.x, y: bar.y, width: 3, height: bar.height, rx: 1.5 }));
        });
        return svg;
      },
    };
  }

  function clear(el) {
    while (el.firstChild) el.removeChild(el.firstChild);
  }

  function messageOf(err) {
    return String((err && err.message) || err || "Something went wrong.");
  }

  function newUiState() {
    return {
      route: { view: "overview" },
      lastJob: "",
      jobs: { query: "", filter: "", showAll: {} },
      people: { query: "", filter: "" },
      leads: { filter: "" },
      open: {},
      editing: {},
      drafts: {},
      checks: {},
      blocked: {},
      scroll: {},
      railCollapsed: false,
      railOpen: false,
    };
  }

  const memory = newUiState();
  let mountCount = 0;

  // ── The cockpit ──────────────────────────────────────────────────────

  function mount(root, options) {
    const settings = options || {};
    const api = settings.api;
    if (!root || !api) throw new Error("JobAppsCockpit.mount needs a root element and an api client.");

    const embedded = !!settings.embedded;
    const doc = root.ownerDocument;
    const win = doc.defaultView || global;
    const h = makeH(doc);
    const svg = makeSvg(doc);
    const ui = embedded ? memory : newUiState();
    const data = { state: null, sig: "", jobs: {}, evidence: null, evidenceSig: "", evidenceError: "", docs: {}, stats: null, why: {} };
    const busy = {};
    const fetching = {};
    const blobUrls = {};
    const listeners = [];
    const addJob = { result: null, error: "" };
    const viewer = { path: "", name: "", doc: null, error: "", loading: false };
    const personForm = { id: "", error: "" };
    const uid = "ja" + (mountCount += 1);
    const addedClasses = ["jobapps-root", embedded ? "jobapps-embedded" : "jobapps-standalone"].filter(function (name) {
      return !root.classList.contains(name);
    });

    let alive = true;
    let error = null;
    let notice = null;
    let inflight = null;
    let pending = null;
    let deferred = false;
    let lastRefresh = 0;
    let timer = null;
    let openMenu = null;

    addedClasses.forEach(function (name) {
      root.classList.add(name);
    });

    function stored(key) {
      try {
        return win.localStorage ? win.localStorage.getItem(key) : null;
      } catch (err) {
        return null;
      }
    }

    function store(key, value) {
      try {
        if (win.localStorage) win.localStorage.setItem(key, value);
      } catch (err) {
        /* remembering the rail is a convenience */
      }
    }

    function listen(target, type, handler) {
      if (!target || !target.addEventListener) return;
      target.addEventListener(type, handler);
      listeners.push([target, type, handler]);
    }

    // ── Shell ──────────────────────────────────────────────────────────

    const els = { nav: {} };
    els.banner = h("div", { class: "ja-slot" });
    els.notice = h("div", { class: "ja-slot" });
    els.main = h("main", { class: "ja-main", tabindex: "-1" });
    els.live = h("div", { class: "ja-sr", "aria-live": "polite" });
    els.addDialog = h("dialog", { class: "ja-dialog", "aria-label": "Add a job" });
    els.viewer = h("dialog", { class: "ja-dialog ja-dialog-wide", "aria-label": "Source" });
    els.personDialog = h("dialog", { class: "ja-dialog", "aria-label": "Person" });
    els.stage = h("div", { class: "ja-stage" }, els.banner, els.notice, els.main);

    function navButton(item, cls) {
      const el = h(
        "button",
        {
          type: "button",
          class: cls,
          title: embedded ? null : item.label,
          "data-ja-key": "nav:" + item.view,
          onclick: function () {
            navigate({ view: item.view });
          },
        },
        embedded ? null : svg.icon(item.icon),
        h("span", { class: "ja-nav-label", text: item.label })
      );
      els.nav[item.view] = el;
      return el;
    }

    function narrowShell() {
      return !!(win.matchMedia && win.matchMedia("(max-width: 720px)").matches);
    }

    if (embedded) {
      els.tabs = h(
        "nav",
        { class: "ja-toptabs", "aria-label": "JobApps sections" },
        NAV.map(function (item) {
          return navButton(item, "ja-toptab");
        })
      );
      els.app = h("div", { class: "ja-app" }, els.tabs, els.stage, els.live, els.addDialog, els.viewer, els.personDialog);
    } else {
      ui.railCollapsed = stored("jobapps.rail") === "collapsed";
      els.crumb = h("strong", { class: "ja-crumb-page" });
      els.toggle = h(
        "button",
        {
          type: "button",
          class: "ja-rail-toggle",
          "aria-label": "Toggle navigation",
          "aria-controls": uid + "-rail",
          "data-ja-key": "rail-toggle",
          onclick: function () {
            if (narrowShell()) {
              ui.railOpen = !ui.railOpen;
            } else {
              ui.railCollapsed = !ui.railCollapsed;
              store("jobapps.rail", ui.railCollapsed ? "collapsed" : "open");
            }
            renderChrome();
          },
        },
        svg.icon("rail")
      );
      els.bar = h(
        "header",
        { class: "ja-bar" },
        els.toggle,
        svg.logo(),
        h("div", { class: "ja-identity" }, h("span", { class: "ja-identity-name", text: "JobApps" }), h("span", { class: "ja-identity-sub", text: "Hermes" })),
        h(
          "div",
          { class: "ja-crumbs" },
          h("span", { class: "ja-crumb", text: "Workspace" }),
          h("span", { class: "ja-crumb", "aria-hidden": "true", text: "/" }),
          els.crumb
        )
      );
      const railItems = [];
      NAV.forEach(function (item, index) {
        if (!index || NAV[index - 1].group !== item.group) {
          if (index) railItems.push(h("div", { class: "ja-rail-rule", "aria-hidden": "true" }));
          railItems.push(h("span", { class: "ja-rail-label", text: item.group }));
        }
        railItems.push(navButton(item, "ja-rail-item"));
      });
      els.rail = h("nav", { class: "ja-rail", id: uid + "-rail", "aria-label": "JobApps sections" }, h("div", { class: "ja-rail-inner" }, railItems));
      els.backdrop = h("button", {
        type: "button",
        class: "ja-rail-backdrop",
        "aria-label": "Close navigation",
        tabindex: "-1",
        onclick: function () {
          ui.railOpen = false;
          renderChrome();
        },
      });
      els.body = h("div", { class: "ja-body" }, els.rail, els.backdrop, els.stage);
      els.app = h("div", { class: "ja-app" }, els.bar, els.body, els.live, els.addDialog, els.viewer, els.personDialog);
    }
    root.appendChild(els.app);

    function pageLabel(view) {
      return (NAV.filter(function (item) {
        return item.view === view;
      })[0] || NAV[0]).label;
    }

    function renderChrome() {
      NAV.forEach(function (item) {
        if (item.view === ui.route.view) els.nav[item.view].setAttribute("aria-current", "page");
        else els.nav[item.view].removeAttribute("aria-current");
      });
      if (embedded) return;
      els.crumb.textContent = pageLabel(ui.route.view);
      els.body.className = "ja-body" + (ui.railCollapsed ? " is-collapsed" : "") + (ui.railOpen ? " is-rail-open" : "");
      els.toggle.setAttribute("aria-expanded", String(narrowShell() ? !!ui.railOpen : !ui.railCollapsed));
    }

    // ── Small pieces ───────────────────────────────────────────────────

    function today() {
      return (data.state && data.state.as_of) || localISODate();
    }

    function shortDate(iso) {
      return formatDate(iso, today());
    }

    /* A plain date. With `due`, a date before today takes the accent color. */
    function dateEl(iso, due, cls) {
      const info = dateInfo(iso, today());
      if (!info) return null;
      return h("span", { class: "ja-date" + (cls ? " " + cls : "") + (due && info.past ? " is-past" : ""), text: info.text });
    }

    function tag(text, tone) {
      return h("span", { class: "ja-tag ja-tone-" + (tone || "neutral"), text: text });
    }

    function empty() {
      return h("p", { class: "ja-empty", text: EMPTY });
    }

    function loading() {
      return h("p", { class: "ja-empty", role: "status", text: "Loading…" });
    }

    function btn(kind, label, onclick, opts) {
      const o = opts || {};
      const working = !!(o.key && busy[o.key]);
      let cls = kind === "quiet" ? "ja-quiet" : kind === "primary" ? "ja-btn ja-btn-primary" : "ja-btn";
      if (o.cls) cls += " " + o.cls;
      return h(
        "button",
        {
          type: o.submit ? "submit" : "button",
          class: cls,
          disabled: !!o.disabled,
          "aria-disabled": working ? "true" : null,
          "aria-label": o.label,
          "data-ja-key": o.key,
          "data-ja-busy": o.busyLabel,
          onclick: onclick,
        },
        o.icon ? svg.icon(o.icon) : null,
        working && o.busyLabel ? o.busyLabel : label
      );
    }

    function action(kind, label, key, fn, opts) {
      return btn(
        kind,
        label,
        function () {
          run(key, fn);
        },
        Object.assign({ key: key }, opts || {})
      );
    }

    function link(label, href, ariaLabel) {
      return h("a", { class: "ja-quiet", href: href, target: "_blank", rel: "noopener noreferrer", "aria-label": ariaLabel }, label);
    }

    function draft(key, fallback) {
      return hasOwn(ui.drafts, key) ? ui.drafts[key] : String(fallback == null ? "" : fallback);
    }

    function clearDrafts(name) {
      const family = name.slice(-1) === ":";
      Object.keys(ui.drafts).forEach(function (key) {
        if (key === name || (family && key.indexOf(name) === 0)) delete ui.drafts[key];
      });
    }

    function field(key, opts) {
      const o = opts || {};
      const saved = String(o.value == null ? "" : o.value);
      const el = h(o.multiline ? "textarea" : "input", {
        class: "ja-input" + (o.multiline ? " ja-textarea" : "") + (o.cls ? " " + o.cls : ""),
        type: o.multiline ? null : o.type || "text",
        rows: o.multiline ? o.rows || 4 : null,
        placeholder: o.placeholder,
        "aria-label": o.label,
        "data-ja-key": key,
        autocomplete: "off",
        required: o.required,
      });
      el.value = draft(key, saved);
      el.addEventListener("input", function () {
        if (el.value === saved) delete ui.drafts[key];
        else ui.drafts[key] = el.value;
      });
      return el;
    }

    function choice(key, items, saved, label) {
      const el = h(
        "select",
        { class: "ja-input ja-select", "aria-label": label, "data-ja-key": key },
        items.map(function (item) {
          return h("option", { value: item.value, selected: item.value === draft(key, saved) }, item.label);
        })
      );
      el.addEventListener("change", function () {
        if (el.value === saved) delete ui.drafts[key];
        else ui.drafts[key] = el.value;
      });
      return el;
    }

    function labelled(text, control, cls) {
      return h("label", { class: "ja-field" + (cls ? " " + cls : "") }, h("span", { class: "ja-label", text: text }), control);
    }

    function announce(text) {
      els.live.textContent = "";
      els.live.textContent = text;
    }

    function flash(el, text) {
      const original = el.textContent;
      el.textContent = text;
      announce(text);
      win.setTimeout(function () {
        if (el.textContent === text) el.textContent = original;
      }, 1600);
    }

    function legacyCopy(text) {
      return new Promise(function (resolve, reject) {
        const area = h("textarea", { class: "ja-sr", "aria-hidden": "true", tabindex: "-1" });
        area.value = text;
        els.app.appendChild(area);
        area.select();
        let ok = false;
        try {
          ok = doc.execCommand("copy");
        } catch (err) {
          ok = false;
        }
        els.app.removeChild(area);
        if (ok) resolve();
        else reject(new Error("Copy failed"));
      });
    }

    function copyText(text) {
      const clipboard = win.navigator && win.navigator.clipboard;
      if (clipboard && clipboard.writeText) {
        return clipboard.writeText(text).catch(function () {
          return legacyCopy(text);
        });
      }
      return legacyCopy(text);
    }

    function copyInto(el, text) {
      copyText(text).then(
        function () {
          flash(el, "Copied");
        },
        function () {
          flash(el, "Copy failed");
        }
      );
    }

    function copyButton(label, text, key, ariaLabel) {
      const el = btn(
        "quiet",
        label,
        function () {
          copyInto(el, text);
        },
        { key: key, label: ariaLabel }
      );
      return el;
    }

    /* A quiet link that opens a small list of prompts; choosing one copies it. */
    function promptMenu(key, label, prompts) {
      const menu = h(
        "div",
        { class: "ja-menu", role: "menu", "aria-label": label, hidden: true },
        prompts.map(function (prompt) {
          return h(
            "button",
            {
              type: "button",
              class: "ja-menu-item",
              role: "menuitem",
              tabindex: "-1",
              onclick: function () {
                setOpen(false);
                trigger.focus();
                copyInto(trigger, prompt.text);
              },
            },
            prompt.label
          );
        })
      );
      const trigger = btn(
        "quiet",
        label,
        function () {
          const opening = menu.hidden;
          setOpen(opening);
          if (opening && menu.firstChild) menu.firstChild.focus();
        },
        { key: "menu:" + key }
      );
      trigger.setAttribute("aria-haspopup", "menu");
      trigger.setAttribute("aria-expanded", "false");
      const wrap = h(
        "span",
        {
          class: "ja-menu-wrap",
          onkeydown: function (event) {
            if (menu.hidden) return;
            const items = menu.children;
            const at = Array.prototype.indexOf.call(items, doc.activeElement);
            if (event.key === "Escape") {
              setOpen(false);
              trigger.focus();
            } else if (event.key === "ArrowDown" || event.key === "ArrowUp") {
              event.preventDefault();
              const step = event.key === "ArrowDown" ? 1 : -1;
              items[(at + step + items.length) % items.length].focus();
            }
          },
        },
        trigger,
        menu
      );
      function setOpen(open) {
        menu.hidden = !open;
        trigger.setAttribute("aria-expanded", String(open));
        if (open) {
          if (openMenu && openMenu.wrap !== wrap) openMenu.close();
          openMenu = {
            wrap: wrap,
            close: function () {
              setOpen(false);
            },
          };
        } else if (openMenu && openMenu.wrap === wrap) {
          openMenu = null;
        }
      }
      return wrap;
    }

    /* `+ Title … count`: a real button that remembers whether it is open. */
    function disclosure(key, title, count, build, opts) {
      const o = opts || {};
      const open = hasOwn(ui.open, key) ? !!ui.open[key] : !!o.open;
      return h(
        "section",
        { class: "ja-disc" + (o.small ? " ja-disc-small" : "") + (open ? " is-open" : "") },
        h(
          "button",
          {
            type: "button",
            class: "ja-disc-head",
            "aria-expanded": String(open),
            "data-ja-key": "disc:" + key,
            onclick: function () {
              ui.open[key] = !open;
              render();
              focusKey("disc:" + key, els.app);
            },
          },
          h("span", { class: "ja-disc-sign", "aria-hidden": "true", text: open ? "−" : "+" }),
          h("span", { class: "ja-disc-title", text: title }),
          count != null && count !== "" ? h("span", { class: "ja-disc-count", text: String(count) }) : null
        ),
        open ? h("div", { class: "ja-disc-body" }, build()) : null
      );
    }

    function chips(items, active, pick, label) {
      return h(
        "div",
        { class: "ja-chips", role: "group", "aria-label": label },
        items.map(function (item) {
          return h(
            "button",
            {
              type: "button",
              class: "ja-chip",
              "aria-pressed": String(item.value === active),
              "data-ja-key": "chip:" + label + ":" + item.value,
              onclick: function () {
                pick(item.value);
                focusKey("chip:" + label + ":" + item.value, els.app);
              },
            },
            item.label
          );
        })
      );
    }

    function metrics(items, onpick) {
      if (onpick) {
        return h(
          "div",
          { class: "ja-metrics", role: "group", "aria-label": "Jobs by state" },
          items.map(function (item) {
            return h(
              "button",
              {
                type: "button",
                class: "ja-metric",
                "data-ja-key": "metric:" + item.key,
                onclick: function () {
                  onpick(item);
                },
              },
              h("span", { class: "ja-metric-value", text: String(item.value) }),
              h("span", { class: "ja-metric-label", text: item.label })
            );
          })
        );
      }
      return h(
        "dl",
        { class: "ja-metrics" },
        items.map(function (item) {
          return h("div", { class: "ja-metric" }, h("dt", { class: "ja-metric-label", text: item.label }), h("dd", { class: "ja-metric-value", text: String(item.value) }));
        })
      );
    }

    function pageHead(title, opts) {
      const o = opts || {};
      return h(
        "header",
        { class: "ja-page-head" },
        h(
          "div",
          { class: "ja-page-head-main" },
          o.eyebrow ? h("span", { class: "ja-eyebrow", text: o.eyebrow }) : null,
          h("h1", { class: "ja-title", text: title }),
          (o.lines || []).map(function (line) {
            return h("p", { class: "ja-meta", text: line });
          })
        ),
        o.action || null
      );
    }

    /* A quiet two-line row that opens something. */
    function quietRow(key, onclick, primary, meta, right) {
      return h(
        "li",
        null,
        h(
          "button",
          { type: "button", class: "ja-qrow", "data-ja-key": key, onclick: onclick },
          h("span", { class: "ja-qrow-main" }, h("strong", { text: primary }), meta ? h("span", { class: "ja-meta", text: meta }) : null),
          right || null
        )
      );
    }

    // ── Requests ───────────────────────────────────────────────────────

    function setError(message, retry, source) {
      error = { message: message, retry: retry, source: source || "action" };
    }

    /* A running action's button is marked aria-disabled, never disabled: a
       disabled button drops keyboard focus, and repeats are ignored here. */
    function run(key, fn, onError) {
      if (busy[key]) return;
      busy[key] = true;
      const trigger = findByKey(els.app, key);
      if (trigger && trigger.tagName === "BUTTON") {
        trigger.setAttribute("aria-disabled", "true");
        if (trigger.getAttribute("data-ja-busy")) trigger.textContent = trigger.getAttribute("data-ja-busy");
      }
      Promise.resolve()
        .then(fn)
        .then(
          function () {
            if (error && error.source === "action") error = null;
          },
          function (err) {
            if (onError) onError(err);
            else
              setError(messageOf(err), function () {
                run(key, fn, onError);
              });
          }
        )
        .then(function () {
          delete busy[key];
          if (alive) render();
        });
    }

    function post(route, body) {
      return api.post(route, body).then(function (result) {
        return refresh().then(function () {
          return result;
        });
      });
    }

    function loadState() {
      return api.get("/state").then(
        function (state) {
          const sig = JSON.stringify(state);
          let changed = sig !== data.sig;
          data.state = state;
          data.sig = sig;
          if (error && error.source === "refresh") {
            error = null;
            changed = true;
          }
          return changed;
        },
        function (err) {
          setError(messageOf(err), refresh, "refresh");
          return true;
        }
      );
    }

    function loadJob(id) {
      return api.get("/jobs/" + encodeURIComponent(id)).then(
        function (detail) {
          const sig = JSON.stringify(detail);
          const previous = data.jobs[id];
          data.jobs[id] = { detail: detail, sig: sig, error: "" };
          return !previous || previous.sig !== sig || !!previous.error;
        },
        function (err) {
          const previous = data.jobs[id];
          data.jobs[id] = { detail: null, sig: "", error: messageOf(err) };
          return !previous || previous.error !== data.jobs[id].error || !!previous.detail;
        }
      );
    }

    function loadEvidence() {
      return api.get("/evidence").then(
        function (payload) {
          const list = (payload && payload.evidence) || [];
          const sig = JSON.stringify(list);
          const changed = sig !== data.evidenceSig || data.evidence === null || !!data.evidenceError;
          data.evidence = list;
          data.evidenceSig = sig;
          data.evidenceError = "";
          return changed;
        },
        function (err) {
          data.evidenceError = messageOf(err);
          if (data.evidence === null) data.evidence = [];
          return true;
        }
      );
    }

    function loadDoc(path) {
      return api.get("/doc", { path: path }).then(
        function (payload) {
          const sig = JSON.stringify(payload);
          const previous = data.docs[path];
          data.docs[path] = { doc: payload, sig: sig, error: "" };
          return !previous || previous.sig !== sig;
        },
        function (err) {
          const previous = data.docs[path];
          data.docs[path] = { doc: null, sig: "", error: messageOf(err) };
          return !previous || previous.error !== data.docs[path].error || !!previous.doc;
        }
      );
    }

    function loadStats() {
      return api.get("/stats").then(
        function (payload) {
          const sig = JSON.stringify(payload);
          const previous = data.stats;
          data.stats = { stats: (payload && payload.stats) || {}, sig: sig, error: "" };
          return !previous || previous.sig !== sig;
        },
        function (err) {
          const previous = data.stats;
          data.stats = { stats: null, sig: "", error: messageOf(err) };
          return !previous || previous.error !== data.stats.error || !!previous.stats;
        }
      );
    }

    /* Why a person matters lives in their file, not in /state: read it once
       per person, and again after that person is saved. */
    function loadWhy() {
      const missing = ((data.state && data.state.people) || []).filter(function (person) {
        return !hasOwn(data.why, person.person);
      });
      if (!missing.length) return Promise.resolve(false);
      return Promise.all(
        missing.map(function (person) {
          return api.get("/doc", { path: "people/" + person.person + ".md" }).then(
            function (payload) {
              data.why[person.person] = sectionText(payload && payload.body, "Why");
            },
            function () {
              data.why[person.person] = "";
            }
          );
        })
      ).then(function () {
        return true;
      });
    }

    function libraryPath() {
      return ui.route.path || PROFILE_DOCS[0].path;
    }

    /* The job shown beside the list: the one in the address, else the one
       opened last, else the first in the list. */
    function shownJob() {
      if (ui.route.job) return ui.route.job;
      const jobs = (data.state && data.state.jobs) || [];
      const known = jobs.some(function (job) {
        return job.job === ui.lastJob;
      });
      if (known) return ui.lastJob;
      const groups = groupJobs(jobs, "", ui.jobs.filter);
      return groups.length ? groups[0].jobs[0].job : "";
    }

    function loadAll() {
      const view = ui.route.view;
      return loadState().then(function (changed) {
        const tasks = [];
        if (view === "jobs" && shownJob()) tasks.push(loadJob(shownJob()));
        if (view === "people") tasks.push(loadWhy());
        if (view === "insights") tasks.push(loadStats());
        if (view === "library") {
          tasks.push(loadEvidence());
          tasks.push(loadDoc(libraryPath()));
        }
        return Promise.all(tasks).then(function (flags) {
          return changed || flags.some(Boolean);
        });
      });
    }

    function refresh(opts) {
      const background = !!(opts && opts.background);
      if (!alive) return Promise.resolve();
      if (inflight) {
        if (!pending) {
          pending = inflight.then(function () {
            pending = null;
            return refresh(opts);
          });
        }
        return pending;
      }
      lastRefresh = Date.now();
      inflight = loadAll().then(function (changed) {
        inflight = null;
        if (!alive || !changed) return;
        if (background && isEditing()) deferred = true;
        else render();
      });
      return inflight;
    }

    function backgroundRefresh() {
      if (!alive || doc.hidden || Date.now() - lastRefresh < 2000) return;
      refresh({ background: true });
    }

    function isEditing() {
      const active = doc.activeElement;
      return !!active && els.main.contains(active) && /^(INPUT|TEXTAREA|SELECT)$/.test(active.tagName);
    }

    // ── Navigation ─────────────────────────────────────────────────────

    function scroller() {
      let el = root.parentElement;
      while (el && el !== doc.body && el !== doc.documentElement) {
        const style = win.getComputedStyle ? win.getComputedStyle(el) : null;
        if (style && /(auto|scroll)/.test(style.overflowY) && el.scrollHeight > el.clientHeight) return el;
        el = el.parentElement;
      }
      return null;
    }

    function getScroll() {
      const el = scroller();
      return el ? el.scrollTop : win.pageYOffset || 0;
    }

    function setScroll(value) {
      const el = scroller();
      if (el) el.scrollTop = value;
      else if (win.scrollTo) win.scrollTo(0, value);
    }

    /* Below this width the job list and the job are separate panes. */
    function singlePane() {
      const width = els.stage.clientWidth;
      return !!width && width <= 900;
    }

    function sameRoute(a, b) {
      return a.view === b.view && (a.job || "") === (b.job || "") && (a.path || "") === (b.path || "");
    }

    function setRoute(route) {
      const previous = ui.route;
      if (sameRoute(previous, route)) {
        ui.route = route;
        render();
        return;
      }
      const jobChange = route.view === "jobs" && previous.view === "jobs";
      const single = jobChange && singlePane();
      if (previous.view !== route.view || (single && !previous.job)) ui.scroll[previous.view] = getScroll();
      if (previous.job && previous.job !== route.job) delete ui.blocked[previous.job];
      if (route.job) ui.lastJob = route.job;
      ui.route = route;
      ui.railOpen = false;
      notice = null;
      deferred = false;
      render();
      if (previous.view !== route.view) setScroll(ui.scroll[route.view] || 0);
      else if (jobChange) setScroll(single && !route.job ? ui.scroll.jobs || 0 : 0);
      refresh();
    }

    function navigate(route) {
      setRoute(route);
      if (embedded) return;
      const hash = formatHash(ui.route);
      if (win.location.hash !== hash) win.location.hash = hash;
    }

    function openJob(id) {
      navigate({ view: "jobs", job: id });
    }

    // ── Rendering ──────────────────────────────────────────────────────

    function findByKey(container, key) {
      const nodes = container.querySelectorAll("[data-ja-key]");
      for (let i = 0; i < nodes.length; i += 1) {
        if (nodes[i].getAttribute("data-ja-key") === key) return nodes[i];
      }
      return null;
    }

    function captureFocus(container) {
      const active = doc.activeElement;
      if (!active || active === container || !container.contains(active)) return null;
      const info = { key: active.getAttribute("data-ja-key"), start: null, end: null };
      try {
        if (typeof active.selectionStart === "number") {
          info.start = active.selectionStart;
          info.end = active.selectionEnd;
        }
      } catch (err) {
        info.start = null;
      }
      return info;
    }

    function restoreFocus(container, info) {
      if (!info) return;
      let target = info.key ? findByKey(container, info.key) : null;
      if (!target || target.disabled) target = container;
      if (target === doc.activeElement) return;
      try {
        target.focus({ preventScroll: true });
        if (info.start !== null && target !== container && target.setSelectionRange) {
          target.setSelectionRange(info.start, info.end);
        }
      } catch (err) {
        /* focus is a convenience; never let it break a render */
      }
    }

    function focusKey(key, container) {
      const target = findByKey(container || els.main, key);
      if (target) target.focus();
    }

    function replaceContent(container, node) {
      const focus = captureFocus(container);
      const page = getScroll();
      const inner = {};
      const scrolled = container.querySelectorAll("[data-ja-scroll]");
      for (let i = 0; i < scrolled.length; i += 1) {
        inner[scrolled[i].getAttribute("data-ja-scroll")] = [scrolled[i].scrollTop, scrolled[i].scrollLeft];
      }
      container.style.minHeight = container.offsetHeight + "px";
      clear(container);
      container.appendChild(node);
      container.style.minHeight = "";
      const restored = container.querySelectorAll("[data-ja-scroll]");
      for (let j = 0; j < restored.length; j += 1) {
        const saved = inner[restored[j].getAttribute("data-ja-scroll")];
        if (saved) {
          restored[j].scrollTop = saved[0];
          restored[j].scrollLeft = saved[1];
        }
      }
      if (getScroll() !== page) setScroll(page);
      restoreFocus(container, focus);
    }

    function render() {
      if (!alive) return;
      deferred = false;
      openMenu = null;
      renderChrome();
      renderBanner();
      renderNotice();
      replaceContent(els.main, buildView());
    }

    function renderBanner() {
      clear(els.banner);
      if (!error) return;
      const current = error;
      els.banner.appendChild(
        h(
          "div",
          { class: "ja-notice ja-notice-error", role: "alert" },
          h("p", { class: "ja-notice-text", text: current.message }),
          current.retry
            ? btn("quiet", "Retry", function () {
                error = null;
                renderBanner();
                current.retry();
              })
            : null,
          btn("quiet", "Dismiss", function () {
            error = null;
            renderBanner();
          })
        )
      );
    }

    function renderNotice() {
      clear(els.notice);
      if (!notice) return;
      const current = notice;
      els.notice.appendChild(
        h(
          "div",
          { class: "ja-notice", role: "status" },
          h("p", { class: "ja-notice-text", text: current.text }),
          current.href ? link(current.linkLabel || "Open", current.href) : null,
          btn("quiet", "Dismiss", function () {
            notice = null;
            renderNotice();
          })
        )
      );
    }

    function buildView() {
      if (!data.state) {
        return h("div", { class: "ja-view" }, error ? h("p", { class: "ja-empty", text: "The workspace could not be loaded" }) : loading());
      }
      const view = ui.route.view;
      if (view === "jobs") return viewJobs();
      if (view === "people") return viewPeople();
      if (view === "leads") return viewLeads();
      if (view === "insights") return viewInsights();
      if (view === "library") return viewLibrary();
      return viewOverview();
    }

    // ── Overview ───────────────────────────────────────────────────────

    function jobLine(job) {
      return [job.company, job.title].filter(Boolean).join(" · ");
    }

    function viewOverview() {
      const state = data.state;
      const attention = state.attention || {};
      const jobs = state.jobs || [];
      const setup = (state.setup || []).slice();
      if (state.ready === false) setup.unshift("No workspace at " + state.workspace);

      const view = h(
        "div",
        { class: "ja-view" },
        pageHead("Overview", {
          eyebrow: longDate(state.as_of),
          lines: setup,
          action: btn("outline", "Add a job", openAddJob, { key: "add-open", icon: "plus" }),
        }),
        metrics(overviewCounts(state.counts), function (item) {
          ui.jobs.filter = item.key;
          ui.jobs.query = "";
          ui.lastJob = "";
          navigate({ view: "jobs" });
        })
      );

      const focus = continueJob(jobs);
      const queue = upNext(attention.due, UP_NEXT_LIMIT, today());
      const dueTotal = attention.due_total != null ? attention.due_total : (attention.due || []).length;
      view.appendChild(
        h(
          "div",
          { class: "ja-summary" },
          h(
            "section",
            { class: "ja-focus", "aria-label": "Continue with" },
            h(
              "div",
              { class: "ja-focus-head" },
              h("span", { class: "ja-eyebrow ja-eyebrow-gold", text: "Continue with" }),
              focus ? tag(stageLabel(focus.stage), stageTone(focus.stage)) : null
            ),
            focus
              ? [
                  h("p", { class: "ja-focus-company", text: focus.company || "" }),
                  h("h2", { class: "ja-focus-title", text: focus.title || "" }),
                  focus.location ? h("p", { class: "ja-focus-place", text: focus.location }) : null,
                  focus.next_action
                    ? h("div", { class: "ja-next" }, h("span", { class: "ja-eyebrow", text: "Next step" }), h("p", { class: "ja-next-text", text: focus.next_action }))
                    : null,
                  h(
                    "div",
                    { class: "ja-focus-actions" },
                    btn(
                      "primary",
                      "Continue",
                      function () {
                        openJob(focus.job);
                      },
                      { key: "continue" }
                    ),
                    focus.created_on ? h("span", { class: "ja-meta", text: "added " + shortDate(focus.created_on) }) : null
                  ),
                ]
              : empty()
          ),
          h(
            "section",
            { class: "ja-queue", "aria-label": "Up next" },
            h("div", { class: "ja-queue-head" }, h("h2", { class: "ja-h2", text: "Up next" }), h("span", { class: "ja-meta", text: String(dueTotal) })),
            queue.length
              ? h(
                  "ul",
                  { class: "ja-plain" },
                  queue.map(function (item) {
                    return quietRow(
                      "next:" + item.job,
                      function () {
                        openJob(item.job);
                      },
                      item.next_action || item.title || "",
                      item.next_action ? jobLine(item) : item.company || "",
                      dateEl(item.due, true)
                    );
                  })
                )
              : empty(),
            btn(
              "quiet",
              "All jobs",
              function () {
                ui.jobs.filter = "";
                navigate({ view: "jobs" });
              },
              { key: "all-jobs" }
            )
          )
        )
      );

      const ready = attention.ready || [];
      const waiting = waitingJobs(jobs);
      const people = attention.people || [];
      const leads = attention.leads || [];
      const total = function (key, list) {
        return attention[key + "_total"] != null ? attention[key + "_total"] : list.length;
      };
      const plain = function (rows) {
        return h("ul", { class: "ja-plain" }, rows);
      };
      const lists = h("div", { class: "ja-discs" });
      if (ready.length) {
        lists.appendChild(
          disclosure("ov:ready", "Ready to send", total("ready", ready), function () {
            return plain(
              ready.map(function (job) {
                return quietRow(
                  "ready:" + job.job,
                  function () {
                    openJob(job.job);
                  },
                  job.title || "",
                  [job.company, job.location].filter(Boolean).join(" · "),
                  dateEl(job.due, true)
                );
              })
            );
          })
        );
      }
      if (waiting.length) {
        lists.appendChild(
          disclosure("ov:waiting", "Waiting to hear back", waiting.length, function () {
            const all = !!ui.open["ov:waiting:all"];
            const shown = all ? waiting : waiting.slice(0, WAITING_LIMIT);
            return [
              plain(
                shown.map(function (job) {
                  return quietRow(
                    "waiting:" + job.job,
                    function () {
                      openJob(job.job);
                    },
                    job.title || "",
                    job.company || "",
                    dateEl(job.applied_on)
                  );
                })
              ),
              waiting.length > shown.length
                ? btn(
                    "quiet",
                    "Show all " + waiting.length,
                    function () {
                      ui.open["ov:waiting:all"] = true;
                      render();
                      focusKey("waiting:" + waiting[WAITING_LIMIT].job);
                    },
                    { key: "waiting-all" }
                  )
                : null,
            ];
          })
        );
      }
      if (people.length) {
        lists.appendChild(
          disclosure("ov:people", "People to reach", total("people", people), function () {
            return plain(
              people.map(function (person) {
                return quietRow(
                  "reach:" + person.person,
                  function () {
                    navigate({ view: "people" });
                  },
                  person.name,
                  [person.role, person.company].filter(Boolean).join(" · "),
                  dateEl(person.next_touch, true)
                );
              })
            );
          })
        );
      }
      if (leads.length) {
        lists.appendChild(
          disclosure("ov:leads", "New leads", total("leads", leads), function () {
            return plain(
              leads.map(function (lead) {
                return quietRow(
                  "newlead:" + lead.lead,
                  function () {
                    navigate({ view: "leads" });
                  },
                  lead.title || "",
                  [lead.company, lead.location].filter(Boolean).join(" · "),
                  dateEl(lead.found_on)
                );
              })
            );
          })
        );
      }
      view.appendChild(lists);
      return view;
    }

    // ── Jobs ───────────────────────────────────────────────────────────

    function afterTrack(result, jobId, wanted) {
      if (result && result.ok === false && result.blocked) {
        ui.blocked[jobId] = { status: wanted || "ready", files: result.blocked };
        return;
      }
      delete ui.blocked[jobId];
      if (result && (result.ok === false || result.ambiguous)) notice = { text: "Not saved" };
    }

    function ensureJob(id) {
      if (!id || data.jobs[id] || fetching[id]) return;
      fetching[id] = true;
      loadJob(id).then(function () {
        delete fetching[id];
        if (alive) render();
      });
    }

    function viewJobs() {
      const j = ui.jobs;
      const jobs = data.state.jobs || [];
      const selected = shownJob();
      /* Alone on a narrow stage, the list marks only a job that was actually read. */
      const marked = singlePane() && !ui.route.job && selected !== ui.lastJob ? "" : selected;
      const list = h("div", { class: "ja-jobs-list", "data-ja-scroll": "jobs-list" });

      function jobRow(job) {
        return h(
          "li",
          null,
          h(
            "button",
            {
              type: "button",
              class: "ja-jobrow",
              "aria-current": job.job === marked ? "true" : null,
              "data-ja-key": "job:" + job.job,
              onclick: function () {
                openJob(job.job);
              },
            },
            h("span", { class: "ja-jobrow-company", text: job.company || "" }),
            h("span", { class: "ja-jobrow-title", text: job.title || "" }),
            h("span", { class: "ja-meta", text: jobRowMeta(job, today()) })
          )
        );
      }

      function fill() {
        const groups = groupJobs(jobs, j.query, j.filter);
        clear(list);
        if (!groups.length) {
          list.appendChild(empty());
          return;
        }
        groups.forEach(function (group) {
          const shown = j.showAll[group.stage] ? group.jobs : group.jobs.slice(0, GROUP_LIMIT);
          list.appendChild(
            h(
              "section",
              { class: "ja-jobgroup", "aria-label": group.label },
              h("h2", { class: "ja-jobgroup-head" }, h("span", { text: group.label }), h("span", { class: "ja-jobgroup-count", text: String(group.jobs.length) })),
              h("ul", { class: "ja-plain" }, shown.map(jobRow)),
              group.jobs.length > shown.length
                ? btn(
                    "quiet",
                    "Show all " + group.jobs.length,
                    function () {
                      j.showAll[group.stage] = true;
                      fill();
                      focusKey("job:" + group.jobs[GROUP_LIMIT].job);
                    },
                    { key: "group-all:" + group.stage }
                  )
                : null
            )
          );
        });
      }

      const search = h("input", {
        type: "search",
        class: "ja-input ja-search",
        placeholder: "Search company, role or location",
        "aria-label": "Search jobs",
        "data-ja-key": "jobs:query",
        autocomplete: "off",
      });
      search.value = j.query;
      search.addEventListener("input", function () {
        j.query = search.value;
        fill();
      });
      fill();
      ensureJob(selected);

      const filters = [{ value: "", label: "All" }].concat(
        JOB_GROUPS.map(function (group) {
          return { value: group.key, label: group.label };
        })
      );
      return h(
        "div",
        { class: "ja-view ja-view-jobs" + (ui.route.job ? " has-job" : "") },
        pageHead("Jobs"),
        h(
          "div",
          { class: "ja-toolbar" },
          search,
          chips(
            filters,
            j.filter,
            function (value) {
              j.filter = value;
              if (!ui.route.job) ui.lastJob = "";
              render();
            },
            "Filter jobs"
          )
        ),
        h("div", { class: "ja-jobs" }, list, jobDetail(selected))
      );
    }

    function saveNext(detail, text, due) {
      const job = detail.job;
      const body = nextActionBody(job, text, due);
      return (body ? post(trackRoute(job.job), body) : Promise.resolve()).then(function () {
        clearDrafts("next:" + job.job);
        clearDrafts("due:" + job.job);
        delete ui.editing["next:" + job.job];
      });
    }

    function openPdf(path) {
      let tab = null;
      try {
        tab = win.open("", "_blank");
        if (tab) tab.opener = null;
      } catch (err) {
        tab = null;
      }
      run(
        "pdf:" + path,
        function () {
          return api.fileBlobUrl(path).then(function (url) {
            if (blobUrls[path]) global.URL.revokeObjectURL(blobUrls[path]);
            blobUrls[path] = url;
            if (tab && !tab.closed) tab.location.href = url;
            else notice = { text: "The preview is ready", href: url, linkLabel: "Open" };
          });
        },
        function (err) {
          if (tab && !tab.closed) tab.close();
          setError(messageOf(err), function () {
            openPdf(path);
          });
        }
      );
    }

    function markdown(text) {
      const box = h("div", { class: "ja-md" });
      box.appendChild(renderMarkdown(text, doc));
      return box;
    }

    function materialRow(material) {
      const path = material.path;
      const names = materialLabel(material);
      const state = materialState(material.qa);
      const canCheck = CHECKABLE_FORMATS.indexOf(material.format) !== -1 && hasOwn(MATERIAL_LABELS, material.kind);
      const isSource = CHECKABLE_FORMATS.indexOf(material.format) !== -1;
      const result = ui.checks[path];
      const found = result ? checkFindings(result) : null;
      return h(
        "li",
        { class: "ja-mat" },
        h(
          "div",
          { class: "ja-mat-row" },
          h(
            "div",
            { class: "ja-mat-main" },
            h("strong", { class: "ja-mat-name", text: names.label }),
            names.file ? h("span", { class: "ja-meta", text: names.file }) : null,
            material.updated_on ? h("span", { class: "ja-meta", text: "Updated " + shortDate(material.updated_on) }) : null
          ),
          state ? h("span", { class: "ja-mat-state", text: state }) : null,
          h(
            "div",
            { class: "ja-links" },
            material.pdf
              ? btn(
                  "quiet",
                  "Preview",
                  function () {
                    openPdf(material.pdf);
                  },
                  { key: "pdf:" + material.pdf, busyLabel: "Opening…", label: "Preview " + material.name }
                )
              : null,
            isSource
              ? btn(
                  "quiet",
                  "Source",
                  function () {
                    openViewer(path, material.name);
                  },
                  { key: "source:" + path, label: "Source of " + material.name }
                )
              : null,
            canCheck
              ? action(
                  "quiet",
                  "Check",
                  "check:" + path,
                  function () {
                    return post("/check", { path: path }).then(function (answer) {
                      ui.checks[path] = answer;
                      ui.open["found:" + path] = true;
                    });
                  },
                  { busyLabel: "Checking…", label: "Check " + material.name }
                )
              : null
          )
        ),
        found
          ? disclosure(
              "found:" + path,
              "Findings",
              found.items.length + found.more,
              function () {
                if (!found.items.length) return h("p", { class: "ja-meta", text: "None" });
                return [
                  h(
                    "ul",
                    { class: "ja-finding-list" },
                    found.items.map(function (item) {
                      return h(
                        "li",
                        null,
                        h("strong", { text: item.rule }),
                        item.excerpt ? h("q", { class: "ja-quote", text: item.excerpt }) : null,
                        null
                      );
                    })
                  ),
                  found.more ? h("p", { class: "ja-meta", text: "+" + found.more + " more" }) : null,
                ];
              },
              { small: true, open: true }
            )
          : null
      );
    }

    function jobDetail(id) {
      const entry = id ? data.jobs[id] : null;
      const back = btn(
        "quiet",
        "All jobs",
        function () {
          navigate({ view: "jobs" });
        },
        { key: "jobs-back", cls: "ja-back" }
      );
      const shell = function () {
        const node = h("article", { class: "ja-detail", "aria-label": "Job" }, back);
        for (let i = 0; i < arguments.length; i += 1) {
          [].concat(arguments[i]).forEach(function (child) {
            if (child) node.appendChild(child);
          });
        }
        return node;
      };
      if (!id) return shell(empty());
      if (!entry || (!entry.detail && !entry.error)) return shell(loading());
      if (!entry.detail) {
        return shell(
          h("p", { class: "ja-line", role: "alert" }, entry.error + " "),
          btn("quiet", "Retry", function () {
            delete data.jobs[id];
            render();
          })
        );
      }

      const detail = entry.detail;
      const job = detail.job;
      const sections = detail.sections || {};
      const route = trackRoute(id);
      const href = safeHref(job.url);
      const has = function (name) {
        return !!String(sections[name] || "").trim();
      };

      const stage = h(
        "select",
        { class: "ja-input ja-select", "data-ja-key": "stage:" + id },
        STAGES.map(function (name) {
          return h("option", { value: name, selected: name === job.stage }, stageLabel(name));
        })
      );
      stage.addEventListener("change", function () {
        const wanted = stage.value;
        if (wanted === job.stage) return;
        run("stage:" + id, function () {
          return post(route, { status: wanted }).then(function (result) {
            afterTrack(result, id, wanted);
          });
        });
      });

      const blocked = ui.blocked[id];
      const blockedLine = blocked
        ? h(
            "p",
            { class: "ja-line", role: "status" },
            "Not marked ready: " +
              blocked.files
                .map(function (file) {
                  return file.name + " (" + (materialState(file.qa) || "Not checked").toLowerCase() + ")";
                })
                .join(", ") +
              " ",
            action("quiet", "Mark ready anyway", "force:" + id, function () {
              return post(route, { status: "ready", force: true }).then(function (result) {
                afterTrack(result, id, "ready");
              });
            })
          )
        : null;

      const nextKey = "next:" + id;
      const dueKey = "due:" + id;
      const editingNext = !!ui.editing[nextKey];
      const nextBlock = h(
        "section",
        { class: "ja-block" },
        h("h3", { class: "ja-label", text: "Next step" }),
        editingNext
          ? h(
              "form",
              {
                class: "ja-form-row",
                onsubmit: function (event) {
                  event.preventDefault();
                  run("next-save:" + id, function () {
                    return saveNext(detail, draft(nextKey, job.next_action).trim(), draft(dueKey, job.due));
                  });
                },
              },
              field(nextKey, { value: job.next_action, label: "Next step", placeholder: "Next step", cls: "ja-grow" }),
              field(dueKey, { type: "date", value: job.due, label: "Date" }),
              btn("outline", "Save", null, { submit: true, key: "next-save:" + id, busyLabel: "Saving…" }),
              btn(
                "quiet",
                "Cancel",
                function () {
                  delete ui.editing[nextKey];
                  clearDrafts(nextKey);
                  clearDrafts(dueKey);
                  render();
                  focusKey("next-edit:" + id);
                },
                { key: "next-cancel:" + id }
              )
            )
          : [
              h("p", { class: "ja-next-text" + (job.next_action ? "" : " is-none"), text: job.next_action || "None" }),
              dateEl(job.due, true, "ja-next-date"),
            ],
        h(
          "div",
          { class: "ja-links" },
          editingNext
            ? null
            : btn(
                "quiet",
                "Edit",
                function () {
                  ui.editing[nextKey] = true;
                  render();
                  focusKey(nextKey);
                },
                { key: "next-edit:" + id, label: "Edit the next step" }
              ),
          promptMenu("prompts:" + id, "Copy Hermes prompt", jobPrompts(job))
        )
      );

      const materials = detail.materials || [];
      const people = detail.people || [];
      const discs = [];
      if (has("posting")) {
        discs.push(
          disclosure("job:posting", "Posting", null, function () {
            return markdown(sections.posting);
          })
        );
      }
      const parts = [
        ["assessment", ""],
        ["strategy", "Strategy"],
        ["requirements", "Requirements"],
        ["application_questions", "Application questions"],
      ].filter(function (part) {
        return has(part[0]);
      });
      if (parts.length) {
        discs.push(
          disclosure("job:assessment", "Assessment", null, function () {
            return parts.map(function (part) {
              return [part[1] ? h("h4", { class: "ja-eyebrow ja-sub", text: part[1] }) : null, markdown(sections[part[0]])];
            });
          })
        );
      }
      if (has("research")) {
        discs.push(
          disclosure("job:research", "Research", null, function () {
            return markdown(sections.research);
          })
        );
      }
      const notesKey = "notes:" + id;
      discs.push(
        disclosure("job:notes", "Notes", null, function () {
          const saved = String(sections.notes || "");
          if (ui.editing[notesKey]) {
            return h(
              "form",
              {
                class: "ja-form",
                onsubmit: function (event) {
                  event.preventDefault();
                  run("notes-save:" + id, function () {
                    return post("/jobs/" + encodeURIComponent(id) + "/notes", { text: draft(notesKey, saved) }).then(function () {
                      clearDrafts(notesKey);
                      delete ui.editing[notesKey];
                    });
                  });
                },
              },
              field(notesKey, { multiline: true, rows: 8, value: saved, label: "Notes" }),
              h(
                "div",
                { class: "ja-links" },
                btn("outline", "Save", null, { submit: true, key: "notes-save:" + id, busyLabel: "Saving…" }),
                btn(
                  "quiet",
                  "Cancel",
                  function () {
                    delete ui.editing[notesKey];
                    clearDrafts(notesKey);
                    render();
                    focusKey("notes-edit:" + id);
                  },
                  { key: "notes-cancel:" + id }
                )
              )
            );
          }
          return [
            saved.trim() ? markdown(saved) : empty(),
            h(
              "div",
              { class: "ja-links" },
              btn(
                "quiet",
                "Edit",
                function () {
                  ui.editing[notesKey] = true;
                  render();
                  focusKey(notesKey);
                },
                { key: "notes-edit:" + id, label: "Edit the notes" }
              )
            ),
          ];
        })
      );
      if (people.length) {
        discs.push(
          disclosure("job:people", "People", people.length, function () {
            return h(
              "ul",
              { class: "ja-plain" },
              people.map(function (person) {
                const mail = mailtoHref(person.email);
                const profile = linkedinHref(person.linkedin);
                return h(
                  "li",
                  { class: "ja-mini-person" },
                  h(
                    "button",
                    {
                      type: "button",
                      class: "ja-qrow",
                      "data-ja-key": "jobperson:" + person.id,
                      onclick: function () {
                        navigate({ view: "people" });
                      },
                    },
                    h(
                      "span",
                      { class: "ja-qrow-main" },
                      h("strong", { text: person.name }),
                      h("span", { class: "ja-meta", text: [person.role, personLabel(person.status)].filter(Boolean).join(" · ") })
                    )
                  ),
                  mail || profile
                    ? h(
                        "div",
                        { class: "ja-links" },
                        mail ? h("a", { class: "ja-quiet", href: mail }, "Email") : null,
                        profile ? link("LinkedIn", profile, "LinkedIn profile of " + person.name) : null
                      )
                    : null
                );
              })
            );
          })
        );
      }
      if (has("log")) {
        discs.push(
          disclosure("job:history", "History", null, function () {
            return markdown(sections.log);
          })
        );
      }
      const priorityKey = "priority:" + id;
      const referralKey = "referral:" + id;
      const savedPriority = String(job.priority || "normal").toLowerCase();
      const savedReferral = String(job.referral || "");
      discs.push(
        disclosure("job:record", "Record details", null, function () {
          const rows = [
            ["Job", h("span", { text: id })],
            ["Folder", [h("span", { class: "ja-path", text: detail.folder }), copyButton("Copy", detail.folder, "copy-folder:" + id, "Copy the folder path")]],
            job.created_on ? ["Added", h("span", { text: shortDate(job.created_on) })] : null,
            job.applied_on ? ["Applied", h("span", { text: shortDate(job.applied_on) })] : null,
            job.decision ? ["Blocker check", h("span", { text: decisionLabel(job.decision) })] : null,
            job.role_family ? ["Role family", h("span", { text: humanize(job.role_family) })] : null,
          ].filter(Boolean);
          return [
            h(
              "dl",
              { class: "ja-record" },
              rows.map(function (item) {
                return [h("dt", { text: item[0] }), h("dd", null, item[1])];
              })
            ),
            h(
              "form",
              {
                class: "ja-form-row",
                onsubmit: function (event) {
                  event.preventDefault();
                  const body = {};
                  const priority = draft(priorityKey, savedPriority);
                  const referral = draft(referralKey, savedReferral).trim();
                  if (priority !== savedPriority) body.priority = priority;
                  if (referral !== savedReferral) body.referral = referral;
                  if (!Object.keys(body).length) {
                    clearDrafts(referralKey);
                    return;
                  }
                  run("record-save:" + id, function () {
                    return post(route, body).then(function (result) {
                      afterTrack(result, id);
                      clearDrafts(priorityKey);
                      clearDrafts(referralKey);
                    });
                  });
                },
              },
              labelled("Priority", choice(priorityKey, PRIORITIES, savedPriority)),
              labelled("Referral", field(referralKey, { value: savedReferral }), "ja-grow"),
              btn("outline", "Save", null, { submit: true, key: "record-save:" + id, busyLabel: "Saving…", label: "Save priority and referral" })
            ),
          ];
        })
      );

      return shell(
        h(
          "header",
          { class: "ja-detail-head" },
          h("span", { class: "ja-eyebrow ja-eyebrow-accent", text: job.company || "" }),
          h("h2", { class: "ja-detail-title", text: job.title || "" }),
          job.location ? h("p", { class: "ja-detail-place", text: job.location }) : null
        ),
        h(
          "div",
          { class: "ja-status-row" },
          h("label", { class: "ja-status" }, h("span", { class: "ja-eyebrow", text: "Status" }), stage),
          href ? link("Open posting", href, "Open posting in a new tab") : null
        ),
        blockedLine,
        nextBlock,
        h(
          "section",
          { class: "ja-block" },
          h("h3", { class: "ja-h3", text: "Materials" }),
          materials.length ? h("ul", { class: "ja-plain ja-mats" }, materials.map(materialRow)) : empty()
        ),
        h("div", { class: "ja-discs" }, discs)
      );
    }

    // ── People ─────────────────────────────────────────────────────────

    function viewPeople() {
      const p = ui.people;
      const people = data.state.people || [];
      const list = h("ul", { class: "ja-plain ja-people" });

      function personRow(person) {
        const mail = mailtoHref(person.email);
        const profile = linkedinHref(person.linkedin);
        const why = data.why[person.person] || "";
        const prompt = personPrompt(person);
        return h(
          "li",
          { class: "ja-person" },
          h(
            "div",
            { class: "ja-person-core" },
            h("div", { class: "ja-person-line" }, h("strong", { class: "ja-person-name", text: person.name }), tag(personLabel(person.status), personTone(person.status))),
            h(
              "p",
              { class: "ja-meta ja-person-meta" },
              [person.role, person.company].filter(Boolean).join(" · "),
              mail ? h("a", { class: "ja-quiet", href: mail }, "Email") : null,
              profile ? link("LinkedIn", profile, "LinkedIn profile of " + person.name) : null
            ),
            why ? h("p", { class: "ja-person-why", text: why }) : null
          ),
          dateEl(person.next_touch, true, "ja-person-date") || h("span", { class: "ja-person-date" }),
          h(
            "div",
            { class: "ja-person-links" },
            btn(
              "quiet",
              "Edit",
              function () {
                openPerson(person.person);
              },
              { key: "person-edit:" + person.person, label: "Edit " + person.name }
            ),
            copyButton("Copy prompt", prompt, "person-prompt:" + person.person, "Copy prompt for " + person.name)
          )
        );
      }

      function fill() {
        const rows = filterPeople(people, p.query, p.filter);
        clear(list);
        rows.forEach(function (person) {
          list.appendChild(personRow(person));
        });
        if (!rows.length) list.appendChild(h("li", null, empty()));
      }

      const search = h("input", {
        type: "search",
        class: "ja-input ja-search",
        placeholder: "Filter people",
        "aria-label": "Filter people",
        "data-ja-key": "people:query",
        autocomplete: "off",
      });
      search.value = p.query;
      search.addEventListener("input", function () {
        p.query = search.value;
        fill();
      });
      fill();

      const filters = [{ value: "", label: "All" }].concat(
        PERSON_STATUSES.map(function (status) {
          return { value: status, label: personLabel(status) };
        })
      );
      return h(
        "div",
        { class: "ja-view" },
        pageHead("People", {
          action: btn(
            "primary",
            "Add person",
            function () {
              openPerson("");
            },
            { key: "person-add" }
          ),
        }),
        metrics(peopleCounts(people)),
        h(
          "div",
          { class: "ja-toolbar" },
          search,
          chips(
            filters,
            p.filter,
            function (value) {
              p.filter = value;
              render();
            },
            "Filter people"
          )
        ),
        list
      );
    }

    function personById(id) {
      return ((data.state && data.state.people) || []).filter(function (person) {
        return person.person === id;
      })[0];
    }

    function openPerson(id) {
      personForm.id = id;
      personForm.error = "";
      clearDrafts("pf:");
      renderPerson();
      showDialog(els.personDialog);
      focusKey("pf:name", els.personDialog);
    }

    function renderPerson() {
      const dialog = els.personDialog;
      const existing = personForm.id ? personById(personForm.id) || {} : {};
      const saved = {
        name: existing.name || "",
        company: existing.company || "",
        role: existing.role || "",
        email: existing.email || "",
        linkedin: existing.linkedin || "",
        why: personForm.id ? data.why[personForm.id] || "" : "",
        status: existing.status || "to_contact",
        next_touch: existing.next_touch || "",
        note: "",
      };
      const value = function (name) {
        return draft("pf:" + name, saved[name]).trim();
      };
      dialog.setAttribute("aria-label", personForm.id ? "Edit person" : "Add person");
      replaceDialog(
        dialog,
        h(
          "form",
          {
            class: "ja-dialog-body ja-form",
            novalidate: true,
            onsubmit: function (event) {
              event.preventDefault();
              if (busy["pf-save"]) return;
              if (!value("name") || (!personForm.id && !value("why"))) {
                personForm.error = personForm.id ? "Missing: name" : "Missing: name and why";
                renderPerson();
                return;
              }
              const body = {};
              Object.keys(saved).forEach(function (name) {
                const current = value(name);
                if (current !== saved[name] && (current || name === "next_touch")) body[name] = current;
              });
              personForm.error = "";
              if (personForm.id) {
                if (!Object.keys(body).length) {
                  closeDialog(dialog);
                  return;
                }
                body.person = personForm.id;
              }
              busy["pf-save"] = true;
              renderPerson();
              api
                .post("/people", body)
                .then(
                  function (result) {
                    if (!result || !result.ok) {
                      personForm.error = "Not saved";
                      return null;
                    }
                    const savedId = (result.person || {}).person || personForm.id;
                    if (savedId) delete data.why[savedId];
                    clearDrafts("pf:");
                    closeDialog(dialog);
                    return refresh();
                  },
                  function (err) {
                    personForm.error = messageOf(err);
                  }
                )
                .then(function () {
                  delete busy["pf-save"];
                  if (alive && dialog.open) renderPerson();
                });
            },
          },
          h("h2", { class: "ja-h2", text: personForm.id ? "Edit person" : "Add person" }),
          labelled("Name", field("pf:name", { value: saved.name, required: true })),
          h("div", { class: "ja-form-grid" }, labelled("Company", field("pf:company", { value: saved.company })), labelled("Role", field("pf:role", { value: saved.role }))),
          h(
            "div",
            { class: "ja-form-grid" },
            labelled("Email", field("pf:email", { type: "email", value: saved.email })),
            labelled("LinkedIn", field("pf:linkedin", { type: "url", value: saved.linkedin }))
          ),
          labelled("Why", field("pf:why", { multiline: true, rows: 3, value: saved.why, required: true })),
          h(
            "div",
            { class: "ja-form-grid" },
            labelled(
              "Status",
              choice(
                "pf:status",
                PERSON_STATUSES.map(function (status) {
                  return { value: status, label: personLabel(status) };
                }),
                saved.status
              )
            ),
            labelled("Next touch", field("pf:next_touch", { type: "date", value: saved.next_touch }))
          ),
          labelled("Note", field("pf:note", {})),
          personForm.error ? h("p", { class: "ja-form-error", role: "alert", text: personForm.error }) : null,
          h(
            "div",
            { class: "ja-dialog-actions" },
            btn("primary", "Save", null, { submit: true, key: "pf-save", busyLabel: "Saving…" }),
            btn(
              "quiet",
              "Cancel",
              function () {
                clearDrafts("pf:");
                closeDialog(dialog);
              },
              { key: "pf-cancel" }
            )
          )
        )
      );
    }

    // ── Leads ──────────────────────────────────────────────────────────

    function viewLeads() {
      const leads = data.state.leads || [];
      const shown = ui.leads.filter === "shortlisted"
        ? leads.filter(function (lead) {
            return lead.status === "shortlisted";
          })
        : leads;
      return h(
        "div",
        { class: "ja-view" },
        pageHead("Leads"),
        h(
          "div",
          { class: "ja-toolbar" },
          chips(
            [
              { value: "", label: "All" },
              { value: "shortlisted", label: "Shortlisted" },
            ],
            ui.leads.filter,
            function (value) {
              ui.leads.filter = value;
              render();
            },
            "Filter leads"
          )
        ),
        shown.length
          ? h(
              "ul",
              { class: "ja-plain ja-leads" },
              shown.map(function (lead) {
                const id = lead.lead;
                const route = "/leads/" + encodeURIComponent(id);
                const href = safeHref(lead.url);
                const word = leadChip(lead.preflight);
                return h(
                  "li",
                  { class: "ja-lead" },
                  h(
                    "div",
                    { class: "ja-lead-core" },
                    h("span", { class: "ja-jobrow-company", text: lead.company || "" }),
                    h("div", { class: "ja-lead-line" }, h("strong", { class: "ja-jobrow-title", text: lead.title || "" }), word ? tag(word, word === "Check" ? "warn" : "neutral") : null),
                    h("span", { class: "ja-meta", text: [lead.location, lead.found_on ? "found " + shortDate(lead.found_on) : ""].filter(Boolean).join(" · ") })
                  ),
                  h(
                    "div",
                    { class: "ja-links" },
                    href ? link("Open posting", href, "Open posting for " + (lead.title || "this lead") + " in a new tab") : null,
                    lead.status === "shortlisted"
                      ? null
                      : action(
                          "quiet",
                          "Shortlist",
                          "lead-shortlist:" + id,
                          function () {
                            return post(route, { status: "shortlisted" });
                          },
                          { label: "Shortlist " + (lead.title || "this lead") }
                        ),
                    action(
                      "quiet",
                      "Start",
                      "lead-start:" + id,
                      function () {
                        return post(route, { status: "promote" }).then(function (result) {
                          const outcome = addJobOutcome(result);
                          if (outcome.jobId) openJob(outcome.jobId);
                          else notice = { text: outcome.lines.join(". ") };
                        });
                      },
                      { busyLabel: "Starting…", label: "Start " + (lead.title || "this lead") }
                    ),
                    action(
                      "quiet",
                      "Dismiss",
                      "lead-dismiss:" + id,
                      function () {
                        return post(route, { status: "dismissed" });
                      },
                      { label: "Dismiss " + (lead.title || "this lead") }
                    )
                  )
                );
              })
            )
          : empty()
      );
    }

    // ── Insights ───────────────────────────────────────────────────────

    function insightTable(title, firstColumn, rows) {
      const numeric = function (value) {
        return h("td", { class: "ja-num", text: String(value) });
      };
      return h(
        "table",
        { class: "ja-table", "aria-label": title },
        h(
          "thead",
          null,
          h(
            "tr",
            null,
            h("th", { scope: "col", text: firstColumn }),
            ["Sent", "Interviews", "Rejected", "No reply"].map(function (label) {
              return h("th", { scope: "col", class: "ja-num", text: label });
            })
          )
        ),
        h(
          "tbody",
          null,
          rows.map(function (item) {
            return h(
              "tr",
              null,
              h("th", { scope: "row", text: item.label }),
              h(
                "td",
                { class: "ja-num ja-meter-cell" },
                h("span", { class: "ja-meter", "aria-hidden": "true" }, h("span", { class: "ja-meter-fill", style: "width:" + item.bar + "%" })),
                h("span", { class: "ja-meter-number", text: String(item.applied) })
              ),
              numeric(item.interviews),
              numeric(item.rejected),
              numeric(item.no_reply)
            );
          })
        )
      );
    }

    function viewInsights() {
      const entry = data.stats;
      const view = h("div", { class: "ja-view" }, pageHead("Insights"));
      if (!entry) {
        view.appendChild(loading());
        return view;
      }
      if (!entry.stats) {
        view.appendChild(
          h(
            "p",
            { class: "ja-line", role: "alert" },
            entry.error + " ",
            btn(
              "quiet",
              "Retry",
              function () {
                refresh();
              },
              { key: "insights-retry" }
            )
          )
        );
        return view;
      }
      const stats = entry.stats;
      const summary = insightFigures(stats);
      if (!summary.sent) {
        view.appendChild(empty());
        return view;
      }
      view.appendChild(metrics(summary.figures));
      view.appendChild(h("p", { class: "ja-caption", text: [summary.rate, summary.median].filter(Boolean).join(" · ") }));
      [
        { title: "By month", column: "Month", rows: insightRows(stats.by_month, "month") },
        { title: "By role family", column: "Role family", rows: insightRows(stats.by_role_family, "role_family") },
        { title: "Referral and cold", column: "Channel", rows: insightRows(stats.by_channel, "channel") },
      ].forEach(function (table) {
        if (!table.rows.length) return;
        view.appendChild(h("section", { class: "ja-section" }, h("h2", { class: "ja-h2", text: table.title }), insightTable(table.title, table.column, table.rows)));
      });
      return view;
    }

    // ── Library ────────────────────────────────────────────────────────

    function metaList(meta) {
      const keys = Object.keys(meta || {}).filter(function (key) {
        const value = meta[key];
        if (key === "title" || key === "name" || key === "sources" || (key === "status" && value === "active")) return false;
        return value !== "" && value != null && !(Array.isArray(value) && !value.length);
      });
      if (!keys.length) return null;
      return h(
        "dl",
        { class: "ja-record" },
        keys.map(function (key) {
          const value = meta[key];
          return [h("dt", { text: humanize(key) }), h("dd", { text: Array.isArray(value) ? value.join(", ") : String(value) })];
        })
      );
    }

    function viewLibrary() {
      const selected = libraryPath();
      const evidence = data.evidence;
      const entry = data.docs[selected];
      const workspace = String(data.state.workspace || "").replace(/[\\/]+$/, "");

      function item(path, label, detail, dim) {
        return h(
          "li",
          null,
          h(
            "button",
            {
              type: "button",
              class: "ja-lib-item" + (dim ? " is-dim" : ""),
              "aria-current": path === selected ? "true" : null,
              "data-ja-key": "lib:" + path,
              onclick: function () {
                navigate({ view: "library", path: path });
              },
            },
            h("span", { class: "ja-lib-title", text: label }),
            detail ? h("span", { class: "ja-meta", text: detail }) : null
          )
        );
      }

      const list = h(
        "nav",
        { class: "ja-lib-list", "aria-label": "Library documents", "data-ja-scroll": "library" },
        h(
          "ul",
          { class: "ja-plain" },
          PROFILE_DOCS.map(function (entryDoc) {
            return item(entryDoc.path, entryDoc.label);
          })
        ),
        h("span", { class: "ja-eyebrow ja-lib-label", text: "Evidence" }),
        data.evidenceError ? h("p", { class: "ja-line", role: "alert", text: data.evidenceError }) : null,
        evidence === null
          ? loading()
          : evidence.length
            ? h(
                "ul",
                { class: "ja-plain" },
                evidence.map(function (record) {
                  const detail = [humanize(record.type), record.status === "active" ? "" : humanize(record.status)].filter(Boolean).join(" · ");
                  return item(record.path, record.title || record.id, detail, record.status === "retired");
                })
              )
            : empty()
      );

      let pane;
      if (!entry) {
        pane = loading();
      } else if (!entry.doc) {
        pane = h("p", { class: "ja-line", role: "alert", text: entry.error });
      } else {
        const full = workspace ? workspace + "/" + entry.doc.path : entry.doc.path;
        const first = parseMarkdown(entry.doc.body)[0];
        const titled = !!first && first.type === "heading" && first.level === 1;
        pane = [
          titled ? null : h("h2", { class: "ja-doc-title", text: String((entry.doc.meta || {}).title || "") || selected.split("/").pop() }),
          String(entry.doc.body || "").trim() ? markdown(entry.doc.body) : empty(),
          metaList(entry.doc.meta),
          h("p", { class: "ja-doc-path" }, h("span", { class: "ja-path", text: full }), copyButton("Copy", full, "copy-doc", "Copy the file path")),
        ];
      }

      return h("div", { class: "ja-view" }, pageHead("Library"), h("div", { class: "ja-library" }, list, h("article", { class: "ja-doc", "aria-label": "Document" }, pane)));
    }

    // ── Dialogs ────────────────────────────────────────────────────────

    function showDialog(dialog) {
      if (dialog.open) return;
      if (typeof dialog.showModal === "function") {
        try {
          dialog.showModal();
          return;
        } catch (err) {
          /* fall through to the attribute */
        }
      }
      dialog.setAttribute("open", "");
    }

    function closeDialog(dialog) {
      if (typeof dialog.close === "function") {
        try {
          dialog.close();
          return;
        } catch (err) {
          /* fall through to the attribute */
        }
      }
      dialog.removeAttribute("open");
    }

    function replaceDialog(dialog, body) {
      const focus = captureFocus(dialog);
      clear(dialog);
      dialog.appendChild(body);
      restoreFocus(dialog, focus);
    }

    function openAddJob() {
      addJob.result = null;
      addJob.error = "";
      renderAddJob();
      showDialog(els.addDialog);
      focusKey("add:url", els.addDialog);
    }

    function submitAddJob() {
      if (busy["add"]) return;
      const body = {
        url: draft("add:url", "").trim(),
        company: draft("add:company", "").trim(),
        title: draft("add:title", "").trim(),
        text: draft("add:text", "").trim(),
      };
      addJob.result = null;
      addJob.error = "";
      if (!body.url && !body.text) addJob.error = "Missing: a link or the posting text";
      else if (body.text && (!body.company || !body.title)) addJob.error = "Missing: company and title";
      if (addJob.error) {
        renderAddJob();
        return;
      }
      busy["add"] = true;
      renderAddJob();
      post("/jobs", body)
        .then(
          function (result) {
            addJob.result = result;
            if (addJobOutcome(result).kind !== "needs") clearDrafts("add:");
          },
          function (err) {
            addJob.error = messageOf(err);
          }
        )
        .then(function () {
          delete busy["add"];
          if (alive) renderAddJob();
        });
    }

    function renderAddJob() {
      const dialog = els.addDialog;
      const outcome = addJob.result ? addJobOutcome(addJob.result) : null;
      const lines = outcome ? outcome.lines : addJob.error ? [addJob.error] : [];
      replaceDialog(
        dialog,
        h(
          "form",
          {
            class: "ja-dialog-body ja-form",
            novalidate: true,
            onsubmit: function (event) {
              event.preventDefault();
              submitAddJob();
            },
          },
          h("h2", { class: "ja-h2", text: "Add a job" }),
          field("add:url", { type: "url", label: "Link", placeholder: "Link to the posting" }),
          h(
            "div",
            { class: "ja-form-grid" },
            field("add:company", { label: "Company", placeholder: "Company" }),
            field("add:title", { label: "Title", placeholder: "Title" })
          ),
          field("add:text", { multiline: true, rows: 8, label: "Posting text", placeholder: "Posting text" }),
          lines.length
            ? h(
                "div",
                { class: "ja-result", role: outcome && outcome.kind !== "needs" ? "status" : "alert" },
                lines.map(function (line) {
                  return h("p", { class: "ja-line", text: line });
                }),
                outcome && outcome.jobId
                  ? btn(
                      "quiet",
                      "Open job",
                      function () {
                        closeDialog(dialog);
                        openJob(outcome.jobId);
                      },
                      { key: "add-open-job" }
                    )
                  : null
              )
            : null,
          h(
            "div",
            { class: "ja-dialog-actions" },
            btn("primary", "Add", null, { submit: true, key: "add", busyLabel: "Adding…" }),
            btn(
              "quiet",
              "Close",
              function () {
                closeDialog(dialog);
              },
              { key: "add-close" }
            )
          )
        )
      );
    }

    function openViewer(path, name) {
      viewer.path = path;
      viewer.name = name;
      viewer.doc = null;
      viewer.error = "";
      viewer.loading = true;
      renderViewer();
      showDialog(els.viewer);
      api.get("/doc", { path: path }).then(
        function (payload) {
          if (viewer.path !== path) return;
          viewer.doc = payload;
          viewer.loading = false;
          if (alive) renderViewer();
        },
        function (err) {
          if (viewer.path !== path) return;
          viewer.error = messageOf(err);
          viewer.loading = false;
          if (alive) renderViewer();
        }
      );
    }

    function renderViewer() {
      const dialog = els.viewer;
      const body = h(
        "div",
        { class: "ja-dialog-body" },
        h(
          "div",
          { class: "ja-dialog-head" },
          h("h2", { class: "ja-h2", text: viewer.name || "Source" }),
          btn(
            "quiet",
            "Close",
            function () {
              closeDialog(dialog);
            },
            { key: "viewer-close" }
          )
        )
      );
      if (viewer.loading) {
        body.appendChild(loading());
      } else if (viewer.error) {
        body.appendChild(h("p", { class: "ja-form-error", role: "alert", text: viewer.error }));
      } else if (viewer.doc) {
        body.appendChild(h("p", { class: "ja-meta", text: viewer.doc.path }));
        const meta = metaList(viewer.doc.meta);
        if (meta) body.appendChild(meta);
        body.appendChild(h("pre", { class: "ja-source", tabindex: "0", text: viewer.doc.body }));
      }
      replaceDialog(dialog, body);
    }

    // ── Lifecycle ──────────────────────────────────────────────────────

    listen(els.main, "focusout", function () {
      if (!deferred) return;
      win.setTimeout(function () {
        if (alive && deferred && !isEditing()) render();
      }, 0);
    });
    listen(doc, "mousedown", function (event) {
      if (openMenu && !openMenu.wrap.contains(event.target)) openMenu.close();
    });
    listen(els.viewer, "close", function () {
      viewer.path = "";
      viewer.doc = null;
    });
    listen(win, "focus", backgroundRefresh);
    listen(doc, "visibilitychange", backgroundRefresh);
    if (!embedded) {
      listen(els.app, "keydown", function (event) {
        if (event.key === "Escape" && ui.railOpen) {
          ui.railOpen = false;
          renderChrome();
          els.toggle.focus();
        }
      });
      listen(win, "hashchange", function () {
        const route = parseHash(win.location.hash);
        if (!sameRoute(route, ui.route)) setRoute(route);
      });
      ui.route = parseHash(win.location.hash);
      if (ui.route.job) ui.lastJob = ui.route.job;
      const hash = formatHash(ui.route);
      if (win.location.hash !== hash && win.history && win.history.replaceState) {
        win.history.replaceState(null, "", hash);
      }
    }
    timer = win.setInterval(backgroundRefresh, REFRESH_MS);

    render();
    refresh();

    return function unmount() {
      if (!alive) return;
      alive = false;
      win.clearInterval(timer);
      listeners.forEach(function (entry) {
        entry[0].removeEventListener(entry[1], entry[2]);
      });
      Object.keys(blobUrls).forEach(function (path) {
        global.URL.revokeObjectURL(blobUrls[path]);
        delete blobUrls[path];
      });
      [els.addDialog, els.viewer, els.personDialog].forEach(function (dialog) {
        if (dialog.open) closeDialog(dialog);
      });
      if (els.app.parentNode === root) root.removeChild(els.app);
      addedClasses.forEach(function (name) {
        root.classList.remove(name);
      });
    };
  }

  // ── Hosts ────────────────────────────────────────────────────────────

  function registerWithHermes() {
    const sdk = global.__HERMES_PLUGIN_SDK__;
    const registry = global.__HERMES_PLUGINS__;
    if (!sdk || !registry || !sdk.React || typeof registry.register !== "function") return false;
    const React = sdk.React;

    function JobAppsTab() {
      const host = React.useRef(null);
      React.useEffect(function () {
        if (!host.current) return undefined;
        return mount(host.current, { api: createHermesApiClient(sdk, "/api/plugins/jobapps"), embedded: true });
      }, []);
      return React.createElement("div", { ref: host, className: "jobapps-root jobapps-embedded" });
    }

    registry.register("jobapps", JobAppsTab);
    return true;
  }

  global.JobAppsCockpit = {
    mount: mount,
    createApiClient: createApiClient,
    helpers: {
      STAGES: STAGES,
      JOB_GROUPS: JOB_GROUPS,
      GROUP_LIMIT: GROUP_LIMIT,
      WAITING_LIMIT: WAITING_LIMIT,
      localISODate: localISODate,
      formatDate: formatDate,
      longDate: longDate,
      dateInfo: dateInfo,
      plural: plural,
      humanize: humanize,
      stageLabel: stageLabel,
      stageTone: stageTone,
      personLabel: personLabel,
      leadChip: leadChip,
      decisionLabel: decisionLabel,
      materialLabel: materialLabel,
      materialState: materialState,
      overviewCounts: overviewCounts,
      continueJob: continueJob,
      upNext: upNext,
      waitingJobs: waitingJobs,
      filterJobs: filterJobs,
      groupJobs: groupJobs,
      jobRowMeta: jobRowMeta,
      nextActionBody: nextActionBody,
      jobPrompts: jobPrompts,
      personPrompt: personPrompt,
      checkFindings: checkFindings,
      addJobOutcome: addJobOutcome,
      peopleCounts: peopleCounts,
      filterPeople: filterPeople,
      sectionText: sectionText,
      percent: percent,
      monthLabel: monthLabel,
      insightRows: insightRows,
      insightFigures: insightFigures,
      safeHref: safeHref,
      mailtoHref: mailtoHref,
      linkedinHref: linkedinHref,
      parseHash: parseHash,
      formatHash: formatHash,
      parseInline: parseInline,
      parseMarkdown: parseMarkdown,
      renderMarkdown: renderMarkdown,
      queryString: queryString,
      createHermesApiClient: createHermesApiClient,
    },
  };

  registerWithHermes();
})();
