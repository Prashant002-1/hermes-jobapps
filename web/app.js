/*
   JobApps Control Center
   Page-based navigation. Immersive. Agent-centered.
   No scores. No risk labels. No maybe.
*/

/* ── DOM refs ── */
const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => document.querySelectorAll(sel);
const transcript = $("#transcript");
const composer = $("#composer");
const composerInput = $("#composerInput");
const barDot = $("#barDot");
const barStatus = $("#barStatus");
const commandMenu = $("#commandMenu");
const agentLive = $("#agentLive");
const agentProfile = $("#agentProfile");
const agentSession = $("#agentSession");
const agentModel = $("#agentModel");
const agentApi = $("#agentApi");
const agentStreaming = $("#agentStreaming");
const agentRuns = $("#agentRuns");
const agentCommands = $("#agentCommands");
const agentEvents = $("#agentEvents");
const agentUsageModel = $("#agentUsageModel");
const usageInput = $("#usageInput");
const usageOutput = $("#usageOutput");
const usageTotal = $("#usageTotal");
const usageCache = $("#usageCache");
const usageCalls = $("#usageCalls");
const usageContext = $("#usageContext");
const sessionRefresh = $("#sessionRefresh");
const sessionSummary = $("#sessionSummary");
const sessionsList = $("#sessionsList");
const materialStats = $("#materialStats");
const materialsOverview = $("#materialsOverview");
const generatedMaterialCount = $("#generatedMaterialCount");
const materialsList = $("#materialsList");
const materialViewer = $("#materialViewer");
const materialViewerClose = $("#materialViewerClose");
const materialViewerTitle = $("#materialViewerTitle");
const materialViewerKind = $("#materialViewerKind");
const materialViewerMeta = $("#materialViewerMeta");
const materialViewerActions = $("#materialViewerActions");
const materialViewerBody = $("#materialViewerBody");
const brainSearch = $("#brainSearch");
const brainStats = $("#brainStats");
const brainList = $("#brainList");
const brainAreaList = $("#brainAreaList");
const brainEventCount = $("#brainEventCount");
const brainAreaCount = $("#brainAreaCount");
const discoveryRefresh = $("#discoveryRefresh");
const discoveryStats = $("#discoveryStats");
const discoverySearchForm = $("#discoverySearchForm");
const discoveryHydrateForm = $("#discoveryHydrateForm");
const discoveryQuery = $("#discoveryQuery");
const discoveryLimit = $("#discoveryLimit");
const discoveryHydrate = $("#discoveryHydrate");
const discoveryUrl = $("#discoveryUrl");
const discoveryMessage = $("#discoveryMessage");
const discoveryFilter = $("#discoveryFilter");
const discoveryList = $("#discoveryList");
const prepareApprovedDiscovery = $("#prepareApprovedDiscovery");
const jobDetailPanel = $("#jobDetailPanel");
const startPendingHermesRuns = $("#startPendingHermesRuns");
const jobsMessage = $("#jobsMessage");
const actionsStats = $("#actionsStats");
const actionsSearch = $("#actionsSearch");
const actionsBoard = $("#actionsBoard");
const actionsMessage = $("#actionsMessage");

const CHAT_STATE_KEY = "hermes-jobapps.chatState.v1";
const MAX_SAVED_TURNS = 80;

/* ── State ── */
let messages = [];
let currentJobId = null;
let appState = null;
let currentView = "dashboard";
let commandCatalog = [];
let commandGroups = [];
let hermesSessions = [];
let latestStreamState = null;
let latestUsage = null;
let activeConversation = "jobapps-cockpit";
let activeHermesSessionId = "";
let activeSessionLabel = "jobapps-cockpit";
let activeConversationHistory = [];
let pendingTurn = null;
let restoringChatState = false;
let brainQuery = "";
let brainAreaFilter = "all";
let discoveryStatus = null;
let discoveryQueryFilter = "";
let discoveryStatusFilter = "all";
let discoveryBusy = false;
let actionsQuery = "";
let actionsLaneFilter = "all";
let actionsMessageTimer = null;
let jobsMessageTimer = null;
let pipelineMessage = "";
let pipelineMessageKind = "";
let pipelineMessageTimer = null;
const pipelineExpanded = { applied: false, skip: false };

/* ── Helpers ── */
const esc = (s) => {
  const value = String(s ?? "");
  const div = document.createElement("div");
  div.appendChild(document.createTextNode(value));
  return div.innerHTML;
};

const postJson = async (url, body) => {
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return res.json();
};

const fetchJson = async (url) => {
  const res = await fetch(url);
  return res.ok ? res.json() : null;
};

const fetchJsonStrict = async (url) => {
  const res = await fetch(url);
  let payload = null;
  try {
    payload = await res.json();
  } catch (err) {
    payload = null;
  }
  if (!res.ok) {
    throw new Error(payload?.error || `Request failed (${res.status})`);
  }
  return payload;
};

const copyText = async (text) => {
  const value = String(text || "");
  if (!value) return false;
  if (navigator.clipboard?.writeText) {
    await navigator.clipboard.writeText(value);
    return true;
  }
  if (composerInput) {
    composerInput.value = value;
    autoResize();
  }
  return false;
};

const setTip = (el, text) => {
  if (!el || !text) return el;
  el.title = text;
  if (!el.getAttribute("aria-label") && el.textContent.trim()) {
    el.setAttribute("aria-label", el.textContent.trim());
  }
  return el;
};

const displayDate = (value) => {
  const text = String(value || "");
  const match = text.match(/^(\d{4})-(\d{2})-(\d{2})$/);
  if (match) return new Date(Number(match[1]), Number(match[2]) - 1, Number(match[3]));
  return new Date(text);
};

const fmtDate = (iso) => {
  if (!iso) return "";
  const d = displayDate(iso);
  if (Number.isNaN(d.getTime())) return "";
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
};

const fmtDateTime = (value) => {
  if (!value) return "";
  const d = typeof value === "number" ? new Date(value * 1000) : new Date(value);
  if (Number.isNaN(d.getTime())) return "";
  return d.toLocaleString("en-US", { month: "short", day: "numeric", year: "numeric", hour: "numeric", minute: "2-digit" });
};

const fmtAge = (seconds) => {
  if (!seconds) return "";
  const ageMs = Date.now() - Number(seconds) * 1000;
  const days = Math.floor(ageMs / 86400000);
  if (days <= 0) return "today";
  if (days === 1) return "yesterday";
  return `${days}d`;
};

const fmtNum = (value) => Number(value || 0).toLocaleString("en-US");

const safeHref = (href) => {
  const value = String(href || "");
  return /^https?:\/\//i.test(value) ? value : "";
};

const fileName = (path) => String(path || "").split(/[\\/]/).pop() || "";

const setText = (selector, value) => {
  const el = $(selector);
  if (el) el.textContent = value;
};

const classToken = (val, valid) => {
  if (!val) return "";
  const v = String(val).toLowerCase();
  return valid.includes(v) ? v : "";
};

const safeConversationName = (value) => `jobapps-${String(value || "cockpit").replace(/[^a-zA-Z0-9_.-]/g, "-")}`;

const normalizeUsage = (usage = {}) => {
  const input = Number(usage.input ?? usage.input_tokens ?? usage.prompt_tokens ?? 0) || 0;
  const output = Number(usage.output ?? usage.output_tokens ?? usage.completion_tokens ?? 0) || 0;
  const total = Number(usage.total ?? usage.total_tokens ?? input + output) || 0;
  return {
    input,
    output,
    total,
    cache: (Number(usage.cache_read ?? usage.cache_read_tokens ?? 0) || 0) + (Number(usage.cache_write ?? usage.cache_write_tokens ?? 0) || 0),
    calls: Number(usage.calls ?? 0) || 0,
    context: Number(usage.context_percent ?? 0) || 0,
    model: usage.model || "",
    cost: usage.cost_usd,
  };
};

const renderUsage = (usage = {}, meta = {}) => {
  latestUsage = normalizeUsage({ ...usage, model: meta.model || usage.model });
  if (usageInput) usageInput.textContent = fmtNum(latestUsage.input);
  if (usageOutput) usageOutput.textContent = fmtNum(latestUsage.output);
  if (usageTotal) usageTotal.textContent = fmtNum(latestUsage.total);
  if (usageCache) usageCache.textContent = fmtNum(latestUsage.cache);
  if (usageCalls) usageCalls.textContent = fmtNum(latestUsage.calls);
  if (usageContext) usageContext.textContent = latestUsage.context ? `${latestUsage.context}%` : "0%";
  if (agentUsageModel) agentUsageModel.textContent = meta.response_id || latestUsage.model || "turn";
};

const compactMessages = (items = []) => {
  return items
    .filter((item) => item && ["user", "assistant", "system"].includes(item.role) && item.content)
    .map((item) => ({ role: item.role, content: String(item.content).slice(0, 12000) }))
    .slice(-MAX_SAVED_TURNS);
};

