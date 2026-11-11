"use strict";

process.env.TZ = "America/Los_Angeles";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const DIST = path.join(__dirname, "..", "dashboard", "dist");
const SOURCE = fs.readFileSync(path.join(DIST, "index.js"), "utf8");
const STYLES = fs.readFileSync(path.join(DIST, "style.css"), "utf8");
const INDEX_HTML = fs.readFileSync(path.join(DIST, "index.html"), "utf8");

// ── A small fake DOM: enough for the helpers, the Markdown renderer and mount ──

class FakeNode {
  constructor(doc) {
    this.ownerDocument = doc;
    this.childNodes = [];
    this.parentNode = null;
  }
  get parentElement() {
    return this.parentNode && this.parentNode.nodeType === 1 ? this.parentNode : null;
  }
  get firstChild() {
    return this.childNodes[0] || null;
  }
  get isConnected() {
    let node = this;
    while (node.parentNode) node = node.parentNode;
    return node === this.ownerDocument.documentElement;
  }
}

class FakeText extends FakeNode {
  constructor(doc, data) {
    super(doc);
    this.nodeType = 3;
    this.data = String(data);
  }
  get textContent() {
    return this.data;
  }
}

class FakeElement extends FakeNode {
  constructor(doc, tag) {
    super(doc);
    this.nodeType = 1;
    this.tagName = String(tag).toUpperCase();
    this.attributes = {};
    this.listeners = {};
    this.style = {};
    this.className = "";
    this.value = "";
    this.disabled = false;
    this.open = false;
    this.scrollTop = 0;
    this.scrollLeft = 0;
    this.offsetHeight = 0;
    this.scrollHeight = 0;
    this.clientHeight = 0;
    this.clientWidth = 0;
    this.hidden = false;
  }
  get classList() {
    const el = this;
    const names = () => el.className.split(/\s+/).filter(Boolean);
    return {
      add: (name) => {
        if (!names().includes(name)) el.className = names().concat(name).join(" ");
      },
      remove: (name) => {
        el.className = names().filter((item) => item !== name).join(" ");
      },
      contains: (name) => names().includes(name),
    };
  }
  setAttribute(name, value) {
    this.attributes[name] = String(value);
  }
  getAttribute(name) {
    return Object.prototype.hasOwnProperty.call(this.attributes, name) ? this.attributes[name] : null;
  }
  removeAttribute(name) {
    delete this.attributes[name];
    if (name === "open") this.open = false;
  }
  appendChild(child) {
    if (child.nodeType === 11) {
      child.childNodes.slice().forEach((item) => this.appendChild(item));
      return child;
    }
    if (child.parentNode) child.parentNode.removeChild(child);
    child.parentNode = this;
    this.childNodes.push(child);
    return child;
  }
  removeChild(child) {
    const index = this.childNodes.indexOf(child);
    if (index === -1) throw new Error("removeChild: not a child");
    this.childNodes.splice(index, 1);
    child.parentNode = null;
    if (this.ownerDocument.activeElement && (child === this.ownerDocument.activeElement || (child.contains && child.contains(this.ownerDocument.activeElement)))) {
      this.ownerDocument.activeElement = this.ownerDocument.body;
    }
    return child;
  }
  get children() {
    return this.childNodes.filter((node) => node.nodeType === 1);
  }
  get textContent() {
    return this.childNodes.map((node) => node.textContent).join("");
  }
  set textContent(value) {
    this.childNodes.slice().forEach((node) => this.removeChild(node));
    if (value !== "" && value != null) this.appendChild(new FakeText(this.ownerDocument, value));
  }
  set innerHTML(_value) {
    throw new Error("innerHTML must never be used");
  }
  addEventListener(type, handler) {
    (this.listeners[type] = this.listeners[type] || []).push(handler);
  }
  removeEventListener(type, handler) {
    this.listeners[type] = (this.listeners[type] || []).filter((item) => item !== handler);
  }
  dispatch(type, init) {
    const event = Object.assign({ type, target: this, defaultPrevented: false }, init || {});
    event.preventDefault = () => {
      event.defaultPrevented = true;
    };
    let node = this;
    while (node) {
      event.currentTarget = node;
      (node.listeners[type] || []).slice().forEach((handler) => handler.call(node, event));
      node = init && init.bubbles === false ? null : node.parentNode && node.parentNode.listeners ? node.parentNode : null;
    }
    return event;
  }
  click() {
    if (!this.disabled) this.dispatch("click", { bubbles: false });
  }
  contains(node) {
    for (let current = node; current; current = current.parentNode) {
      if (current === this) return true;
    }
    return false;
  }
  walk(visit) {
    this.childNodes.forEach((node) => {
      if (node.nodeType !== 1) return;
      visit(node);
      node.walk(visit);
    });
  }
  querySelectorAll(selector) {
    const match = /^\[([\w-]+)\]$/.exec(selector);
    if (!match) throw new Error("fake DOM only supports [attr] selectors, got " + selector);
    const found = [];
    this.walk((node) => {
      if (node.getAttribute(match[1]) !== null) found.push(node);
    });
    return found;
  }
  focus() {
    this.ownerDocument.activeElement = this;
  }
  select() {}
  setSelectionRange(start, end) {
    this.selectionStart = start;
    this.selectionEnd = end;
  }
  showModal() {
    this.open = true;
  }
  close() {
    this.open = false;
    this.dispatch("close", { bubbles: false });
  }
}

class FakeFragment extends FakeElement {
  constructor(doc) {
    super(doc, "#fragment");
    this.nodeType = 11;
  }
}

function fakeWindow(hash) {
  const doc = {
    hidden: false,
    listeners: {},
    createElement: (tag) => new FakeElement(doc, tag),
    createElementNS: (_namespace, tag) => new FakeElement(doc, tag),
    createTextNode: (text) => new FakeText(doc, text),
    createDocumentFragment: () => new FakeFragment(doc),
    addEventListener(type, handler) {
      (this.listeners[type] = this.listeners[type] || []).push(handler);
    },
    removeEventListener(type, handler) {
      this.listeners[type] = (this.listeners[type] || []).filter((item) => item !== handler);
    },
    execCommand: () => true,
  };
  doc.documentElement = new FakeElement(doc, "html");
  doc.body = new FakeElement(doc, "body");
  doc.documentElement.appendChild(doc.body);
  doc.activeElement = doc.body;

  const win = {
    document: doc,
    listeners: {},
    intervals: [],
    timeouts: [],
    cleared: [],
    copied: [],
    opened: [],
    replaced: [],
    blobs: { created: [], revoked: [] },
    location: { hash: hash || "" },
    pageYOffset: 0,
    narrow: false,
    localStorage: {
      data: {},
      getItem(key) {
        return Object.prototype.hasOwnProperty.call(this.data, key) ? this.data[key] : null;
      },
      setItem(key, value) {
        this.data[key] = String(value);
      },
    },
    matchMedia() {
      return { matches: !!win.narrow };
    },
    addEventListener(type, handler) {
      (this.listeners[type] = this.listeners[type] || []).push(handler);
    },
    removeEventListener(type, handler) {
      this.listeners[type] = (this.listeners[type] || []).filter((item) => item !== handler);
    },
    emit(type) {
      (this.listeners[type] || []).slice().forEach((handler) => handler({ type }));
    },
    setInterval(fn, ms) {
      this.intervals.push({ fn, ms });
      return this.intervals.length;
    },
    clearInterval(id) {
      this.cleared.push(id);
    },
    setTimeout(fn) {
      this.timeouts.push(fn);
      return this.timeouts.length;
    },
    scrollTo(_x, y) {
      this.pageYOffset = y;
    },
    getComputedStyle: () => ({ overflowY: "visible" }),
    open(url, target) {
      const tab = { closed: false, location: { href: url }, close() { this.closed = true; } };
      this.opened.push({ tab, target });
      return tab;
    },
  };
  win.history = {
    replaceState(_state, _title, url) {
      win.replaced.push(url);
      win.location.hash = url;
    },
  };
  win.navigator = { clipboard: { writeText: (text) => (win.copied.push(text), Promise.resolve()) } };
  win.URL = {
    createObjectURL(blob) {
      const url = "blob:fake/" + (win.blobs.created.length + 1);
      win.blobs.created.push({ url, blob });
      return url;
    },
    revokeObjectURL(url) {
      win.blobs.revoked.push(url);
    },
  };
  doc.defaultView = win;
  return win;
}

function load(setup) {
  const win = fakeWindow();
  const clock = { offset: 0 };
  class TestDate extends Date {
    static now() {
      return Date.now() + clock.offset;
    }
  }
  if (setup) setup(win);
  const context = vm.createContext({ window: win, console, Date: TestDate });
  vm.runInContext(SOURCE, context, { filename: "dashboard/dist/index.js" });
  return { win, doc: win.document, cockpit: win.JobAppsCockpit, helpers: win.JobAppsCockpit.helpers, clock };
}

const { helpers } = load();
const plain = (value) => JSON.parse(JSON.stringify(value));
const settle = async () => {
  for (let i = 0; i < 8; i += 1) await new Promise((resolve) => setImmediate(resolve));
};

function all(root, predicate) {
  const found = [];
  root.walk((node) => {
    if (predicate(node)) found.push(node);
  });
  return found;
}
const byTag = (root, tag) => all(root, (node) => node.tagName === tag.toUpperCase());
const byClass = (root, name) => all(root, (node) => node.classList.contains(name) || (node.getAttribute("class") || "").split(/\s+/).includes(name));
const byKey = (root, key) => all(root, (node) => node.getAttribute("data-ja-key") === key)[0];
const button = (root, label) => all(root, (node) => node.tagName === "BUTTON" && node.textContent === label)[0];
const tags = (root) => all(root, () => true).map((node) => node.tagName);
// Identity of two nodes. Never assert.equal on nodes: a failure would print the whole fake tree.
const same = (actual, expected, message) => assert.ok(actual === expected, message || "expected the same node");

function type(el, value) {
  el.value = value;
  el.dispatch("input");
}

function md(text) {
  const doc = fakeWindow().document;
  const host = doc.createElement("div");
  host.appendChild(helpers.renderMarkdown(text, doc));
  return host;
}

function shape(node) {
  if (node.nodeType === 3) return node.data;
  const kids = node.childNodes.map(shape);
  return kids.length ? [node.tagName.toLowerCase(), ...kids] : [node.tagName.toLowerCase()];
}

// ── Dates: plain dates, nothing counted ──────────────────────────────────

test("dates are plain calendar dates, with the year only when it differs", () => {
  assert.equal(helpers.formatDate("2026-11-03", "2026-11-10"), "Nov 3");
  assert.equal(helpers.formatDate("2025-12-31", "2026-11-10"), "Dec 31, 2025");
  assert.equal(helpers.formatDate("2026-11-03T09:30:00", "2026-11-10"), "Nov 3");
  assert.equal(helpers.formatDate("2026-11-03"), "Nov 3, 2026");
  assert.equal(helpers.formatDate(""), "");
  assert.equal(helpers.formatDate("2026-13-01", "2026-11-10"), "");
  assert.equal(helpers.formatDate("soon", "2026-11-10"), "");
  assert.equal(helpers.longDate("2026-11-10"), "Tuesday, November 10");
  assert.equal(helpers.longDate("2027-01-01"), "Friday, January 1");
  assert.equal(helpers.longDate(""), "");
  assert.equal(helpers.localISODate(new Date(2026, 10, 10, 23, 30)), "2026-11-10");
  assert.equal(new Date(2026, 10, 10, 23, 30).toISOString().slice(0, 10), "2026-11-11", "the test zone must differ from UTC");
});

test("a date says whether it is in the past and never counts days", () => {
  const today = "2026-11-10";
  assert.deepEqual(plain(helpers.dateInfo("2026-11-09", today)), { text: "Nov 9", past: true });
  assert.deepEqual(plain(helpers.dateInfo("2026-11-10", today)), { text: "Nov 10", past: false });
  assert.deepEqual(plain(helpers.dateInfo("2026-11-11", today)), { text: "Nov 11", past: false });
  assert.deepEqual(plain(helpers.dateInfo("2025-08-27", today)), { text: "Aug 27, 2025", past: true });
  assert.equal(helpers.dateInfo("", today), null);
  assert.equal(helpers.dateInfo(undefined, today), null);
  assert.equal(helpers.dateInfo("2026-11-09", "").past, false);
  for (const iso of ["2026-08-01", "2026-11-09", "2026-11-10", "2026-12-25"]) {
    assert.ok(!/overdue|ago|days?|today|tomorrow|in \d/i.test(helpers.dateInfo(iso, today).text), iso);
  }
});

// ── Overview ─────────────────────────────────────────────────────────────

const JOBS = [
  { job: "2026-11-northstar-product-designer", company: "Northstar", title: "Product Designer", stage: "new", location: "New York, NY", updated_on: "2026-11-09", created_on: "2026-11-08" },
  { job: "2026-11-meridian-design-engineer", company: "Meridian", title: "Design Engineer", stage: "new", updated_on: "2026-11-05" },
  { job: "2026-11-harbor-designer", company: "Harbor", title: "Designer", stage: "ready", updated_on: "2026-11-06" },
  { job: "2026-10-quill-researcher", company: "Quill", title: "Researcher", stage: "ready", updated_on: "2026-11-07" },
  { job: "2026-10-fieldwork-design-engineer", company: "Fieldwork", title: "Design Engineer", stage: "applied", applied_on: "2026-10-20", updated_on: "2026-10-20" },
  { job: "2026-10-lantern-designer", company: "Lantern", title: "Designer", stage: "applied", applied_on: "2026-10-29", updated_on: "2026-10-29" },
  { job: "2026-09-common-ground-staff-designer", company: "Common Ground", title: "Staff Designer", stage: "interviewing", updated_on: "2026-11-01" },
  { job: "2026-09-tidewater-lead", company: "Tidewater", title: "Lead Designer", stage: "offer", updated_on: "2026-11-04" },
  { job: "2026-08-oakridge-designer", company: "Oakridge", title: "Designer", stage: "rejected", updated_on: "2026-09-01" },
  { job: "2026-08-driftwood-designer", company: "Driftwood", title: "Designer", stage: "skipped", updated_on: "2026-08-20" },
  { job: "2026-08-lumen-lead", company: "Lumen", title: "Design Lead", stage: "mystery", updated_on: "2026-08-10" },
];

test("the overview counts four groups", () => {
  const counts = { new: 44, ready: 14, applied: 90, interviewing: 1, offer: 1, rejected: 3, closed: 1, skipped: 7, total: 161 };
  assert.deepEqual(plain(helpers.overviewCounts(counts)), [
    { key: "progress", label: "In progress", value: 58 },
    { key: "applied", label: "Applied", value: 90 },
    { key: "interviewing", label: "Interviewing", value: 2 },
    { key: "aside", label: "Set aside", value: 11 },
  ]);
  assert.deepEqual(plain(helpers.overviewCounts(undefined).map((item) => item.value)), [0, 0, 0, 0]);
  assert.deepEqual(plain(helpers.JOB_GROUPS.map((group) => group.stages)), [["new", "ready"], ["applied"], ["interviewing", "offer"], ["rejected", "closed", "skipped"]]);
});

test("continue with: an interview or offer, then the freshest ready job, then the freshest new one", () => {
  assert.equal(helpers.continueJob(JOBS).company, "Tidewater", "the interview or offer touched most recently");
  const noInterviews = JOBS.filter((job) => job.stage !== "interviewing" && job.stage !== "offer");
  assert.equal(helpers.continueJob(noInterviews).company, "Quill", "the ready job touched most recently");
  const onlyNew = noInterviews.filter((job) => job.stage !== "ready");
  assert.equal(helpers.continueJob(onlyNew).company, "Northstar");
  assert.equal(helpers.continueJob(onlyNew.filter((job) => job.stage !== "new")), null, "applied and set-aside jobs are never offered");
  assert.equal(helpers.continueJob([]), null);
  assert.equal(helpers.continueJob(undefined), null);
  assert.equal(JOBS[0].company, "Northstar", "the caller's list is not reordered");
});

test("up next is the soonest five, in date order", () => {
  const due = [
    { job: "c", due: "2026-11-12" },
    { job: "a", due: "2026-11-08" },
    { job: "x", due: "" },
    { job: "d", due: "2026-11-12" },
    { job: "b", due: "2026-11-10" },
    { job: "e", due: "2026-11-13" },
    { job: "f", due: "2026-11-14" },
  ];
  assert.deepEqual(plain(helpers.upNext(due, undefined, "2026-11-10").map((row) => row.job)), ["a", "b", "c", "d", "e"]);
  assert.deepEqual(plain(helpers.upNext(due, 2, "2026-11-10").map((row) => row.job)), ["a", "b"]);
  assert.deepEqual(plain(helpers.upNext(undefined)), []);
  const withOld = [{ job: "old1", due: "2026-08-27" }, { job: "old2", due: "2026-09-04" }, ...due];
  assert.deepEqual(
    plain(helpers.upNext(withOld, 7, "2026-11-10").map((row) => row.job)),
    ["a", "b", "c", "d", "e", "f", "old2"],
    "dates from the last two weeks onward come first; older ones follow, newest first"
  );
  assert.equal(due[0].job, "c", "the caller's list is not reordered");
});

