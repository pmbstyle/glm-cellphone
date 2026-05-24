const state = {
  jobs: [],
  selectedId: null,
  selectedStatus: null,
  poll: null,
  theme: localStorage.getItem("theme") || "auto",
};

const $ = (id) => document.getElementById(id);
const liveStatuses = new Set(["queued", "running", "retrying"]);
const detailPollStatuses = new Set(["queued", "running", "retrying", "paused", "stopping"]);
const controllableStatuses = new Set(["queued", "running", "retrying", "paused"]);

function applyTheme(value) {
  state.theme = value;
  localStorage.setItem("theme", value);
  if (value === "auto") {
    document.documentElement.removeAttribute("data-theme");
  } else {
    document.documentElement.dataset.theme = value;
  }
  $("themeInput").value = value;
}

function statusBadge(status) {
  return `<span class="status ${status}">${status}</span>`;
}

function fmtDate(value) {
  if (!value) return "";
  return new Date(value).toLocaleString();
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

async function fetchJson(url, options) {
  const response = await fetch(url, options);
  const data = await response.json();
  if (!response.ok) {
    throw new Error(data.detail || response.statusText);
  }
  return data;
}

async function refreshAll() {
  await Promise.all([refreshHealth(), refreshStats(), refreshJobs()]);
  const selected = getSelectedJob();
  const shouldRefreshDetail =
    selected &&
    (detailPollStatuses.has(selected.status) || detailPollStatuses.has(state.selectedStatus));
  if (shouldRefreshDetail) {
    await selectJob(state.selectedId, false);
  }
}

async function refreshHealth() {
  const health = await fetchJson("/health");
  $("health").textContent = `${health.ok ? "Ready" : "Not ready"} · ${health.model} · ${
    health.busy ? "busy" : "idle"
  }`;
}

async function refreshStats() {
  const stats = await fetchJson("/stats");
  const items = [
    ["Total", stats.total],
    ["Completed", stats.completed],
    ["Failed", stats.failed],
    ["Takeover", stats.needs_takeover],
    ["Active", stats.queued + stats.running + stats.retrying + stats.paused + stats.stopping],
    ["Avg sec", stats.average_duration_seconds ?? "-"],
  ];
  $("statsGrid").innerHTML = items
    .map(
      ([label, value]) => `<div class="stat"><strong>${value}</strong><span>${label}</span></div>`,
    )
    .join("");
}

async function refreshJobs() {
  const data = await fetchJson("/jobs?limit=100");
  state.jobs = data.jobs;
  $("jobCount").textContent = `${state.jobs.length} shown`;
  $("jobs").innerHTML = state.jobs
    .map((job) => {
      const active = job.id === state.selectedId ? " active" : "";
      const duration = job.result ? `${job.result.duration_seconds}s` : "";
      return `
        <button class="job${active}" data-job-id="${job.id}" type="button">
          <span class="job-title">${escapeHtml(job.task)}</span>
          <span>${statusBadge(job.status)}</span>
          <span class="meta">${fmtDate(job.updated_at)} ${duration}</span>
        </button>
      `;
    })
    .join("");

  document.querySelectorAll("[data-job-id]").forEach((node) => {
    node.addEventListener("click", () => selectJob(node.dataset.jobId));
  });
}

async function selectJob(jobId, updateSelection = true) {
  const [job, logs, artifacts] = await Promise.all([
    fetchJson(`/jobs/${jobId}`),
    fetchJson(`/jobs/${jobId}/logs?tail=60000`),
    fetchJson(`/jobs/${jobId}/artifacts`),
  ]);
  if (updateSelection) {
    state.selectedId = jobId;
    $("selectedJob").textContent = jobId.slice(0, 10);
    await refreshJobs();
  }
  renderDetail(job, logs.logs, artifacts.artifacts);
}

function renderDetail(job, logs, liveArtifacts = []) {
  state.selectedStatus = job.status;
  const existingLog = $("logFrame");
  const keepLogPinned =
    liveStatuses.has(job.status) &&
    (!existingLog || existingLog.scrollTop + existingLog.clientHeight >= existingLog.scrollHeight - 24);
  const result = job.result;
  const artifacts = liveArtifacts.length ? liveArtifacts : result?.artifacts || [];
  const screenshots = artifacts.filter((item) => item.kind === "screenshot");
  const files = artifacts.filter((item) => item.kind !== "screenshot");
  const steps = result?.steps || [];

  $("detail").className = "";
  $("detail").innerHTML = `
    <div class="summary">
      <div>${statusBadge(job.status)}</div>
      <strong>${escapeHtml(job.task)}</strong>
      <span class="meta">Created ${fmtDate(job.created_at)} · Updated ${fmtDate(job.updated_at)}</span>
      ${result ? `<span class="meta">Duration ${result.duration_seconds}s · attempts ${result.attempts}</span>` : ""}
      ${renderJobActions(job)}
      ${job.error ? `<div class="message">${escapeHtml(job.error)}</div>` : ""}
      ${result ? `<div class="message">${escapeHtml(result.message)}</div>` : ""}
    </div>

    <h3>Artifacts</h3>
    <div class="artifacts">
      ${screenshots
        .map(
          (item) => `
            <div class="artifact">
              <a href="${item.url}" target="_blank" rel="noreferrer">
                <img src="${item.url}" alt="${escapeHtml(item.label)}" />
                ${escapeHtml(item.label)}
              </a>
            </div>
          `,
        )
        .join("")}
      ${files
        .map(
          (item) => `
            <div class="artifact">
              <a href="${item.url}" target="_blank" rel="noreferrer">${escapeHtml(item.label)}</a>
            </div>
          `,
        )
        .join("")}
    </div>

    <h3>Steps</h3>
    <div class="steps">
      ${steps
        .map(
          (step) => `
            <div class="step">
              <strong>Step ${step.index}</strong>
              <span class="meta">success=${step.success} finished=${step.finished}</span>
              <pre>${escapeHtml(JSON.stringify(step.action, null, 2))}</pre>
              ${step.message ? `<div class="message">${escapeHtml(step.message)}</div>` : ""}
            </div>
          `,
        )
        .join("")}
    </div>

    <h3>Logs</h3>
    <pre id="logFrame" class="log-frame">${escapeHtml(logs)}</pre>
  `;
  const logFrame = $("logFrame");
  if (keepLogPinned && logFrame) {
    logFrame.scrollTop = logFrame.scrollHeight;
  }
  bindJobActionButtons();
}

function renderJobActions(job) {
  if (!controllableStatuses.has(job.status) && job.status !== "stopping") {
    return "";
  }
  const pauseButton =
    job.status === "paused"
      ? `<button data-job-action="resume" data-job-id="${job.id}" type="button">Resume</button>`
      : liveStatuses.has(job.status)
        ? `<button class="warn" data-job-action="pause" data-job-id="${job.id}" type="button">Pause</button>`
        : "";
  const stopButton = controllableStatuses.has(job.status)
    ? `<button class="danger" data-job-action="stop" data-job-id="${job.id}" type="button">Stop</button>`
    : "";
  return `<div class="job-actions">${pauseButton}${stopButton}</div>`;
}

function bindJobActionButtons() {
  document.querySelectorAll("[data-job-action]").forEach((button) => {
    button.addEventListener("click", async () => {
      await runJobAction(button.dataset.jobId, button.dataset.jobAction);
    });
  });
}

async function runJobAction(jobId, action) {
  await fetchJson(`/jobs/${jobId}/${action}`, { method: "POST" });
  await refreshAll();
}

async function clearHistory() {
  const active = state.jobs.filter((job) => controllableStatuses.has(job.status)).length;
  const suffix = active ? ` Active runs will be kept (${active}).` : "";
  if (!confirm(`Clear stored run history and artifacts?${suffix}`)) {
    return;
  }
  await fetchJson("/jobs", { method: "DELETE" });
  if (state.selectedId && !controllableStatuses.has(getSelectedJobStatus())) {
    state.selectedId = null;
    state.selectedStatus = null;
    $("selectedJob").textContent = "";
    $("detail").className = "detail-empty";
    $("detail").textContent = "Select a run.";
  }
  await refreshAll();
}

function getSelectedJobStatus() {
  return getSelectedJob()?.status;
}

function getSelectedJob() {
  return state.jobs.find((job) => job.id === state.selectedId);
}

async function startRun(event) {
  event.preventDefault();
  const payload = {
    task: $("taskInput").value,
    max_steps: Number($("stepsInput").value || 20),
    max_retries: Number($("retriesInput").value || 0),
    lang: $("langInput").value,
    allow_sensitive_actions: $("sensitiveInput").checked,
  };
  const deviceId = $("deviceInput").value.trim();
  if (deviceId) {
    payload.device_id = deviceId;
  }
  const job = await fetchJson("/jobs", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(payload),
  });
  state.selectedId = job.id;
  state.selectedStatus = job.status;
  await refreshAll();
  await selectJob(job.id);
}

$("runForm").addEventListener("submit", (event) => {
  startRun(event).catch((error) => alert(error.message));
});
$("refreshButton").addEventListener("click", () => refreshAll().catch(console.error));
$("clearHistoryButton").addEventListener("click", () => {
  clearHistory().catch((error) => alert(error.message));
});
$("themeInput").addEventListener("change", (event) => applyTheme(event.target.value));

applyTheme(state.theme);
refreshAll().catch(console.error);
state.poll = setInterval(() => refreshAll().catch(console.error), 5000);