const readChatState = () => {
  try {
    const raw = localStorage.getItem(CHAT_STATE_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch (err) {
    return null;
  }
};

const saveChatState = () => {
  if (restoringChatState) return;
  try {
    localStorage.setItem(CHAT_STATE_KEY, JSON.stringify({
      version: 1,
      savedAt: new Date().toISOString(),
      activeConversation,
      activeHermesSessionId,
      activeSessionLabel,
      activeConversationHistory: compactMessages(activeConversationHistory),
      currentJobId,
      currentView,
      draft: composerInput?.value || "",
      messages: compactMessages(messages),
      pendingTurn,
      usage: latestUsage,
    }));
  } catch (err) {
    // Local storage is a convenience checkpoint, not canonical app state.
  }
};

const setActiveSessionLabel = (label) => {
  activeSessionLabel = label || activeHermesSessionId || activeConversation;
  if (agentSession) agentSession.textContent = activeSessionLabel;
};

const setRuntimeStatus = (status) => {
  barDot.classList.remove("thinking", "disconnected");
  if (status === "running") {
    barDot.classList.add("thinking");
    barStatus.textContent = "running";
    if (agentLive) agentLive.textContent = "running";
    return;
  }
  if (status === "offline") {
    barDot.classList.add("disconnected");
    barStatus.textContent = "offline";
    if (agentLive) agentLive.textContent = "offline";
    return;
  }
  barStatus.textContent = "connected";
  if (agentLive) agentLive.textContent = "idle";
};

const addAgentEvent = (kind, label, detail = "") => {
  if (!agentEvents) return;
  const row = document.createElement("div");
  row.className = `agent-event ${kind}`;
  row.innerHTML = `
    <span class="agent-event-kind">${esc(label)}</span>
    ${detail ? `<span class="agent-event-detail">${esc(detail)}</span>` : ""}
  `;
  agentEvents.prepend(row);
  while (agentEvents.children.length > 12) {
    agentEvents.lastElementChild.remove();
  }
};

const updateHermesStatus = (status) => {
  if (!status) return;
  agentProfile.textContent = status.profile || "jobapps";
  agentModel.textContent = status.advertised_model || status.model || "jobapps";
  agentApi.textContent = status.status || "unknown";
  agentStreaming.textContent = status.features?.responses_streaming ? "on" : "off";
  agentRuns.textContent = status.features?.run_events_sse ? "on" : "off";
  agentCommands.textContent = status.commands?.available ? "on" : "off";
  setActiveSessionLabel(activeSessionLabel);
  if (status.status === "offline") setRuntimeStatus("offline");
};

/* ── Navigation ── */
const initNav = () => {
  const items = $$(".nav-item");
  items.forEach((item) => {
    item.addEventListener("click", () => {
      const view = item.dataset.view;
      switchView(view);
    });
  });
  $$("[data-view-jump]").forEach((item) => {
    item.addEventListener("click", () => {
      const view = item.dataset.viewJump;
      if (view) switchView(view);
    });
  });
};

const switchView = (view) => {
  currentView = view;

  // Update nav
  $$(".nav-item").forEach((el) => el.classList.toggle("active", el.dataset.view === view));

  // Update views
  $$(".view").forEach((el) => el.classList.toggle("active", el.dataset.view === view));

  // Render view-specific content
  if (view === "dashboard") renderDashboard();
  if (view === "actions") renderActions();
  if (view === "brain") renderBrain();
  if (view === "discovery") renderDiscovery();
  if (view === "jobs") renderJobs();
  if (view === "materials") renderMaterials();
  if (view === "activity") renderActivity();
  if (view === "criteria") renderCriteria();
  if (view === "network") renderNetwork();
  if (view === "sessions") renderSessions();
  scrollCurrentViewToTop();
  saveChatState();
};

const scrollCurrentViewToTop = () => {
  const view = $(`.view[data-view="${currentView}"]`);
  if (!view) return;
  requestAnimationFrame(() => {
    view.scrollTop = 0;
    view.scrollLeft = 0;
  });
};

/* ── Dashboard ── */
const humanize = (value) => String(value || "").replace(/_/g, " ");
const jobDecision = (job) => job?.decision || job?.evaluation?.decision || "pending";
const jobMaterials = (job) => job?.materials_workbench?.items || [];
const CLOSED_ACTION_STATUSES = new Set(["done", "closed", "complete", "completed", "dismissed", "not_needed", "canceled", "cancelled", "approved", "rejected", "superseded"]);
const ACTION_ACTIVE_LANES = new Set(["do_now", "state", "hermes"]);
const ACTION_LANES = [
  { id: "do_now", label: "Do Now" },
  { id: "state", label: "State" },
  { id: "hermes", label: "Hermes" },
  { id: "backlog", label: "Backlog" },
];
const openItems = (items = []) => items.filter((item) => !CLOSED_ACTION_STATUSES.has(String(item.status || "").toLowerCase()));
const PIPELINE_LIMITED_STAGES = new Set(["applied", "skip"]);
const PIPELINE_PREVIEW_LIMIT = 10;
const JOB_STATUS_OPTIONS = [
  { stage: "new", status: "new", label: "New" },
  { stage: "applied", status: "applied", label: "Applied" },
  { stage: "skip", status: "skip", label: "Skip" },
];
const STATUS_BY_STAGE = Object.fromEntries(JOB_STATUS_OPTIONS.map((item) => [item.stage, item.status]));
const STATUS_LABELS = Object.fromEntries(JOB_STATUS_OPTIONS.map((item) => [item.status, item.label]));
const COCKPIT_JOB_STATUSES = new Set(JOB_STATUS_OPTIONS.map((item) => item.status));
const LEGACY_JOB_STATUSES = new Set([
  "evaluated",
  "saved",
  "hydrated",
  "needs_review",
  "preparing",
  "ready",
  "ready_to_apply",
  "approved",
  "materials_ready",
  "materials_ready_for_upload",
  "materials_ready_networking_drafts_created",
  "referral_draft_ready",
  "pending_referral_upload",
  "materials_ready_for_review",
  "waiting",
  "follow_up",
  "interview",
  "phone_screen",
  "offer",
  "closed",
  "rejected",
  "declined",
  "archived",
  "hermes_queued",
  "hermes_running",
  "hermes_completed",
  "hermes_failed",
]);

const localDateKey = (date = new Date()) => {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
};

const addDaysKey = (days) => {
  const date = new Date();
  date.setDate(date.getDate() + days);
  return localDateKey(date);
};

const dateKey = (value) => String(value || "").slice(0, 10);
const isPastDate = (value) => {
  const key = dateKey(value);
  return key && key < localDateKey();
};
const isTodayDate = (value) => dateKey(value) === localDateKey();
const actionDueText = (value, fallback = "") => {
  const key = dateKey(value);
  if (!key) return fallback;
  if (key < localDateKey()) return `overdue ${fmtDate(key)}`;
  if (key === localDateKey()) return "today";
  return fmtDate(key);
};

const actionLaneLabel = (lane) => (ACTION_LANES.find((item) => item.id === lane)?.label || humanize(lane));
const findJobById = (jobId) => (appState?.jobs || []).find((job) => job.id === jobId);

const stateLabel = (stage) => {
  if (stage === "applied") return "Applied";
  if (stage === "skip") return "Skip";
  return "New";
};

const jobEventDate = (job, predicate) => {
  const events = (job?.events || [])
    .filter(predicate)
    .map((event) => event.created_at)
    .filter(Boolean)
    .sort();
  return events[events.length - 1] || "";
};

const jobStateDate = (job, stage = jobStage(job)) => {
  if (!job) return "";
  const dates = job.state_dates || {};
  if (dates.current) return dates.current;
  if (stage === "applied" && dates.applied) return dates.applied;
  if (stage === "skip" && dates.skip) return dates.skip;
  if (stage === "new" && dates.new) return dates.new;
  if (stage === "applied") {
    return jobEventDate(job, (event) => event.payload?.status === "applied" || /applied|submitted/i.test(event.summary || event.note || "")) || job.updated_at || job.created_at;
  }
  if (stage === "skip") {
    return jobEventDate(job, (event) => ["skip", "skipped", "not_interested", "not_needed"].includes(String(event.payload?.status || "").toLowerCase())) || job.updated_at || job.created_at;
  }
  return job.created_at || job.updated_at || "";
};

const jobDateMeta = (job, stage = jobStage(job)) => {
  const created = fmtDate(job?.created_at);
  const updated = fmtDate(job?.updated_at);
  const stateDate = fmtDate(jobStateDate(job, stage));
  const parts = [];
  if (created) parts.push(`added ${created}`);
  if (updated && updated !== created) parts.push(`updated ${updated}`);
  if (stateDate && stage !== "new") parts.push(`${stateLabel(stage).toLowerCase()} ${stateDate}`);
  return parts.join(" · ");
};

const jobOpenActionCount = (job = {}) => (
  Number.isFinite(Number(job.open_action_count)) ? Number(job.open_action_count) :
  openItems(job.progress || []).length +
  openItems(job.followups || []).length +
  (job.approvals || []).filter((item) => !CLOSED_ACTION_STATUSES.has(String(item.status || "").toLowerCase())).length
);

const jobStage = (job) => {
  const bucket = String(job?.state_bucket || "").toLowerCase();
  if (["new", "applied", "skip"].includes(bucket)) return bucket;
  const status = String(job?.status || "new").toLowerCase().replace(/-/g, "_");
  if (["skip", "skipped", "not_interested", "not_needed"].includes(status)) return "skip";
  if (["applied", "interview", "phone_screen", "offer", "follow_up", "waiting", "closed", "rejected", "declined", "archived"].includes(status)) return "applied";
  return "new";
};

const dashboardCurrentJob = (jobs = []) => (
  jobs.find((job) => jobStage(job) === "new") ||
  jobs.find((job) => jobStage(job) === "applied") ||
  jobs[0] ||
  null
);

const actionContext = (item = {}) => (
  [item.job_company, item.job_title].filter(Boolean).join(" · ") ||
  [findJobById(item.job_id)?.company, findJobById(item.job_id)?.title].filter(Boolean).join(" · ") ||
  "unmapped"
);

const approvalActionTitle = (action) => {
  const normalized = String(action || "");
  if (normalized.startsWith("manual_send_")) return `Send ${humanize(normalized.replace(/^manual_send_/, ""))}`;
  return humanize(normalized || "approval");
};

const actionPromptFor = (item, kind) => {
  const title = item.title || item.reason || item.action || "this action";
  const context = actionContext(item);
  if (kind === "research") return `Help me resolve this JobApps action: ${title}. Context: ${context}. Show the evidence and suggest the smallest next step.`;
  if (kind === "networking") return `Help me turn this networking action into a concrete next step: ${title}. Context: ${context}. If outreach is needed, draft but do not send.`;
  return `Help me decide the next JobApps step for: ${title}. Context: ${context}.`;
};

const isExternalAction = (text) => /(send|email|message|contact|follow[\s-]?up)/i.test(text || "");
const isReviewAction = (text) => /(review|approve|materials|resume|cover|draft|pdf)/i.test(text || "");
const isGenericWorkflowHint = (item = {}) => {
  const text = `${item.title || ""} ${item.kind || ""}`.toLowerCase();
  return !item.due_date && (
    text.includes("run quick company") ||
    text.includes("sponsorship research") ||
    text.includes("find networking targets")
  );
};

const classifyProgressAction = (item) => {
  const text = `${item.title || ""} ${item.kind || ""}`;
  if (isGenericWorkflowHint(item)) return "backlog";
  if (isReviewAction(text)) return "backlog";
  if (isExternalAction(text) || ["follow_up"].includes(String(item.kind || ""))) return "do_now";
  if (/(research|sponsorship|networking|find)/i.test(text)) return "hermes";
  return item.due_date ? "do_now" : "backlog";
};

const actionUrgency = (row) => {
  if (isPastDate(row.dueKey)) return 0;
  if (isTodayDate(row.dueKey)) return 1;
  if (row.lane === "do_now") return 2;
  if (row.lane === "state") return 3;
  if (row.lane === "hermes") return 4;
  return 6;
};

const sortActionRows = (rows) => rows.sort((a, b) => (
  actionUrgency(a) - actionUrgency(b) ||
  (a.dueKey || "9999-99-99").localeCompare(b.dueKey || "9999-99-99") ||
  (a.context || "").localeCompare(b.context || "") ||
  (a.title || "").localeCompare(b.title || "")
));

const buildActionRows = () => {
  const rows = [];
  (appState?.approvals || []).forEach((item) => {
    const action = String(item.action || "");
    const payload = item.payload || {};
    const title = approvalActionTitle(action);
    const lane = isExternalAction(action) ? "do_now" : "backlog";
    rows.push({
      id: `approval-${item.id}`,
      itemId: item.id,
      sourceType: "approval",
      lane,
      type: lane === "do_now" ? "External" : "Approval",
      title,
      context: actionContext(item),
      detail: payload.reason || payload.policy || payload.approval_gate || "",
      due: item.updated_at ? actionDueText(item.updated_at, "pending") : "pending",
      dueKey: dateKey(item.updated_at),
      status: item.status || "pending",
      jobId: item.job_id,
      materialId: payload.material_id || (Array.isArray(payload.material_ids) ? payload.material_ids[0] : ""),
      prompt: "",
    });
  });
  openItems(appState?.progress_items || []).forEach((item) => {
    const lane = classifyProgressAction(item);
    const prompt = ["hermes", "backlog"].includes(lane) ? actionPromptFor(item, item.kind) : "";
    rows.push({
      id: `progress-${item.id}`,
      itemId: item.id,
      sourceType: "progress",
      lane,
      type: lane === "backlog" ? "Backlog" : humanize(item.kind || "Task"),
      title: item.title || "Open task",
      context: actionContext(item),
      detail: item.notes || "",
      due: actionDueText(item.due_date, item.status || ""),
      dueKey: dateKey(item.due_date),
      status: item.status || "open",
      jobId: item.job_id,
      materialId: "",
      prompt,
    });
  });
  openItems(appState?.followups || []).forEach((item) => rows.push({
    id: `followup-${item.id}`,
    itemId: item.id,
    sourceType: "followup",
    lane: "do_now",
    type: "Follow-up",
    title: item.reason || "Follow up",
    context: actionContext(item),
    detail: "",
    due: actionDueText(item.due_date, item.status || ""),
    dueKey: dateKey(item.due_date),
    status: item.status || "open",
    jobId: item.job_id,
    materialId: "",
    prompt: "",
  }));
  (appState?.jobs || []).forEach((job) => {
    const status = String(job.status || "new").toLowerCase();
    if (!COCKPIT_JOB_STATUSES.has(status) && !LEGACY_JOB_STATUSES.has(status) && !CLOSED_ACTION_STATUSES.has(status)) {
      rows.push({
        id: `state-${job.id}`,
        itemId: job.id,
        sourceType: "state",
        lane: "state",
        type: "State",
        title: "Choose the current job state",
        context: [job.company, job.title].filter(Boolean).join(" · "),
        detail: `Current stored status is ${humanize(status)}.`,
        due: "",
        dueKey: "",
        status,
        jobId: job.id,
        materialId: "",
        prompt: "",
      });
    }
  });
  return sortActionRows(rows);
};

const activeActionRows = () => buildActionRows().filter((row) => ACTION_ACTIVE_LANES.has(row.lane));

const dashboardQueue = () => {
  const rows = activeActionRows().map((item) => ({
    type: actionLaneLabel(item.lane),
    title: item.title,
    context: item.context,
    due: item.due,
  }));
  const health = appState?.database_health || {};
  if (health.status && health.status !== "ok") {
    rows.push({
      type: "State",
      title: humanize(health.status),
      context: `${fmtNum(health.actionable_count || 0)} records need mapping`,
      due: "",
    });
  }
  return rows;
};

const renderStateFocus = (job, queueRows) => {
  const focus = $("#stateFocus");
  if (!focus) return;
  if (!job) {
    focus.innerHTML = `
      <div class="state-focus-head">
        <span class="eyebrow">Current Job</span>
        <span class="badge badge-pending">none</span>
      </div>
      <h2>No job selected</h2>
      <p>Add a job link or paste a description to start the workflow.</p>
      <div class="state-actions">
        <button class="btn btn-primary" type="button" data-state-view="discovery">Find Jobs</button>
        <button class="btn" type="button" data-state-view="jobs">Review Jobs</button>
      </div>
    `;
    return;
  }
  const decision = jobDecision(job);
  const requirements = job.tailoring_requirements || [];
  const signals = job.application_signals || [];
  const materials = jobMaterials(job);
  const contacts = job.outreach?.contacts || job.contacts || [];
  const followups = openItems(job.outreach?.followups || job.followups || []);
  const stage = jobStage(job);
  const actionCount = jobOpenActionCount(job);
  focus.innerHTML = `
    <div class="state-focus-head">
      <span class="eyebrow">Current Job</span>
      <span class="state-pill state-${esc(stage)}">${esc(stateLabel(stage))}</span>
    </div>
    <h2>${esc(job.title || "untitled")}</h2>
    <p>${esc([job.company, job.location].filter(Boolean).join(" · ") || "company pending")}</p>
    <div class="job-packet-dates">
      <span>${esc(jobDateMeta(job, stage) || "date pending")}</span>
      <span class="badge badge-${classToken(decision, ["apply", "skip", "pending"])}">${esc(decision)}</span>
    </div>
    <div class="next-action-box">
      <span>Next Action</span>
      <strong>${esc(job.next_action || (queueRows.length ? queueRows[0].title : "Prepare the role, review materials, then decide the next move."))}</strong>
    </div>
    <div class="state-metrics">
      <span><strong>${fmtNum(actionCount)}</strong> actions</span>
      <span><strong>${fmtNum(requirements.length)}</strong> requirements</span>
      <span><strong>${fmtNum(signals.length)}</strong> signals</span>
      <span><strong>${fmtNum(materials.length)}</strong> materials</span>
      <span><strong>${fmtNum(contacts.length)}</strong> people</span>
      ${followups.length ? `<span><strong>${fmtNum(followups.length)}</strong> follow-ups</span>` : ""}
    </div>
    <div class="state-actions">
      <button class="btn btn-primary" type="button" data-state-view="jobs" data-state-job="${esc(job.id)}">Open Job</button>
      <button class="btn" type="button" data-state-view="materials">Materials</button>
      <button class="btn" type="button" data-state-view="network">Network</button>
    </div>
  `;
};

const renderStateQueue = (rows) => {
  const queue = $("#stateQueue");
  if (!queue) return;
  const body = rows.length ? rows.slice(0, 7).map((item) => `
    <div class="queue-row">
      <span class="queue-type">${esc(item.type)}</span>
      <div>
        <strong>${esc(item.title)}</strong>
        <span>${esc(item.context || "unmapped")}</span>
      </div>
      <time>${esc(item.due || "")}</time>
    </div>
  `).join("") : '<div class="empty-state">clear</div>';
  queue.innerHTML = `
    <div class="state-focus-head">
      <span class="eyebrow">Needs Action</span>
      <span class="count">${fmtNum(rows.length)}</span>
    </div>
    ${body}
    ${rows.length ? '<button class="btn btn-primary state-queue-open" type="button" data-state-view="actions"><span class="material-symbols-outlined btn-icon">task_alt</span> Open Actions</button>' : ""}
  `;
};

const setActionsMessage = (message, kind = "") => {
  if (!actionsMessage) return;
  actionsMessage.textContent = message || "";
  actionsMessage.className = `pipeline-message ${kind || ""}`.trim();
  if (actionsMessageTimer) window.clearTimeout(actionsMessageTimer);
  if (message) {
    actionsMessageTimer = window.setTimeout(() => {
      if (actionsMessage) {
        actionsMessage.textContent = "";
        actionsMessage.className = "pipeline-message";
      }
    }, kind === "error" ? 6000 : 2600);
  }
};

const actionButtonLabel = (row) => {
  const text = `${row.title || ""} ${row.type || ""}`.toLowerCase();
  if (text.includes("send") || text.includes("email") || text.includes("message")) return "Mark Sent";
  if (text.includes("submit") || text.includes("apply")) return "Mark Applied";
  return "Mark Done";
};

const actionDispositionButtons = (row, options = {}) => {
  const showOpenJob = options.showOpenJob !== false;
  if (row.sourceType === "approval") {
    const external = row.lane === "do_now";
    return `
      ${row.materialId ? `<button class="link-button" type="button" data-preview-material="${esc(row.materialId)}">Preview</button>` : ""}
      ${showOpenJob && row.jobId ? `<button class="link-button" type="button" data-action-open-job="${esc(row.jobId)}">Open Job</button>` : ""}
      <button class="btn btn-primary" type="button" data-action-op="approve" data-action-source="approval" data-action-id="${esc(row.itemId)}">${external ? esc(actionButtonLabel(row)) : "Approve"}</button>
      <button class="btn" type="button" data-action-op="reject" data-action-source="approval" data-action-id="${esc(row.itemId)}">${external ? "Not Needed" : "Needs Edits"}</button>
    `;
  }
  if (row.sourceType === "state") {
    const job = findJobById(row.jobId);
    return `
      ${showOpenJob && row.jobId ? `<button class="link-button" type="button" data-action-open-job="${esc(row.jobId)}">Open Job</button>` : ""}
      ${job ? statusSelectMarkup(job, "action-status-menu") : ""}
    `;
  }
  const laterLabel = row.lane === "backlog" ? "Do Later" : "Snooze";
  return `
    ${row.prompt ? `<button class="link-button" type="button" data-action-prompt="${esc(row.prompt)}">Copy Hermes Prompt</button>` : ""}
    ${showOpenJob && row.jobId ? `<button class="link-button" type="button" data-action-open-job="${esc(row.jobId)}">Open Job</button>` : ""}
    <button class="btn btn-primary" type="button" data-action-op="done" data-action-source="${esc(row.sourceType)}" data-action-id="${esc(row.itemId)}">${esc(actionButtonLabel(row))}</button>
    <button class="btn" type="button" data-action-op="snooze" data-action-days="${row.lane === "backlog" ? "7" : "3"}" data-action-source="${esc(row.sourceType)}" data-action-id="${esc(row.itemId)}">${laterLabel}</button>
    <button class="btn" type="button" data-action-op="not_needed" data-action-source="${esc(row.sourceType)}" data-action-id="${esc(row.itemId)}">Not Needed</button>
  `;
};

const renderActionRow = (row, options = {}) => `
  <article class="action-row action-row-${esc(row.lane)}">
    <div class="action-main">
      <div class="action-kicker">
        <span class="queue-type">${esc(actionLaneLabel(row.lane))}</span>
        <span>${esc(row.type)}</span>
        <span>${esc(row.status || "")}</span>
        ${row.due ? `<time>${esc(row.due)}</time>` : ""}
      </div>
      <h3>${esc(row.title)}</h3>
      ${options.showContext === false ? "" : `<p>${esc(row.context || "unmapped")}</p>`}
      ${row.detail ? `<div class="action-detail">${esc(row.detail).slice(0, 240)}</div>` : ""}
      ${row.prompt ? `<div class="action-prompt">${esc(row.prompt)}</div>` : ""}
    </div>
    <div class="action-dispositions">
      ${actionDispositionButtons(row, { showOpenJob: options.showOpenJob })}
    </div>
  </article>
`;

const actionJobMeta = (row) => {
  const job = findJobById(row.jobId);
  if (job) {
    return {
      key: `job-${job.id}`,
      job,
      jobId: job.id,
      company: job.company || "company pending",
      title: job.title || "Untitled role",
      location: job.location || "",
      status: job.status || currentJobStatusValue(job),
      decision: jobDecision(job),
      nextAction: job.next_action || "",
    };
  }
  const context = row.context && row.context !== "unmapped" ? row.context : "Unmapped actions";
  return {
    key: `unmapped-${context.toLowerCase().replace(/[^a-z0-9]+/g, "-") || "actions"}`,
    job: null,
    jobId: "",
    company: context,
    title: "",
    location: "",
    status: "needs mapping",
    decision: "pending",
    nextAction: "Link this action to a job before acting.",
  };
};

const actionGroupDueKey = (group) => (
  group.rows.map((row) => row.dueKey).filter(Boolean).sort()[0] || ""
);

const actionGroupDueText = (group) => {
  const active = group.rows.filter((row) => ACTION_ACTIVE_LANES.has(row.lane));
  const overdue = active.filter((row) => isPastDate(row.dueKey)).length;
  if (overdue) return `${fmtNum(overdue)} overdue`;
  const today = active.filter((row) => isTodayDate(row.dueKey)).length;
  if (today) return `${fmtNum(today)} today`;
  const nextDue = actionGroupDueKey(group);
  return nextDue ? `next ${actionDueText(nextDue)}` : "unscheduled";
};

const actionGroupBadgeClass = (group) => (
  classToken(group.decision, ["apply", "skip", "pending"]) ||
  (String(group.status || "").toLowerCase().includes("review") ? "review" : "pending")
);

const groupActionRows = (rows) => {
  const groups = new Map();
  rows.forEach((row) => {
    const meta = actionJobMeta(row);
    if (!groups.has(meta.key)) {
      groups.set(meta.key, { ...meta, rows: [], laneCounts: {} });
    }
    const group = groups.get(meta.key);
    group.rows.push(row);
    group.laneCounts[row.lane] = (group.laneCounts[row.lane] || 0) + 1;
  });
  return Array.from(groups.values()).sort((a, b) => (
    Math.min(...a.rows.map(actionUrgency)) - Math.min(...b.rows.map(actionUrgency)) ||
    (actionGroupDueKey(a) || "9999-99-99").localeCompare(actionGroupDueKey(b) || "9999-99-99") ||
    [a.company, a.title].filter(Boolean).join(" ").localeCompare([b.company, b.title].filter(Boolean).join(" "))
  ));
};

const renderActionLaneSummary = (group) => (
  ACTION_LANES
    .filter((lane) => group.laneCounts[lane.id])
    .map((lane) => `
      <span class="action-lane-count">
        <span>${esc(lane.label)}</span>
        <strong>${fmtNum(group.laneCounts[lane.id])}</strong>
      </span>
    `).join("")
);

const renderActionJobGroup = (group) => {
  const heading = [group.company, group.title].filter(Boolean).join(" · ");
  const subline = [
    group.location,
    group.nextAction ? `Next: ${group.nextAction}` : "",
  ].filter(Boolean).join(" · ");
  return `
    <section class="action-job-group">
      <div class="action-job-head">
        <div class="action-job-title">
          <span class="eyebrow">Job</span>
          <h2>${esc(heading || "Unmapped actions")}</h2>
          ${subline ? `<p>${esc(subline)}</p>` : ""}
        </div>
        <div class="action-job-meta">
          <span class="badge badge-${esc(actionGroupBadgeClass(group))}">${esc(humanize(group.status || group.decision || "pending"))}</span>
          <span class="action-job-due">${esc(actionGroupDueText(group))}</span>
          <span class="count">${fmtNum(group.rows.length)} ${group.rows.length === 1 ? "action" : "actions"}</span>
          ${group.jobId ? `<button class="link-button" type="button" data-action-open-job="${esc(group.jobId)}">Open Job</button>` : ""}
        </div>
      </div>
      <div class="action-job-lanes">
        ${renderActionLaneSummary(group)}
      </div>
      <div class="action-job-body">
        ${group.rows.map((row) => renderActionRow(row, { showContext: false, showOpenJob: false })).join("")}
      </div>
    </section>
  `;
};

const actionSummary = (rows) => {
  const active = rows.filter((row) => ACTION_ACTIVE_LANES.has(row.lane));
  return {
    total: rows.length,
    jobs: groupActionRows(rows).length,
    active: active.length,
    overdue: active.filter((row) => isPastDate(row.dueKey)).length,
    today: active.filter((row) => isTodayDate(row.dueKey)).length,
    approvals: rows.filter((row) => row.sourceType === "approval").length,
    followups: rows.filter((row) => row.sourceType === "followup").length,
    backlog: rows.filter((row) => row.lane === "backlog").length,
  };
};

const renderActions = () => {
  if (!appState || !actionsBoard) return;
  const rows = buildActionRows();
  const summary = actionSummary(rows);
  if (actionsStats) {
    actionsStats.innerHTML = [
      ["Jobs", summary.jobs],
      ["Active", summary.active],
      ["Overdue", summary.overdue],
      ["Today", summary.today],
    ].map(([label, value]) => `
      <div class="stat-item">
        <span class="stat-value">${fmtNum(value)}</span>
        <span class="stat-label">${esc(label)}</span>
      </div>
    `).join("");
  }
  const query = actionsQuery.trim().toLowerCase();
  const filtered = rows.filter((row) => (
    (actionsLaneFilter === "all" || row.lane === actionsLaneFilter) &&
    (!query || `${row.title} ${row.context} ${row.type} ${row.detail} ${row.prompt} ${row.status} ${actionLaneLabel(row.lane)}`.toLowerCase().includes(query))
  ));
  const groups = groupActionRows(filtered);
  actionsBoard.innerHTML = groups.length
    ? groups.map(renderActionJobGroup).join("")
    : `<div class="empty-state">${rows.length ? "no matching actions" : "clear"}</div>`;
  attachActionControls(actionsBoard);
};

const performActionDisposition = async (source, id, op, options = {}) => {
  if (!source || !id || !op) return;
  setActionsMessage("updating", "pending");
  let endpoint = "";
  let payload = {};
  if (source === "approval") {
    endpoint = `/api/approvals/${encodeURIComponent(id)}/disposition`;
    payload = { action: op === "approve" ? "approve" : "reject" };
  } else if (source === "progress") {
    endpoint = `/api/progress-items/${encodeURIComponent(id)}/disposition`;
    payload = { status: op === "done" ? "done" : op === "not_needed" ? "not_needed" : "pending" };
  } else if (source === "followup") {
    endpoint = `/api/followups/${encodeURIComponent(id)}/disposition`;
    payload = { status: op === "done" ? "done" : op === "not_needed" ? "not_needed" : "open" };
  }
  if (!endpoint) return;
  if (op === "snooze") {
    payload.due_date = addDaysKey(Number(options.days || 3));
    payload.note = `Snoozed from Actions until ${payload.due_date}.`;
  }
  const result = await postJson(endpoint, payload);
  if (result?.error) {
    setActionsMessage(result.error, "error");
    return;
  }
  if (result?.state) appState = result.state;
  setActionsMessage(op === "snooze" ? "snoozed" : "updated", "ok");
  renderCurrentView();
  saveChatState();
};

const attachActionControls = (root = document) => {
  root.querySelectorAll("[data-action-op]").forEach((button) => {
    button.addEventListener("click", () => {
      performActionDisposition(
        button.dataset.actionSource,
        button.dataset.actionId,
        button.dataset.actionOp,
        { days: button.dataset.actionDays || "" }
      );
    });
  });
  root.querySelectorAll("[data-action-open-job]").forEach((button) => {
    button.addEventListener("click", () => {
      currentJobId = button.dataset.actionOpenJob;
      switchView("jobs");
    });
  });
  root.querySelectorAll("[data-action-prompt]").forEach((button) => {
    button.addEventListener("click", async () => {
      const prompt = button.dataset.actionPrompt || "";
      const copied = await copyText(prompt);
      setActionsMessage(copied ? "prompt copied for Hermes TUI" : "prompt placed in chat draft", copied ? "ok" : "pending");
    });
  });
  root.querySelectorAll("[data-preview-material]").forEach((button) => {
    button.addEventListener("click", () => openMaterialViewer(button.dataset.previewMaterial || ""));
  });
  attachJobStatusControls(root);
};

const currentJobStatusValue = (job) => STATUS_BY_STAGE[jobStage(job)] || "new";

const statusSelectMarkup = (job, className = "") => {
  const value = currentJobStatusValue(job);
  return `
    <label class="status-menu ${esc(className)}">
      <span>State</span>
      <select data-job-status="${esc(job.id)}" aria-label="Update state for ${esc(job.title || "job")}">
        ${JOB_STATUS_OPTIONS.map((item) => `
          <option value="${esc(item.status)}"${item.status === value ? " selected" : ""}>${esc(item.label)}</option>
        `).join("")}
      </select>
    </label>
  `;
};

const setPipelineMessage = (message, kind = "") => {
  pipelineMessage = message;
  pipelineMessageKind = kind;
  if (pipelineMessageTimer) window.clearTimeout(pipelineMessageTimer);
  if (message) {
    pipelineMessageTimer = window.setTimeout(() => {
      pipelineMessage = "";
      pipelineMessageKind = "";
      if (currentView === "dashboard") renderDashboard();
    }, kind === "error" ? 6000 : 2800);
  }
};

const setJobsMessage = (message, kind = "") => {
  if (!jobsMessage) return;
  jobsMessage.textContent = message || "";
  jobsMessage.className = `pipeline-message ${kind || ""}`.trim();
  if (jobsMessageTimer) window.clearTimeout(jobsMessageTimer);
  if (message) {
    jobsMessageTimer = window.setTimeout(() => {
      if (jobsMessage) {
        jobsMessage.textContent = "";
        jobsMessage.className = "pipeline-message";
      }
    }, kind === "error" ? 6000 : 2800);
  }
};

const updateJobStatus = async (jobId, status, note = "Updated from JobApps cockpit.") => {
  if (!jobId || !status) return;
  const label = STATUS_LABELS[status] || humanize(status);
  setPipelineMessage(`Moving to ${label}`, "pending");
  if (currentView === "dashboard") renderDashboard();
  const result = await postJson(`/api/jobs/${encodeURIComponent(jobId)}/status`, { status, note });
  if (result?.error) {
    setPipelineMessage(result.error, "error");
    renderCurrentView();
    return;
  }
  if (result?.state) {
    appState = result.state;
  } else {
    const state = await fetchJson("/api/state");
    if (state) appState = state;
  }
  currentJobId = jobId;
  setPipelineMessage(`Moved to ${label}`, "ok");
  renderCurrentView();
  saveChatState();
};

const attachJobStatusControls = (root = document) => {
  root.querySelectorAll("[data-job-status]").forEach((select) => {
    select.addEventListener("click", (event) => event.stopPropagation());
    select.addEventListener("mousedown", (event) => event.stopPropagation());
    select.addEventListener("change", () => {
      updateJobStatus(select.dataset.jobStatus, select.value);
    });
  });
  root.querySelectorAll("[data-job-set-status]").forEach((button) => {
    button.addEventListener("click", (event) => {
      event.stopPropagation();
      updateJobStatus(
        button.dataset.jobId,
        button.dataset.jobSetStatus,
        `Moved to ${button.dataset.jobStage || "status"} from job detail.`
      );
    });
  });
};

const renderPipelineCard = (job) => {
  const card = document.createElement("div");
  const stage = jobStage(job);
  const actionCount = jobOpenActionCount(job);
  card.className = `pipe-card state-${stage}`;
  card.draggable = true;
  card.dataset.jobId = job.id;
  const decision = jobDecision(job);
  const materials = jobMaterials(job);
  const contacts = job.outreach?.contacts || job.contacts || [];
  card.innerHTML = `
    <div class="pipe-card-top">
      <span class="state-pill state-${esc(stage)}">${esc(stateLabel(stage))}</span>
      <time>${esc(fmtDate(jobStateDate(job, stage)) || "")}</time>
    </div>
    <div class="pipe-card-title">${esc(job.title || "untitled")}</div>
    <div class="pipe-card-company">${esc(job.company || "")}</div>
    <div class="pipe-card-date">${esc(jobDateMeta(job, stage) || "date pending")}</div>
    <div class="pipe-card-meta">
      <span class="badge badge-${classToken(decision, ["apply", "skip", "pending"])}">${esc(decision)}</span>
      <span>${fmtNum(actionCount)} actions</span>
      <span>${fmtNum(materials.length)} files</span>
      <span>${fmtNum(contacts.length)} people</span>
    </div>
    <div class="pipe-card-next">${esc(job.next_action || humanize(job.status || "new"))}</div>
    ${statusSelectMarkup(job, "pipe-status-menu")}
  `;
  attachJobStatusControls(card);
  card.addEventListener("dragstart", (event) => {
    event.dataTransfer.effectAllowed = "move";
    event.dataTransfer.setData("text/plain", job.id);
    card.classList.add("dragging");
  });
  card.addEventListener("dragend", () => {
    card.classList.remove("dragging");
    $$(".pipeline-body.drag-over").forEach((el) => el.classList.remove("drag-over"));
  });
  card.addEventListener("click", () => {
    currentJobId = job.id;
    switchView("jobs");
  });
  return card;
};

const setupPipelineDropZone = (body, stage) => {
  if (!body) return;
  body.dataset.pipelineStage = stage;
  if (body.dataset.pipelineDropReady === "true") return;
  body.dataset.pipelineDropReady = "true";
  body.addEventListener("dragover", (event) => {
    event.preventDefault();
    event.dataTransfer.dropEffect = "move";
    body.classList.add("drag-over");
  });
  body.addEventListener("dragleave", (event) => {
    if (!body.contains(event.relatedTarget)) body.classList.remove("drag-over");
  });
  body.addEventListener("drop", (event) => {
    event.preventDefault();
    body.classList.remove("drag-over");
    const jobId = event.dataTransfer.getData("text/plain");
    const status = STATUS_BY_STAGE[stage];
    if (jobId && status) updateJobStatus(jobId, status, `Moved to ${stage} on the JobApps board.`);
  });
};

const renderDashboard = () => {
  if (!appState) return;
  const jobs = appState.jobs || [];
  const counts = appState.context_counts || {};
  const materialCount = jobs.reduce((total, job) => total + (job.materials_workbench?.items?.length || 0), 0);
  const queueRows = dashboardQueue();
  const active = dashboardCurrentJob(jobs);
  const stateCounts = {
    new: jobs.filter((job) => jobStage(job) === "new").length,
    applied: jobs.filter((job) => jobStage(job) === "applied").length,
    skip: jobs.filter((job) => jobStage(job) === "skip").length,
  };

  // Stats
  setText("#statJobs", stateCounts.new);
  setText("#statNeedsAction", stateCounts.applied);
  setText("#statMaterials", stateCounts.skip);
  setText("#statPeople", queueRows.length);
  setText("#routeJobs", jobs.length);
  setText("#routeSignals", counts.application_signals || 0);
  setText("#routeEvidence", counts.proof_points || 0);
  setText("#routeMaterials", materialCount);
  setText("#routeFollowups", (appState.followups || []).length);
  setText("#opsActiveJob", active ? `${active.company || ""} ${active.title || "untitled"}`.trim() : "none");
  setText("#opsSignals", counts.application_signals || 0);
  setText("#opsEvidence", counts.proof_points || 0);
  setText("#opsMaterials", materialCount);
  setText("#pipelineWip", `${fmtNum(stateCounts.new)} new`);

  renderStateFocus(active, queueRows);
  renderStateQueue(queueRows);
  $("#stateFocus")?.querySelectorAll("[data-state-view]").forEach((button) => {
    button.addEventListener("click", () => {
      if (button.dataset.stateJob) currentJobId = button.dataset.stateJob;
      switchView(button.dataset.stateView);
    });
  });
  $("#stateQueue")?.querySelectorAll("[data-state-view]").forEach((button) => {
    button.addEventListener("click", () => switchView(button.dataset.stateView));
  });

  // Pipeline
  const columns = {
    new: $("#pipeNew"),
    applied: $("#pipeApplied"),
    skip: $("#pipeSkip"),
  };
  const stageCounts = Object.fromEntries(Object.keys(columns).map((key) => [key, 0]));
  Object.values(columns).forEach((el) => {
    if (el) el.innerHTML = "";
  });
  Object.entries(columns).forEach(([stage, el]) => setupPipelineDropZone(el, stage));
  const jobsByStage = Object.fromEntries(Object.keys(columns).map((key) => [key, []]));

  jobs.forEach((j) => {
    const stage = jobStage(j);
    stageCounts[stage] += 1;
    jobsByStage[stage]?.push(j);
  });

  Object.entries(columns).forEach(([stage, el]) => {
    if (!el) return;
    const stageJobs = jobsByStage[stage] || [];
    const isLimited = PIPELINE_LIMITED_STAGES.has(stage);
    const expanded = Boolean(pipelineExpanded[stage]);
    const visibleJobs = isLimited && !expanded ? stageJobs.slice(0, PIPELINE_PREVIEW_LIMIT) : stageJobs;
    visibleJobs.forEach((job) => el.appendChild(renderPipelineCard(job)));
    if (isLimited && stageJobs.length > PIPELINE_PREVIEW_LIMIT) {
      const toggle = document.createElement("button");
      toggle.type = "button";
      toggle.className = "pipeline-more";
      toggle.textContent = expanded
        ? "Show 10 most recent"
        : `View more ${fmtNum(stageJobs.length - PIPELINE_PREVIEW_LIMIT)}`;
      toggle.addEventListener("click", () => {
        pipelineExpanded[stage] = !expanded;
        renderDashboard();
      });
      el.appendChild(toggle);
    }
    if (!el.children.length) {
      el.innerHTML = '<div class="empty-state">empty</div>';
    }
  });
  setText("#pipeInboxCount", stageCounts.new);
  setText("#pipeAppliedCount", stageCounts.applied);
  setText("#pipeSkipCount", stageCounts.skip);
  const message = $("#pipelineMessage");
  if (message) {
    message.textContent = pipelineMessage;
    message.className = `pipeline-message ${classToken(pipelineMessageKind, ["ok", "error", "pending"])}`;
  }

  // Recent activity
  const timeline = $("#dashboardTimeline");
  timeline.innerHTML = "";
  const events = [];
  jobs.forEach((j) => {
    (j.events || []).forEach((ev) => {
      events.push({ ...ev, jobTitle: j.title, jobCompany: j.company });
    });
  });
  events.sort((a, b) => new Date(b.created_at || 0) - new Date(a.created_at || 0));
  events.slice(0, 8).forEach((ev) => {
    timeline.appendChild(renderTimelineItem(ev, true));
  });
  if (!events.length) {
    timeline.innerHTML = '<div class="empty-state">empty</div>';
  }

  // Workflows
  const wfList = $("#workflowList");
  wfList.innerHTML = "";
  const runs = appState.agent_runs || [];
  if (runs.length) {
    runs.slice(0, 6).forEach((r) => {
      const item = document.createElement("div");
      item.className = "workflow-item";
      const statusColor = r.status === "completed" ? "var(--good)" : r.status === "failed" ? "var(--bad)" : "var(--warn)";
      item.innerHTML = `
        <span class="workflow-name">${esc(r.description || "run")}</span>
        <span class="workflow-meta" style="color:${statusColor}">${esc(r.status || "?")}</span>
      `;
      wfList.appendChild(item);
    });
  } else {
    wfList.innerHTML = '<div class="empty-state">empty</div>';
  }
};

/* ── Brain ── */
const renderBrain = () => {
  if (!appState) return;
  const brain = appState.brain || {};
  const entityCounts = brain.entity_counts || {};
  const eventCounts = brain.event_counts || {};
  const events = brain.recent_events || [];
  const query = brainQuery.trim().toLowerCase();
  const areas = Object.entries(entityCounts).sort((a, b) => Number(b[1]) - Number(a[1]));
  if (brainAreaFilter !== "all" && !areas.some(([type]) => type === brainAreaFilter)) {
    brainAreaFilter = "all";
  }
  const filtered = events.filter((event) => {
    const entity = event.entity || {};
    const areaMatch = brainAreaFilter === "all" || entity.type === brainAreaFilter;
    const queryMatch = !query || [
      event.event_type,
      event.title,
      event.content,
      event.evidence_text,
      entity.title,
      entity.type,
    ].some((value) => String(value || "").toLowerCase().includes(query));
    return areaMatch && queryMatch;
  });

  if (brainStats) {
    brainStats.innerHTML = `
      <div class="brain-stat"><span>Entities</span><strong>${fmtNum(appState.context_counts?.brain_entities || 0)}</strong></div>
      <div class="brain-stat"><span>Events</span><strong>${fmtNum(appState.context_counts?.brain_events || 0)}</strong></div>
      <div class="brain-stat"><span>Decisions</span><strong>${fmtNum(eventCounts.portrayal_decision || 0)}</strong></div>
      <div class="brain-stat"><span>Signals</span><strong>${fmtNum(eventCounts.conversation_signal || 0)}</strong></div>
    `;
  }

  if (brainAreaCount) brainAreaCount.textContent = fmtNum(areas.length);
  if (brainAreaList) {
    brainAreaList.innerHTML = "";
    const all = document.createElement("button");
    all.type = "button";
    all.className = `brain-area${brainAreaFilter === "all" ? " active" : ""}`;
    all.innerHTML = `<span>All</span><strong>${fmtNum(events.length)}</strong>`;
    setTip(all, "Show every recorded memory event.");
    all.addEventListener("click", () => {
      brainAreaFilter = "all";
      renderBrain();
    });
    brainAreaList.appendChild(all);
    areas.forEach(([type, count]) => {
      const item = document.createElement("button");
      item.type = "button";
      item.className = `brain-area${brainAreaFilter === type ? " active" : ""}`;
      item.innerHTML = `<span>${esc(type.replace(/_/g, " "))}</span><strong>${fmtNum(count)}</strong>`;
      setTip(item, `Show ${type.replace(/_/g, " ")} memory events.`);
      item.addEventListener("click", () => {
        brainAreaFilter = type;
        renderBrain();
      });
      brainAreaList.appendChild(item);
    });
  }

  if (brainEventCount) brainEventCount.textContent = fmtNum(filtered.length);
  if (brainList) {
    brainList.innerHTML = "";
    if (!filtered.length) {
      brainList.innerHTML = '<div class="empty-state">empty</div>';
    } else {
      filtered.forEach((event) => {
        const entity = event.entity || {};
        const item = document.createElement("article");
        item.className = "brain-event";
        const meta = [
          event.event_type ? humanize(event.event_type) : "",
          entity.title || entity.type || "",
          event.job_id ? `job ${event.job_id}` : "",
          fmtDateTime(event.occurred_at || event.created_at),
        ].filter(Boolean);
        item.innerHTML = `
          <div class="brain-event-top">
            <span class="brain-kind">${esc(entity.type ? humanize(entity.type) : "memory")}</span>
            <span class="brain-importance">${Math.round(Number(event.importance || 0) * 100)} importance</span>
          </div>
          <h3>${esc(event.title || "Memory")}</h3>
          <p>${esc(event.content || event.evidence_text || "").slice(0, 560)}</p>
          <div class="brain-meta">${meta.map((part) => `<span>${esc(part)}</span>`).join("")}</div>
        `;
        brainList.appendChild(item);
      });
    }
  }
};

/* ── Discovery ── */
const discoveryCandidates = () => appState?.discovery?.candidates || [];
const discoveryLanes = [
  { id: "inbox", label: "Inbox", statuses: ["new", "hydrated"] },
  { id: "needs_review", label: "Needs Review", statuses: ["needs_review"] },
  { id: "ready", label: "Ready", statuses: ["ready"] },
  { id: "approved", label: "Interesting", statuses: ["approved"] },
  { id: "prepared", label: "Prepared", statuses: ["prepared"] },
  { id: "blocked", label: "Blocked", statuses: ["blocked", "dismissed"] },
];

const setDiscoveryMessage = (text, tone = "") => {
  if (!discoveryMessage) return;
  discoveryMessage.textContent = text || "";
  discoveryMessage.dataset.tone = tone || "";
};

const renderDiscovery = () => {
  if (!appState) return;
  const candidates = discoveryCandidates();
  const counts = appState.discovery?.counts || {};
  const exa = discoveryStatus?.providers?.exa || {};
  const ats = discoveryStatus?.providers?.ats || {};
  const disabled = discoveryStatus && !discoveryStatus.enabled;
  if (discoveryStats) {
    discoveryStats.innerHTML = `
      <div class="discovery-stat"><span>Mode</span><strong>${disabled ? "disabled" : "active"}</strong></div>
      <div class="discovery-stat"><span>Leads</span><strong>${fmtNum(counts.total || 0)}</strong></div>
      <div class="discovery-stat"><span>Ready</span><strong>${fmtNum(counts.ready || 0)}</strong></div>
      <div class="discovery-stat"><span>Interesting</span><strong>${fmtNum(counts.approved || 0)}</strong></div>
      <div class="discovery-stat"><span>Review</span><strong>${fmtNum(counts.needs_review || 0)}</strong></div>
      <div class="discovery-stat"><span>Search</span><strong>${exa.configured ? "ready" : "not set"}</strong></div>
      <div class="discovery-stat wide"><span>ATS</span><strong>${esc((ats.hydrators || []).join(" / ") || "none")}</strong></div>
    `;
  }
  renderDiscoveryControls(disabled);
  renderDiscoveryList(candidates);
};

const renderDiscoveryControls = (disabled) => {
  const enabledTips = new Map([
    [discoveryQuery, "Search with your own role, company, skill, location, or exact ATS URL."],
    [discoveryLimit, "Limit how many leads are returned for this search."],
    [discoveryHydrate, "Pull official ATS details when available before saving the lead."],
    [discoveryUrl, "Paste one posting URL to add it directly to the lead board."],
    [prepareApprovedDiscovery, "Create JobApps job records from leads marked Interesting. This does not apply, submit, or send anything."],
  ]);
  [discoveryQuery, discoveryLimit, discoveryHydrate, discoveryUrl, prepareApprovedDiscovery].forEach((control) => {
    if (control) {
      control.disabled = Boolean(disabled);
      control.title = disabled ? "Find is disabled in config" : enabledTips.get(control) || "";
    }
  });
  [discoverySearchForm, discoveryHydrateForm].forEach((form) => {
    form?.querySelectorAll("button").forEach((button) => {
      button.disabled = Boolean(disabled);
      if (disabled) {
        button.title = "Find is disabled in config";
      } else if (!button.title) {
        button.title = button.closest("#discoverySearchForm")
          ? "Search job sources using exactly what you typed."
          : "Add this exact URL as a lead.";
      }
    });
  });
};

const renderDiscoveryList = (candidates) => {
  if (!discoveryList) return;
  discoveryList.innerHTML = "";
  const query = discoveryQueryFilter.trim().toLowerCase();
  let filtered = candidates || [];
  if (discoveryStatusFilter !== "all") {
    filtered = filtered.filter((item) => {
      if (discoveryStatusFilter === "new") return ["new", "hydrated"].includes(item.status);
      return item.status === discoveryStatusFilter;
    });
  }
  if (query) {
    filtered = filtered.filter((item) =>
      [
        item.title,
        item.company,
        item.location,
        item.source_provider,
        item.canonical_url,
        item.description,
      ].some((value) => String(value || "").toLowerCase().includes(query))
    );
  }
  if (!filtered.length) {
    discoveryList.innerHTML = '<div class="empty-state">empty</div>';
    return;
  }
  discoveryList.className = "discovery-list discovery-board";
  discoveryLanes.forEach((lane) => {
    const laneItems = filtered.filter((item) => lane.statuses.includes(item.status || "new"));
    const col = document.createElement("section");
    col.className = "lead-column";
    col.innerHTML = `
      <div class="lead-column-head">
        <span>${esc(lane.label)}</span>
        <strong>${fmtNum(laneItems.length)}</strong>
      </div>
      <div class="lead-column-body"></div>
    `;
    const body = col.querySelector(".lead-column-body");
    if (!laneItems.length) {
      body.innerHTML = '<div class="empty-state">empty</div>';
    }
    laneItems.forEach((item) => {
      body.appendChild(renderLeadCard(item));
    });
    discoveryList.appendChild(col);
  });
};

const renderLeadCard = (item) => {
    const card = document.createElement("article");
    card.className = `discovery-card ${classToken(item.status, ["ready", "approved", "needs_review", "blocked", "prepared", "new", "hydrated", "dismissed"])}`;
    const blocker = item.blocker_status || "unknown";
    const meta = [
      item.source_provider,
      item.location,
      item.workplace_type,
      item.posted_at ? fmtDateTime(item.posted_at) : "",
      item.sighting_count ? `${fmtNum(item.sighting_count)} sightings` : "",
    ].filter(Boolean).join(" · ");
    const reasons = (item.blocker_reasons || [])
      .slice(0, 2)
      .map((reason) => reason.evidence || reason.area || "")
      .filter(Boolean)
      .join(" ");
    card.innerHTML = `
      <div class="discovery-card-main">
        <div class="discovery-card-top">
          <span class="material-kind">${esc(item.source_provider || "source")}</span>
          <span class="discovery-status ${classToken(item.status, ["ready", "approved", "needs_review", "blocked", "prepared", "new", "hydrated", "dismissed"])}">${esc(humanize(item.status || "new"))}</span>
        </div>
        <h3>${esc(item.title || "Untitled role")}</h3>
        <p>${esc([item.company, meta].filter(Boolean).join(" · "))}</p>
        <div class="discovery-evidence">${esc(humanize(blocker))}${reasons ? " · " + esc(reasons).slice(0, 220) : ""}</div>
        <code>${esc(item.canonical_url || item.discovered_url || "")}</code>
      </div>
      <div class="discovery-card-side">
        <span>${esc(item.source_provider || "source")}</span>
        ${item.job_id ? `<span>job ${esc(item.job_id)}</span>` : ""}
      </div>
    `;
    const evidence = [
      item.compensation ? `Compensation: ${item.compensation}` : "",
      item.workplace_type ? `Workplace: ${item.workplace_type}` : "",
      item.employment_type ? `Employment: ${item.employment_type}` : "",
      item.application_form_summary ? `Form: ${item.application_form_summary}` : "",
      item.description ? `Description: ${item.description.slice(0, 700)}` : "",
    ].filter(Boolean);
    if (evidence.length) {
      const detail = document.createElement("details");
      detail.className = "discovery-detail";
      detail.innerHTML = `
        <summary>evidence</summary>
        <div>${evidence.map((line) => `<p>${esc(line)}</p>`).join("")}</div>
      `;
      card.appendChild(detail);
    }
    const actions = document.createElement("div");
    actions.className = "material-actions";
    const disabled = discoveryStatus && !discoveryStatus.enabled;
    const url = item.canonical_url || item.discovered_url || "";
    if (url) actions.appendChild(materialLink("Open Posting", url, "Open the original job posting in a new browser tab."));
    if (!disabled && !item.job_id && item.status !== "blocked" && item.status !== "dismissed" && item.status !== "approved") {
      const approve = document.createElement("button");
      approve.type = "button";
      approve.className = "link-button";
      approve.textContent = "Mark Interesting";
      setTip(approve, "Move this lead into the Interesting lane so it can be prepared as a job later.");
      approve.addEventListener("click", () => approveDiscoveryCandidate(item.id));
      actions.appendChild(approve);
    }
    if (!disabled && !item.job_id && item.status === "approved") {
      const prepare = document.createElement("button");
      prepare.type = "button";
      prepare.className = "link-button";
      prepare.textContent = "Prepare Job";
      setTip(prepare, "Create a JobApps job from this lead and start the app-owned workflow. No external submission happens.");
      prepare.addEventListener("click", () => prepareDiscoveryCandidate(item.id));
      actions.appendChild(prepare);
    }
    if (item.status !== "dismissed" && !item.job_id) {
      const dismiss = document.createElement("button");
      dismiss.type = "button";
      dismiss.className = "link-button";
      dismiss.textContent = "Dismiss";
      setTip(dismiss, "Hide this lead from active lanes without deleting the record.");
      dismiss.addEventListener("click", () => updateDiscoveryCandidateStatus(item.id, "dismissed"));
      actions.appendChild(dismiss);
    }
    const discuss = document.createElement("button");
    discuss.type = "button";
    discuss.className = "link-button";
    discuss.textContent = "Copy Prompt";
    setTip(discuss, "Copy a native Hermes prompt for blocker inspection or next steps. Nothing is submitted.");
    discuss.addEventListener("click", () => askHermesAboutDiscovery(item));
    actions.appendChild(discuss);
    card.appendChild(actions);
    return card;
};

const refreshDiscovery = async () => {
  const [status, state] = await Promise.all([
    fetchJson("/api/discovery/status"),
    fetchJson("/api/state"),
  ]);
  discoveryStatus = status || discoveryStatus;
  if (state) appState = state;
  renderCurrentView();
};

const runDiscoverySearch = async () => {
  const query = discoveryQuery?.value.trim() || "";
  if (!query) return;
  discoveryBusy = true;
  setDiscoveryMessage("searching", "");
  renderDiscovery();
  const result = await postJson("/api/discovery/search", {
    query,
    limit: Number(discoveryLimit?.value || 8),
    hydrate: Boolean(discoveryHydrate?.checked),
  });
  discoveryBusy = false;
  if (result?.error) {
    setDiscoveryMessage(result.error, "error");
  } else {
    setDiscoveryMessage(`${fmtNum(result.count || 0)} candidates`, "ok");
  }
  await refreshDiscovery();
};

const hydrateDiscoveryUrl = async () => {
  const url = discoveryUrl?.value.trim() || "";
  if (!url) return;
  discoveryBusy = true;
  setDiscoveryMessage("hydrating", "");
  const result = await postJson("/api/discovery/hydrate", { url });
  discoveryBusy = false;
  if (result?.error) {
    setDiscoveryMessage(result.error, "error");
  } else {
    setDiscoveryMessage("hydrated", "ok");
    if (discoveryUrl) discoveryUrl.value = "";
  }
  await refreshDiscovery();
};

const approveDiscoveryCandidate = async (candidateId) => {
  if (!candidateId) return;
  const result = await postJson(`/api/discovery/candidates/${encodeURIComponent(candidateId)}/status`, {
    status: "approved",
    note: "User approved from shortlist in dashboard.",
  });
  if (result?.error) {
    setDiscoveryMessage(result.error, "error");
    return;
  }
  setDiscoveryMessage("approved", "ok");
  await refreshDiscovery();
};

const prepareApprovedDiscoveryCandidates = async () => {
  setDiscoveryMessage("preparing approved", "");
  const result = await postJson("/api/discovery/candidates/prepare-approved", { limit: 5 });
  if (result?.error) {
    setDiscoveryMessage(result.error, "error");
    return;
  }
  setDiscoveryMessage(`${fmtNum(result?.prepared_count || 0)} prepared`, "ok");
  const first = result?.prepared?.[0]?.job?.job?.id;
  if (first) currentJobId = first;
  await refreshDiscovery();
  switchView("jobs");
};

const prepareDiscoveryCandidate = async (candidateId) => {
  if (!candidateId) return;
  setDiscoveryMessage("preparing", "");
  const result = await postJson(`/api/discovery/candidates/${encodeURIComponent(candidateId)}/prepare`, {});
  if (result?.error) {
    setDiscoveryMessage(result.error, "error");
    return;
  }
  setDiscoveryMessage("prepared", "ok");
  if (result?.job?.job?.id) currentJobId = result.job.job.id;
  await refreshDiscovery();
  switchView("jobs");
};

const updateDiscoveryCandidateStatus = async (candidateId, status) => {
  if (!candidateId) return;
  const result = await postJson(`/api/discovery/candidates/${encodeURIComponent(candidateId)}/status`, { status });
  if (result?.error) {
    setDiscoveryMessage(result.error, "error");
    return;
  }
  setDiscoveryMessage(status, "ok");
  await refreshDiscovery();
};

const askHermesAboutDiscovery = (item) => {
  const prompt = [
    "Review this discovered role before I spend time on it.",
    `Candidate id: ${item.id}`,
    `Role: ${item.title || "untitled"} at ${item.company || "unknown company"}`,
    `URL: ${item.canonical_url || item.discovered_url || ""}`,
    `Status: ${item.status || "new"}; blocker: ${item.blocker_status || "unknown"}`,
    item.compensation ? `Compensation: ${item.compensation}` : "",
    item.application_form_summary ? `Application form: ${item.application_form_summary}` : "",
    "Tell me whether the blocker preflight is enough or what source I should check next.",
  ].filter(Boolean).join("\n");
  copyText(prompt)
    .then((copied) => setDiscoveryMessage(copied ? "prompt copied for Hermes TUI" : "prompt placed in chat draft", copied ? "ok" : ""))
    .catch((err) => setDiscoveryMessage(err.message || "copy failed", "error"));
};

/* ── Jobs ── */
let jobsFilter = "all";
let jobsQuery = "";

const initJobsFilters = () => {
  $("#jobsSearch").addEventListener("input", (e) => {
    jobsQuery = e.target.value.toLowerCase();
    renderJobs();
  });
  $$("#jobsFilters [data-filter]").forEach((chip) => {
    chip.addEventListener("click", () => {
      $$("#jobsFilters [data-filter]").forEach((c) => c.classList.remove("active"));
      chip.classList.add("active");
      jobsFilter = chip.dataset.filter || "all";
      renderJobs();
    });
  });
};

const selectedJob = () => {
  const jobs = appState?.jobs || [];
  if (currentView === "jobs" && !currentJobId) return null;
  return jobs.find((j) => j.id === currentJobId) || jobs[0] || null;
};

const jobActiveRun = (job = {}) => job.active_run || null;

const startHermesRun = async (jobId) => {
  if (!jobId) return;
  setJobsMessage("starting", "pending");
  const result = await postJson(`/api/jobs/${encodeURIComponent(jobId)}/hermes-run`, {});
  if (result?.error) {
    setJobsMessage(result.error, "error");
    return;
  }
  currentJobId = jobId;
  const state = await fetchJson("/api/state");
  if (state) appState = state;
  const status = result?.active_run?.status || "queued";
  setJobsMessage(`run ${humanize(status)}`, "ok");
  renderCurrentView();
  saveChatState();
};

const refreshHermesRun = async (jobId) => {
  if (!jobId) return;
  setJobsMessage("refreshing", "pending");
  const result = await fetchJson(`/api/jobs/${encodeURIComponent(jobId)}/hermes-run`);
  if (result?.error) {
    setJobsMessage(result.error, "error");
    return;
  }
  currentJobId = jobId;
  const state = await fetchJson("/api/state");
  if (state) appState = state;
  setJobsMessage("refreshed", "ok");
  renderCurrentView();
  saveChatState();
};

const startPendingMaterialPrep = async () => {
  setJobsMessage("starting", "pending");
  const result = await postJson("/api/jobs/hermes-runs", { scope: "pending" });
  if (result?.error) {
    setJobsMessage(result.error, "error");
    return;
  }
  if (result?.state) appState = result.state;
  const queued = Number(result?.queued_count || 0);
  const existing = Number(result?.existing_count || 0);
  const failed = Number(result?.failed_count || 0);
  const parts = [];
  if (queued) parts.push(`${fmtNum(queued)} queued`);
  if (existing) parts.push(`${fmtNum(existing)} active`);
  if (failed) parts.push(`${fmtNum(failed)} failed`);
  setJobsMessage(parts.join(" · ") || "nothing pending", failed ? "error" : "ok");
  renderCurrentView();
  saveChatState();
};

const materialDisplayName = (item) => (
  item.display_name || item.filename || fileName(item.file_path || item.path || item.pdf_path) || `${item.kind || "material"}.${item.format || "txt"}`
);

const MATERIAL_KIND_LABELS = {
  cover_letter: "Cover letter",
  outreach: "Outreach",
  outreach_draft: "Outreach draft",
  resume: "Resume",
  resume_notes: "Resume notes",
  resume_tailoring: "Resume notes",
  short_answers: "Short answers",
};

const materialKindLabel = (item = {}) => MATERIAL_KIND_LABELS[item.kind] || humanize(item.kind || "Material");

const materialUserName = (item = {}) => {
  const display = materialDisplayName(item);
  if (!display || /\.(tex|json|text|txt)$/i.test(display)) return materialKindLabel(item);
  return display;
};

const renderJobs = () => {
  if (!appState) return;
  const list = $("#jobsList");
  list.innerHTML = "";

  let jobs = appState.jobs || [];
  if (!currentJobId && jobs.length) currentJobId = jobs[0].id;
  if (jobsFilter !== "all") {
    jobs = jobs.filter((j) => jobStage(j) === jobsFilter);
  }
  if (jobsQuery) {
    jobs = jobs.filter((j) =>
      (j.title || "").toLowerCase().includes(jobsQuery) ||
      (j.company || "").toLowerCase().includes(jobsQuery) ||
      (j.location || "").toLowerCase().includes(jobsQuery) ||
      (j.status || "").toLowerCase().includes(jobsQuery)
    );
  }
  if (jobs.length && !jobs.some((j) => j.id === currentJobId)) {
    currentJobId = jobs[0].id;
  }

  if (!jobs.length) {
    currentJobId = null;
    list.innerHTML = '<div class="empty-state">empty</div>';
    renderJobDetail();
    return;
  }

  const sections = JOB_STATUS_OPTIONS
    .map((option) => ({
      ...option,
      jobs: jobs.filter((job) => jobStage(job) === option.stage),
    }))
    .filter((section) => section.jobs.length || jobsFilter === section.stage);

  sections.forEach((section) => {
    const sectionEl = document.createElement("section");
    sectionEl.className = "job-list-section";
    sectionEl.innerHTML = `
      <div class="job-list-section-head">
        <span>${esc(section.label)}</span>
        <strong>${fmtNum(section.jobs.length)}</strong>
      </div>
      <div class="job-list-section-body"></div>
    `;
    const body = sectionEl.querySelector(".job-list-section-body");
    if (!section.jobs.length) {
      body.innerHTML = '<div class="empty-state">empty</div>';
    }
    section.jobs.forEach((j) => {
      const stage = jobStage(j);
      const decision = j.decision || j.evaluation?.decision || "pending";
      const activeRun = jobActiveRun(j);
      const actionCount = jobOpenActionCount(j);
      const row = document.createElement("div");
      row.className = `job-row state-${stage}${j.id === currentJobId ? " active" : ""}`;
      row.innerHTML = `
        <div class="job-row-info">
          <div class="job-row-title">${esc(j.title || "untitled")}</div>
          <div class="job-row-company">${esc([j.company, j.location].filter(Boolean).join(" · "))}</div>
          <div class="job-row-date">${esc(jobDateMeta(j, stage) || "date pending")}</div>
        </div>
        <div class="job-row-meta">
          <span class="state-pill state-${esc(stage)}">${esc(stateLabel(stage))}</span>
          <span class="badge badge-${classToken(decision, ["apply", "skip", "pending"])}">${esc(decision)}</span>
          ${activeRun ? `<span class="job-row-run">run ${esc(humanize(activeRun.status || "active"))}</span>` : ""}
          <span class="job-row-actions">${fmtNum(actionCount)} actions</span>
        </div>
      `;
      row.addEventListener("click", () => {
        currentJobId = j.id;
        renderJobs();
        renderJobDetail();
        saveChatState();
      });
      body.appendChild(row);
    });
    list.appendChild(sectionEl);
  });
  renderJobDetail();
};

const renderJobDetail = () => {
  if (!jobDetailPanel) return;
  if (!appState) {
    jobDetailPanel.innerHTML = '<div class="empty-state">loading</div>';
    return;
  }
  const job = selectedJob();
  if (!job) {
    jobDetailPanel.innerHTML = '<div class="empty-state">select a job</div>';
    return;
  }
  currentJobId = job.id;
  const decision = jobDecision(job);
  const stage = jobStage(job);
  const risks = job.risks || [];
  const requirements = job.tailoring_requirements || [];
  const signals = job.application_signals || [];
  const decisions = job.portrayal_decisions || [];
  const progress = openItems(job.progress || []);
  const materials = materialPreferredItems(job.materials_workbench?.items || []).filter(materialShouldShow).sort((a, b) => {
    const order = { resume: 0, resume_tailoring: 1, cover_letter: 2 };
    return (order[a.kind] ?? 10) - (order[b.kind] ?? 10);
  });
  const outreach = job.outreach || {};
  const drafts = outreach.drafts || [];
  const contacts = outreach.contacts || job.contacts || [];
  const followups = outreach.followups || job.followups || [];
  const jobUrl = safeHref(job.url || job.apply_url || "");
  const activeRun = jobActiveRun(job);
  const runStatus = activeRun?.status || job.hermes_run_status || "";
  const actionCount = jobOpenActionCount(job);
  const dateMeta = jobDateMeta(job, stage);
  const runActionMarkup = activeRun
    ? `
      <span class="badge">run: ${esc(humanize(runStatus || "active"))}</span>
      <button class="link-button" type="button" data-refresh-hermes-run="${esc(job.id)}">Refresh Run</button>
    `
    : `
      <button class="link-button" type="button" data-start-hermes-run="${esc(job.id)}">Start Prep</button>
    `;
  const materialRows = materials.length ? materials.map((item) => {
    const name = materialUserName(item);
    const meta = materialMetaText(item);
    const pdfPath = materialPdfPath(item);
    const canPreview = materialCanPreviewInApp(item);
    const needsPdf = materialNeedsPdf(item);
    return `
      <div class="detail-row material-detail-row">
        <div>
          <strong>${esc(name)}</strong>
          <span>${esc(meta)}</span>
        </div>
        <div class="detail-actions">
          ${pdfPath && item.id ? `<a class="link-button material-link" href="${esc(materialUrl(item.id, "pdf"))}" target="_blank" rel="noopener" title="Open the PDF in the browser.">Open PDF</a>` : ""}
          ${canPreview ? `<button class="link-button" type="button" data-preview-material="${esc(item.id)}" title="Preview this saved text or data inside JobApps.">Preview</button>` : ""}
          ${needsPdf && item.id ? `<button class="link-button" type="button" data-compile-material="${esc(item.id)}" title="Build the PDF for this material.">Build PDF</button>` : ""}
        </div>
      </div>
    `;
  }).join("") : '<div class="empty-state">no materials yet</div>';

  const riskRows = risks.length ? risks.map((item) => {
    const label = typeof item === "string" ? "risk" : (item.label || item.area || "risk");
    const assessment = typeof item === "string" ? item : (item.assessment || item.evidence || item.value || "");
    return `<li><span>${esc(label)}</span><p>${esc(assessment)}</p></li>`;
  }).join("") : '<li><span>risks</span><p>none recorded</p></li>';

  const requirementRows = requirements.length ? requirements.slice(0, 8).map((item) => `
    <div class="detail-row requirement-row">
      <div>
        <strong>${esc(item.requirement || "Requirement")}</strong>
        <span>${esc([item.category, item.status, item.priority != null ? `priority ${Math.round(Number(item.priority || 0) * 100)}` : ""].filter(Boolean).join(" · "))}</span>
        ${item.source_text ? `<p>${esc(item.source_text).slice(0, 260)}</p>` : ""}
      </div>
    </div>
  `).join("") : '<div class="empty-state">no tailoring requirements yet</div>';

  const signalRows = signals.length ? signals.slice(0, 8).map((item) => `
    <div class="detail-row signal-row">
      <div>
        <strong>${esc(item.label || humanize(item.signal_type || "signal"))}</strong>
        <span>${esc([humanize(item.signal_type), item.actionability, item.confidence != null ? `${Math.round(Number(item.confidence || 0) * 100)}%` : ""].filter(Boolean).join(" · "))}</span>
        <p>${esc(item.value || item.evidence_text || "").slice(0, 260)}</p>
      </div>
    </div>
  `).join("") : '<div class="empty-state">no job signals yet</div>';

  const decisionRows = decisions.length ? decisions.slice(0, 6).map((item) => `
    <div class="detail-row decision-row">
      <div>
        <strong>${esc(item.target || humanize(item.decision_type || "portrayal decision"))}</strong>
        <span>${esc([humanize(item.decision_type), item.source].filter(Boolean).join(" · "))}</span>
        <p>${esc(item.rationale || item.after_text || "").slice(0, 320)}</p>
      </div>
    </div>
  `).join("") : '<div class="empty-state">no portrayal decisions yet</div>';

  const progressRows = progress.length ? progress.map((item) => `
    <div class="detail-row progress-row">
      <div>
        <strong>${esc(item.summary || item.title || "Task")}</strong>
        <span>${esc([humanize(item.kind), item.status, item.due_date].filter(Boolean).join(" · "))}</span>
      </div>
    </div>
  `).join("") : '<div class="empty-state">no open tasks</div>';

  const draftRows = drafts.length ? drafts.map((draft) => {
    const contact = draft.contact || {};
    const contactLabel = contact.name || draft.to_email || draft.contact_id || "contact pending";
    return `
      <div class="detail-row outreach-draft-row">
        <div>
          <strong>${esc(draft.subject || draft.display_name || "Outreach draft")}</strong>
          <span>${esc([draft.channel, contactLabel].filter(Boolean).join(" · "))}</span>
          ${draft.content_preview ? `<p>${esc(draft.content_preview)}</p>` : ""}
        </div>
        <div class="detail-actions">
          ${draft.id ? `<button class="link-button" type="button" data-preview-material="${esc(draft.id)}" title="Preview this saved outreach draft inside JobApps.">Preview</button>` : ""}
        </div>
      </div>
    `;
  }).join("") : '<div class="empty-state">no outreach drafts yet</div>';

  const contactRows = contacts.length ? contacts.map((contact) => {
    const profileUrl = safeHref(contact.linkedin_url || contact.source_url || "");
    return `
      <div class="detail-row contact-row">
        <div>
          <strong>${esc(contact.name || "Contact")}</strong>
          <span>${esc([contact.role, contact.company, contact.email_status || (contact.email ? "found" : "missing")].filter(Boolean).join(" · "))}</span>
          ${contact.email ? `<code>${esc(contact.email)}</code>` : ""}
        </div>
        <div class="detail-actions">
          ${profileUrl ? `<a class="link-button material-link" href="${esc(profileUrl)}" target="_blank" rel="noopener">Open Profile</a>` : ""}
        </div>
      </div>
    `;
  }).join("") : '<div class="empty-state">no contacts yet</div>';

  const followupRows = followups.length ? followups.map((item) => `
    <div class="detail-row followup-row">
      <div>
        <strong>${esc(item.reason || item.note || item.summary || item.title || "Follow up")}</strong>
        <span>${esc([item.due_date, item.status].filter(Boolean).join(" · "))}</span>
      </div>
    </div>
  `).join("") : '<div class="empty-state">no follow-ups yet</div>';

  jobDetailPanel.innerHTML = `
    <div class="job-detail-head">
      <span class="eyebrow">Job detail</span>
      <h2>${esc(job.title || "untitled")}</h2>
      <p>${esc([job.company, job.location].filter(Boolean).join(" · "))}</p>
      <div class="job-packet-dates">
        <span>${esc(dateMeta || "date pending")}</span>
        ${job.id ? `<span>${esc(job.id)}</span>` : ""}
      </div>
      <div class="job-detail-badges">
        <span class="state-pill state-${esc(stage)}">${esc(stateLabel(stage))}</span>
        <span class="badge badge-${classToken(decision, ["apply", "skip", "pending"])}">decision: ${esc(decision)}</span>
        ${job.status && job.status !== currentJobStatusValue(job) ? `<span class="badge">stored: ${esc(humanize(job.status))}</span>` : ""}
      </div>
      <div class="job-status-toolbar">
        ${statusSelectMarkup(job, "detail-status-menu")}
        ${runActionMarkup}
      </div>
      ${jobUrl ? `<a class="link-button material-link" href="${esc(jobUrl)}" target="_blank" rel="noopener">Open posting</a>` : ""}
    </div>
    <div class="job-detail-metrics">
      <span><strong>${fmtNum(actionCount)}</strong> actions</span>
      <span><strong>${fmtNum(requirements.length)}</strong> requirements</span>
      <span><strong>${fmtNum(signals.length)}</strong> signals</span>
      <span><strong>${fmtNum(materials.length)}</strong> materials</span>
      <span><strong>${fmtNum(contacts.length)}</strong> people</span>
      <span><strong>${fmtNum(followups.length)}</strong> follow-ups</span>
    </div>
    <section class="job-detail-section next-action-section">
      <h3>Next action</h3>
      <p>${esc(job.next_action || "Approve, generate, review, apply, then handle outreach/follow-up.")}</p>
    </section>
    <div class="job-detail-grid">
      <section class="job-detail-section">
        <h3>Blockers</h3>
        <ul class="risk-list">${riskRows}</ul>
      </section>
      <section class="job-detail-section">
        <h3>Open Tasks</h3>
        ${progressRows}
      </section>
      <section class="job-detail-section wide">
        <h3>Materials</h3>
        ${materialRows}
      </section>
      <details class="job-detail-section wide detail-disclosure">
        <summary><span>Tailoring Requirements</span><strong>${fmtNum(requirements.length)}</strong></summary>
        <h3>Tailoring Requirements</h3>
        ${requirementRows}
      </details>
      <details class="job-detail-section wide detail-disclosure">
        <summary><span>Job Signals</span><strong>${fmtNum(signals.length)}</strong></summary>
        <h3>Job Signals</h3>
        ${signalRows}
      </details>
      <details class="job-detail-section wide detail-disclosure">
        <summary><span>Portrayal Decisions</span><strong>${fmtNum(decisions.length)}</strong></summary>
        <h3>Portrayal Decisions</h3>
        ${decisionRows}
      </details>
      <details class="job-detail-section wide detail-disclosure">
        <summary><span>Network</span><strong>${fmtNum(contacts.length + drafts.length + followups.length)}</strong></summary>
        <h3>Network</h3>
        ${draftRows}
        <h4>People</h4>
        ${contactRows}
      </details>
      <details class="job-detail-section wide detail-disclosure">
        <summary><span>Follow-ups</span><strong>${fmtNum(followups.length)}</strong></summary>
        <h3>Follow-ups</h3>
        ${followupRows}
      </details>
    </div>
  `;
  jobDetailPanel.querySelectorAll("[data-compile-material]").forEach((button) => {
    button.addEventListener("click", () => compileMaterial(button.dataset.compileMaterial || ""));
  });
  jobDetailPanel.querySelectorAll("[data-preview-material]").forEach((button) => {
    button.addEventListener("click", () => openMaterialViewer(button.dataset.previewMaterial || ""));
  });
  jobDetailPanel.querySelectorAll("[data-start-hermes-run]").forEach((button) => {
    button.addEventListener("click", () => startHermesRun(button.dataset.startHermesRun || ""));
  });
  jobDetailPanel.querySelectorAll("[data-refresh-hermes-run]").forEach((button) => {
    button.addEventListener("click", () => refreshHermesRun(button.dataset.refreshHermesRun || ""));
  });
  attachJobStatusControls(jobDetailPanel);
};

/* ── Activity ── */
const renderActivity = () => {
  const container = $("#activityTimeline");
  container.innerHTML = "";
  if (!appState) return;

  const events = [];
  (appState.jobs || []).forEach((j) => {
    (j.events || []).forEach((ev) => {
      events.push({ ...ev, jobTitle: j.title, jobCompany: j.company });
    });
  });
  (appState.agent_runs || []).forEach((r) => {
    events.push({
      event_type: "agent_run",
      summary: r.description || "Agent run",
      note: r.status,
      created_at: r.updated_at || r.created_at,
      runStatus: r.status,
    });
  });
  events.sort((a, b) => new Date(b.created_at || 0) - new Date(a.created_at || 0));

  if (!events.length) {
    container.innerHTML = '<div class="empty-state">empty</div>';
    return;
  }

  events.forEach((ev) => {
    container.appendChild(renderTimelineItem(ev, false));
  });
};

const renderTimelineItem = (ev, compact) => {
  const item = document.createElement("div");
  item.className = "timeline-item";
  const dot = document.createElement("div");
  dot.className = "timeline-dot";
  if (ev.event_type === "evaluated") dot.classList.add("event");
  else if (ev.event_type === "agent_run") dot.classList.add("run");
  else if (ev.event_type === "material_saved") dot.classList.add("material");

  const content = document.createElement("div");
  content.className = "timeline-content";
  const title = document.createElement("div");
  title.className = "timeline-title";
  title.textContent = ev.summary || ev.note || ev.event_type;
  const meta = document.createElement("div");
  meta.className = "timeline-meta";
  const parts = [];
  if (ev.jobTitle) parts.push(ev.jobTitle);
  if (ev.event_type) parts.push(ev.event_type);
  if (ev.created_at) parts.push(fmtDate(ev.created_at));
  meta.textContent = parts.join(" · ");

  content.appendChild(title);
  content.appendChild(meta);
  item.appendChild(dot);
  item.appendChild(content);
  return item;
};

/* ── Network ── */
const renderNetwork = () => {
  const grid = $("#networkGrid");
  if (!appState) return;
  const contacts = appState.contacts || [];
  const jobs = appState.jobs || [];
  const openFollowups = appState.followups || [];
  const notes = [];
  jobs.forEach((j) => {
    (j.research_notes || []).forEach((n) => {
      if (n.subject?.toLowerCase().includes("contact") || n.subject?.toLowerCase().includes("network")) {
        notes.push({ ...n, job_title: j.title, company: j.company });
      }
    });
  });
  const missing = contacts.filter((contact) => (contact.email_status || (contact.email ? "found" : "missing")) !== "found");
  const jobsWithContacts = new Set(contacts.map((contact) => {
    const company = String(contact.company || "").toLowerCase();
    return jobs.find((job) => String(job.company || "").toLowerCase() === company)?.id || "";
  }).filter(Boolean)).size;
  const stats = $("#networkStats");
  if (stats) {
    stats.innerHTML = `
      <div class="network-stat"><span>People</span><strong>${fmtNum(contacts.length)}</strong></div>
      <div class="network-stat"><span>Missing Email</span><strong>${fmtNum(missing.length)}</strong></div>
      <div class="network-stat"><span>Follow-ups</span><strong>${fmtNum(openFollowups.length)}</strong></div>
      <div class="network-stat"><span>Jobs Mapped</span><strong>${fmtNum(jobsWithContacts)}</strong></div>
    `;
  }
  if (!contacts.length && !notes.length) {
    grid.innerHTML = '<div class="network-empty">empty</div>';
    return;
  }
  const lanes = [
    { id: "need_email", label: "Need Email", items: [] },
    { id: "ready", label: "Ready To Draft", items: [] },
    { id: "follow_up", label: "Follow-up", items: [] },
    { id: "notes", label: "Company Notes", items: [] },
  ];
  const followupsByContact = new Map();
  openFollowups.forEach((followup) => {
    if (!followup.contact_id) return;
    if (!followupsByContact.has(followup.contact_id)) followupsByContact.set(followup.contact_id, []);
    followupsByContact.get(followup.contact_id).push(followup);
  });
  contacts.forEach((contact) => {
    const status = contact.email_status || (contact.email ? "found" : "missing");
    const laneId = followupsByContact.has(contact.id) ? "follow_up" : status === "found" ? "ready" : "need_email";
    const company = String(contact.company || "").toLowerCase();
    const relatedJobs = jobs.filter((job) => String(job.company || "").toLowerCase() === company);
    lanes.find((lane) => lane.id === laneId)?.items.push({ type: "contact", contact, relatedJobs, followups: followupsByContact.get(contact.id) || [] });
  });
  notes.forEach((note) => lanes.find((lane) => lane.id === "notes")?.items.push({ type: "note", note }));
  grid.innerHTML = "";
  lanes.forEach((lane) => {
    const col = document.createElement("section");
    col.className = "network-column";
    col.innerHTML = `
      <div class="network-column-head">
        <span>${esc(lane.label)}</span>
        <strong>${fmtNum(lane.items.length)}</strong>
      </div>
      <div class="network-column-body"></div>
    `;
    const body = col.querySelector(".network-column-body");
    if (!lane.items.length) {
      body.innerHTML = '<div class="empty-state">empty</div>';
    }
    groupNetworkLaneItems(lane.items).forEach((group) => {
      body.appendChild(renderNetworkGroup(group));
    });
    grid.appendChild(col);
  });
};

const networkGroupInfo = (item) => {
  if (item.type === "note") {
    const note = item.note || {};
    const label = [note.company, note.job_title].filter(Boolean).join(" · ") || "Unmapped notes";
    return { key: `note:${label.toLowerCase()}`, label };
  }
  const contact = item.contact || {};
  const relatedJob = (item.relatedJobs || [])[0] || null;
  const company = contact.company || relatedJob?.company || "Unmapped people";
  const title = relatedJob?.title || "";
  const label = [company, title].filter(Boolean).join(" · ");
  const key = relatedJob?.id || `company:${String(company).toLowerCase()}`;
  return { key, label };
};

const groupNetworkLaneItems = (items) => {
  const groups = new Map();
  items.forEach((item) => {
    const info = networkGroupInfo(item);
    if (!groups.has(info.key)) groups.set(info.key, { ...info, items: [] });
    groups.get(info.key).items.push(item);
  });
  return Array.from(groups.values()).sort((a, b) => b.items.length - a.items.length || a.label.localeCompare(b.label));
};

const renderNetworkGroup = (group) => {
  const details = document.createElement("details");
  details.className = "network-group";
  details.open = group.items.length <= 3;
  const contacts = group.items.filter((item) => item.type === "contact").map((item) => item.contact || {});
  const missing = contacts.filter((contact) => (contact.email_status || (contact.email ? "found" : "missing")) !== "found").length;
  details.innerHTML = `
    <summary class="network-group-head" title="Expand or collapse this job/company group.">
      <span>${esc(group.label)}</span>
      <strong>${fmtNum(group.items.length)}${contacts.length ? ` people${missing ? ` · ${fmtNum(missing)} missing email` : ""}` : ""}</strong>
    </summary>
    <div class="network-group-body"></div>
  `;
  const body = details.querySelector(".network-group-body");
  group.items.forEach((item) => body.appendChild(renderNetworkItem(item)));
  return details;
};

const renderNetworkItem = (item) => {
  const card = document.createElement("article");
  card.className = "network-note";
  if (item.type === "note") {
    const note = item.note;
    card.innerHTML = `
      <div class="network-note-title">${esc(note.subject || "Note")}</div>
      <div class="network-note-body">
        <span>${esc([note.company, note.job_title].filter(Boolean).join(" · "))}</span>
        <p>${esc(note.content || "").slice(0, 420)}</p>
      </div>
    `;
    return card;
  }
  const contact = item.contact;
  const status = contact.email_status || (contact.email ? "found" : "missing");
  const profileUrl = safeHref(contact.linkedin_url || contact.source_url || "");
  const jobContext = item.relatedJobs.map((job) => job.title).slice(0, 2).join(" · ");
  const followup = item.followups[0];
  card.innerHTML = `
    <div class="network-note-title">
      ${esc(contact.name || "Contact")}
      <span class="network-email-status ${classToken(status, ["found", "missing", "unverified", "unknown"])}">${esc(humanize(status))}</span>
    </div>
    <div class="network-note-body">
      <span>${esc([contact.role, contact.company].filter(Boolean).join(" · ") || "company pending")}</span>
      ${jobContext ? `<p>${esc(jobContext)}</p>` : '<p>no job mapped</p>'}
      ${contact.email ? `<code>${esc(contact.email)}</code>` : "<code>email not found</code>"}
      ${followup ? `<p>${esc([followup.due_date, followup.reason].filter(Boolean).join(" · "))}</p>` : ""}
    </div>
    <div class="network-actions"></div>
  `;
  const actions = card.querySelector(".network-actions");
  if (profileUrl) actions.appendChild(materialLink("Profile", profileUrl, "Open this person's profile in the browser."));
  const ask = document.createElement("button");
  ask.type = "button";
  ask.className = "link-button";
  ask.textContent = "Copy Prompt";
  setTip(ask, "Copy a native Hermes prompt for the next networking move. Nothing is sent.");
  ask.addEventListener("click", async () => {
    const prompt = [
      `Review this contact for networking.`,
      `Contact: ${contact.name || "unknown"}`,
      contact.company ? `Company: ${contact.company}` : "",
      jobContext ? `Related job: ${jobContext}` : "",
      `Email status: ${status}`,
      "Tell me the next useful move without sending anything.",
    ].filter(Boolean).join("\n");
    const copied = await copyText(prompt);
    ask.textContent = copied ? "Copied" : "Drafted";
    window.setTimeout(() => { ask.textContent = "Copy Prompt"; }, 1600);
    saveChatState();
  });
  actions.appendChild(ask);
  return card;
};

/* ── Criteria ── */
const renderCriteria = () => {
  const grid = $("#criteriaGrid");
  grid.innerHTML = "";
  if (!appState) return;
  const criteria = appState.criteria?.blockers || [];
  if (criteria.length) {
    criteria.forEach((c) => {
      const card = document.createElement("div");
      card.className = `criterion-card ${classToken(c.severity, ["blocker", "flag", "clear"])}`;
      card.innerHTML = `
        <div class="criterion-head">
          <span class="criterion-area">${esc(c.area || "")}</span>
          <span class="criterion-severity ${classToken(c.severity, ["blocker", "flag", "clear"])}">${esc(c.severity || "flag")}</span>
        </div>
        <div class="criterion-condition">${esc(c.condition || "")}</div>
        <div class="criterion-action">${esc(c.action || "")}</div>
      `;
      grid.appendChild(card);
    });
  } else {
    grid.innerHTML = '<div class="empty-state">empty</div>';
  }
};

/* ── Chat ── */
const renderMessage = (msg, container) => {
  const turn = document.createElement("div");
  turn.className = "turn";

  const msgEl = document.createElement("div");
  msgEl.className = `msg role-${msg.role}`;
  if (msg.role === "tool" && msg.error) msgEl.classList.add("error");

  const body = document.createElement("div");
  body.className = "msg-body";
  body.textContent = msg.content || "";
  msgEl.appendChild(body);
  turn.appendChild(msgEl);

  if (msg.toolCalls?.length) {
    msg.toolCalls.forEach((tc) => {
      const tcEl = document.createElement("div");
      tcEl.className = "tool-call";
      tcEl.innerHTML = `<span class="tool-name">${esc(tc.name)}</span> <span class="tool-status ${tc.ok !== false ? "ok" : "err"}">${tc.ok !== false ? "ok" : "err"}</span>`;
      turn.appendChild(tcEl);
    });
  }

  if (msg.card) {
    const card = renderCard(msg.card);
    if (card) turn.appendChild(card);
  }

  container.appendChild(turn);
  transcript.scrollTop = transcript.scrollHeight;
};

const renderCard = (card) => {
  if (!card?.type) return null;
  const wrap = document.createElement("div");
  wrap.className = "result-card";
  switch (card.type) {
    case "opportunity": return renderOpportunityCard(wrap, card);
    case "requirements": return renderRequirementsCard(wrap, card);
    case "materials": return renderMaterialsCard(wrap, card);
    case "artifacts": return renderFilesCard(wrap, card);
    case "trail": return renderTrailCard(wrap, card);
    default: return null;
  }
};

const renderOpportunityCard = (wrap, card) => {
  const head = document.createElement("div");
  head.className = "result-card-head";
  head.innerHTML = `<h3>Job</h3>`;
  if (card.decision) {
    const color = card.decision === "apply" ? "var(--good)" : card.decision === "skip" ? "var(--bad)" : "var(--ink-faint)";
    head.innerHTML += `<span class="card-badge" style="color:${color}">${esc(card.decision)}</span>`;
  }
  wrap.appendChild(head);
  const body = document.createElement("div");
  body.className = "result-card-body";
  if (card.title || card.company) {
    body.innerHTML += `<div style="font-weight:600;font-size:16px;margin-bottom:6px">${esc(card.title || "untitled")}${card.company ? " · " + esc(card.company) : ""}</div>`;
  }
  if (card.meta?.length) {
    body.innerHTML += `<div style="color:var(--ink-dim);font-size:14px">${card.meta.map((m) => esc(m)).join(" · ")}</div>`;
  }
  wrap.appendChild(body);
  return wrap;
};

const renderRequirementsCard = (wrap, card) => {
  const requirements = card.requirements || [];
  const head = document.createElement("div");
  head.className = "result-card-head";
  head.innerHTML = `<h3>Requirements</h3><span class="card-badge">${requirements.length}</span>`;
  wrap.appendChild(head);
  const body = document.createElement("div");
  body.className = "result-card-body";
  requirements.slice(0, 8).forEach((r) => {
    body.innerHTML += `<div class="card-detail">${esc(r)}</div>`;
  });
  wrap.appendChild(body);
  return wrap;
};

const compileMaterial = async (materialId) => {
  if (!materialId) return;
  try {
    barDot.classList.add("thinking");
    await postJson("/api/tools/jobapps_compile_material_pdf", { material_id: materialId });
    barDot.classList.remove("thinking");
    const state = await fetchJson("/api/state");
    if (state) { appState = state; renderCurrentView(); }
  } catch (err) {
    barDot.classList.remove("thinking");
    barDot.classList.add("disconnected");
  }
};

const renderMaterialsCard = (wrap, card) => {
  const items = card.items || [];
  const head = document.createElement("div");
  head.className = "result-card-head";
  head.innerHTML = `<h3>Materials</h3><span class="card-badge">${items.length}</span>`;
  wrap.appendChild(head);
  const body = document.createElement("div");
  body.className = "result-card-body";
  if (!items.length) {
    body.innerHTML = '<div class="card-detail" style="color:var(--ink-faint)">none</div>';
    wrap.appendChild(body);
    return wrap;
  }
  items.forEach((item) => {
    const row = document.createElement("div");
    row.className = "card-row";
    row.innerHTML = `<span class="card-row-label">${esc(item.kind || "unknown")} · ${esc(item.path || "—")} <span style="color:var(--ink-faint)">rev ${item.revision_count || 0}</span></span>`;
    const action = document.createElement("button");
    action.type = "button";
    action.className = "link-button";
    action.textContent = "Compile PDF";
    action.addEventListener("click", () => compileMaterial(item.id || ""));
    row.appendChild(action);
    body.appendChild(row);
  });
  wrap.appendChild(body);
  return wrap;
};

/* ── Materials ── */
const materialUrl = (materialId, target = "source") => `/api/materials/${encodeURIComponent(materialId)}/file?target=${encodeURIComponent(target)}`;
const materialRecordUrl = (materialId) => `/api/materials/${encodeURIComponent(materialId)}`;

const materialPdfPath = (item = {}) => {
  const metadata = item.metadata && typeof item.metadata === "object" ? item.metadata : {};
  const compileInfo = metadata.compile && typeof metadata.compile === "object" ? metadata.compile : {};
  const sourcePath = item.file_path || item.path || "";
  const directPdfPath = item.format === "pdf" || /\.pdf$/i.test(sourcePath) ? sourcePath : "";
  return item.pdf_path || compileInfo.pdf_path || metadata.pdf_path || directPdfPath || "";
};

const materialTextValue = (value) => {
  if (value == null) return "";
  return typeof value === "string" ? value : JSON.stringify(value, null, 2);
};

const materialFieldLabel = (key) => {
  const labels = {
    why_this_role: "Why this role",
    relevant_experience: "Relevant experience",
    why_company: "Why company",
    linkedin_messages: "LinkedIn messages",
    email_messages: "Email messages",
    contact_id: "Contact ID",
    linkedin_url: "LinkedIn",
    follow_up: "Follow up",
  };
  if (labels[key]) return labels[key];
  const words = humanize(key).trim();
  return words ? words.replace(/\b[a-z]/g, (char) => char.toUpperCase()) : "Note";
};

const materialTryParseJson = (raw, format = "") => {
  const trimmed = String(raw || "").trim();
  if (!trimmed || (format !== "json" && !/^[{[]/.test(trimmed))) return null;
  try {
    return JSON.parse(trimmed);
  } catch (err) {
    return null;
  }
};

const materialAppend = (parent, tag, className = "", text = "") => {
  const el = document.createElement(tag);
  if (className) el.className = className;
  if (text) el.textContent = text;
  parent.appendChild(el);
  return el;
};

const materialAppendLinkedText = (parent, text) => {
  const value = String(text || "");
  const pattern = /https?:\/\/[^\s<>"']+/g;
  let lastIndex = 0;
  for (const match of value.matchAll(pattern)) {
    if (match.index > lastIndex) {
      parent.appendChild(document.createTextNode(value.slice(lastIndex, match.index)));
    }
    let url = match[0];
    let trailing = "";
    while (/[),.;:!?]$/.test(url)) {
      trailing = `${url.slice(-1)}${trailing}`;
      url = url.slice(0, -1);
    }
    const href = safeHref(url);
    if (href) {
      const link = document.createElement("a");
      link.href = href;
      link.target = "_blank";
      link.rel = "noopener";
      link.textContent = url;
      parent.appendChild(link);
    } else {
      parent.appendChild(document.createTextNode(match[0]));
    }
    if (trailing) parent.appendChild(document.createTextNode(trailing));
    lastIndex = match.index + match[0].length;
  }
  if (lastIndex < value.length) {
    parent.appendChild(document.createTextNode(value.slice(lastIndex)));
  }
};

const materialAppendParagraphs = (parent, text) => {
  String(text || "").split(/\n\s*\n/).map((part) => part.trim()).filter(Boolean).forEach((paragraph) => {
    const el = materialAppend(parent, "p");
    materialAppendLinkedText(el, paragraph);
  });
};

const materialAppendNoteText = (parent, text) => {
  const value = String(text || "").trim();
  const match = value.match(/^([^:]{3,80}):\s*(.+)$/s);
  if (!match) {
    const paragraph = materialAppend(parent, "p");
    materialAppendLinkedText(paragraph, value);
    return;
  }
  materialAppend(parent, "span", "material-note-label", match[1].trim());
  const body = match[2].trim();
  const arrowIndex = body.indexOf(" -> ");
  if (arrowIndex > -1) {
    const paragraph = materialAppend(parent, "p");
    materialAppendLinkedText(paragraph, body.slice(0, arrowIndex).trim());
    const use = materialAppend(parent, "small");
    materialAppendLinkedText(use, `Use: ${body.slice(arrowIndex + 4).trim()}`);
    return;
  }
  const paragraph = materialAppend(parent, "p");
  materialAppendLinkedText(paragraph, body);
};

const materialRenderList = (parent, values = []) => {
  const list = materialAppend(parent, "ul", "material-note-list");
  values.forEach((value) => {
    const item = materialAppend(list, "li");
    if (value && typeof value === "object" && !Array.isArray(value)) {
      materialRenderObjectCard(item, value);
      return;
    }
    materialAppendNoteText(item, materialTextValue(value));
  });
};

const materialRenderObjectCard = (parent, value = {}) => {
  const title = value.contact || value.name || value.subject || value.title || "";
  if (title) {
    const head = materialAppend(parent, "div", "material-message-head");
    materialAppend(head, "strong", "", title);
    const href = safeHref(value.linkedin_url || value.profile || value.url || value.source_url || "");
    if (href) {
      const link = materialAppend(head, "a", "", "Open");
      link.href = href;
      link.target = "_blank";
      link.rel = "noopener";
    }
  }
  const mainText = value.message || value.body || value.content || value.text || value.note || value.summary || "";
  if (mainText) materialAppendParagraphs(parent, mainText);
  Object.entries(value).forEach(([key, fieldValue]) => {
    if (["contact", "name", "subject", "title", "message", "body", "content", "text", "note", "summary", "linkedin_url", "url", "source_url"].includes(key)) {
      return;
    }
    if (fieldValue == null || fieldValue === "") return;
    const meta = materialAppend(parent, "div", "material-inline-meta");
    materialAppend(meta, "span", "", materialFieldLabel(key));
    const valueEl = materialAppend(meta, "strong");
    materialAppendLinkedText(valueEl, materialTextValue(fieldValue));
  });
};

const materialRenderCollection = (parent, key, values = []) => {
  const section = materialAppend(parent, "section", "material-section");
  const head = materialAppend(section, "div", "material-section-head");
  materialAppend(head, "h3", "", materialFieldLabel(key));
  materialAppend(head, "span", "", fmtNum(values.length));
  const list = materialAppend(section, "div", "material-message-list");
  values.forEach((value) => {
    const card = materialAppend(list, "article", "material-message-card");
    if (value && typeof value === "object" && !Array.isArray(value)) {
      materialRenderObjectCard(card, value);
    } else {
      materialAppendParagraphs(card, materialTextValue(value));
    }
  });
};

const materialRenderStructured = (parent, value, item = {}) => {
  if (Array.isArray(value)) {
    materialRenderList(parent, value);
    return;
  }
  if (!value || typeof value !== "object") {
    materialAppendParagraphs(parent, materialTextValue(value));
    return;
  }
  const entries = Object.entries(value).filter(([, fieldValue]) => {
    if (fieldValue == null) return false;
    if (Array.isArray(fieldValue)) return fieldValue.length > 0;
    return String(fieldValue).trim() !== "";
  });
  if (!entries.length) {
    materialAppend(parent, "div", "material-empty", "No preview content is stored for this material.");
    return;
  }
  entries.forEach(([key, fieldValue]) => {
    if (Array.isArray(fieldValue)) {
      materialRenderCollection(parent, key, fieldValue);
      return;
    }
    const section = materialAppend(parent, "section", "material-section");
    const head = materialAppend(section, "div", "material-section-head");
    materialAppend(head, "h3", "", materialFieldLabel(key));
    if (fieldValue && typeof fieldValue === "object") {
      materialRenderObjectCard(section, fieldValue);
      return;
    }
    materialAppendParagraphs(section, materialTextValue(fieldValue));
  });
};

const materialIsOutreach = (item = {}) => /outreach|linkedin|email/.test(String(item.kind || ""));

const materialRenderPlainText = (parent, raw, item = {}) => {
  const text = String(raw || "").trim();
  if (!text) {
    materialAppend(parent, "div", "material-empty", "No preview content is stored for this material.");
    return;
  }
  const blocks = text.split(/\n\s*\n/).map((part) => part.trim()).filter(Boolean);
  if (materialIsOutreach(item)) {
    const letter = materialAppend(parent, "article", "material-letter");
    blocks.forEach((block, index) => {
      if (index === 0 && /^(hi|hello|dear)\b/i.test(block)) {
        materialAppend(letter, "p", "material-greeting", block);
      } else if (/^follow up\b/i.test(block)) {
        const callout = materialAppend(letter, "div", "material-followup");
        materialAppend(callout, "span", "", "Follow up");
        materialAppend(callout, "p", "", block.replace(/^follow up[:\s]*/i, "").trim() || block);
      } else if (/^(best|thanks|thank you|sincerely|regards),?/i.test(block)) {
        materialAppend(letter, "p", "material-signoff", block);
      } else {
        materialAppendParagraphs(letter, block);
      }
    });
    return;
  }
  const lines = text.split("\n").map((line) => line.trim()).filter(Boolean);
  const listLines = lines.filter((line) => /^[-*•]\s+|^\d+[.)]\s+/.test(line));
  if (lines.length > 1 && listLines.length >= Math.ceil(lines.length * 0.6)) {
    materialRenderList(parent, lines.map((line) => line.replace(/^[-*•]\s+|^\d+[.)]\s+/, "")));
    return;
  }
  blocks.forEach((block) => {
    const section = materialAppend(parent, "section", "material-section");
    materialAppendNoteText(section, block);
  });
};

const renderMaterialViewerContent = (item = {}) => {
  if (!materialViewerBody) return;
  materialViewerBody.innerHTML = "";
  const wrap = materialAppend(materialViewerBody, "div", "material-rendered-content");
  if (item.format === "tex") {
    materialAppend(wrap, "p", "material-empty", materialPdfPath(item)
      ? "This material is reviewed as a PDF. Open the PDF from the action bar."
      : "This material needs a PDF before it can be reviewed here.");
    return;
  }
  const raw = materialTextValue(item.content ?? item.content_preview ?? "").trim();
  const parsed = materialTryParseJson(raw, item.format);
  if (parsed !== null) {
    materialRenderStructured(wrap, parsed, item);
    return;
  }
  if (raw) {
    materialRenderPlainText(wrap, raw, item);
    return;
  }
  const metadata = item.metadata && typeof item.metadata === "object" ? item.metadata : {};
  if (Object.keys(metadata).length) {
    materialRenderStructured(wrap, metadata, item);
    return;
  }
  materialAppend(wrap, "div", "material-empty", "No preview content is stored for this material.");
};

const closeMaterialViewer = () => {
  if (!materialViewer) return;
  materialViewer.hidden = true;
  if (materialViewerBody) materialViewerBody.textContent = "";
  if (materialViewerActions) materialViewerActions.innerHTML = "";
};

const renderMaterialViewer = (material, fallback = {}) => {
  if (!materialViewer) return;
  const item = {
    ...fallback,
    ...material,
    pdf_path: materialPdfPath(material) || materialPdfPath(fallback),
  };
  const title = materialUserName(item);
  if (materialViewerTitle) materialViewerTitle.textContent = title;
  if (materialViewerKind) materialViewerKind.textContent = materialKindLabel(item);
  if (materialViewerMeta) {
    materialViewerMeta.textContent = [
      item.company,
      item.job_title,
      item.format === "tex" ? "" : item.format,
      item.source,
      item.updated_at ? fmtDateTime(item.updated_at) : "",
    ].filter(Boolean).join(" · ");
  }
  if (materialViewerActions) {
    materialViewerActions.innerHTML = "";
    if (materialPdfPath(item) && item.id) {
      materialViewerActions.appendChild(materialLink("Open PDF", materialUrl(item.id, "pdf"), "Open the PDF in the browser."));
    }
    if (materialNeedsPdf(item) && item.id) {
      const compile = document.createElement("button");
      compile.type = "button";
      compile.className = "link-button";
      compile.textContent = "Build PDF";
      setTip(compile, "Build the PDF for this material.");
      compile.addEventListener("click", () => compileMaterial(item.id || ""));
      materialViewerActions.appendChild(compile);
    }
  }
  renderMaterialViewerContent(item);
  materialViewer.hidden = false;
};

const openMaterialViewer = async (materialOrId) => {
  const fallback = typeof materialOrId === "object" && materialOrId ? materialOrId : {};
  const materialId = typeof materialOrId === "string" ? materialOrId : fallback.id;
  if (!materialId) return;
  if (materialIsCompilable(fallback)) {
    if (materialPdfPath(fallback)) {
      window.open(materialUrl(materialId, "pdf"), "_blank", "noopener");
      return;
    }
    if (materialNeedsPdf(fallback)) {
      await compileMaterial(materialId);
      return;
    }
  }
  if (materialViewer) {
    materialViewer.hidden = false;
    if (materialViewerTitle) materialViewerTitle.textContent = materialUserName(fallback) || "Preview";
    if (materialViewerKind) materialViewerKind.textContent = materialKindLabel(fallback);
    if (materialViewerMeta) materialViewerMeta.textContent = "loading";
    if (materialViewerActions) materialViewerActions.innerHTML = "";
    if (materialViewerBody) materialViewerBody.textContent = "Loading material...";
  }
  try {
    const material = await fetchJsonStrict(materialRecordUrl(materialId));
    renderMaterialViewer(material, fallback);
  } catch (err) {
    if (fallback.content || fallback.content_preview) {
      renderMaterialViewer({ ...fallback, content: fallback.content || fallback.content_preview }, fallback);
      return;
    }
    if (materialViewerMeta) materialViewerMeta.textContent = "not available";
    if (materialViewerBody) materialViewerBody.textContent = "This saved material could not be loaded. Refresh the page and try again.";
  }
};

const collectGeneratedMaterials = () => {
  if (!appState) return [];
  const items = [];
  (appState.jobs || []).forEach((job) => {
    (job.materials_workbench?.items || []).forEach((material) => {
      const enriched = {
        ...material,
        job_id: job.id,
        job_title: job.title || "untitled",
        company: job.company || "",
        decision: job.decision || job.evaluation?.decision || "",
      };
      enriched.pdf_path = materialPdfPath(enriched);
      items.push(enriched);
    });
  });
  return items.sort((a, b) => new Date(b.updated_at || 0) - new Date(a.updated_at || 0));
};

const materialHasSource = (item = {}) => Boolean(item.file_path || item.path);
const materialHasPdf = (item = {}) => Boolean(materialPdfPath(item));
const materialIsTex = (item = {}) => item.format === "tex";
const materialIsCompilable = (item = {}) => ["tex", "typ"].includes(item.format || "");
const materialNeedsPdf = (item = {}) => materialIsCompilable(item) && !materialHasPdf(item) && ["cover_letter", "resume"].includes(item.kind || "");
const materialIsStoredRecord = (item = {}) => !materialHasSource(item) && !materialHasPdf(item);
const materialCanPreviewInApp = (item = {}) => (
  Boolean(item.id) &&
  !materialIsCompilable(item) &&
  Boolean(item.content || item.content_preview || item.has_content)
);
const materialShouldShow = (item = {}) => !materialIsCompilable(item) || materialHasPdf(item) || materialNeedsPdf(item);
const materialUpdatedMs = (item = {}) => {
  const raw = item.updated_at || item.created_at || "";
  if (!raw) return 0;
  const ms = new Date(raw).getTime();
  return Number.isNaN(ms) ? 0 : ms;
};

const MATERIAL_KIND_RANK = {
  resume: 0,
  cover_letter: 1,
  short_answers: 2,
  answer: 2,
  outreach: 3,
  outreach_draft: 3,
  networking: 3,
  resume_notes: 4,
  research: 5,
};

const materialSort = (a, b) => {
  const kindA = MATERIAL_KIND_RANK[a.kind] ?? 20;
  const kindB = MATERIAL_KIND_RANK[b.kind] ?? 20;
  if (kindA !== kindB) return kindA - kindB;
  return materialUpdatedMs(b) - materialUpdatedMs(a);
};

const materialCanonicalKey = (item = {}) => {
  const display = materialDisplayName(item).toLowerCase().replace(/\.(tex|pdf|json|text|txt)$/i, "");
  return `${item.kind || "material"}:${display}`;
};

const materialPreferenceScore = (item = {}) => (
  {
    readiness: materialHasPdf(item) ? 4 : materialCanPreviewInApp(item) ? 3 : materialNeedsPdf(item) ? 2 : 1,
    updated: materialUpdatedMs(item),
  }
);

const materialPreferredOver = (candidate = {}, existing = {}) => {
  const a = materialPreferenceScore(candidate);
  const b = materialPreferenceScore(existing);
  if (a.readiness !== b.readiness) return a.readiness > b.readiness;
  return a.updated > b.updated;
};

const materialPreferredItems = (items = []) => {
  const preferred = new Map();
  items.forEach((item) => {
    const key = materialCanonicalKey(item);
    const existing = preferred.get(key);
    if (!existing || materialPreferredOver(item, existing)) {
      preferred.set(key, item);
    }
  });
  return Array.from(preferred.values()).sort(materialSort);
};

const materialStatusFor = (item = {}) => {
  if (materialNeedsPdf(item)) return { key: "needs-pdf", label: "needs PDF" };
  if (materialHasPdf(item)) return { key: "pdf-ready", label: "PDF ready" };
  return { key: "stored-record", label: "saved in app" };
};

const materialJobStats = (items = []) => {
  const latestMs = items.reduce((max, item) => Math.max(max, materialUpdatedMs(item)), 0);
  return {
    total: items.length,
    canOpen: items.filter((item) => materialHasPdf(item) || materialCanPreviewInApp(item)).length,
    pdf: items.filter(materialHasPdf).length,
    needsPdf: items.filter(materialNeedsPdf).length,
    records: items.filter((item) => materialCanPreviewInApp(item) && materialIsStoredRecord(item)).length,
    latestLabel: latestMs ? fmtDateTime(new Date(latestMs).toISOString()) : "",
    latestMs,
  };
};

const materialGroups = (items = []) => {
  const groups = new Map();
  items.forEach((item) => {
    const key = item.job_id || "unmapped";
    if (!groups.has(key)) {
      groups.set(key, {
        job_id: key,
        company: item.company || "",
        job_title: item.job_title || "Unmapped materials",
        decision: item.decision || "",
        items: [],
      });
    }
    groups.get(key).items.push(item);
  });
  return Array.from(groups.values()).map((group) => {
    const sortedItems = [...group.items].sort(materialSort);
    return {
      ...group,
      items: sortedItems,
      stats: materialJobStats(sortedItems),
    };
  }).sort((a, b) => b.stats.latestMs - a.stats.latestMs);
};

const materialMetaText = (item = {}) => [
  materialIsCompilable(item) ? "" : item.format,
  materialIsCompilable(item) && item.compile_status ? humanize(item.compile_status) : "",
  item.updated_at ? fmtDateTime(item.updated_at) : "",
  `rev ${fmtNum(item.revision_count || 0)}`,
].filter(Boolean).join(" · ");

const appendMaterialActions = (actions, item, labels = {}) => {
  if (!actions) return;
  const pdfPath = materialPdfPath(item);
  if (pdfPath && item.id) {
    actions.appendChild(materialLink(labels.pdf || "Open PDF", materialUrl(item.id, "pdf"), "Open the PDF in the browser."));
  }
  if (materialCanPreviewInApp(item)) {
    const preview = document.createElement("button");
    preview.type = "button";
    preview.className = "link-button";
    preview.textContent = labels.preview || "Preview";
    setTip(preview, "Preview this saved text or data inside JobApps.");
    preview.addEventListener("click", () => openMaterialViewer(item));
    actions.appendChild(preview);
  }
  if (materialNeedsPdf(item) && item.id) {
    const compile = document.createElement("button");
    compile.type = "button";
    compile.className = "link-button";
    compile.textContent = labels.compile || "Build PDF";
    setTip(compile, "Build the PDF for this material.");
    compile.addEventListener("click", () => compileMaterial(item.id || ""));
    actions.appendChild(compile);
  }
};

const renderMaterialQuickRows = (container, items, emptyLabel) => {
  if (!container) return;
  container.innerHTML = "";
  if (!items.length) {
    container.innerHTML = `<div class="material-empty">${esc(emptyLabel)}</div>`;
    return;
  }
  items.forEach((item) => {
    const status = materialStatusFor(item);
    const row = document.createElement("div");
    row.className = "material-quick-row";
    row.innerHTML = `
      <div class="material-quick-main">
        <strong>${esc(materialUserName(item))}</strong>
        <span>${esc(materialMetaText(item))}</span>
      </div>
      <span class="material-row-status ${esc(status.key)}">${esc(status.label)}</span>
      <div class="material-row-actions"></div>
    `;
    appendMaterialActions(row.querySelector(".material-row-actions"), item);
    container.appendChild(row);
  });
};

const renderMaterialsOverview = (items, groups = materialGroups(items)) => {
  if (!materialsOverview) return;
  materialsOverview.innerHTML = "";
  if (!items.length) {
    materialsOverview.innerHTML = '<div class="empty-state">no generated materials yet</div>';
    return;
  }

  const group = groups[0];
  const currentItems = materialPreferredItems(group.items);
  const stats = materialJobStats(currentItems);
  const reviewNow = currentItems.filter(materialHasPdf).slice(0, 5);
  const needsAction = currentItems.filter(materialNeedsPdf).slice(0, 5);
  const records = currentItems.filter((item) => materialCanPreviewInApp(item) && materialIsStoredRecord(item)).slice(0, 5);
  const jobTitle = [group.company, group.job_title].filter(Boolean).join(" · ") || "Unmapped materials";
  const jobLabel = "Most recent job";
  materialsOverview.innerHTML = `
    <div class="materials-job-panel">
      <div class="materials-job-copy">
        <span class="material-kind">${esc(jobLabel)}</span>
        <h2>${esc(jobTitle)}</h2>
        <p>${stats.latestLabel ? `Latest update ${esc(stats.latestLabel)}` : "No update timestamp recorded."}</p>
      </div>
      <div class="materials-job-metrics">
        <div><span>Can Open</span><strong>${fmtNum(stats.canOpen)}</strong></div>
        <div><span>PDFs</span><strong>${fmtNum(stats.pdf)}</strong></div>
        <div><span>Need PDF</span><strong>${fmtNum(stats.needsPdf)}</strong></div>
        <div><span>Saved Here</span><strong>${fmtNum(stats.records)}</strong></div>
      </div>
    </div>
    <div class="materials-overview-grid">
      <section class="material-panel">
        <div class="material-panel-head">
          <h3>PDFs</h3>
          <span>${fmtNum(reviewNow.length)}</span>
        </div>
        <div class="material-mini-list" data-material-bucket="review"></div>
      </section>
      <section class="material-panel">
        <div class="material-panel-head">
          <h3>Need PDF</h3>
          <span>${fmtNum(needsAction.length)}</span>
        </div>
        <div class="material-mini-list" data-material-bucket="needs"></div>
      </section>
      <section class="material-panel">
        <div class="material-panel-head">
          <h3>Saved in App</h3>
          <span>${fmtNum(records.length)}</span>
        </div>
        <div class="material-mini-list" data-material-bucket="records"></div>
      </section>
    </div>
  `;
  renderMaterialQuickRows(materialsOverview.querySelector('[data-material-bucket="review"]'), reviewNow, "no PDFs yet for this job");
  renderMaterialQuickRows(materialsOverview.querySelector('[data-material-bucket="needs"]'), needsAction, "everything that needs a PDF has one");
  renderMaterialQuickRows(materialsOverview.querySelector('[data-material-bucket="records"]'), records, "no text or data saved only in the app");
};

const renderMaterials = () => {
  const generated = collectGeneratedMaterials().filter(materialShouldShow);
  const groups = materialGroups(generated);
  const stats = materialJobStats(generated);
  if (generatedMaterialCount) generatedMaterialCount.textContent = fmtNum(generated.length);

  if (materialStats) {
    materialStats.innerHTML = `
      <div class="material-stat"><span>Materials</span><strong>${fmtNum(stats.total)}</strong></div>
      <div class="material-stat"><span>Jobs</span><strong>${fmtNum(groups.length)}</strong></div>
      <div class="material-stat"><span>Can Open</span><strong>${fmtNum(stats.canOpen)}</strong></div>
      <div class="material-stat"><span>Needs PDF</span><strong>${fmtNum(stats.needsPdf)}</strong></div>
    `;
  }

  renderMaterialsOverview(generated, groups);
  renderGeneratedMaterials(generated, groups);
};

const renderGeneratedMaterials = (items, groups = materialGroups(items)) => {
  if (!materialsList) return;
  materialsList.innerHTML = "";
  if (!items.length) {
    materialsList.innerHTML = '<div class="empty-state">empty</div>';
    return;
  }
  groups.forEach((group) => {
    const stats = group.stats;
    const shell = document.createElement("details");
    shell.className = "material-job";
    shell.open = groups.indexOf(group) === 0;
    shell.innerHTML = `
      <summary class="material-job-head" title="Expand or collapse this job's generated materials.">
        <div>
          <span class="material-kind">${esc(group.company || "job")}</span>
          <h3>${esc(group.job_title)}</h3>
        </div>
        <div class="material-job-meta">
          <span>${fmtNum(stats.canOpen)} can open</span>
          <span>${fmtNum(stats.needsPdf)} need PDF</span>
          <span>${fmtNum(stats.records)} saved here</span>
          ${group.decision ? `<span>${esc(group.decision)}</span>` : ""}
          <span class="material-expand">details</span>
        </div>
      </summary>
      <div class="material-job-files">
        <div class="material-job-strip">
          <span>${fmtNum(stats.total)} materials</span>
          <span>${fmtNum(stats.pdf)} PDFs</span>
          ${stats.latestLabel ? `<span>updated ${esc(stats.latestLabel)}</span>` : ""}
        </div>
      </div>
    `;
    const body = shell.querySelector(".material-job-files");
    group.items.forEach((item) => {
      const pdfPath = item.pdf_path || "";
      const status = materialStatusFor(item);
      const row = document.createElement("div");
      row.className = "material-row";
      row.innerHTML = `
        <div class="material-row-main">
          <strong>${esc(materialUserName(item))}</strong>
          <span>${esc(materialMetaText(item))}</span>
        </div>
        <span class="material-row-status ${esc(status.key)}">${esc(status.label)}</span>
        <div class="material-row-actions"></div>
      `;
      const actions = row.querySelector(".material-row-actions");
      appendMaterialActions(actions, { ...item, pdf_path: pdfPath });
      body.appendChild(row);
    });
    materialsList.appendChild(shell);
  });
};

const materialLink = (label, href, title = "") => {
  const link = document.createElement("a");
  link.className = "link-button material-link";
  link.href = href;
  link.target = "_blank";
  link.rel = "noopener";
  link.textContent = label;
  if (title) setTip(link, title);
  return link;
};

const renderFilesCard = (wrap, card) => {
  const head = document.createElement("div");
  head.className = "result-card-head";
  head.innerHTML = "<h3>Files</h3>";
  wrap.appendChild(head);
  const body = document.createElement("div");
  body.className = "result-card-body";
  if (card.tabs?.length) {
    card.tabs.forEach((tab) => {
      body.innerHTML += `<details style="margin:8px 0"><summary style="font-size:14px;color:var(--ink-dim);cursor:pointer;font-weight:500">${esc(tab.label || "?")}</summary><pre style="font-size:14px;color:var(--ink);margin:8px 0 0;max-height:280px;overflow:auto;background:var(--bg);padding:12px;border-radius:6px;border:1px solid var(--line)">${esc((tab.content || "").slice(0, 2000))}</pre></details>`;
    });
  }
  wrap.appendChild(body);
  return wrap;
};

const renderTrailCard = (wrap, card) => {
  const head = document.createElement("div");
  head.className = "result-card-head";
  head.innerHTML = `<h3>Events</h3><span class="card-badge">${card.events ? card.events.length : 0}</span>`;
  wrap.appendChild(head);
  const body = document.createElement("div");
  body.className = "result-card-body";
  if (card.events?.length) {
    card.events.slice(0, 10).forEach((ev) => {
      body.innerHTML += `<div class="card-detail"><span style="color:var(--ink-faint)">${esc(ev.event_type || "?")}</span> ${esc(ev.summary || ev.note || "")}</div>`;
    });
  }
  wrap.appendChild(body);
  return wrap;
};

const buildCardsFromState = (state) => {
  const cards = [];
  const job = state.active_job || (state.jobs?.length ? state.jobs[0] : null);
  if (!job) return cards;

  cards.push({
    type: "opportunity",
    title: job.title,
    company: job.company,
    decision: job.decision || job.evaluation?.decision,
    meta: [job.id, job.status].filter(Boolean),
  });

  if (job.top_requirements?.length || job.tailoring_requirements?.length) {
    cards.push({
      type: "requirements",
      requirements: job.top_requirements || job.tailoring_requirements?.map((t) => t.requirement) || [],
    });
  }

  if (job.materials_workbench?.items?.length) {
    cards.push({ type: "materials", items: job.materials_workbench.items });
  }

  const tabs = [];
  if (job.resume_tex) tabs.push({ label: "Resume source", content: job.resume_tex });
  if (job.cover_letter_tex) tabs.push({ label: "Letter .tex", content: job.cover_letter_tex });
  if (job.prompt) tabs.push({ label: "Prompt", content: job.prompt });
  if (job.hermes_output) tabs.push({ label: "Output", content: job.hermes_output });
  if (job.research_notes?.length) {
    tabs.push({ label: "Research", content: job.research_notes.map((n) => n.content || n).join("\n\n---\n\n") });
  }
  if (tabs.length) cards.push({ type: "artifacts", tabs });

  if (job.events?.length) {
    cards.push({ type: "trail", events: job.events });
  }

  return cards;
};

const appendAssistantWithCards = (text, cards, toolCalls) => {
  const msg = { role: "assistant", content: text || "", card: null, toolCalls: toolCalls || [] };
  messages.push(msg);
  renderMessage(msg, transcript);

  if (cards?.length) {
    cards.forEach((card) => {
      const msgCard = { role: "system", content: "", card };
      messages.push(msgCard);
      renderMessage(msgCard, transcript);
    });
  }
};

const appendSystemMessage = (text) => {
  const msg = { role: "system", content: text };
  messages.push(msg);
  renderMessage(msg, transcript);
  saveChatState();
};

const normalizeCommandCatalog = (catalog) => {
  const seen = new Set();
  const groups = [];
  const addGroup = (name, commands) => {
    const items = [];
    (commands || []).forEach((item) => {
      const command = item.command || "";
      if (!command || seen.has(command)) return;
      seen.add(command);
      items.push({
        command,
        description: item.description || "",
        category: item.category || name || "Commands",
      });
    });
    if (items.length) groups.push({ name: name || "Commands", commands: items });
  };

  (catalog?.categories || []).forEach((group) => addGroup(group.name, group.commands));
  const leftovers = [];
  (catalog?.commands || []).forEach((item) => {
    if (!item.command || seen.has(item.command)) return;
    leftovers.push(item);
  });
  addGroup("Skills", leftovers.filter((item) => item.category === "Skills"));
  addGroup("Commands", leftovers.filter((item) => item.category !== "Skills"));
  return {
    groups,
    commands: groups.flatMap((group) => group.commands),
  };
};

const renderCommandMenu = () => {
  const value = composerInput.value.trimStart();
  if (!commandMenu || !value.startsWith("/") || value.includes("\n")) {
    if (commandMenu) commandMenu.hidden = true;
    return;
  }
  const token = value.slice(1).split(/\s+/, 1)[0].toLowerCase();
  const matchesByGroup = commandGroups
    .map((group) => ({
      name: group.name,
      commands: group.commands.filter((item) => {
        const command = (item.command || "").toLowerCase();
        const description = (item.description || "").toLowerCase();
        return !token || command.slice(1).startsWith(token) || command.includes(token) || description.includes(token);
      }),
    }))
    .filter((group) => group.commands.length);
  if (!matchesByGroup.length) {
    commandMenu.hidden = true;
    return;
  }
  commandMenu.innerHTML = "";
  matchesByGroup.forEach((group) => {
    const groupEl = document.createElement("div");
    groupEl.className = "command-group";
    const title = document.createElement("div");
    title.className = "command-group-title";
    title.textContent = `${group.name} · ${group.commands.length}`;
    groupEl.appendChild(title);
    group.commands.forEach((item) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "command-option";
      button.innerHTML = `
        <span class="command-name">${esc(item.command || "")}</span>
        <span class="command-desc">${esc(item.description || "")}</span>
      `;
      button.addEventListener("click", () => {
        composerInput.value = `${item.command} `;
        autoResize();
        commandMenu.hidden = true;
        composerInput.focus();
      });
      groupEl.appendChild(button);
    });
    commandMenu.appendChild(groupEl);
  });
  commandMenu.hidden = false;
};

const normalizeSessionMessages = (items = []) => {
  return items
    .map((item) => ({
      role: ["user", "assistant", "system", "tool"].includes(item.role) ? item.role : "system",
      content: item.text || item.content || "",
    }))
    .filter((item) => item.content && item.role !== "tool");
};

const renderSessions = () => {
  if (!sessionsList) return;
  sessionsList.innerHTML = "";
  if (sessionSummary) {
    const active = activeHermesSessionId ? hermesSessions.find((session) => session.id === activeHermesSessionId) : null;
    const activeTitle = active?.title || active?.preview || activeSessionLabel || "jobapps-cockpit";
    sessionSummary.innerHTML = `
      <div class="session-stat"><span>Total</span><strong>${fmtNum(hermesSessions.length)}</strong></div>
      <div class="session-stat"><span>Active</span><strong>${esc(activeHermesSessionId ? activeTitle : "cockpit")}</strong></div>
    `;
  }
  if (!hermesSessions.length) {
    sessionsList.innerHTML = '<div class="agent-session-empty">no sessions</div>';
    return;
  }
  hermesSessions.forEach((session) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = `session-item${session.id === activeHermesSessionId ? " active" : ""}`;
    const title = session.title || session.preview || session.id || "untitled";
    const meta = [fmtAge(session.started_at), session.source || "tui"].filter(Boolean).join(" · ");
    button.innerHTML = `
      <span class="session-item-main">${esc(title)}</span>
      <span class="session-item-count">${fmtNum(session.message_count || 0)}</span>
      <span class="session-item-meta">${esc(meta)}</span>
      <span class="session-item-id">${esc(session.id || "")}</span>
    `;
    button.addEventListener("click", () => resumeHermesSession(session.id));
    sessionsList.appendChild(button);
  });
};