test("waiting to hear back lists applied jobs, newest application first", () => {
  assert.deepEqual(plain(helpers.waitingJobs(JOBS).map((job) => job.company)), ["Lantern", "Fieldwork"]);
  assert.deepEqual(plain(helpers.waitingJobs([])), []);
  assert.equal(helpers.WAITING_LIMIT, 12);
});

// ── Jobs ─────────────────────────────────────────────────────────────────

test("the jobs list is grouped by stage, in stage order, without empty groups", () => {
  const all = helpers.groupJobs(JOBS, "", "");
  assert.deepEqual(plain(all.map((group) => [group.stage, group.label, group.jobs.length])), [
    ["new", "New", 3],
    ["ready", "Ready", 2],
    ["applied", "Applied", 2],
    ["interviewing", "Interviewing", 1],
    ["offer", "Offer", 1],
    ["rejected", "Rejected", 1],
    ["skipped", "Skipped", 1],
  ]);
  assert.equal(all[0].jobs[2].company, "Lumen", "an unknown stage falls back to new");
  assert.deepEqual(plain(helpers.groupJobs(JOBS, "", "progress").map((group) => group.stage)), ["new", "ready"]);
  assert.deepEqual(plain(helpers.groupJobs(JOBS, "", "applied").map((group) => group.stage)), ["applied"]);
  assert.deepEqual(plain(helpers.groupJobs(JOBS, "", "interviewing").map((group) => group.stage)), ["interviewing", "offer"]);
  assert.deepEqual(plain(helpers.groupJobs(JOBS, "", "aside").map((group) => group.stage)), ["rejected", "skipped"]);
  assert.deepEqual(plain(helpers.groupJobs(JOBS, "", "nonsense").map((group) => group.stage)).length, 7);
  assert.deepEqual(plain(helpers.groupJobs(JOBS, "designer", "progress").map((group) => group.jobs.map((job) => job.company))), [["Northstar"], ["Harbor"]]);
  assert.deepEqual(plain(helpers.groupJobs(JOBS, "nobody", "")), []);
  assert.deepEqual(plain(helpers.groupJobs([{ job: "x", stage: "constructor" }], "", "")[0].stage), "new");
  assert.equal(helpers.GROUP_LIMIT, 20);
});

test("search matches company, role, location and id", () => {
  const names = (query) => helpers.filterJobs(JOBS, query).map((job) => job.company);
  assert.equal(names("").length, JOBS.length);
  assert.deepEqual(plain(names("DESIGN engineer")), ["Meridian", "Fieldwork"]);
  assert.deepEqual(plain(names("new york")), ["Northstar"]);
  assert.deepEqual(plain(names("2026-09")), ["Common Ground", "Tidewater"]);
  assert.deepEqual(plain(names("nobody")), []);
  assert.notEqual(helpers.filterJobs(JOBS, ""), JOBS);
  assert.equal(helpers.jobRowMeta({ location: "Remote", applied_on: "2026-10-20", created_on: "2026-10-01" }, "2026-11-10"), "Remote · Oct 20");
  assert.equal(helpers.jobRowMeta({ created_on: "2026-11-08" }, "2026-11-10"), "Nov 8");
  assert.equal(helpers.jobRowMeta({ location: "Remote" }, "2026-11-10"), "Remote");
});

test("the next-step request is one POST, and a date can be cleared on its own", () => {
  const saved = { next_action: "Send the portfolio", due: "2026-11-12" };
  assert.equal(helpers.nextActionBody(saved, "Send the portfolio", "2026-11-12"), null);
  assert.deepEqual(plain(helpers.nextActionBody(saved, "Send the portfolio", "")), { due: "" });
  assert.deepEqual(plain(helpers.nextActionBody(saved, "Send the portfolio", "2026-11-20")), { due: "2026-11-20" });
  assert.deepEqual(plain(helpers.nextActionBody(saved, "Email Riley", "2026-11-12")), { next_action: "Email Riley" });
  assert.deepEqual(plain(helpers.nextActionBody(saved, "Email Riley", "")), { next_action: "Email Riley", due: "" });
  assert.deepEqual(plain(helpers.nextActionBody(saved, "", "2026-11-30")), { next_action: "" }, "clearing the text clears its date");
  assert.deepEqual(plain(helpers.nextActionBody({}, "", "2026-11-30")), { due: "2026-11-30" });
  assert.equal(helpers.nextActionBody({}, "", ""), null);
});

test("the prompt menu offers five prompts that name the job", () => {
  const prompts = helpers.jobPrompts({ job: "2026-11-northstar-product-designer", company: "Northstar", title: "Product Designer" });
  assert.deepEqual(plain(prompts), [
    { label: "Plan my application", text: "Plan my application for Northstar, Product Designer (job 2026-11-northstar-product-designer)." },
    { label: "Tailor my resume", text: "Tailor my resume for Northstar, Product Designer (job 2026-11-northstar-product-designer)." },
    { label: "Write the cover letter", text: "Write the cover letter for Northstar, Product Designer (job 2026-11-northstar-product-designer)." },
    { label: "Draft outreach", text: "Draft outreach for Northstar, Product Designer (job 2026-11-northstar-product-designer)." },
    { label: "Prepare for the interview", text: "Help me prepare for the interview at Northstar, Product Designer (job 2026-11-northstar-product-designer)." },
  ]);
  assert.equal(
    helpers.personPrompt({ person: "riley-stone", name: "Riley Stone", role: "Design Manager", company: "Northstar" }),
    "Draft a note to Riley Stone, Design Manager at Northstar (person riley-stone)."
  );
  assert.equal(helpers.personPrompt({ person: "sam", name: "Sam" }), "Draft a note to Sam (person sam).");
});

// ── Materials ────────────────────────────────────────────────────────────

test("materials carry a human label, and a state word only when there is something to say", () => {
  assert.deepEqual(plain(helpers.materialLabel({ kind: "resume", name: "Jordan Example - Resume.typ" })), { label: "Resume", file: "Jordan Example - Resume.typ" });
  assert.deepEqual(plain(helpers.materialLabel({ kind: "cover_letter", name: "letter.typ" })), { label: "Cover letter", file: "letter.typ" });
  assert.deepEqual(plain(helpers.materialLabel({ kind: "application_answers", name: "answers.md" })), { label: "Answers", file: "answers.md" });
  assert.deepEqual(plain(helpers.materialLabel({ kind: "outreach", name: "note.md" })), { label: "Outreach", file: "note.md" });
  assert.deepEqual(plain(helpers.materialLabel({ kind: "other", name: "portfolio.pdf" })), { label: "portfolio.pdf", file: "" });
  assert.deepEqual(plain(helpers.materialLabel({ kind: "toString", name: "x.md" })), { label: "x.md", file: "" });
  assert.equal(helpers.materialState("pass"), "Checked");
  assert.equal(helpers.materialState("review"), "Needs attention");
  assert.equal(helpers.materialState("fail"), "Needs attention");
  assert.equal(helpers.materialState("stale"), "Changed since check");
  assert.equal(helpers.materialState("none"), "");
  assert.equal(helpers.materialState(undefined), "");
  assert.equal(helpers.materialState("constructor"), "");
});

test("check findings are one flat list: the rule in words, the excerpt, the fix", () => {
  const found = helpers.checkFindings({
    ok: true,
    status: "fail",
    build: { ok: false, error: "error: unknown variable", integrity_errors: ["missing_fonts"], contamination: ["TODO"] },
    layout: { violations_total: 3, violations: [{ type: "orphan_word", page: 1, text: "systems.", fix: "Shorten the bullet." }] },
    content: { findings: [{ rule: "banned_phrase", severity: "error", where: "bullet 3", excerpt: "passionate about", fix: "Say what you did." }], findings_truncated: 4 },
  });
  assert.deepEqual(plain(found), {
    state: "Needs attention",
    items: [
      { rule: "Build", excerpt: "error: unknown variable", fix: "" },
      { rule: "Missing fonts", excerpt: "", fix: "" },
      { rule: "Leftover text", excerpt: "TODO", fix: "" },
      { rule: "Orphan word, page 1", excerpt: "systems.", fix: "Shorten the bullet." },
      { rule: "Banned phrase, bullet 3", excerpt: "passionate about", fix: "Say what you did." },
    ],
    more: 6,
  });
  assert.deepEqual(plain(helpers.checkFindings({ ok: true, status: "pass", content: { findings: [] } })), { state: "Checked", items: [], more: 0 });
  assert.deepEqual(plain(helpers.checkFindings({ ok: false, error: "File not found: jobs/x/resume.typ" })), {
    state: "Not checked",
    items: [{ rule: "Check", excerpt: "File not found: jobs/x/resume.typ", fix: "" }],
    more: 0,
  });
});

test("adding a job answers in one or two plain lines", () => {
  const created = helpers.addJobOutcome({ ok: true, job: { job: "2026-11-fieldwork-researcher", company: "Fieldwork", title: "Researcher" }, preflight: { decision: "apply", blockers: [] } });
  assert.deepEqual(plain(created), { kind: "created", jobId: "2026-11-fieldwork-researcher", lines: ["Added Fieldwork, Researcher"] });
  const flagged = helpers.addJobOutcome({
    ok: true,
    job: { job: "x", company: "Granite", title: "Director" },
    preflight: { decision: "skip", blockers: [{ area: "sponsorship", severity: "blocker", evidence: "No visa sponsorship.", action: "Confirm before applying." }] },
  });
  assert.deepEqual(plain(flagged.lines), ["Added Granite, Director", "Blocker check: Skip. Sponsorship: No visa sponsorship."]);
  assert.ok(!flagged.lines.join(" ").includes("Confirm before applying"), "advice from the server is not repeated");
  assert.deepEqual(plain(helpers.addJobOutcome({ ok: true, duplicate: true, job: { job: "x", company: "Northstar", title: "Designer" }, hint: "Continue with it." })), {
    kind: "duplicate",
    jobId: "x",
    lines: ["Already here: Northstar, Designer"],
  });
  assert.deepEqual(plain(helpers.addJobOutcome({ ok: false, needs: "posting_text", hint: "Fetch the posting with your web tool.", error: "HTTP 404" })), {
    kind: "needs",
    jobId: "",
    lines: ["Missing: posting text", "HTTP 404"],
  });
  assert.deepEqual(plain(helpers.addJobOutcome({ ok: false, needs: ["company", "title"], hint: "Read them from the posting." }).lines), ["Missing: company and title"]);
  assert.deepEqual(plain(helpers.addJobOutcome(null).lines), ["Not added"]);
});

// ── Labels, people and leads ─────────────────────────────────────────────

test("stages, people and leads have short labels", () => {
  assert.equal(helpers.stageLabel("interviewing"), "Interviewing");
  assert.equal(helpers.stageLabel("toString"), "ToString");
  assert.deepEqual(plain(["new", "ready", "applied", "offer", "rejected", "closed"].map(helpers.stageTone)), ["warn", "warn", "good", "good", "neutral", "neutral"]);
  assert.equal(helpers.personLabel("to_contact"), "To contact");
  assert.equal(helpers.personLabel("follow_up"), "Follow up");
  assert.equal(helpers.leadChip("skip"), "Blocked");
  assert.equal(helpers.leadChip("Pending"), "Check");
  assert.equal(helpers.leadChip("apply"), "");
  assert.equal(helpers.leadChip(undefined), "");
  assert.equal(helpers.leadChip("constructor"), "");
  assert.equal(helpers.decisionLabel("apply"), "Apply");
  assert.equal(helpers.decisionLabel("SKIP"), "Skip");
  assert.equal(helpers.decisionLabel(""), "");
  assert.equal(helpers.humanize("orphan_word"), "Orphan word");
});

test("people are counted and filtered by status and text", () => {
  const people = [
    { person: "a", name: "Alex Rivera", company: "Northstar", role: "Designer", status: "to_contact" },
    { person: "b", name: "Jamie Chen", company: "Common Ground", role: "Manager", status: "follow_up" },
    { person: "c", name: "Sam Patel", company: "Fieldwork", role: "Design Lead", status: "contacted" },
    { person: "d", name: "Morgan Lee", company: "Tidewater", role: "Head of Design", status: "replied" },
  ];
  assert.deepEqual(plain(helpers.peopleCounts(people)), [
    { label: "People", value: 4 },
    { label: "To contact", value: 1 },
    { label: "Follow up", value: 1 },
    { label: "Contacted", value: 1 },
  ]);
  assert.deepEqual(plain(helpers.peopleCounts(undefined).map((item) => item.value)), [0, 0, 0, 0]);
  const names = (query, status) => helpers.filterPeople(people, query, status).map((person) => person.name);
  assert.deepEqual(plain(names("", "")), ["Alex Rivera", "Jamie Chen", "Sam Patel", "Morgan Lee"]);
  assert.deepEqual(plain(names("design", "")), ["Alex Rivera", "Sam Patel", "Morgan Lee"]);
  assert.deepEqual(plain(names("design", "contacted")), ["Sam Patel"]);
  assert.deepEqual(plain(names("", "paused")), []);
});

test("the why of a person is read from their record", () => {
  const body = "# Sam Patel\n\n## Why\n\nMet at a meetup.\nOffered to refer.\n\n## Notes\n\nprivate\n\n## Log\n\n- 2026-11-01: Added.";
  assert.equal(helpers.sectionText(body, "Why"), "Met at a meetup.\nOffered to refer.");
  assert.equal(helpers.sectionText(body, "why"), "Met at a meetup.\nOffered to refer.");
  assert.equal(helpers.sectionText(body, "Notes"), "private");
  assert.equal(helpers.sectionText(body, "Missing"), "");
  assert.equal(helpers.sectionText("## Why\n\n_Why this person matters to the search._\n\n## Notes\n", "Why"), "", "a placeholder is not a reason");
  assert.equal(helpers.sectionText(null, "Why"), "");
});

// ── Insights ─────────────────────────────────────────────────────────────

test("insights: percentages, rows and labels", () => {
  assert.equal(helpers.percent(3, 96), 3);
  assert.equal(helpers.percent(1, 3), 33);
  assert.equal(helpers.percent(9, 5), 100);
  assert.equal(helpers.percent(5, 0), 0);
  assert.equal(helpers.percent("x", undefined), 0);
  assert.equal(helpers.monthLabel("2026-11"), "Nov 2026");
  assert.equal(helpers.monthLabel("undated"), "No date");
  assert.equal(helpers.monthLabel("2026-13"), "2026-13");
  assert.deepEqual(
    plain(helpers.insightRows([{ month: "2026-09", applied: 40, interviews: 1, rejected: 9, no_reply: 30 }, { month: "2026-10", applied: 10, interviews: 2, rejected: 3, no_reply: 5 }], "month")),
    [
      { label: "Sep 2026", applied: 40, interviews: 1, rejected: 9, no_reply: 30, bar: 100 },
      { label: "Oct 2026", applied: 10, interviews: 2, rejected: 3, no_reply: 5, bar: 25 },
    ]
  );
  assert.deepEqual(plain(helpers.insightRows([{ role_family: "product_design", applied: 3 }, { role_family: "", applied: "2" }], "role_family").map((row) => [row.label, row.bar])), [["Product design", 100], ["Unlabelled", 67]]);
  assert.deepEqual(plain(helpers.insightRows([{ channel: "cold", applied: 4 }, { channel: "referral", applied: 1 }], "channel").map((row) => row.label)), ["Cold", "Referral"]);
  assert.deepEqual(plain(helpers.insightRows(undefined, "month")), []);
  assert.equal(helpers.channelComparison, undefined, "the cockpit does not compare channels in words");
});

test("insights: plain figures and one caption", () => {
  const figures = helpers.insightFigures({ applied: 96, interviews: 3, offers: 1, rejected: 20, no_reply: 72, interview_rate: "3 of 96", median_days_to_outcome: 12 });
  assert.deepEqual(plain(figures), {
    sent: 96,
    figures: [
      { label: "Sent", value: 96 },
      { label: "Interviews", value: 3 },
      { label: "Offers", value: 1 },
      { label: "Rejected", value: 20 },
      { label: "No reply", value: 72 },
    ],
    rate: "3 of 96 reached an interview",
    median: "Median 12 days to an outcome",
  });
  const none = helpers.insightFigures({ applied: 0 });
  assert.deepEqual(plain([none.sent, none.rate, none.median]), [0, "", ""]);
  assert.equal(helpers.insightFigures(undefined).sent, 0);
});

// ── Links and routes ─────────────────────────────────────────────────────