const refreshSessions = async () => {
  if (sessionsList) sessionsList.innerHTML = '<div class="agent-session-empty">loading</div>';
  const data = await fetchJson("/api/hermes/sessions");
  hermesSessions = data?.sessions || [];
  renderSessions();
};

const resumeHermesSession = async (sessionId, options = {}) => {
  if (!sessionId) return;
  setRuntimeStatus("running");
  const result = await postJson("/api/hermes/sessions/resume", { session_id: sessionId });
  if (result?.error) {
    setRuntimeStatus("offline");
    appendSystemMessage(result.error);
    return;
  }

  activeHermesSessionId = result.resumed || sessionId;
  activeConversation = safeConversationName(activeHermesSessionId);
  activeConversationHistory = normalizeSessionMessages(result.messages || []);
  pendingTurn = null;
  messages = [];
  transcript.innerHTML = "";
  activeConversationHistory.slice(-36).forEach((msg) => {
    messages.push(msg);
    renderMessage(msg, transcript);
  });
  const sessionMeta = hermesSessions.find((session) => session.id === sessionId);
  const title = sessionMeta?.title || sessionMeta?.preview || activeHermesSessionId;
  setActiveSessionLabel(title);
  if (result.info?.usage) renderUsage(result.info.usage, { model: result.info.model || "" });
  renderSessions();
  switchView("chat");
  if (options.announce !== false) appendSystemMessage(`continued ${title}`);
  setRuntimeStatus("connected");
  saveChatState();
};

const restoreChatState = () => {
  const saved = readChatState();
  if (!saved || saved.version !== 1) return;

  restoringChatState = true;
  activeConversation = saved.activeConversation || "jobapps-cockpit";
  activeHermesSessionId = saved.activeHermesSessionId || "";
  activeSessionLabel = saved.activeSessionLabel || activeHermesSessionId || activeConversation;
  activeConversationHistory = compactMessages(saved.activeConversationHistory || []);
  currentJobId = saved.currentJobId || null;
  latestUsage = saved.usage || null;
  pendingTurn = saved.pendingTurn || null;
  messages = compactMessages(saved.messages || []);
  transcript.innerHTML = "";
  messages.forEach((msg) => renderMessage(msg, transcript));
  if (composerInput && saved.draft) composerInput.value = saved.draft;
  setActiveSessionLabel(activeSessionLabel);
  if (latestUsage) renderUsage(latestUsage, { model: latestUsage.model || "" });

  if (pendingTurn?.status === "running") {
    const interrupted = pendingTurn;
    pendingTurn = null;
    messages.push({
      role: "system",
      content: `previous response was interrupted before completion: ${interrupted.text || "last turn"}`,
    });
    renderMessage(messages[messages.length - 1], transcript);
  }

  const savedView = saved.currentView === "chat" ? "dashboard" : (saved.currentView || "dashboard");
  restoringChatState = false;
  if (savedView !== "dashboard") switchView(savedView);
  saveChatState();
};