test("only http, https and mailto targets are links", () => {
  assert.equal(helpers.safeHref("https://northstar.example/jobs/1?x=1#top"), "https://northstar.example/jobs/1?x=1#top");
  assert.equal(helpers.safeHref(" HTTP://northstar.example "), "HTTP://northstar.example");
  assert.equal(helpers.safeHref("mailto:riley@northstar.example"), "mailto:riley@northstar.example");
  for (const bad of [
    "javascript:alert(1)",
    "JaVaScRiPt:alert(1)",
    " javascript:alert(1)",
    "java\tscript:alert(1)",
    "data:text/html,<script>alert(1)</script>",
    "vbscript:msgbox(1)",
    "file:///etc/passwd",
    "//evil.example",
    "/relative",
    "ftp://example.org",
    "https://",
    "https://a b",
    "mailto:",
    "",
    null,
    undefined,
  ]) {
    assert.equal(helpers.safeHref(bad), null, String(bad));
  }
  assert.equal(helpers.mailtoHref("riley@northstar.example"), "mailto:riley@northstar.example");
  assert.equal(helpers.mailtoHref("riley"), null);
  assert.equal(helpers.mailtoHref("a@b.c?subject=<x>"), null);
  assert.equal(helpers.linkedinHref("https://www.linkedin.com/in/riley-stone"), "https://www.linkedin.com/in/riley-stone");
  assert.equal(helpers.linkedinHref("linkedin.com/in/riley-stone"), "https://linkedin.com/in/riley-stone");
  assert.equal(helpers.linkedinHref("www.linkedin.com/in/riley"), "https://www.linkedin.com/in/riley");
  assert.equal(helpers.linkedinHref("javascript:alert(1)"), null);
  assert.equal(helpers.linkedinHref("riley-stone"), null);
});

test("addresses: the new routes, and the old ones as aliases", () => {
  assert.deepEqual(plain(helpers.parseHash("")), { view: "overview" });
  assert.deepEqual(plain(helpers.parseHash("#/overview")), { view: "overview" });
  assert.deepEqual(plain(helpers.parseHash("#/jobs")), { view: "jobs" });
  assert.deepEqual(plain(helpers.parseHash("#/jobs/2026-11-northstar-product-designer")), { view: "jobs", job: "2026-11-northstar-product-designer" });
  assert.deepEqual(plain(helpers.parseHash("#/jobs/a%20b")), { view: "jobs", job: "a b" });
  assert.deepEqual(plain(helpers.parseHash("#/people")), { view: "people" });
  assert.deepEqual(plain(helpers.parseHash("#/leads")), { view: "leads" });
  assert.deepEqual(plain(helpers.parseHash("#/insights")), { view: "insights" });
  assert.deepEqual(plain(helpers.parseHash("#/library")), { view: "library" });
  assert.deepEqual(plain(helpers.parseHash("#/library/evidence/Field%20notes.md")), { view: "library", path: "evidence/Field notes.md" });

  assert.deepEqual(plain(helpers.parseHash("#/today")), { view: "overview" });
  assert.deepEqual(plain(helpers.parseHash("#/pipeline")), { view: "jobs" });
  assert.deepEqual(plain(helpers.parseHash("#/job/2026-11-a.b_c")), { view: "jobs", job: "2026-11-a.b_c" });
  assert.deepEqual(plain(helpers.parseHash("#/job")), { view: "jobs" });

  assert.deepEqual(plain(helpers.parseHash("#/nonsense")), { view: "overview" });
  assert.deepEqual(plain(helpers.parseHash("#/jobs/%E0%A4%A")), { view: "overview" });
  assert.deepEqual(plain(helpers.parseHash("#/constructor")), { view: "overview" });

  assert.equal(helpers.formatHash({ view: "overview" }), "#/overview");
  assert.equal(helpers.formatHash({ view: "jobs" }), "#/jobs");
  assert.equal(helpers.formatHash({ view: "jobs", job: "a b/c" }), "#/jobs/a%20b%2Fc");
  assert.equal(helpers.formatHash({ view: "library", path: "evidence/Field notes.md" }), "#/library/evidence/Field%20notes.md");
  assert.equal(helpers.formatHash({ view: "today" }), "#/overview");
  assert.equal(helpers.formatHash(null), "#/overview");
  for (const route of [
    { view: "overview" },
    { view: "jobs" },
    { view: "people" },
    { view: "leads" },
    { view: "insights" },
    { view: "library" },
    { view: "jobs", job: "2026-11-a.b_c" },
    { view: "library", path: "profile/voice.md" },
  ]) {
    assert.deepEqual(plain(helpers.parseHash(helpers.formatHash(route))), route);
  }
});

// ── Markdown ─────────────────────────────────────────────────────────────

test("markdown blocks: headings, paragraphs, rules and code", () => {
  const blocks = helpers.parseMarkdown("# One\n## Two\n### Three\n#### Four\n##### Five\n\nFirst line\nsecond line\n\n---\n\n```js\nconst a = **b**;\n```\ntail");
  assert.deepEqual(
    plain(blocks.map((block) => block.type)),
    ["heading", "heading", "heading", "heading", "paragraph", "paragraph", "rule", "code", "paragraph"]
  );
  assert.deepEqual(plain(blocks.slice(0, 4).map((block) => block.level)), [1, 2, 3, 4]);
  assert.deepEqual(plain(blocks[4].children), [{ type: "text", text: "##### Five" }]);
  assert.deepEqual(plain(blocks[5].children), [{ type: "text", text: "First line" }, { type: "break" }, { type: "text", text: "second line" }]);
  assert.deepEqual(plain(blocks[7]), { type: "code", lang: "js", text: "const a = **b**;" });
  assert.deepEqual(plain(helpers.parseMarkdown("")), []);
  assert.deepEqual(plain(helpers.parseMarkdown(null)), []);
  assert.equal(helpers.parseMarkdown("```\nnever closed\n# not a heading").length, 1);
  assert.deepEqual(plain(helpers.parseMarkdown("# C#")[0].children), [{ type: "text", text: "C#" }]);
  assert.deepEqual(plain(helpers.parseMarkdown("***\n___\n- - -").map((block) => block.type)), ["rule", "rule", "rule"]);
});

test("markdown lists: unordered, ordered and one nested level", () => {
  const [list, after] = helpers.parseMarkdown("- one\n- two\n  - inner a\n  - inner b\n    - deeper\n- three\n  continued\n\nAfter");
  assert.equal(list.type, "list");
  assert.equal(list.ordered, false);
  assert.equal(list.items.length, 3);
  assert.equal(list.items[1].list.items.length, 3, "deeper levels fold into the one nested level");
  assert.equal(list.items[1].list.items[2].list, null);
  assert.deepEqual(plain(list.items[2].children), [{ type: "text", text: "three" }, { type: "break" }, { type: "text", text: "continued" }]);
  assert.equal(after.type, "paragraph");

  const [ordered] = helpers.parseMarkdown("3. three\n4. four\n   - nested");
  assert.deepEqual(plain([ordered.ordered, ordered.start, ordered.items.length, ordered.items[1].list.ordered]), [true, 3, 2, false]);

  const mixed = helpers.parseMarkdown("Requirements:\n- a\n- b\n1. first\n2. second\nplain again");
  assert.deepEqual(
    plain(mixed.map((block) => block.type + (block.type === "list" ? ":" + block.ordered : ""))),
    ["paragraph", "list:false", "list:true", "paragraph"]
  );
  assert.equal(helpers.parseMarkdown("- a\n\n- b\n\n- c")[0].items.length, 3);
  assert.deepEqual(plain(helpers.parseMarkdown("**Bold** start\n-not a list\n2026 was a year").map((block) => block.type)), ["paragraph"]);
});

test("markdown inline: bold, italic, code and links", () => {
  assert.deepEqual(plain(helpers.parseInline("a **bold** b _it_ c *it2* d `x*y_z`")), [
    { type: "text", text: "a " },
    { type: "strong", children: [{ type: "text", text: "bold" }] },
    { type: "text", text: " b " },
    { type: "em", children: [{ type: "text", text: "it" }] },
    { type: "text", text: " c " },
    { type: "em", children: [{ type: "text", text: "it2" }] },
    { type: "text", text: " d " },
    { type: "code", text: "x*y_z" },
  ]);
  assert.deepEqual(plain(helpers.parseInline("snake_case_name and 2 * 3 * 4 and **unclosed")), [
    { type: "text", text: "snake_case_name and 2 * 3 * 4 and **unclosed" },
  ]);
  assert.deepEqual(plain(helpers.parseInline("**bold _nested_**")), [
    { type: "strong", children: [{ type: "text", text: "bold " }, { type: "em", children: [{ type: "text", text: "nested" }] }] },
  ]);
  assert.deepEqual(plain(helpers.parseInline("[site](https://northstar.example/a_b) and [mail](mailto:riley@northstar.example)")), [
    { type: "link", href: "https://northstar.example/a_b", children: [{ type: "text", text: "site" }] },
    { type: "text", text: " and " },
    { type: "link", href: "mailto:riley@northstar.example", children: [{ type: "text", text: "mail" }] },
  ]);
  assert.deepEqual(plain(helpers.parseInline("See https://northstar.example/jobs_(new)/1. Then (http://fieldwork.example/a), ok")), [
    { type: "text", text: "See " },
    { type: "link", href: "https://northstar.example/jobs_(new)/1", children: [{ type: "text", text: "https://northstar.example/jobs_(new)/1" }] },
    { type: "text", text: ". Then (" },
    { type: "link", href: "http://fieldwork.example/a", children: [{ type: "text", text: "http://fieldwork.example/a" }] },
    { type: "text", text: "), ok" },
  ]);
  assert.deepEqual(plain(helpers.parseInline("\\*not italic\\* and xhttps://a.example")), [{ type: "text", text: "*not italic* and xhttps://a.example" }]);
});

test("unsafe link targets stay text", () => {
  for (const source of [
    "[click](javascript:alert(1))",
    "[click](javascript:alert)",
    "[click](JAVASCRIPT:alert)",
    "[click](data:text/html;base64,PHNjcmlwdD4=)",
    "[click](vbscript:x)",
    "[click](//evil.example)",
    "[click](/local/path)",
    "[click](file:///etc/passwd)",
    "[click]( javascript:alert )",
  ]) {
    const nodes = helpers.parseInline(source);
    assert.deepEqual(plain(nodes), [{ type: "text", text: source }], source);
    assert.deepEqual(tags(md(source)), ["P"], source);
  }
});

test("markdown renders DOM nodes, never markup", () => {
  const host = md("# Title\n\nHello **bold** and _it_ with `code`.\n\n- one\n- two\n  1. inner\n\n2. start\n\n---\n\n```\n<b>raw</b>\n```\n\n[site](https://northstar.example) https://fieldwork.example");
  assert.deepEqual(shape(host), [
    "div",
    ["h3", "Title"],
    ["p", "Hello ", ["strong", "bold"], " and ", ["em", "it"], " with ", ["code", "code"], "."],
    ["ul", ["li", "one"], ["li", "two", ["ol", ["li", "inner"]]]],
    ["ol", ["li", "start"]],
    ["hr"],
    ["pre", ["code", "<b>raw</b>"]],
    ["p", ["a", "site"], " ", ["a", "https://fieldwork.example"]],
  ]);
  assert.equal(byTag(host, "h3")[0].className, "ja-md-h1");
  assert.equal(byTag(host, "ol")[1].getAttribute("start"), "2");
  assert.deepEqual(tags(md("# a\n## b\n### c\n#### d")), ["H3", "H4", "H5", "H6"]);
  for (const anchor of byTag(host, "a")) {
    assert.equal(anchor.getAttribute("target"), "_blank");
    assert.equal(anchor.getAttribute("rel"), "noopener noreferrer");
  }
  assert.deepEqual(
    byTag(host, "a").map((anchor) => anchor.getAttribute("href")),
    ["https://northstar.example", "https://fieldwork.example"]
  );
  assert.equal(md("").childNodes.length, 0);
});

test("raw HTML and script text never become elements", () => {
  const source = [
    "<script>alert(1)</script>",
    "",
    '<img src=x onerror="alert(1)"> and <a href="javascript:alert(1)">x</a>',
    "",
    "- <iframe src=//evil.example></iframe>",
    "",
    "## <svg onload=alert(1)>",
    "",
    "[<b>bold</b>](https://northstar.example)",
    "",
    "`<script>`",
    "",
    "[x](javascript:alert(1)) <style>*{display:none}</style>",
  ].join("\n");
  const host = md(source);
  const allowed = new Set(["P", "UL", "LI", "H4", "A", "CODE", "BR"]);
  for (const tag of tags(host)) assert.ok(allowed.has(tag), "unexpected element " + tag);
  assert.equal(byTag(host, "a").length, 1);
  assert.equal(byTag(host, "a")[0].getAttribute("href"), "https://northstar.example");
  assert.equal(byTag(host, "a")[0].textContent, "<b>bold</b>");
  const text = host.textContent;
  for (const literal of ["<script>alert(1)</script>", '<img src=x onerror="alert(1)">', "<iframe src=//evil.example></iframe>", "<svg onload=alert(1)>", "[x](javascript:alert(1))", "<style>"]) {
    assert.ok(text.includes(literal), literal);
  }
  all(host, () => true).forEach((node) => {
    Object.keys(node.attributes).forEach((name) => assert.ok(!/^on/i.test(name), name));
    assert.deepEqual(Object.keys(node.listeners), []);
  });
});

// ── Source rules ─────────────────────────────────────────────────────────