const createStreamTurn = () => {
  const turn = document.createElement("div");
  turn.className = "turn stream-turn";
  const msgEl = document.createElement("div");
  msgEl.className = "msg role-assistant";
  const body = document.createElement("div");
  body.className = "msg-body";
  msgEl.appendChild(body);
  const trace = document.createElement("div");
  trace.className = "agent-trace";
  turn.appendChild(msgEl);
  turn.appendChild(trace);
  transcript.appendChild(turn);
  transcript.scrollTop = transcript.scrollHeight;
  return { turn, body, trace, text: "" };
};

const appendTrace = (trace, kind, label, detail = "") => {
  const row = document.createElement("div");
  row.className = `trace-row trace-${kind}`;
  row.innerHTML = `
    <span class="trace-label">${esc(label)}</span>
    ${detail ? `<span class="trace-detail">${esc(detail)}</span>` : ""}
  `;
  trace.appendChild(row);
  transcript.scrollTop = transcript.scrollHeight;
};

const applyStreamEvent = (event, streamTurn) => {
  if (!event?.type) return null;
  if (event.type === "message.delta") {
    streamTurn.text += event.text || "";
    streamTurn.body.textContent = streamTurn.text;
    transcript.scrollTop = transcript.scrollHeight;
    return null;
  }
  if (event.type === "status") {
    const detail = event.response_id || event.message || "";
    appendTrace(streamTurn.trace, "status", event.label || "status", detail);
    addAgentEvent("status", event.label || "status", detail);
    return null;
  }
  if (event.type === "command") {
    appendTrace(streamTurn.trace, "command", event.command || "command", event.status || "");
    addAgentEvent("command", event.command || "command", event.status || "");
    return null;
  }
  if (event.type === "tool") {
    const name = event.name || event.call_id || "tool";
    const detail = event.output || event.status || "";
    appendTrace(streamTurn.trace, "tool", name, detail);
    addAgentEvent("tool", name, event.status || "");
    return null;
  }
  if (event.type === "reasoning") {
    appendTrace(streamTurn.trace, "reasoning", "reasoning", event.text || "");
    addAgentEvent("reasoning", "reasoning", event.text || "");
    return null;
  }
  if (event.type === "menu") {
    const menuType = event.menu?.type || "menu";
    appendTrace(streamTurn.trace, "menu", menuType, "native Hermes data");
    addAgentEvent("menu", menuType, "native Hermes data");
    return null;
  }
  if (event.type === "state") {
    latestStreamState = event.state || null;
    return null;
  }
  if (event.type === "usage") {
    renderUsage(event.usage || {}, { model: event.model || "", response_id: event.response_id || "" });
    addAgentEvent("status", "usage", `${fmtNum((event.usage || {}).total)} tokens`);
    return null;
  }
  if (event.type === "error") {
    appendTrace(streamTurn.trace, "error", "error", event.message || "");
    addAgentEvent("error", "error", event.message || "");
    return event;
  }
  return null;
};

const readEventStream = async (response, onEvent) => {
  if (!response.body) throw new Error("streaming response body unavailable");
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  const flush = (chunk) => {
    const lines = chunk.split(/\r?\n/);
    let eventName = "message";
    const dataLines = [];
    lines.forEach((line) => {
      if (line.startsWith("event:")) eventName = line.slice(6).trim() || "message";
      if (line.startsWith("data:")) dataLines.push(line.slice(5).trimStart());
    });
    if (!dataLines.length) return;
    const data = dataLines.join("\n");
    const payload = JSON.parse(data);
    payload.event = eventName;
    onEvent(payload);
  };

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const chunks = buffer.split(/\n\n/);
    buffer = chunks.pop() || "";
    chunks.forEach(flush);
  }
  if (buffer.trim()) flush(buffer);
};

const streamChat = async (text) => {
  latestStreamState = null;
  const historyForRequest = activeHermesSessionId ? activeConversationHistory.slice() : null;
  pendingTurn = {
    status: "running",
    text,
    activeConversation,
    activeHermesSessionId,
    startedAt: new Date().toISOString(),
  };
  saveChatState();
  const streamTurn = createStreamTurn();
  const response = await fetch("/api/hermes/chat/stream", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      message: text,
      conversation: activeConversation,
      conversation_history: historyForRequest,
    }),
  });
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new Error(data.error || `request failed: ${response.status}`);
  }

  let finalResult = null;
  await readEventStream(response, (event) => {
    applyStreamEvent(event, streamTurn);
    if (event.type === "done") finalResult = event.result || {};
  });

  if (!streamTurn.text.trim()) {
    streamTurn.body.textContent = finalResult?.output_text || "done";
  }
  if (finalResult?.usage) {
    renderUsage(finalResult.usage, { model: finalResult.model || "", response_id: finalResult.id || "" });
  }
  const state = latestStreamState || finalResult?.state || await fetchJson("/api/state");
  if (state) {
    appState = state;
    if (state.jobs?.length && !currentJobId) currentJobId = state.jobs[0].id;
    renderCurrentView();
    buildCardsFromState(state).forEach((card) => {
      const msgCard = { role: "system", content: "", card };
      messages.push(msgCard);
      renderMessage(msgCard, transcript);
    });
  }
  const assistantText = streamTurn.body.textContent || "";
  messages.push({ role: "assistant", content: assistantText });
  if (activeHermesSessionId) {
    activeConversationHistory.push({ role: "user", content: text });
    if (assistantText) activeConversationHistory.push({ role: "assistant", content: assistantText });
  }
  pendingTurn = null;
  saveChatState();
  return finalResult;
};