test("the script never writes markup and only the API clients call fetch", () => {
  for (const banned of ["innerHTML", "outerHTML", "insertAdjacentHTML", "document.write", "eval(", "new Function"]) {
    assert.ok(!SOURCE.includes(banned), banned);
  }
  const fetchCalls = SOURCE.split("\n").filter((line) => /\bfetch\(/.test(line));
  assert.deepEqual(
    fetchCalls.map((line) => line.trim()),
    ["return global.fetch(url, init);", "return global.fetch(url, {"]
  );
  assert.ok(!/https?:\/\/(?!…)[a-z0-9.-]+\.(com|net|io)\b/i.test(SOURCE.replace(/linkedin\.com/g, "")), "no network hosts in the script");
});

test("the interface displays; it does not direct", () => {
  const strings = SOURCE.match(/"(?:[^"\\\n]|\\.)*"/g).map((item) => item.slice(1, -1));
  const directing = strings.filter((text) => /\b(you should|should|must|remember to|don't forget|make sure|try to|consider)\b/i.test(text) && / /.test(text));
  assert.deepEqual(directing, ["JobAppsCockpit.mount needs a root element and an api client."].filter((text) => directing.includes(text)));
  for (const gone of ["Overdue", " ago", "Snooze", "Follow up in", "Close all", "Before you move on", "Read-only", "paste it into", "No strategy yet", "Mark applied", "close-stale", "reminders"]) {
    assert.ok(!SOURCE.includes(gone), gone);
  }
});

test("every style rule is scoped under .jobapps-root", () => {
  const css = STYLES.replace(/\/\*[\s\S]*?\*\//g, "");
  assert.ok(!/@import/i.test(css), "no imports");
  assert.deepEqual(css.match(/url\([^)]*\)/g), ['url("fonts/hanken-grotesk-latin.woff2")'], "the only asset is the bundled font, by a path relative to the stylesheet");
  assert.ok(fs.existsSync(path.join(DIST, "fonts", "hanken-grotesk-latin.woff2")));
  assert.match(css, /@font-face\s*\{[^}]*font-display:\s*swap/);
  const selectors = [];
  const pattern = /([^{}]+)\{/g;
  let match;
  while ((match = pattern.exec(css))) {
    const head = match[1].trim();
    if (head.startsWith("@")) {
      assert.match(head, /^@(media|container|font-face)\b/, head);
      continue;
    }
    selectors.push(...head.split(",").map((item) => item.trim()));
  }
  assert.ok(selectors.length > 150);
  for (const selector of selectors) {
    assert.match(selector, /^\.jobapps-root(?![\w-])/, selector);
    assert.ok(!/(^|[\s>+~,])(html|body|:root)\b/.test(selector), selector);
  }
  assert.match(css, /prefers-color-scheme:\s*dark/);
  assert.match(css, /\.jobapps-root\.jobapps-embedded\s*\{/);
  assert.match(css, /:focus-visible/);
  assert.ok(!/border-radius:\s*[1-9]/.test(css), "square corners");
  assert.ok(!/box-shadow|gradient\(/.test(css), "no shadows, no gradients");
});

test("the standalone page loads only local files and mounts with /api", () => {
  assert.match(INDEX_HTML, /<link rel="stylesheet" href="\/static\/style\.css">/);
  assert.match(INDEX_HTML, /<script src="\/static\/index\.js"><\/script>/);
  assert.match(INDEX_HTML, /<div id="jobapps-root"><\/div>/);
  assert.match(INDEX_HTML, /createApiClient\(\{ base: "\/api" \}\)/);
  assert.match(INDEX_HTML, /<link rel="preload" href="\/static\/fonts\/hanken-grotesk-latin\.woff2" as="font" type="font\/woff2" crossorigin>/);
  assert.ok(!/https?:\/\//.test(INDEX_HTML.replace(/xmlns='http:\/\/www\.w3\.org\/2000\/svg'/g, "")), "no network resources");
});

// ── API clients ──────────────────────────────────────────────────────────

function response(status, body, type) {
  return {
    ok: status >= 200 && status < 300,
    status,
    text: () => Promise.resolve(typeof body === "string" ? body : JSON.stringify(body)),
    blob: () => Promise.resolve({ kind: "blob", type: type || "application/pdf", body }),
  };
}

test("standalone API client: JSON in, JSON out, server errors as Error", async () => {
  const { cockpit, win } = load();
  const calls = [];
  const replies = [];
  const client = cockpit.createApiClient({
    base: "/api",
    fetch: (url, init) => {
      calls.push({ url, init });
      const reply = replies.shift();
      return reply instanceof Error ? Promise.reject(reply) : Promise.resolve(reply);
    },
  });

  replies.push(response(200, { ok: true, n: 1 }));
  assert.deepEqual(plain(await client.get("/doc", { path: "evidence/Field notes & more.md", skip: null })), { ok: true, n: 1 });
  assert.equal(calls[0].url, "/api/doc?path=evidence%2FField%20notes%20%26%20more.md");
  assert.equal(calls[0].init.method, undefined);

  replies.push(response(200, { ok: true }));
  await client.post("/jobs/a/track", { status: "applied" });
  assert.equal(calls[1].url, "/api/jobs/a/track");
  assert.equal(calls[1].init.method, "POST");
  assert.equal(calls[1].init.headers["Content-Type"], "application/json");
  assert.equal(calls[1].init.body, '{"status":"applied"}');

  replies.push(response(400, { error: "due must be a date written as YYYY-MM-DD, got 'soon'." }));
  await assert.rejects(client.post("/jobs/a/track", { due: "soon" }), (err) => {
    assert.ok(err instanceof Error || err.name === "Error");
    assert.equal(err.message, "due must be a date written as YYYY-MM-DD, got 'soon'.");
    return true;
  });
  replies.push(response(502, "<html>Bad gateway</html>"));
  await assert.rejects(client.get("/state"), { message: "The request failed (502)." });
  replies.push(new TypeError("Failed to fetch"));
  await assert.rejects(client.get("/state"), { message: "The cockpit server is not answering. Is it still running?" });

  replies.push(response(200, "%PDF", "application/pdf"));
  assert.equal(await client.fileBlobUrl("jobs/a/Jordan Example resume.pdf"), "blob:fake/1");
  assert.equal(calls[calls.length - 1].url, "/api/file?path=jobs%2Fa%2FJordan%20Example%20resume.pdf");
  assert.equal(win.blobs.created[0].blob.type, "application/pdf");
  replies.push(response(404, { error: "No such file: jobs/a/missing.pdf" }));
  await assert.rejects(client.fileBlobUrl("jobs/a/missing.pdf"), { message: "No such file: jobs/a/missing.pdf" });
  assert.equal(win.blobs.created.length, 1);
});

test("dashboard API client uses the SDK's authenticated fetches", async () => {
  const { helpers: fresh, win } = load();
  const json = [];
  const raw = [];
  const sdk = {
    fetchJSON: (url, init) => {
      json.push({ url, init });
      if (url.includes("/nope")) return Promise.reject(Object.assign(new Error("Unknown route: /nope"), { status: 404 }));
      if (url.includes("/legacy")) return Promise.reject(new Error('400: {"error":"Missing path."}'));
      return Promise.resolve({ ok: true });
    },
    authedFetch: (url, init) => {
      raw.push({ url, init });
      return Promise.resolve(url.includes("missing") ? response(404, { error: "No such file: x" }) : response(200, "%PDF"));
    },
  };
  win.fetch = () => {
    throw new Error("the dashboard client must not call window.fetch when the SDK provides authedFetch");
  };
  const client = fresh.createHermesApiClient(sdk, "/api/plugins/jobapps");

  assert.deepEqual(plain(await client.get("/state")), { ok: true });
  assert.deepEqual(plain(json[0]), { url: "/api/plugins/jobapps/state" });
  await client.get("/doc", { path: "profile/voice.md" });
  assert.equal(json[1].url, "/api/plugins/jobapps/doc?path=profile%2Fvoice.md");
  await client.post("/people", { name: "Riley Stone", why: "Leads the team." });
  assert.equal(json[2].url, "/api/plugins/jobapps/people");
  assert.deepEqual(plain(json[2].init), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: '{"name":"Riley Stone","why":"Leads the team."}',
  });
  await assert.rejects(client.get("/nope"), { message: "Unknown route: /nope" });
  await assert.rejects(client.get("/legacy"), { message: "Missing path." });

  assert.equal(await client.fileBlobUrl("jobs/a/resume.pdf"), "blob:fake/1");
  assert.deepEqual(plain(raw[0]), { url: "/api/plugins/jobapps/file?path=jobs%2Fa%2Fresume.pdf" });
  await assert.rejects(client.fileBlobUrl("jobs/a/missing.pdf"), { message: "No such file: x" });
});

test("dashboard API client falls back to a token header on older dashboards", async () => {
  const { helpers: fresh, win } = load();
  const calls = [];
  win.__HERMES_SESSION_TOKEN__ = "token-123";
  win.fetch = (url, init) => {
    calls.push({ url, init });
    return Promise.resolve(response(200, "%PDF"));
  };
  const client = fresh.createHermesApiClient({ fetchJSON: () => Promise.resolve({}) }, "/api/plugins/jobapps");
  await client.fileBlobUrl("jobs/a/resume.pdf");
  assert.deepEqual(plain(calls), [
    {
      url: "/api/plugins/jobapps/file?path=jobs%2Fa%2Fresume.pdf",
      init: { credentials: "include", headers: { "X-Hermes-Session-Token": "token-123" } },
    },
  ]);
});

// ── Mounted cockpit ──────────────────────────────────────────────────────

const TODAY = helpers.localISODate();
const day = (offset) => {
  const base = new Date();
  return helpers.localISODate(new Date(base.getFullYear(), base.getMonth(), base.getDate() + offset));
};
const NORTHSTAR = "2026-11-northstar-product-designer";
const HARBOR = "2026-11-harbor-designer";
const TIDEWATER = "2026-09-tidewater-lead-designer";
const BANNED = /Overdue|days? ago|Snooze|Follow up in|Close all|No reply for|Before you move on|Read-only|paste it into|should|Mark applied/;

function sampleState() {
  const applied = [];
  for (let i = 0; i < 25; i += 1) {
    applied.push({ job: "2026-09-applied-" + i, company: "Applied " + i, title: "Designer", stage: "applied", applied_on: day(-40 - i), updated_on: day(-40 - i) });
  }
  const due = [
    { job: HARBOR, company: "Harbor", title: "Designer", stage: "ready", next_action: "Finish the answers", due: day(1) },
    { job: NORTHSTAR, company: "Northstar", title: "Product Designer", stage: "new", next_action: "Send the portfolio", due: day(-2), priority: "high" },
    { job: TIDEWATER, company: "Tidewater", title: "Lead Designer", stage: "offer", next_action: "Reply to the offer", due: day(0) },
    { job: "2026-10-quill-staff-designer", company: "Quill", title: "Staff Designer", stage: "interviewing", next_action: "Prepare the review", due: day(3) },
    { job: "2026-09-applied-0", company: "Applied 0", title: "Designer", stage: "applied", next_action: "", due: day(2) },
    { job: "2026-09-applied-1", company: "Applied 1", title: "Designer", stage: "applied", next_action: "Check on the application", due: day(5) },
    { job: "2026-09-applied-2", company: "Applied 2", title: "Designer", stage: "applied", next_action: "Check on the application", due: day(6) },
  ];
  return {
    version: "1.0.0",
    workspace: "/tmp/example/JobApps",
    ready: true,
    as_of: TODAY,
    counts: { new: 2, ready: 1, applied: 26, interviewing: 1, offer: 1, rejected: 1, closed: 0, skipped: 0, total: 32, people: 2, leads: 2 },
    attention: {
      due: due,
      due_total: 9,
      applied_quiet: [{ job: "2026-10-fieldwork-design-engineer", company: "Fieldwork", title: "Design Engineer", applied_on: day(-12), days: 12 }],
      applied_quiet_total: 1,
      applied_stale: [{ job: "2026-09-applied-9", company: "Applied 9", title: "Designer", applied_on: day(-49), days: 49 }],
      applied_stale_total: 16,
      applied_stale_hint: "No reply for 45 days or more. Follow up once through a person, or close them so the pipeline shows what is live.",
      ready: [{ job: HARBOR, company: "Harbor", title: "Designer", stage: "ready", location: "Portland, OR", due: day(1), materials: [{ name: "resume.typ", kind: "resume", qa: "pass" }] }],
      ready_total: 1,
      people: [{ person: "jamie-chen", name: "Jamie Chen", company: "Common Ground", role: "Design Manager", status: "follow_up", next_touch: day(-1) }],
      people_total: 1,
      leads: [{ lead: "meridian-senior-designer", company: "Meridian", title: "Senior Designer", location: "Remote", found_on: day(-1), status: "new", preflight: "apply" }],
      leads_total: 2,
    },
    setup: [],
    jobs: [
      { job: NORTHSTAR, company: "Northstar", title: "Product Designer", stage: "new", location: "New York, NY", next_action: "Send the portfolio", due: day(-2), updated_on: day(-1), created_on: day(-2), priority: "high" },
      { job: "2026-11-meridian-design-engineer", company: "Meridian", title: "Design Engineer", stage: "new", location: "Remote", updated_on: day(-3), created_on: day(-3) },
      { job: HARBOR, company: "Harbor", title: "Designer", stage: "ready", location: "Portland, OR", next_action: "Finish the answers", due: day(1), updated_on: day(-4), created_on: day(-9) },
      { job: "2026-10-fieldwork-design-engineer", company: "Fieldwork", title: "Design Engineer", stage: "applied", applied_on: day(-12), updated_on: day(-12) },
      { job: "2026-10-quill-staff-designer", company: "Quill", title: "Staff Designer", stage: "interviewing", location: "Brooklyn, NY", next_action: "Prepare the review", due: day(3), updated_on: day(-6), created_on: day(-30) },
      { job: TIDEWATER, company: "Tidewater", title: "Lead Designer", stage: "offer", location: "Remote", next_action: "Reply to the offer", due: day(0), updated_on: day(-2), created_on: day(-40) },
      { job: "2026-08-lumen-designer", company: "Lumen", title: "Designer", stage: "rejected", updated_on: day(-50) },
    ].concat(applied),
    people: [
      { person: "jamie-chen", name: "Jamie Chen", company: "Common Ground", role: "Design Manager", email: "jamie@commonground.example", linkedin: "javascript:alert(1)", status: "follow_up", next_touch: day(-1) },
      { person: "sam-patel", name: "Sam Patel", company: "Fieldwork", role: "Design Lead", linkedin: "https://www.linkedin.com/in/sam-patel-example", status: "contacted", next_touch: day(4), jobs: [NORTHSTAR] },
    ],
    leads: [
      { lead: "harbor-systems-lead", company: "Harbor", title: "Design Systems Lead", location: "Portland, OR", url: "https://harbor.example/jobs/3", found_on: day(-3), status: "shortlisted", preflight: "apply" },
      { lead: "meridian-senior-designer", company: "Meridian", title: "Senior Designer", location: "Remote", url: "https://meridian.example/jobs/1", found_on: day(-1), status: "new", preflight: "pending" },
      { lead: "granite-director", company: "Granite", title: "Design Director", location: "London, UK", url: "javascript:alert(1)", found_on: day(-8), status: "new", preflight: "skip" },
    ],
    followups: {},
  };
}

function sampleJob() {
  return {
    job: { job: NORTHSTAR, company: "Northstar", title: "Product Designer", stage: "new", location: "New York, NY", url: "https://northstar.example/jobs/1", next_action: "Send the portfolio", due: day(-2), decision: "apply", created_on: day(-2), role_family: "product_design" },
    folder: "/tmp/example/JobApps/jobs/" + NORTHSTAR,
    path: "jobs/" + NORTHSTAR + "/job.md",
    sections: { posting: "Design the **planning** tools.\n\n<script>alert(1)</script>", notes: "Saved note.", log: "- Added." },
    materials: [
      { name: "resume.typ", kind: "resume", format: "typ", qa: "fail", updated_on: day(-1), path: "jobs/" + NORTHSTAR + "/resume.typ", pdf: "jobs/" + NORTHSTAR + "/resume.pdf" },
      { name: "letter.typ", kind: "cover_letter", format: "typ", qa: "pass", updated_on: day(-1), path: "jobs/" + NORTHSTAR + "/letter.typ" },
      { name: "answers.md", kind: "application_answers", format: "md", qa: "none", updated_on: day(-1), path: "jobs/" + NORTHSTAR + "/answers.md" },
      { name: "note-to-riley.md", kind: "outreach", format: "md", qa: "stale", path: "jobs/" + NORTHSTAR + "/note-to-riley.md" },
      { name: "portfolio.pdf", kind: "other", format: "pdf", qa: "none", path: "jobs/" + NORTHSTAR + "/portfolio.pdf", pdf: "jobs/" + NORTHSTAR + "/portfolio.pdf" },
    ],
    people: [{ id: "riley-stone", name: "Riley Stone", role: "Design Manager", status: "follow_up", email: "riley@northstar.example" }],
  };
}

function sampleStats() {
  return {
    as_of: TODAY,
    counts: { total: 32 },
    stats: {
      applied: 96,
      interviews: 3,
      offers: 1,
      rejected: 20,
      no_reply: 72,
      interview_rate: "3 of 96",
      median_days_to_outcome: 12,
      by_channel: [
        { channel: "cold", applied: 91, interviews: 1, rejected: 19, no_reply: 70 },
        { channel: "referral", applied: 5, interviews: 2, rejected: 1, no_reply: 2 },
      ],
      by_month: [
        { month: "2026-09", applied: 80, interviews: 1, rejected: 15, no_reply: 63 },
        { month: "2026-10", applied: 16, interviews: 2, rejected: 5, no_reply: 9 },
      ],
      by_role_family: [
        { role_family: "product_design", applied: 60, interviews: 3, rejected: 12, no_reply: 44 },
        { role_family: "unlabelled", applied: 36, interviews: 0, rejected: 8, no_reply: 28 },
      ],
    },
  };
}

function fakeApi(overrides) {
  const api = {
    calls: [],
    state: sampleState(),
    job: sampleJob(),
    stats: sampleStats(),
    why: { "jamie-chen": "Hiring manager for the staff role.", "sam-patel": "_Why this person matters to the search._" },
    fail: {},
    replies: Object.assign({}, overrides),
    gets(route) {
      return this.calls.filter((call) => call.method === "GET" && call.route === route).length;
    },
    posts() {
      return this.calls.filter((call) => call.method === "POST");
    },
    get(route, query) {
      this.calls.push({ method: "GET", route, query });
      if (this.fail[route]) return Promise.reject(new Error(this.fail[route]));
      if (route === "/state") return Promise.resolve(plain(this.state));
      if (route === "/stats") return Promise.resolve(plain(this.stats));
      if (route.startsWith("/jobs/")) {
        const detail = plain(this.job);
        detail.job.job = decodeURIComponent(route.slice(6));
        return Promise.resolve(detail);
      }
      if (route === "/evidence") {
        return Promise.resolve({
          evidence: [
            { id: "harbor-redesign", title: "Harbor redesign", type: "project", status: "active", tags: ["design"], path: "evidence/harbor-redesign.md" },
            { id: "design-system", title: "Design system", type: "project", status: "needs_review", path: "evidence/design-system.md" },
            { id: "internship", title: "Internship", type: "role", status: "retired", path: "evidence/internship.md" },
          ],
        });
      }
      if (route === "/doc" && /^people\//.test(query.path)) {
        const id = query.path.slice(7, -3);
        return Promise.resolve({ path: query.path, meta: {}, body: "# Person\n\n## Why\n\n" + (this.why[id] || "") + "\n\n## Notes\n\n## Log\n\n- Added." });
      }
      if (route === "/doc") return Promise.resolve({ path: query.path, meta: { title: "A document", tags: ["a", "b"] }, body: "# Heading\n\nBody text." });
      return Promise.reject(new Error("Unknown route: " + route));
    },
    post(route, body) {
      this.calls.push({ method: "POST", route, body });
      if (this.fail[route]) return Promise.reject(new Error(this.fail[route]));
      const reply = this.replies[route];
      return Promise.resolve(typeof reply === "function" ? reply(body) : reply || { ok: true });
    },
    fileBlobUrl(file) {
      this.calls.push({ method: "BLOB", route: file });
      return Promise.resolve("blob:fake/" + file);
    },
  };
  return api;
}

async function start(options) {
  const opts = options || {};
  const env = load(opts.setup);
  env.win.location.hash = opts.hash || "";
  env.api = opts.api || fakeApi();
  env.root = env.doc.createElement("div");
  env.doc.body.appendChild(env.root);
  env.unmount = env.cockpit.mount(env.root, { api: env.api, embedded: !!opts.embedded });
  await settle();
  env.main = byTag(env.root, "main")[0];
  return env;
}

const disc = (root, key) => byKey(root, "disc:" + key);
const formOf = (node) => {
  let current = node;
  while (current.tagName !== "FORM") current = current.parentNode;
  return current;
};
const selectedValue = (select) => select.children.filter((option) => option.selected)[0].value;

test("the shell: top bar, mark, breadcrumb and a grouped navigation rail", async () => {
  const env = await start();
  const bar = byClass(env.root, "ja-bar")[0];
  assert.equal(bar.tagName, "HEADER");
  const logo = byClass(bar, "ja-logo")[0];
  assert.equal(logo.tagName, "SVG");
  assert.deepEqual(logo.children.map((bar) => bar.getAttribute("class")), ["ja-logo-amber", "ja-logo-accent", "ja-logo-accent", "ja-logo-amber", "ja-logo-accent"]);
  assert.equal(byClass(bar, "ja-identity")[0].textContent, "JobAppsHermes");
  assert.equal(byClass(bar, "ja-crumbs")[0].textContent, "Workspace/Overview");
  assert.equal(byTag(bar, "button").length, 1, "nothing on the right: only the sidebar toggle");

  const rail = byClass(env.root, "ja-rail")[0];
  assert.equal(rail.tagName, "NAV");
  assert.deepEqual(byClass(rail, "ja-rail-label").map((el) => el.textContent), ["Daily workspace", "Explore", "Reference"]);
  const items = byClass(rail, "ja-rail-item");
  assert.deepEqual(items.map((el) => el.textContent), ["Overview", "Jobs", "People", "Leads", "Insights", "Library"]);
  items.forEach((el) => {
    assert.equal(el.children[0].tagName, "SVG");
    assert.equal(el.children[0].getAttribute("aria-hidden"), "true");
    assert.ok(el.children[0].children.length > 0, "the icon is drawn inline");
  });
  assert.equal(items[0].getAttribute("aria-current"), "page");
  assert.ok(!/\d/.test(rail.textContent), "no counts in the navigation");

  const toggle = byKey(env.root, "rail-toggle");
  const body = byClass(env.root, "ja-body")[0];
  assert.deepEqual([toggle.getAttribute("aria-expanded"), body.className], ["true", "ja-body"]);
  toggle.click();
  assert.deepEqual([toggle.getAttribute("aria-expanded"), body.className], ["false", "ja-body is-collapsed"]);
  assert.equal(env.win.localStorage.data["jobapps.rail"], "collapsed");
  toggle.click();
  assert.equal(env.win.localStorage.data["jobapps.rail"], "open");

  items[2].click();
  await settle();
  assert.equal(byClass(bar, "ja-crumb-page")[0].textContent, "People");
  assert.equal(items[2].getAttribute("aria-current"), "page");
  assert.equal(items[0].getAttribute("aria-current"), null);
  same(byClass(env.root, "ja-rail-item")[2], items[2], "the rail is not rebuilt when the page changes");
});

test("the rail remembers being collapsed and opens as an overlay on a narrow window", async () => {
  const collapsed = await start({ setup: (win) => (win.localStorage.data["jobapps.rail"] = "collapsed") });
  assert.equal(byClass(collapsed.root, "ja-body")[0].className, "ja-body is-collapsed");

  const env = await start({ setup: (win) => (win.narrow = true) });
  const toggle = byKey(env.root, "rail-toggle");
  const body = byClass(env.root, "ja-body")[0];
  assert.equal(toggle.getAttribute("aria-expanded"), "false");
  toggle.click();
  assert.deepEqual([toggle.getAttribute("aria-expanded"), body.className], ["true", "ja-body is-rail-open"]);
  assert.equal(env.win.localStorage.data["jobapps.rail"], undefined, "the overlay is not the remembered state");
  byClass(env.root, "ja-rail-backdrop")[0].click();
  assert.equal(body.className, "ja-body");
  toggle.click();
  byClass(env.root, "ja-app")[0].dispatch("keydown", { key: "Escape" });
  assert.equal(body.className, "ja-body");
  toggle.click();
  byKey(env.root, "nav:leads").click();
  await settle();
  assert.equal(body.className, "ja-body", "choosing a page closes the overlay");
});

test("overview: date, four plain numerals, one job to continue with and what is next", async () => {
  const env = await start();
  const main = env.main;
  assert.equal(byClass(main, "ja-eyebrow")[0].textContent, helpers.longDate(TODAY));
  assert.equal(byTag(main, "h1")[0].textContent, "Overview");
  assert.equal(byKey(main, "add-open").textContent, "Add a job");
  assert.ok(!byKey(main, "add-open").classList.contains("ja-btn-primary"));

  assert.deepEqual(
    byClass(main, "ja-metric").map((el) => [el.tagName, el.children[0].textContent, el.children[1].textContent]),
    [["BUTTON", "3", "In progress"], ["BUTTON", "26", "Applied"], ["BUTTON", "2", "Interviewing"], ["BUTTON", "1", "Set aside"]]
  );

  const focus = byClass(main, "ja-focus")[0];
  assert.equal(byClass(focus, "ja-eyebrow")[0].textContent, "Continue with");
  assert.equal(byClass(focus, "ja-tag")[0].textContent, "Offer");
  assert.equal(byClass(focus, "ja-focus-company")[0].textContent, "Tidewater");
  assert.equal(byTag(focus, "h2")[0].textContent, "Lead Designer");
  assert.equal(byClass(focus, "ja-focus-place")[0].textContent, "Remote");
  assert.equal(byClass(focus, "ja-next")[0].textContent, "Next stepReply to the offer");
  assert.ok(focus.textContent.includes("added " + helpers.formatDate(day(-40), TODAY)));
  assert.deepEqual(byTag(focus, "button").map((el) => [el.textContent, el.className]), [["Continue", "ja-btn ja-btn-primary"]]);
  assert.equal(byClass(env.root, "ja-btn-primary").length, 1, "one primary action on the page");

  const queue = byClass(main, "ja-queue")[0];
  assert.equal(byTag(queue, "h2")[0].textContent, "Up next");
  assert.equal(byClass(byClass(queue, "ja-queue-head")[0], "ja-meta")[0].textContent, "9");
  const rows = byClass(queue, "ja-qrow");
  assert.deepEqual(
    rows.map((row) => [byTag(row, "strong")[0].textContent, byClass(row, "ja-meta")[0].textContent, byClass(row, "ja-date")[0].textContent]),
    [
      ["Send the portfolio", "Northstar · Product Designer", helpers.formatDate(day(-2), TODAY)],
      ["Reply to the offer", "Tidewater · Lead Designer", helpers.formatDate(day(0), TODAY)],
      ["Finish the answers", "Harbor · Designer", helpers.formatDate(day(1), TODAY)],
      ["Designer", "Applied 0", helpers.formatDate(day(2), TODAY)],
      ["Prepare the review", "Quill · Staff Designer", helpers.formatDate(day(3), TODAY)],
    ]
  );
  assert.deepEqual(rows.map((row) => byClass(row, "ja-date")[0].classList.contains("is-past")), [true, false, false, false, false]);
  rows.forEach((row) => assert.equal(row.tagName, "BUTTON", "the whole row opens the job"));
  assert.equal(byKey(queue, "all-jobs").textContent, "All jobs");

  assert.ok(!BANNED.test(env.root.textContent), "no urgency, advice or quick actions");
  assert.equal(byTag(main, "input").length + byTag(main, "select").length + byTag(main, "textarea").length, 0, "no forms on the overview");
  assert.equal(env.api.posts().length, 0);

  rows[0].click();
  await settle();
  assert.equal(env.win.location.hash, "#/jobs/" + NORTHSTAR);
});

test("overview: the numerals open Jobs filtered to their group, Continue opens the job", async () => {
  const env = await start();
  byKey(env.main, "metric:interviewing").click();
  await settle();
  assert.equal(env.win.location.hash, "#/jobs");
  assert.deepEqual(byClass(env.main, "ja-jobgroup-head").map((el) => el.textContent), ["Interviewing1", "Offer1"]);
  assert.equal(all(env.main, (node) => node.getAttribute("aria-pressed") === "true")[0].textContent, "Interviewing");

  byKey(env.root, "nav:overview").click();
  await settle();
  byKey(env.main, "continue").click();
  await settle();
  assert.equal(env.win.location.hash, "#/jobs/" + TIDEWATER);
  assert.equal(byClass(env.main, "ja-detail-title")[0].textContent, "Product Designer");
});

test("overview: with nothing to continue the block says so in one phrase; setup shows as plain lines", async () => {
  const api = fakeApi();
  api.state.jobs = api.state.jobs.filter((job) => job.stage === "applied");
  api.state.attention = {};
  api.state.setup = ["Add your name and contact details to profile/profile.md."];
  const env = await start({ api });
  assert.equal(byClass(byClass(env.main, "ja-focus")[0], "ja-empty")[0].textContent, "Nothing here yet");
  assert.equal(byClass(byClass(env.main, "ja-queue")[0], "ja-empty")[0].textContent, "Nothing here yet");
  const lines = byClass(byClass(env.main, "ja-page-head")[0], "ja-meta");
  assert.deepEqual(lines.map((el) => el.textContent), ["Add your name and contact details to profile/profile.md."]);
  assert.deepEqual(byClass(env.main, "ja-disc-title").map((el) => el.textContent), ["Waiting to hear back"]);
});

test("overview disclosures are collapsed, show a count and remember being opened", async () => {
  const env = await start();
  const titles = () => byClass(env.main, "ja-disc-head").map((el) => [byClass(el, "ja-disc-title")[0].textContent, byClass(el, "ja-disc-count")[0].textContent, el.getAttribute("aria-expanded")]);
  assert.deepEqual(titles(), [
    ["Ready to send", "1", "false"],
    ["Waiting to hear back", "26", "false"],
    ["People to reach", "1", "false"],
    ["New leads", "2", "false"],
  ]);
  assert.equal(byClass(env.main, "ja-disc-body").length, 0);
  byClass(env.main, "ja-disc-head").forEach((el) => {
    assert.equal(el.tagName, "BUTTON");
    assert.equal(byClass(el, "ja-disc-sign")[0].textContent, "+");
  });

  disc(env.main, "ov:waiting").click();
  assert.equal(disc(env.main, "ov:waiting").getAttribute("aria-expanded"), "true");
  assert.equal(byClass(disc(env.main, "ov:waiting"), "ja-disc-sign")[0].textContent, "−");
  same(env.doc.activeElement, disc(env.main, "ov:waiting"), "focus stays on the disclosure");
  const body = () => byClass(env.main, "ja-disc-body")[0];
  assert.equal(byClass(body(), "ja-qrow").length, 12);
  const first = byClass(body(), "ja-qrow")[0];
  assert.deepEqual([byTag(first, "strong")[0].textContent, byClass(first, "ja-meta")[0].textContent, byClass(first, "ja-date")[0].textContent], [
    "Design Engineer",
    "Fieldwork",
    helpers.formatDate(day(-12), TODAY),
  ]);
  assert.ok(!byClass(first, "ja-date")[0].classList.contains("is-past"), "an applied date is just a date");
  assert.deepEqual(byTag(body(), "button").filter((el) => !el.classList.contains("ja-qrow")).map((el) => el.textContent), ["Show all 26"]);
  button(body(), "Show all 26").click();
  assert.equal(byClass(body(), "ja-qrow").length, 26);

  env.api.state.counts.total = 33;
  env.clock.offset += 60000;
  env.win.intervals[0].fn();
  await settle();
  assert.equal(disc(env.main, "ov:waiting").getAttribute("aria-expanded"), "true", "a refresh keeps it open");
  assert.equal(byClass(body(), "ja-qrow").length, 26);

  byKey(env.root, "nav:leads").click();
  await settle();
  byKey(env.root, "nav:overview").click();
  await settle();
  assert.deepEqual(titles().map((item) => item[2]), ["false", "true", "false", "false"], "and so does leaving the page");

  disc(env.main, "ov:people").click();
  const person = byKey(env.main, "reach:jamie-chen");
  assert.deepEqual([byTag(person, "strong")[0].textContent, byClass(person, "ja-meta")[0].textContent], ["Jamie Chen", "Design Manager · Common Ground"]);
  assert.ok(byClass(person, "ja-date")[0].classList.contains("is-past"));
  person.click();
  await settle();
  assert.equal(env.win.location.hash, "#/people");
});

test("jobs: a grouped list beside the detail of one job", async () => {
  const env = await start({ hash: "#/jobs" });
  assert.equal(byTag(env.main, "h1")[0].textContent, "Jobs");
  assert.deepEqual(byClass(env.main, "ja-chip").map((el) => [el.textContent, el.getAttribute("aria-pressed")]), [
    ["All", "true"],
    ["In progress", "false"],
    ["Applied", "false"],
    ["Interviewing", "false"],
    ["Set aside", "false"],
  ]);
  assert.deepEqual(byClass(env.main, "ja-jobgroup-head").map((el) => el.textContent), ["New2", "Ready1", "Applied26", "Interviewing1", "Offer1", "Rejected1"]);
  const rows = byClass(env.main, "ja-jobrow");
  assert.equal(rows.length, 2 + 1 + 20 + 1 + 1 + 1, "a long group shows twenty");
  assert.deepEqual(rows[0].children.map((el) => el.textContent), ["Northstar", "Product Designer", "New York, NY · " + helpers.formatDate(day(-2), TODAY)]);
  assert.equal(rows[3].children[2].textContent, helpers.formatDate(day(-12), TODAY), "an applied job shows when it was sent");
  assert.equal(rows[0].getAttribute("aria-current"), "true", "the first job is shown");
  assert.equal(env.api.gets("/jobs/" + NORTHSTAR), 1);
  assert.equal(byClass(env.main, "ja-detail-title")[0].textContent, "Product Designer");
  assert.ok(!byClass(env.main, "ja-view-jobs")[0].classList.contains("has-job"));
  assert.equal(env.win.location.hash, "#/jobs");

  button(env.main, "Show all 26").click();
  assert.equal(byClass(env.main, "ja-jobrow").length, 32);
  assert.equal(env.doc.activeElement.getAttribute("data-ja-key"), "job:2026-09-applied-19");

  const search = byKey(env.main, "jobs:query");
  type(search, "designer applied-2");
  same(byKey(env.main, "jobs:query"), search, "typing does not rebuild the search box");
  assert.deepEqual(byClass(env.main, "ja-jobrow").map((el) => el.children[0].textContent), ["Applied 2", "Applied 20", "Applied 21", "Applied 22", "Applied 23", "Applied 24"]);
  assert.deepEqual(byClass(env.main, "ja-jobgroup-head").map((el) => el.textContent), ["Applied6"]);
  type(search, "nobody at all");
  assert.equal(byClass(env.main, "ja-jobs-list")[0].textContent, "Nothing here yet");
  type(search, "");

  button(env.main, "Set aside").click();
  await settle();
  assert.deepEqual(byClass(env.main, "ja-jobgroup-head").map((el) => el.textContent), ["Rejected1"]);
  assert.equal(byClass(env.main, "ja-jobrow")[0].getAttribute("aria-current"), "true", "the shown job follows the filter");
  assert.equal(env.api.gets("/jobs/2026-08-lumen-designer"), 1);

  button(env.main, "All").click();
  byKey(env.main, "job:" + HARBOR).click();
  await settle();
  assert.equal(env.win.location.hash, "#/jobs/" + HARBOR);
  assert.equal(byKey(env.main, "job:" + HARBOR).getAttribute("aria-current"), "true");
  assert.ok(byClass(env.main, "ja-view-jobs")[0].classList.contains("has-job"));
  assert.equal(byKey(env.root, "nav:jobs").getAttribute("aria-current"), "page");
});

test("job detail: company, role, status, next step, quiet links and no boxes of controls", async () => {
  const env = await start({ hash: "#/jobs/" + NORTHSTAR });
  const detail = byClass(env.main, "ja-detail")[0];
  assert.equal(byClass(detail, "ja-eyebrow")[0].textContent, "Northstar");
  assert.equal(byClass(detail, "ja-detail-title")[0].textContent, "Product Designer");
  assert.equal(byClass(detail, "ja-detail-place")[0].textContent, "New York, NY");
  const status = byClass(detail, "ja-status")[0];
  assert.equal(status.tagName, "LABEL");
  assert.equal(byClass(status, "ja-eyebrow")[0].textContent, "Status");
  assert.deepEqual(byTag(status, "select")[0].children.map((option) => option.value), plain(helpers.STAGES));
  const posting = byTag(detail, "a").filter((a) => a.textContent === "Open posting")[0];
  assert.deepEqual([posting.getAttribute("href"), posting.getAttribute("target"), posting.getAttribute("rel")], ["https://northstar.example/jobs/1", "_blank", "noopener noreferrer"]);

  const next = byClass(detail, "ja-block")[0];
  assert.equal(byTag(next, "h3")[0].textContent, "Next step");
  assert.equal(byClass(next, "ja-next-text")[0].textContent, "Send the portfolio");
  const date = byClass(next, "ja-date")[0];
  assert.deepEqual([date.textContent, date.classList.contains("is-past")], [helpers.formatDate(day(-2), TODAY), true]);
  assert.deepEqual(byTag(next, "button").filter((el) => el.getAttribute("role") !== "menuitem").map((el) => el.textContent), ["Edit", "Copy Hermes prompt"]);

  assert.deepEqual(byTag(detail, "input").length + byTag(detail, "textarea").length, 0, "forms stay hidden until asked for");
  assert.deepEqual(byTag(detail, "select").length, 1, "the only control is the status");
  assert.equal(byClass(env.root, "ja-btn-primary").length, 0, "no primary button on this page");
  assert.ok(!BANNED.test(env.root.textContent));

  assert.deepEqual(byClass(detail, "ja-disc-head").map((el) => [byClass(el, "ja-disc-title")[0].textContent, el.getAttribute("aria-expanded")]), [
    ["Posting", "false"],
    ["Notes", "false"],
    ["People", "false"],
    ["History", "false"],
    ["Record details", "false"],
  ]);
  assert.equal(byClass(disc(detail, "job:people"), "ja-disc-count")[0].textContent, "1");
});

test("job detail: status saves at once; a blocked ready is one plain line with a quiet link", async () => {
  const api = fakeApi({
    ["/jobs/" + NORTHSTAR + "/track"]: (body) =>
      body.status === "ready" && !body.force
        ? { ok: false, blocked: [{ name: "resume.typ", qa: "fail" }, { name: "draft.typ", qa: "none" }], hint: "Run jobapps_check on these files." }
        : { ok: true, reminders: ["No one at Northstar is tracked."] },
  });
  const env = await start({ hash: "#/jobs/" + NORTHSTAR, api });
  const select = () => byKey(env.main, "stage:" + NORTHSTAR);
  select().value = "ready";
  select().dispatch("change");
  await settle();
  assert.deepEqual(plain(api.posts()[0]), { method: "POST", route: "/jobs/" + NORTHSTAR + "/track", body: { status: "ready" } });
  const line = byClass(env.main, "ja-line")[0];
  assert.equal(line.tagName, "P");
  assert.ok(line.textContent.startsWith("Not marked ready: resume.typ (needs attention), draft.typ (not checked)"));
  assert.deepEqual(byTag(line, "button").map((el) => [el.textContent, el.className]), [["Mark ready anyway", "ja-quiet"]]);
  assert.ok(!env.root.textContent.includes("jobapps_check"));
  assert.equal(selectedValue(select()), "new", "the status did not move");

  button(env.main, "Mark ready anyway").click();
  await settle();
  assert.deepEqual(plain(api.posts()[1].body), { status: "ready", force: true });
  assert.equal(byClass(env.main, "ja-line").length, 0);
  assert.ok(!env.root.textContent.includes("No one at Northstar"), "reminders from the server are not shown");

  select().value = "applied";
  select().dispatch("change");
  await settle();
  assert.deepEqual(plain(api.posts()[2].body), { status: "applied" });
  assert.equal(api.gets("/state") >= 4, true, "each save refreshes");
});

test("job detail: Edit reveals the next-step form; Save sends one request; Cancel hides it", async () => {
  const env = await start({ hash: "#/jobs/" + NORTHSTAR });
  const track = "/jobs/" + NORTHSTAR + "/track";
  const nextKey = "next:" + NORTHSTAR;
  const dueKey = "due:" + NORTHSTAR;
  assert.equal(byKey(env.main, nextKey), undefined);

  byKey(env.main, "next-edit:" + NORTHSTAR).click();
  same(env.doc.activeElement, byKey(env.main, nextKey), "the field takes focus");
  assert.deepEqual([byKey(env.main, nextKey).value, byKey(env.main, dueKey).value], ["Send the portfolio", day(-2)]);
  assert.equal(byKey(env.main, "next-edit:" + NORTHSTAR), undefined);
  assert.deepEqual(byTag(formOf(byKey(env.main, nextKey)), "button").map((el) => [el.textContent, el.className]), [["Save", "ja-btn"], ["Cancel", "ja-quiet"]]);

  type(byKey(env.main, nextKey), "Email the recruiter");
  env.api.state.counts.total = 33;
  env.clock.offset += 60000;
  env.win.intervals[0].fn();
  await settle();
  env.doc.activeElement = env.doc.body;
  env.win.intervals[0].fn();
  await settle();
  assert.equal(byKey(env.main, nextKey).value, "Email the recruiter", "an open form and its text survive a refresh");

  byKey(env.main, "next-cancel:" + NORTHSTAR).click();
  assert.equal(byKey(env.main, nextKey), undefined);
  assert.equal(byClass(env.main, "ja-next-text")[0].textContent, "Send the portfolio");
  assert.equal(env.api.posts().length, 0);

  byKey(env.main, "next-edit:" + NORTHSTAR).click();
  assert.equal(byKey(env.main, nextKey).value, "Send the portfolio", "a cancelled edit is forgotten");
  type(byKey(env.main, dueKey), "");
  const submitted = formOf(byKey(env.main, nextKey)).dispatch("submit");
  assert.equal(submitted.defaultPrevented, true);
  await settle();
  assert.deepEqual(plain(env.api.posts()), [{ method: "POST", route: track, body: { due: "" } }], "a date is removed in one request");
  assert.equal(byKey(env.main, nextKey), undefined, "the form closes after saving");

  byKey(env.main, "next-edit:" + NORTHSTAR).click();
  type(byKey(env.main, nextKey), "  Email the recruiter  ");
  type(byKey(env.main, dueKey), day(3));
  formOf(byKey(env.main, nextKey)).dispatch("submit");
  await settle();
  assert.deepEqual(plain(env.api.posts()[1].body), { next_action: "Email the recruiter", due: day(3) });

  env.api.job.job.next_action = "";
  env.api.job.job.due = "";
  env.clock.offset += 60000;
  env.win.intervals[0].fn();
  await settle();
  assert.deepEqual([byClass(env.main, "ja-next-text")[0].textContent, byClass(byClass(env.main, "ja-block")[0], "ja-date").length], ["None", 0]);
});

test("job detail: Copy Hermes prompt opens a small menu; choosing copies and says Copied", async () => {
  const env = await start({ hash: "#/jobs/" + NORTHSTAR });
  const trigger = byKey(env.main, "menu:prompts:" + NORTHSTAR);
  const menu = all(env.main, (node) => node.getAttribute("role") === "menu")[0];
  assert.deepEqual([trigger.textContent, trigger.getAttribute("aria-haspopup"), trigger.getAttribute("aria-expanded"), menu.hidden], ["Copy Hermes prompt", "menu", "false", true]);
  const items = byTag(menu, "button");
  assert.deepEqual(items.map((el) => [el.textContent, el.getAttribute("role")]), [
    ["Plan my application", "menuitem"],
    ["Tailor my resume", "menuitem"],
    ["Write the cover letter", "menuitem"],
    ["Draft outreach", "menuitem"],
    ["Prepare for the interview", "menuitem"],
  ]);
  assert.equal(byTag(menu, "p").length, 0, "no explanatory text");

  trigger.click();
  assert.deepEqual([trigger.getAttribute("aria-expanded"), menu.hidden], ["true", false]);
  same(env.doc.activeElement, items[0], "the first choice takes focus");
  menu.dispatch("keydown", { key: "ArrowDown" });
  same(env.doc.activeElement, items[1]);
  menu.dispatch("keydown", { key: "ArrowUp" });
  menu.dispatch("keydown", { key: "ArrowUp" });
  same(env.doc.activeElement, items[4]);
  menu.dispatch("keydown", { key: "Escape" });
  assert.equal(menu.hidden, true);
  same(env.doc.activeElement, trigger, "Escape returns to the link");

  trigger.click();
  env.doc.listeners.mousedown[0]({ target: byClass(env.main, "ja-detail-title")[0] });
  assert.equal(menu.hidden, true, "a click elsewhere closes it");
  trigger.click();
  env.doc.listeners.mousedown[0]({ target: items[2] });
  assert.equal(menu.hidden, false);

  items[1].click();
  await settle();
  assert.deepEqual(env.win.copied, ["Tailor my resume for Northstar, Product Designer (job " + NORTHSTAR + ")."]);
  assert.deepEqual([menu.hidden, trigger.textContent, trigger.getAttribute("aria-expanded")], [true, "Copied", "false"]);
  env.win.timeouts.splice(0).forEach((fn) => fn());
  assert.equal(trigger.textContent, "Copy Hermes prompt");
});

test("materials: a human label, a state word only when there is one, quiet links, findings beneath", async () => {
  const api = fakeApi({
    "/check": {
      ok: true,
      status: "fail",
      build: { ok: false, error: "error: unknown variable: nmae" },
      layout: { violations: [{ type: "orphan_word", page: 1, text: "systems.", fix: "Shorten the bullet." }] },
      content: { findings: [{ rule: "banned_phrase", severity: "warning", where: "bullet 2", excerpt: "passionate", fix: "Say what you did." }] },
    },
  });
  const env = await start({ hash: "#/jobs/" + NORTHSTAR, api });
  const rows = () => byClass(env.main, "ja-mat");
  assert.equal(byTag(byClass(env.main, "ja-block")[1], "h3")[0].textContent, "Materials");
  assert.deepEqual(
    rows().map((row) => [
      byClass(row, "ja-mat-name")[0].textContent,
      byClass(row, "ja-meta").map((el) => el.textContent),
      byClass(row, "ja-mat-state").map((el) => el.textContent),
      byTag(row, "button").map((el) => el.textContent),
    ]),
    [
      ["Resume", ["resume.typ", "Updated " + helpers.formatDate(day(-1), TODAY)], ["Needs attention"], ["Preview", "Source", "Check"]],
      ["Cover letter", ["letter.typ", "Updated " + helpers.formatDate(day(-1), TODAY)], ["Checked"], ["Source", "Check"]],
      ["Answers", ["answers.md", "Updated " + helpers.formatDate(day(-1), TODAY)], [], ["Source", "Check"]],
      ["Outreach", ["note-to-riley.md"], ["Changed since check"], ["Source", "Check"]],
      ["portfolio.pdf", [], [], ["Preview"]],
    ]
  );
  rows().forEach((row) => byTag(row, "button").forEach((el) => assert.equal(el.className, "ja-quiet")));
  assert.ok(!env.main.textContent.includes("Not checked"), "never checked says nothing");

  const source = "jobs/" + NORTHSTAR + "/resume.typ";
  byKey(env.main, "check:" + source).click();
  assert.deepEqual([byKey(env.main, "check:" + source).textContent, byKey(env.main, "check:" + source).getAttribute("aria-disabled")], ["Checking…", "true"]);
  await settle();
  assert.deepEqual(plain(api.posts()[0]), { method: "POST", route: "/check", body: { path: source } });
  const head = disc(rows()[0], "found:" + source);
  assert.deepEqual([byClass(head, "ja-disc-title")[0].textContent, byClass(head, "ja-disc-count")[0].textContent, head.getAttribute("aria-expanded")], ["Findings", "3", "true"]);
  assert.deepEqual(
    byTag(byClass(rows()[0], "ja-finding-list")[0], "li").map((li) => li.children.map((el) => el.textContent)),
    [["Build", "error: unknown variable: nmae"], ["Orphan word, page 1", "systems."], ["Banned phrase, bullet 2", "passionate"]]
  );
  head.click();
  assert.equal(byClass(rows()[0], "ja-finding-list").length, 0, "the findings fold away");
  assert.equal(disc(rows()[0], "found:" + source).getAttribute("aria-expanded"), "false");

  const viewer = byTag(env.root, "dialog")[1];
  byKey(env.main, "source:" + source).click();
  assert.equal(viewer.open, true);
  await settle();
  assert.equal(byTag(viewer, "pre")[0].textContent, "# Heading\n\nBody text.");
  button(viewer, "Close").click();
  assert.equal(viewer.open, false);

  const pdf = "jobs/" + NORTHSTAR + "/resume.pdf";
  byKey(env.main, "pdf:" + pdf).click();
  assert.equal(env.win.opened.length, 1, "the tab opens inside the click");
  await settle();
  assert.equal(env.win.opened[0].tab.location.href, "blob:fake/" + pdf);
  byKey(env.main, "pdf:" + pdf).click();
  await settle();
  assert.deepEqual(env.win.blobs.revoked, ["blob:fake/" + pdf], "the replaced object URL is revoked");
  env.unmount();
  assert.deepEqual(env.win.blobs.revoked, ["blob:fake/" + pdf, "blob:fake/" + pdf]);
});

test("job disclosures: posting, assessment with subsections, notes, people, history, record details", async () => {
  const api = fakeApi();
  Object.assign(api.job.sections, {
    assessment: "- Decision: apply",
    strategy: "**Thesis:** field-first.",
    application_questions: "- Why Northstar?",
    research: "Series B.",
  });
  api.job.job.priority = "high";
  api.job.job.referral = "Riley Stone";
  api.job.job.applied_on = day(-1);
  const env = await start({ hash: "#/jobs/" + NORTHSTAR, api });
  const detail = () => byClass(env.main, "ja-detail")[0];
  assert.deepEqual(byClass(detail(), "ja-disc-title").map((el) => el.textContent), ["Posting", "Assessment", "Research", "Notes", "People", "History", "Record details"]);
  const bodyOf = (key) => byClass(disc(detail(), key).parentNode, "ja-disc-body")[0];

  disc(detail(), "job:posting").click();
  assert.equal(byTag(bodyOf("job:posting"), "strong")[0].textContent, "planning");
  assert.equal(byTag(bodyOf("job:posting"), "script").length, 0);
  assert.ok(bodyOf("job:posting").textContent.includes("<script>alert(1)</script>"));

  disc(detail(), "job:assessment").click();
  assert.deepEqual(byTag(bodyOf("job:assessment"), "h4").map((el) => el.textContent), ["Strategy", "Application questions"], "requirements are absent, so they are omitted");
  const text = bodyOf("job:assessment").textContent;
  assert.ok(text.indexOf("Decision: apply") < text.indexOf("Thesis:") && text.indexOf("Thesis:") < text.indexOf("Why Northstar?"));
  assert.ok(!/No strategy|thesis, proof|keeps every document/i.test(env.root.textContent));

  disc(detail(), "job:notes").click();
  assert.equal(byClass(bodyOf("job:notes"), "ja-md")[0].textContent, "Saved note.");
  assert.equal(byTag(bodyOf("job:notes"), "textarea").length, 0);
  byKey(env.main, "notes-edit:" + NORTHSTAR).click();
  const notes = byKey(env.main, "notes:" + NORTHSTAR);
  assert.deepEqual([notes.tagName, notes.value, env.doc.activeElement === notes], ["TEXTAREA", "Saved note.", true]);
  type(notes, "Saved note.\nAsk about the team.");
  formOf(notes).dispatch("submit");
  await settle();
  assert.deepEqual(plain(api.posts()[0]), { method: "POST", route: "/jobs/" + NORTHSTAR + "/notes", body: { text: "Saved note.\nAsk about the team." } });
  assert.equal(byKey(env.main, "notes:" + NORTHSTAR), undefined, "the editor closes after saving");
  byKey(env.main, "notes-edit:" + NORTHSTAR).click();
  type(byKey(env.main, "notes:" + NORTHSTAR), "discard me");
  byKey(env.main, "notes-cancel:" + NORTHSTAR).click();
  assert.equal(byClass(bodyOf("job:notes"), "ja-md")[0].textContent, "Saved note.");

  disc(detail(), "job:people").click();
  assert.ok(bodyOf("job:people").textContent.includes("Riley Stone"));
  assert.equal(byTag(bodyOf("job:people"), "a")[0].getAttribute("href"), "mailto:riley@northstar.example");

  disc(detail(), "job:history").click();
  assert.equal(bodyOf("job:history").textContent, "Added.");

  disc(detail(), "job:record").click();
  const record = bodyOf("job:record");
  assert.deepEqual(byTag(record, "dt").map((el) => el.textContent), ["Job", "Folder", "Added", "Applied", "Blocker check", "Role family"]);
  assert.deepEqual(
    byTag(record, "dd").map((el) => el.children[0].textContent),
    [NORTHSTAR, "/tmp/example/JobApps/jobs/" + NORTHSTAR, helpers.formatDate(day(-2), TODAY), helpers.formatDate(day(-1), TODAY), "Apply", "Product design"]
  );
  byKey(record, "copy-folder:" + NORTHSTAR).click();
  await settle();
  assert.deepEqual(env.win.copied, ["/tmp/example/JobApps/jobs/" + NORTHSTAR]);

  const priority = byKey(record, "priority:" + NORTHSTAR);
  assert.deepEqual(priority.children.map((option) => [option.value, option.textContent]), [["high", "High"], ["normal", "Normal"], ["low", "Low"]]);
  assert.equal(selectedValue(priority), "high");
  assert.equal(byKey(record, "referral:" + NORTHSTAR).value, "Riley Stone");
  formOf(priority).dispatch("submit");
  await settle();
  assert.equal(api.posts().length, 1, "nothing changed, nothing sent");
  priority.value = "normal";
  priority.dispatch("change");
  type(byKey(env.main, "referral:" + NORTHSTAR), "  ");
  formOf(byKey(env.main, "referral:" + NORTHSTAR)).dispatch("submit");
  await settle();
  assert.deepEqual(plain(api.posts()[1]), { method: "POST", route: "/jobs/" + NORTHSTAR + "/track", body: { priority: "normal", referral: "" } });

  byKey(env.main, "job:" + HARBOR).click();
  await settle();
  assert.equal(disc(detail(), "job:record").getAttribute("aria-expanded"), "true", "an opened section stays open for the next job");
  assert.ok(!/High priority|Referred by/.test(env.root.textContent));
});

test("on a narrow stage the list and the job are separate panes with a way back", async () => {
  const env = await start({ hash: "#/jobs" });
  byClass(env.root, "ja-stage")[0].clientWidth = 390;
  button(env.main, "All").click();
  assert.equal(all(env.main, (node) => node.getAttribute("aria-current") === "true").length, 0, "with no job open or read, no row is marked");
  env.win.pageYOffset = 640;
  byKey(env.main, "job:" + HARBOR).click();
  await settle();
  assert.equal(env.win.pageYOffset, 0, "the job opens at its top");
  assert.ok(byClass(env.main, "ja-view-jobs")[0].classList.contains("has-job"));
  const back = byKey(env.main, "jobs-back");
  assert.deepEqual([back.textContent, back.className], ["All jobs", "ja-quiet ja-back"]);
  back.click();
  await settle();
  assert.equal(env.win.location.hash, "#/jobs");
  assert.equal(env.win.pageYOffset, 640, "the list returns to where it was");
  assert.ok(!byClass(env.main, "ja-view-jobs")[0].classList.contains("has-job"));
  assert.equal(byKey(env.main, "job:" + HARBOR).getAttribute("aria-current"), "true", "the job just read stays marked");
});

test("refresh keeps the page, the open dialog and unsaved text; it waits while a field has focus", async () => {
  const env = await start({ hash: "#/jobs/" + NORTHSTAR });
  byKey(env.main, "next-edit:" + NORTHSTAR).click();
  const field = byKey(env.main, "next:" + NORTHSTAR);
  type(field, "half-written thought");
  byKey(env.root, "nav:overview").click();
  await settle();
  byKey(env.main, "add-open").click();
  const dialog = byTag(env.root, "dialog")[0];
  type(byKey(dialog, "add:company"), "Fieldwork");
  byKey(env.root, "nav:jobs").click();
  await settle();
  assert.equal(env.win.location.hash, "#/jobs", "the job read last is shown without changing the address");
  const again = byKey(env.main, "next:" + NORTHSTAR);
  assert.equal(again.value, "half-written thought");
  again.focus();

  env.api.job.job.stage = "applied";
  env.clock.offset += 60000;
  env.win.emit("focus");
  await settle();
  same(byKey(env.main, "next:" + NORTHSTAR), again, "the field being typed in is left alone");
  assert.equal(selectedValue(byKey(env.main, "stage:" + NORTHSTAR)), "new");
  env.doc.activeElement = env.doc.body;
  again.dispatch("focusout");
  env.win.timeouts.splice(0).forEach((fn) => fn());
  assert.equal(selectedValue(byKey(env.main, "stage:" + NORTHSTAR)), "applied");
  assert.equal(byKey(env.main, "next:" + NORTHSTAR).value, "half-written thought");
  assert.equal(dialog.open, true);
  assert.equal(byKey(dialog, "add:company").value, "Fieldwork");
});

test("refresh runs on focus and every 20 seconds while visible, and skips unchanged data", async () => {
  const env = await start();
  assert.equal(env.win.intervals[0].ms, 20000);
  assert.equal(env.api.gets("/state"), 1);
  const before = env.main.childNodes[0];
  env.win.intervals[0].fn();
  await settle();
  assert.equal(env.api.gets("/state"), 1, "a refresh that just ran is not repeated");
  env.clock.offset += 21000;
  env.win.intervals[0].fn();
  await settle();
  assert.equal(env.api.gets("/state"), 2);
  same(env.main.childNodes[0], before, "unchanged data does not rebuild the view");
  env.clock.offset += 21000;
  env.doc.hidden = true;
  env.win.intervals[0].fn();
  env.win.emit("focus");
  await settle();
  assert.equal(env.api.gets("/state"), 2, "nothing is fetched while the tab is hidden");
  env.doc.hidden = false;
  env.doc.listeners.visibilitychange[0]();
  await settle();
  assert.equal(env.api.gets("/state"), 3);
});

test("a failed request shows one plain line with Retry and keeps the page", async () => {
  const env = await start({ hash: "#/jobs/" + NORTHSTAR });
  const banner = () => all(env.root, (node) => node.getAttribute("role") === "alert")[0];
  assert.equal(banner(), undefined);
  env.api.fail["/jobs/" + NORTHSTAR + "/track"] = "The job file is locked.";
  const select = byKey(env.main, "stage:" + NORTHSTAR);
  select.value = "applied";
  select.dispatch("change");
  await settle();
  assert.ok(banner().textContent.includes("The job file is locked."));
  assert.deepEqual(byTag(banner(), "button").map((el) => [el.textContent, el.className]), [["Retry", "ja-quiet"], ["Dismiss", "ja-quiet"]]);
  delete env.api.fail["/jobs/" + NORTHSTAR + "/track"];
  button(banner(), "Retry").click();
  await settle();
  assert.equal(env.api.posts().length, 2);
  assert.equal(banner(), undefined);

  env.api.fail["/state"] = "The cockpit server is not answering. Is it still running?";
  env.clock.offset += 60000;
  env.win.emit("focus");
  await settle();
  assert.ok(banner().textContent.includes("not answering"));
  assert.ok(env.main.textContent.includes("Northstar"), "the last good data stays on screen");
  button(banner(), "Dismiss").click();
  assert.equal(banner(), undefined);
});

test("a first load that fails can be retried", async () => {
  const api = fakeApi();
  api.fail["/state"] = "Workspace settings.json is not valid JSON.";
  const env = await start({ api });
  assert.ok(env.main.textContent.includes("The workspace could not be loaded"));
  const banner = all(env.root, (node) => node.getAttribute("role") === "alert")[0];
  delete api.fail["/state"];
  button(banner, "Retry").click();
  await settle();
  assert.equal(byTag(env.main, "h1")[0].textContent, "Overview");
});

test("people: plain numerals, filters, quiet rows with the reason, and nothing to type into", async () => {
  const env = await start({ hash: "#/people" });
  const main = env.main;
  assert.equal(byTag(main, "h1")[0].textContent, "People");
  assert.deepEqual(byClass(env.root, "ja-btn-primary").map((el) => el.textContent), ["Add person"]);
  assert.deepEqual(byClass(main, "ja-metric").map((el) => [el.tagName, byTag(el, "dt")[0].textContent, byTag(el, "dd")[0].textContent]), [
    ["DIV", "People", "2"],
    ["DIV", "To contact", "0"],
    ["DIV", "Follow up", "1"],
    ["DIV", "Contacted", "1"],
  ]);
  assert.deepEqual(byClass(main, "ja-chip").map((el) => el.textContent), ["All", "To contact", "Follow up", "Contacted", "Replied", "Paused"]);
  assert.deepEqual(env.api.calls.filter((call) => call.route === "/doc").map((call) => call.query.path), ["people/jamie-chen.md", "people/sam-patel.md"]);

  const rows = () => byClass(main, "ja-person");
  assert.equal(rows().length, 2);
  const jamie = rows()[0];
  assert.equal(byClass(jamie, "ja-person-name")[0].textContent, "Jamie Chen");
  assert.deepEqual([byClass(jamie, "ja-tag")[0].textContent, byClass(jamie, "ja-tag")[0].className], ["Follow up", "ja-tag ja-tone-warn"]);
  assert.ok(byClass(jamie, "ja-person-meta")[0].textContent.startsWith("Design Manager · Common Ground"));
  assert.deepEqual(byTag(jamie, "a").map((a) => [a.textContent, a.getAttribute("href")]), [["Email", "mailto:jamie@commonground.example"]], "an unsafe LinkedIn value is not linked");
  assert.equal(byClass(jamie, "ja-person-why")[0].textContent, "Hiring manager for the staff role.");
  const date = byClass(jamie, "ja-person-date")[0];
  assert.deepEqual([date.textContent, date.classList.contains("is-past")], [helpers.formatDate(day(-1), TODAY), true]);
  assert.deepEqual(byTag(jamie, "button").map((el) => [el.textContent, el.className]), [["Edit", "ja-quiet"], ["Copy prompt", "ja-quiet"]]);
  const sam = rows()[1];
  assert.equal(byClass(sam, "ja-person-why").length, 0, "a placeholder reason is not shown");
  assert.equal(byTag(sam, "a")[0].getAttribute("href"), "https://www.linkedin.com/in/sam-patel-example");
  assert.ok(!byClass(sam, "ja-person-date")[0].classList.contains("is-past"));
  assert.equal(byTag(byTag(main, "ul")[0], "input").length + byTag(main, "select").length + byTag(main, "textarea").length, 0, "no always-visible controls in the list");
  assert.ok(!BANNED.test(env.root.textContent));

  button(jamie, "Copy prompt").click();
  await settle();
  assert.deepEqual(env.win.copied, ["Draft a note to Jamie Chen, Design Manager at Common Ground (person jamie-chen)."]);
  assert.equal(button(jamie, "Copied").tagName, "BUTTON");

  const search = byKey(main, "people:query");
  type(search, "fieldwork");
  assert.deepEqual(byClass(main, "ja-person-name").map((el) => el.textContent), ["Sam Patel"]);
  type(search, "");
  button(main, "Follow up").click();
  assert.deepEqual(byClass(env.main, "ja-person-name").map((el) => el.textContent), ["Jamie Chen"]);
  button(env.main, "Paused").click();
  assert.equal(byClass(env.main, "ja-people")[0].textContent, "Nothing here yet");

  env.clock.offset += 60000;
  env.win.intervals[0].fn();
  await settle();
  assert.equal(env.api.calls.filter((call) => call.route === "/doc").length, 2, "reasons are read once, not on every refresh");
});

test("people: Edit and Add person open the same dialog; saving sends what changed", async () => {
  const api = fakeApi({ "/people": (body) => ({ ok: true, created: !body.person, person: { person: body.person || "alex-reed", name: body.name || "Jamie Chen" } }) });
  const env = await start({ hash: "#/people", api });
  const dialog = byTag(env.root, "dialog")[2];
  const field = (name) => byKey(dialog, "pf:" + name);

  byKey(env.main, "person-edit:jamie-chen").click();
  assert.equal(dialog.open, true);
  assert.equal(byTag(dialog, "h2")[0].textContent, "Edit person");
  same(env.doc.activeElement, field("name"));
  assert.deepEqual(byClass(dialog, "ja-label").map((el) => el.textContent), ["Name", "Company", "Role", "Email", "LinkedIn", "Why", "Status", "Next touch", "Note"]);
  assert.deepEqual(
    ["name", "company", "role", "email", "why", "next_touch", "note"].map((name) => field(name).value),
    ["Jamie Chen", "Common Ground", "Design Manager", "jamie@commonground.example", "Hiring manager for the staff role.", day(-1), ""]
  );
  assert.equal(selectedValue(field("status")), "follow_up");

  formOf(field("name")).dispatch("submit");
  await settle();
  assert.equal(api.posts().length, 0, "nothing changed, nothing sent");
  assert.equal(dialog.open, false);

  byKey(env.main, "person-edit:jamie-chen").click();
  field("status").value = "contacted";
  field("status").dispatch("change");
  type(field("next_touch"), "");
  type(field("note"), "Spoke on the phone.");
  type(field("role"), "Design Director");
  formOf(field("name")).dispatch("submit");
  assert.equal(button(dialog, "Saving…").getAttribute("aria-disabled"), "true");
  await settle();
  assert.deepEqual(plain(api.posts()[0]), {
    method: "POST",
    route: "/people",
    body: { role: "Design Director", status: "contacted", next_touch: "", note: "Spoke on the phone.", person: "jamie-chen" },
  });
  assert.equal(dialog.open, false);
  assert.equal(api.calls.filter((call) => call.route === "/doc" && call.query.path === "people/jamie-chen.md").length, 2, "the saved person's reason is read again");

  button(env.main, "Add person").click();
  assert.equal(byTag(dialog, "h2")[0].textContent, "Add person");
  assert.deepEqual(["name", "why", "note"].map((name) => field(name).value), ["", "", ""], "the form starts empty");
  type(field("name"), "Alex Reed");
  formOf(field("name")).dispatch("submit");
  await settle();
  assert.equal(byClass(dialog, "ja-form-error")[0].textContent, "Missing: name and why");
  assert.equal(field("name").value, "Alex Reed");
  type(field("why"), "Former teammate.");
  type(field("email"), "alex@northstar.example");
  formOf(field("name")).dispatch("submit");
  await settle();
  assert.deepEqual(plain(api.posts()[1].body), { name: "Alex Reed", email: "alex@northstar.example", why: "Former teammate." });
  assert.equal(dialog.open, false);

  api.fail["/people"] = "email must be an address containing @.";
  button(env.main, "Add person").click();
  type(field("name"), "Sam Park");
  type(field("why"), "Referral.");
  formOf(field("name")).dispatch("submit");
  await settle();
  assert.equal(byClass(dialog, "ja-form-error")[0].textContent, "email must be an address containing @.");
  assert.equal(dialog.open, true);
  assert.equal(button(dialog, "Save").getAttribute("aria-disabled"), null);
  button(dialog, "Cancel").click();
  assert.equal(dialog.open, false);
});

test("leads: quiet rows, a word only when the blocker check is not apply, four quiet links", async () => {
  const api = fakeApi({
    "/leads/meridian-senior-designer": (body) =>
      body.status === "promote" ? { ok: true, job: { job: NORTHSTAR, company: "Meridian", title: "Senior Designer" }, preflight: { decision: "apply", blockers: [] } } : { ok: true },
    "/leads/granite-director": { ok: false, needs: "posting_text", hint: "Provide the full job description." },
  });
  const env = await start({ hash: "#/leads", api });
  assert.equal(byTag(env.main, "h1")[0].textContent, "Leads");
  assert.deepEqual(byClass(env.main, "ja-chip").map((el) => el.textContent), ["All", "Shortlisted"]);
  const rows = () => byClass(env.main, "ja-lead");
  assert.deepEqual(
    rows().map((row) => [
      byClass(row, "ja-jobrow-company")[0].textContent,
      byClass(row, "ja-jobrow-title")[0].textContent,
      byClass(row, "ja-meta")[0].textContent,
      byClass(row, "ja-tag").map((el) => el.textContent),
      byClass(row, "ja-quiet").map((el) => el.textContent),
    ]),
    [
      ["Harbor", "Design Systems Lead", "Portland, OR · found " + helpers.formatDate(day(-3), TODAY), [], ["Open posting", "Start", "Dismiss"]],
      ["Meridian", "Senior Designer", "Remote · found " + helpers.formatDate(day(-1), TODAY), ["Check"], ["Open posting", "Shortlist", "Start", "Dismiss"]],
      ["Granite", "Design Director", "London, UK · found " + helpers.formatDate(day(-8), TODAY), ["Blocked"], ["Shortlist", "Start", "Dismiss"]],
    ]
  );
  assert.equal(byTag(rows()[0], "a")[0].getAttribute("href"), "https://harbor.example/jobs/3");
  assert.equal(byClass(env.root, "ja-btn").length, 0, "every action is a quiet link");

  button(rows()[1], "Shortlist").click();
  await settle();
  button(rows()[1], "Dismiss").click();
  await settle();
  assert.deepEqual(plain(api.posts().map((call) => [call.route, call.body])), [
    ["/leads/meridian-senior-designer", { status: "shortlisted" }],
    ["/leads/meridian-senior-designer", { status: "dismissed" }],
  ]);

  button(rows()[2], "Start").click();
  await settle();
  assert.equal(byTag(env.main, "h1")[0].textContent, "Leads");
  const notice = all(env.root, (node) => node.getAttribute("role") === "status" && node.classList.contains("ja-notice"))[0];
  assert.equal(byClass(notice, "ja-notice-text")[0].textContent, "Missing: posting text");
  assert.ok(!env.root.textContent.includes("Provide the full job description"));

  button(env.main, "Shortlisted").click();
  assert.deepEqual(byClass(env.main, "ja-jobrow-title").map((el) => el.textContent), ["Design Systems Lead"]);
  button(env.main, "All").click();
  button(rows()[1], "Start").click();
  await settle();
  assert.deepEqual(plain(api.posts().pop().body), { status: "promote" });
  assert.equal(env.win.location.hash, "#/jobs/" + NORTHSTAR);
});

test("insights: plain numerals, one caption and three plain tables", async () => {
  const env = await start({ hash: "#/insights" });
  assert.equal(env.api.gets("/stats"), 1);
  assert.equal(byTag(env.main, "h1")[0].textContent, "Insights");
  assert.deepEqual(byClass(env.main, "ja-metric").map((el) => [byTag(el, "dt")[0].textContent, byTag(el, "dd")[0].textContent]), [
    ["Sent", "96"],
    ["Interviews", "3"],
    ["Offers", "1"],
    ["Rejected", "20"],
    ["No reply", "72"],
  ]);
  assert.equal(byClass(env.main, "ja-caption")[0].textContent, "3 of 96 reached an interview · Median 12 days to an outcome");
  assert.deepEqual(byClass(env.main, "ja-h2").map((el) => el.textContent), ["By month", "By role family", "Referral and cold"]);

  const tables = byTag(env.main, "table");
  for (const table of tables) {
    const head = byTag(byTag(table, "thead")[0], "th");
    assert.deepEqual(head.map((th) => th.textContent).slice(1), ["Sent", "Interviews", "Rejected", "No reply"]);
    head.forEach((th) => assert.equal(th.getAttribute("scope"), "col"));
    byTag(byTag(table, "tbody")[0], "tr").forEach((tr) => assert.equal(tr.children[0].getAttribute("scope"), "row"));
  }
  const cells = (table) => byTag(byTag(table, "tbody")[0], "tr").map((tr) => tr.children.map((cell) => cell.textContent));
  assert.deepEqual(cells(tables[0]), [["Sep 2026", "80", "1", "15", "63"], ["Oct 2026", "16", "2", "5", "9"]]);
  assert.deepEqual(cells(tables[1]), [["Product design", "60", "3", "12", "44"], ["Unlabelled", "36", "0", "8", "28"]]);
  assert.deepEqual(cells(tables[2]), [["Cold", "91", "1", "19", "70"], ["Referral", "5", "2", "1", "2"]]);
  const bars = byClass(tables[0], "ja-meter-fill");
  assert.deepEqual(bars.map((bar) => bar.getAttribute("style")), ["width:100%", "width:20%"]);
  bars.forEach((bar) => assert.equal(bar.parentNode.getAttribute("aria-hidden"), "true"));
  assert.ok(!/compared with|referred applications|%/.test(env.main.textContent), "no comparison or advice");

  env.api.stats.stats.applied = 97;
  env.clock.offset += 60000;
  env.win.intervals[0].fn();
  await settle();
  assert.equal(byTag(byClass(env.main, "ja-metric")[0], "dd")[0].textContent, "97", "insights refresh with the page");
});

test("insights: empty and failed states are one plain line", async () => {
  const api = fakeApi();
  api.stats.stats = { applied: 0, interviews: 0, offers: 0, rejected: 0, no_reply: 0, by_channel: [], by_month: [], by_role_family: [] };
  const env = await start({ hash: "#/insights", api });
  assert.equal(byClass(env.main, "ja-empty")[0].textContent, "Nothing here yet");
  assert.equal(byTag(env.main, "table").length + byClass(env.main, "ja-metric").length, 0);

  const broken = fakeApi();
  broken.fail["/stats"] = "The figures could not be computed.";
  const other = await start({ hash: "#/insights", api: broken });
  assert.ok(other.main.textContent.includes("The figures could not be computed."));
  delete broken.fail["/stats"];
  button(other.main, "Retry").click();
  await settle();
  assert.equal(byClass(other.main, "ja-metric").length, 5);
});

test("library: a quiet list, the rendered document, its details and its path", async () => {
  const env = await start({ hash: "#/library" });
  assert.equal(byTag(env.main, "h1")[0].textContent, "Library");
  const items = () => byClass(env.main, "ja-lib-item");
  assert.deepEqual(items().map((el) => el.children.map((child) => child.textContent)), [
    ["Profile"],
    ["Voice"],
    ["Playbook"],
    ["Harbor redesign", "Project"],
    ["Design system", "Project · Needs review"],
    ["Internship", "Role · Retired"],
  ]);
  assert.deepEqual(items().map((el) => el.classList.contains("is-dim")), [false, false, false, false, false, true]);
  assert.equal(byClass(env.main, "ja-lib-label")[0].textContent, "Evidence");
  assert.equal(items()[0].getAttribute("aria-current"), "true");
  const doc = byClass(env.main, "ja-doc")[0];
  assert.equal(byTag(doc, "h3")[0].textContent, "Heading");
  assert.deepEqual(byTag(doc, "dt").map((el) => el.textContent), ["Tags"]);
  assert.deepEqual(byTag(doc, "dd").map((el) => el.textContent), ["a, b"]);
  assert.equal(byClass(doc, "ja-path")[0].textContent, "/tmp/example/JobApps/profile/profile.md");
  assert.equal(byTag(doc, "textarea").length + byTag(doc, "input").length, 0);
  assert.ok(!BANNED.test(env.root.textContent));
  assert.deepEqual(byTag(doc, "p").map((p) => p.textContent), ["Body text.", "/tmp/example/JobApps/profile/profile.mdCopy"], "no explanatory sentence");

  byKey(doc, "copy-doc").click();
  await settle();
  assert.deepEqual(env.win.copied, ["/tmp/example/JobApps/profile/profile.md"]);

  items()[3].click();
  await settle();
  assert.equal(env.win.location.hash, "#/library/evidence/harbor-redesign.md");
  assert.equal(items()[3].getAttribute("aria-current"), "true");
  env.api.fail["/doc"] = "No such file: profile/voice.md";
  items()[1].click();
  await settle();
  assert.equal(byClass(env.main, "ja-doc")[0].textContent, "No such file: profile/voice.md");
});

test("add job: four fields with placeholders, one primary action, the answer in plain lines", async () => {
  const answers = [
    { ok: false, needs: "posting_text", hint: "This URL is not a supported ATS page." },
    { ok: true, job: { job: NORTHSTAR, company: "Northstar", title: "Product Designer" }, preflight: { decision: "pending", blockers: [{ area: "seniority", severity: "flag", evidence: "8+ years", action: "Check the level." }] } },
    { ok: true, duplicate: true, job: { job: NORTHSTAR, company: "Northstar", title: "Product Designer" } },
  ];
  const api = fakeApi({ "/jobs": () => answers.shift() });
  const env = await start({ api });
  const dialog = byTag(env.root, "dialog")[0];
  const submit = () => byTag(dialog, "form")[0].dispatch("submit");

  byKey(env.main, "add-open").click();
  assert.equal(dialog.open, true);
  assert.equal(byTag(dialog, "h2")[0].textContent, "Add a job");
  assert.equal(env.doc.activeElement.getAttribute("data-ja-key"), "add:url");
  assert.deepEqual(
    ["add:url", "add:company", "add:title", "add:text"].map((key) => [byKey(dialog, key).tagName, byKey(dialog, key).getAttribute("placeholder"), byKey(dialog, key).getAttribute("aria-label")]),
    [["INPUT", "Link to the posting", "Link"], ["INPUT", "Company", "Company"], ["INPUT", "Title", "Title"], ["TEXTAREA", "Posting text", "Posting text"]]
  );
  assert.equal(byTag(dialog, "p").length, 0, "no helper paragraphs");
  assert.deepEqual(byTag(dialog, "button").map((el) => [el.textContent, el.className]), [["Add", "ja-btn ja-btn-primary"], ["Close", "ja-quiet"]]);

  submit();
  assert.deepEqual(byClass(dialog, "ja-line").map((el) => el.textContent), ["Missing: a link or the posting text"]);
  type(byKey(dialog, "add:text"), "We are hiring a designer.");
  submit();
  assert.deepEqual(byClass(dialog, "ja-line").map((el) => el.textContent), ["Missing: company and title"]);
  assert.equal(api.posts().length, 0);

  type(byKey(dialog, "add:text"), "");
  type(byKey(dialog, "add:url"), " https://northstar.example/jobs/1 ");
  submit();
  assert.equal(button(dialog, "Adding…").getAttribute("aria-disabled"), "true");
  await settle();
  assert.deepEqual(plain(api.posts()[0]), { method: "POST", route: "/jobs", body: { url: "https://northstar.example/jobs/1", company: "", title: "", text: "" } });
  assert.deepEqual(byClass(dialog, "ja-line").map((el) => el.textContent), ["Missing: posting text"]);
  assert.ok(!dialog.textContent.includes("supported ATS"), "the server's instructions are not shown");
  assert.equal(byKey(dialog, "add:url").value, " https://northstar.example/jobs/1 ", "the form keeps what was typed");

  type(byKey(dialog, "add:company"), "Northstar");
  type(byKey(dialog, "add:title"), "Product Designer");
  type(byKey(dialog, "add:text"), "We are hiring a designer.");
  submit();
  await settle();
  assert.deepEqual(byClass(dialog, "ja-line").map((el) => el.textContent), ["Added Northstar, Product Designer", "Blocker check: Pending. Seniority: 8+ years"]);
  assert.equal(byKey(dialog, "add:company").value, "", "a saved job clears the form");
  assert.equal(byKey(dialog, "add-open-job").className, "ja-quiet");

  type(byKey(dialog, "add:url"), "https://northstar.example/jobs/1");
  submit();
  await settle();
  assert.deepEqual(byClass(dialog, "ja-line").map((el) => el.textContent), ["Already here: Northstar, Product Designer"]);
  button(dialog, "Open job").click();
  await settle();
  assert.equal(dialog.open, false);
  assert.equal(env.win.location.hash, "#/jobs/" + NORTHSTAR);

  api.fail["/jobs"] = "The posting could not be saved.";
  byKey(env.root, "nav:overview").click();
  await settle();
  byKey(env.main, "add-open").click();
  type(byKey(dialog, "add:url"), "https://fieldwork.example/jobs/9");
  submit();
  await settle();
  assert.deepEqual(byClass(dialog, "ja-line").map((el) => el.textContent), ["The posting could not be saved."]);
  assert.equal(dialog.open, true);
});

test("the address follows the page in standalone mode, and the old addresses still open", async () => {
  const env = await start();
  assert.deepEqual(env.win.replaced, ["#/overview"]);
  for (const [view, hash] of [["jobs", "#/jobs"], ["people", "#/people"], ["leads", "#/leads"], ["insights", "#/insights"], ["library", "#/library"], ["overview", "#/overview"]]) {
    byKey(env.root, "nav:" + view).click();
    await settle();
    assert.equal(env.win.location.hash, hash);
  }
  env.win.location.hash = "#/job/" + HARBOR;
  env.win.emit("hashchange");
  await settle();
  assert.equal(byKey(env.main, "job:" + HARBOR).getAttribute("aria-current"), "true");

  const today = await start({ hash: "#/today" });
  assert.equal(byTag(today.main, "h1")[0].textContent, "Overview");
  assert.deepEqual(today.win.replaced, ["#/overview"]);
  const pipeline = await start({ hash: "#/pipeline" });
  assert.equal(byTag(pipeline.main, "h1")[0].textContent, "Jobs");
  const job = await start({ hash: "#/job/" + HARBOR });
  assert.deepEqual(job.win.replaced, ["#/jobs/" + HARBOR]);
  assert.equal(job.api.gets("/jobs/" + HARBOR), 1);
});

test("inside the dashboard: one quiet row of tabs, no bar, no rail, no address changes", async () => {
  const env = await start({ embedded: true });
  assert.ok(env.root.classList.contains("jobapps-embedded"));
  assert.equal(byClass(env.root, "ja-bar").length + byClass(env.root, "ja-rail").length + byClass(env.root, "ja-logo").length, 0);
  const tabs = byClass(env.root, "ja-toptabs")[0];
  assert.equal(tabs.tagName, "NAV");
  assert.deepEqual(byTag(tabs, "button").map((el) => [el.textContent, el.getAttribute("aria-current")]), [
    ["Overview", "page"],
    ["Jobs", null],
    ["People", null],
    ["Leads", null],
    ["Insights", null],
    ["Library", null],
  ]);
  assert.equal(byTag(tabs, "svg").length, 0);
  assert.equal(byTag(env.main, "h1")[0].textContent, "Overview");
  byKey(env.root, "nav:jobs").click();
  await settle();
  assert.equal(byTag(env.main, "h1")[0].textContent, "Jobs");
  assert.equal(env.win.location.hash, "");
  assert.deepEqual(env.win.replaced, []);
  assert.equal((env.win.listeners.hashchange || []).length, 0);
  assert.equal(env.win.localStorage.data["jobapps.rail"], undefined);

  env.unmount();
  const again = env.doc.createElement("div");
  env.doc.body.appendChild(again);
  env.cockpit.mount(again, { api: env.api, embedded: true });
  await settle();
  assert.equal(byTag(again, "h1")[0].textContent, "Jobs", "the embedded cockpit remembers its page between mounts");
});

test("unmount stops the timer, removes listeners and restores the root", async () => {
  const env = await start();
  assert.equal((env.win.listeners.focus || []).length, 1);
  assert.equal((env.win.listeners.hashchange || []).length, 1);
  assert.equal(env.doc.listeners.visibilitychange.length, 1);
  assert.equal(env.doc.listeners.mousedown.length, 1);
  env.unmount();
  env.unmount();
  assert.deepEqual(env.win.cleared, [1]);
  assert.equal(env.win.listeners.focus.length, 0);
  assert.equal(env.win.listeners.hashchange.length, 0);
  assert.equal(env.doc.listeners.visibilitychange.length, 0);
  assert.equal(env.doc.listeners.mousedown.length, 0);
  assert.equal(env.root.childNodes.length, 0);
  assert.equal(env.root.className, "");
  const calls = env.api.calls.length;
  env.clock.offset += 60000;
  env.win.intervals[0].fn();
  await settle();
  assert.equal(env.api.calls.length, calls);
  assert.throws(() => env.cockpit.mount(null, { api: env.api }));
  assert.throws(() => env.cockpit.mount(env.root, {}));
});

// ── Hermes dashboard host ────────────────────────────────────────────────

test("inside the Hermes dashboard the same UI registers as a React component", async () => {
  const registered = [];
  const fetched = [];
  const effects = [];
  let hostRef = null;
  const env = load((win) => {
    win.__HERMES_PLUGINS__ = { register: (name, component) => registered.push({ name, component }) };
    win.__HERMES_PLUGIN_SDK__ = {
      React: {
        useRef: (initial) => (hostRef = hostRef || { current: initial }),
        useEffect: (effect, deps) => effects.push({ effect, deps }),
        createElement: (tag, props, ...children) => ({ tag, props, children }),
      },
      fetchJSON: (url, init) => {
        fetched.push({ url, init });
        if (url.endsWith("/state")) return Promise.resolve(sampleState());
        return Promise.resolve(/\/jobs\/[^/]+$/.test(url) && !init ? sampleJob() : { ok: true });
      },
      authedFetch: () => Promise.resolve(response(200, "%PDF")),
    };
    win.fetch = () => {
      throw new Error("window.fetch must not be used inside the dashboard");
    };
  });

  assert.equal(registered.length, 1);
  assert.equal(registered[0].name, "jobapps");
  const element = registered[0].component();
  assert.equal(element.tag, "div");
  assert.equal(element.props.className, "jobapps-root jobapps-embedded");
  assert.equal(element.props.ref, hostRef);
  assert.equal(element.children.length, 0, "no JSX children: the cockpit owns the node");
  assert.equal(effects.length, 1);
  assert.equal(effects[0].deps.length, 0);

  const node = env.doc.createElement("div");
  node.className = element.props.className;
  env.doc.body.appendChild(node);
  hostRef.current = node;
  const cleanup = effects[0].effect();
  await settle();
  assert.equal(typeof cleanup, "function");
  assert.deepEqual(plain(fetched[0]), { url: "/api/plugins/jobapps/state" });
  assert.equal(byTag(node, "h1")[0].textContent, "Overview");
  assert.equal(byClass(node, "ja-toptabs").length, 1);

  byKey(node, "nav:jobs").click();
  await settle();
  assert.ok(fetched.some((call) => call.url === "/api/plugins/jobapps/jobs/" + NORTHSTAR));
  const select = byKey(node, "stage:" + NORTHSTAR);
  select.value = "applied";
  select.dispatch("change");
  await settle();
  const post = fetched.filter((call) => call.init && call.init.method === "POST")[0];
  assert.equal(post.url, "/api/plugins/jobapps/jobs/" + NORTHSTAR + "/track");
  assert.equal(post.init.body, '{"status":"applied"}');
  assert.equal(env.win.location.hash, "", "the dashboard's URL is left alone");

  cleanup();
  assert.equal(node.childNodes.length, 0);
  assert.equal(node.className, "jobapps-root jobapps-embedded", "classes React set are kept");
  assert.deepEqual(env.win.cleared, [1]);

  hostRef.current = null;
  assert.equal(effects[0].effect(), undefined);
});

test("without the Hermes globals nothing is registered", () => {
  const partial = load((win) => {
    win.__HERMES_PLUGIN_SDK__ = { React: {} };
  });
  assert.equal(typeof partial.cockpit.mount, "function");
  assert.equal(typeof partial.cockpit.createApiClient, "function");
  assert.ok(Object.keys(partial.helpers).length > 20);
});