/* ── Composer ── */
composer.addEventListener("submit", async (e) => {
  e.preventDefault();
  const text = composerInput.value.trim();
  if (!text) return;
  composerInput.value = "";
  autoResize();
  saveChatState();
  if (commandMenu) commandMenu.hidden = true;

  const userMsg = { role: "user", content: text };
  messages.push(userMsg);
  renderMessage(userMsg, transcript);

  setRuntimeStatus("running");

  try {
    await streamChat(text);
    setRuntimeStatus("connected");
  } catch (err) {
    setRuntimeStatus("offline");
    pendingTurn = null;

    const errTurn = document.createElement("div");
    errTurn.className = "turn";
    const errEl = document.createElement("div");
    errEl.className = "msg error";
    const errBody = document.createElement("div");
    errBody.className = "msg-body";
    errBody.textContent = err.message || "request failed";
    errEl.appendChild(errBody);
    errTurn.appendChild(errEl);
    transcript.appendChild(errTurn);
    transcript.scrollTop = transcript.scrollHeight;
    messages.push({ role: "system", content: err.message || "request failed" });
    saveChatState();
  }
});

const extractText = (data) => {
  if (!data) return "";
  if (typeof data === "string") return data;
  if (data.output_text) return data.output_text;
  if (typeof data.output === "string") return data.output;
  if (data.message?.content) {
    if (typeof data.message.content === "string") return data.message.content;
    if (Array.isArray(data.message.content)) {
      return data.message.content
        .filter((c) => c.type === "text")
        .map((c) => c.text)
        .join("\n");
    }
  }
  if (data.choices?.[0]?.message?.content) return data.choices[0].message.content;
  return JSON.stringify(data);
};

const renderCurrentView = () => {
  if (currentView === "dashboard") renderDashboard();
  if (currentView === "actions") renderActions();
  if (currentView === "brain") renderBrain();
  if (currentView === "discovery") renderDiscovery();
  if (currentView === "jobs") renderJobs();
  if (currentView === "materials") renderMaterials();
  if (currentView === "activity") renderActivity();
  if (currentView === "criteria") renderCriteria();
  if (currentView === "network") renderNetwork();
  if (currentView === "sessions") renderSessions();
};

/* ── Init ── */
const autoResize = () => {
  composerInput.style.height = "auto";
  composerInput.style.height = Math.min(composerInput.scrollHeight, 200) + "px";
};

composerInput.addEventListener("input", () => {
  autoResize();
  renderCommandMenu();
  saveChatState();
});
composerInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    composer.dispatchEvent(new Event("submit"));
  }
  if (e.key === "Escape" && commandMenu) {
    commandMenu.hidden = true;
  }
});
if (sessionRefresh) {
  sessionRefresh.addEventListener("click", () => {
    refreshSessions().catch(() => {
      hermesSessions = [];
      renderSessions();
    });
  });
}
if (materialViewerClose) {
  materialViewerClose.addEventListener("click", closeMaterialViewer);
}
if (materialViewer) {
  materialViewer.addEventListener("click", (event) => {
    if (event.target === materialViewer) closeMaterialViewer();
  });
}
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && materialViewer && !materialViewer.hidden) {
    closeMaterialViewer();
  }
});
if (brainSearch) {
  brainSearch.addEventListener("input", (event) => {
    brainQuery = event.target.value || "";
    renderBrain();
  });
}
if (actionsSearch) {
  actionsSearch.addEventListener("input", (event) => {
    actionsQuery = event.target.value || "";
    renderActions();
  });
}
$$("[data-action-filter]").forEach((chip) => {
  chip.addEventListener("click", () => {
    $$("[data-action-filter]").forEach((item) => item.classList.remove("active"));
    chip.classList.add("active");
    actionsLaneFilter = chip.dataset.actionFilter || "all";
    renderActions();
  });
});
if (discoveryRefresh) {
  discoveryRefresh.addEventListener("click", () => {
    refreshDiscovery().catch((err) => setDiscoveryMessage(err.message || "refresh failed", "error"));
  });
}
if (discoverySearchForm) {
  discoverySearchForm.addEventListener("submit", (event) => {
    event.preventDefault();
    if (discoveryBusy) return;
    runDiscoverySearch().catch((err) => {
      discoveryBusy = false;
      setDiscoveryMessage(err.message || "search failed", "error");
    });
  });
}
if (discoveryHydrateForm) {
  discoveryHydrateForm.addEventListener("submit", (event) => {
    event.preventDefault();
    if (discoveryBusy) return;
    hydrateDiscoveryUrl().catch((err) => {
      discoveryBusy = false;
      setDiscoveryMessage(err.message || "hydrate failed", "error");
    });
  });
}
if (prepareApprovedDiscovery) {
  prepareApprovedDiscovery.addEventListener("click", () => {
    if (discoveryBusy) return;
    prepareApprovedDiscoveryCandidates().catch((err) => setDiscoveryMessage(err.message || "prepare failed", "error"));
  });
}
if (startPendingHermesRuns) {
  startPendingHermesRuns.addEventListener("click", () => {
    startPendingMaterialPrep().catch((err) => setJobsMessage(err.message || "start failed", "error"));
  });
}
if (discoveryFilter) {
  discoveryFilter.addEventListener("input", (event) => {
    discoveryQueryFilter = event.target.value || "";
    renderDiscovery();
  });
}
$$("[data-discovery-filter]").forEach((chip) => {
  chip.addEventListener("click", () => {
    $$("[data-discovery-filter]").forEach((item) => item.classList.remove("active"));
    chip.classList.add("active");
    discoveryStatusFilter = chip.dataset.discoveryFilter || "all";
    renderDiscovery();
  });
});

const init = async () => {
  initNav();
  initJobsFilters();
  restoreChatState();
  autoResize();
  setActiveSessionLabel(activeSessionLabel);
  if (latestUsage) renderUsage(latestUsage, { model: latestUsage.model || "" });
  else renderUsage();

  try {
    updateHermesStatus(await fetchJson("/api/hermes/status"));
  } catch (err) {
    setRuntimeStatus("offline");
  }

  try {
    const catalog = await fetchJson("/api/hermes/commands");
    const normalized = normalizeCommandCatalog(catalog || {});
    commandCatalog = normalized.commands;
    commandGroups = normalized.groups;
    if (agentCommands) {
      agentCommands.textContent = commandCatalog.length ? `${commandCatalog.length}` : "off";
    }
  } catch (err) {
    commandCatalog = [];
    if (agentCommands) agentCommands.textContent = "off";
  }

  try {
    await refreshSessions();
  } catch (err) {
    hermesSessions = [];
    renderSessions();
  }

  try {
    discoveryStatus = await fetchJson("/api/discovery/status");
  } catch (err) {
    discoveryStatus = null;
  }

  try {
    const state = await fetchJson("/api/state");
    appState = state;
    if (state?.jobs?.length && !currentJobId) currentJobId = state.jobs[0].id;
    renderCurrentView();
    scrollCurrentViewToTop();
  } catch (err) {
    setRuntimeStatus("offline");
  }
};

init();
