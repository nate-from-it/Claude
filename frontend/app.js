const API_BASE = window.NIST_API_BASE || "http://localhost:5057";

const MODES = { nist: "NIST Guidance", stig: "STIG Guidance" };

const state = {
  families: [],
  audiences: [],
  technologies: [], // scoped to the current audience (and, in STIG mode, to STIG-covered tech)
  stigTechnologies: {}, // id -> source meta, only for technologies with STIG coverage
  activeFamily: null,
  query: "",
  includeEnhancements: true,
  selectedControlId: null,
  selectedTechnologies: new Set(),
  selectedAudience: "sysadmin",
  mode: "nist",
};

const el = (id) => document.getElementById(id);

async function api(path, options) {
  const res = await fetch(`${API_BASE}${path}`, options);
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.error || `Request failed (${res.status})`);
  }
  return res.json();
}

async function init() {
  const [families, audiences, stigTechs] = await Promise.all([
    api("/api/families"),
    api("/api/audiences"),
    api("/api/stig-technologies"),
  ]);
  state.families = families;
  state.audiences = audiences;
  state.stigTechnologies = Object.fromEntries(stigTechs.map((t) => [t.id, t]));

  renderFamilyList();
  renderModeSelect();
  renderAudienceSelect();
  await refreshControlList();

  el("search").addEventListener("input", debounce((e) => {
    state.query = e.target.value;
    refreshControlList();
    refreshStigMatches();
  }, 250));

  el("toggle-enhancements").addEventListener("change", (e) => {
    state.includeEnhancements = e.target.checked;
    refreshControlList();
  });

  el("back-btn").addEventListener("click", () => showListView());
  el("tailor-btn").addEventListener("click", runTailor);

  el("narrative-start-btn").addEventListener("click", startNarrativeFlow);
  el("narrative-met-btn").addEventListener("click", () => generateAtoNarrative("met"));
  el("narrative-not-met-btn").addEventListener("click", () => generateAtoNarrative("not_met"));
  el("narrative-copy-btn").addEventListener("click", copyNarrativeToClipboard);
  el("narrative-restart-btn").addEventListener("click", resetNarrativeUI);
}

// ISSO-only: drafts an SSP implementation statement (control met) or a
// POA&M-style gap/compensating-control narrative (control not met) for
// ATO/A&A documentation. Rule-based like the rest of the app's guidance,
// not an LLM call - a structured first draft for the ISSO to edit.
function resetNarrativeUI() {
  el("narrative-question").classList.add("hidden");
  el("narrative-output").classList.add("hidden");
  el("narrative-start-btn").classList.remove("hidden");
  el("narrative-hint").classList.add("hidden");
  el("narrative-copy-status").textContent = "";
}

function renderNarrativeSection() {
  el("narrative-section").classList.toggle("hidden", state.selectedAudience !== "isso");
  resetNarrativeUI();
}

function startNarrativeFlow() {
  if (state.selectedTechnologies.size === 0) {
    el("narrative-hint").classList.remove("hidden");
    return;
  }
  el("narrative-hint").classList.add("hidden");
  el("narrative-start-btn").classList.add("hidden");
  el("narrative-question").classList.remove("hidden");
}

async function generateAtoNarrative(status) {
  el("narrative-question").classList.add("hidden");
  const data = await api(`/api/controls/${state.selectedControlId}/narrative`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ technologies: Array.from(state.selectedTechnologies), status }),
  });
  el("narrative-text").value = data.narrative;
  el("narrative-output").classList.remove("hidden");
}

function copyNarrativeToClipboard() {
  navigator.clipboard.writeText(el("narrative-text").value).then(() => {
    const status = el("narrative-copy-status");
    status.textContent = "Copied!";
    setTimeout(() => { status.textContent = ""; }, 2000);
  });
}

function debounce(fn, ms) {
  let t;
  return (...args) => {
    clearTimeout(t);
    t = setTimeout(() => fn(...args), ms);
  };
}

function renderFamilyList() {
  const ul = el("family-list");
  ul.innerHTML = "";

  const allLi = document.createElement("li");
  allLi.textContent = "All families";
  allLi.className = state.activeFamily === null ? "active" : "";
  allLi.addEventListener("click", () => {
    state.activeFamily = null;
    refreshControlList();
    renderFamilyList();
  });
  ul.appendChild(allLi);

  for (const f of state.families) {
    const li = document.createElement("li");
    li.className = state.activeFamily === f.id ? "active" : "";
    const label = document.createElement("span");
    label.textContent = `${f.id} — ${f.title}`;
    const count = document.createElement("span");
    count.className = "fam-count";
    count.textContent = f.control_count;
    li.appendChild(label);
    li.appendChild(count);
    li.addEventListener("click", () => {
      state.activeFamily = f.id;
      refreshControlList();
      renderFamilyList();
    });
    ul.appendChild(li);
  }
}

function renderModeSelect() {
  const container = el("mode-select");
  container.innerHTML = "";
  for (const key of Object.keys(MODES)) {
    const btn = document.createElement("button");
    btn.textContent = MODES[key];
    btn.className = state.mode === key ? "active" : "";
    btn.addEventListener("click", () => {
      if (state.mode === key) return;
      state.mode = key;
      state.selectedTechnologies = new Set();
      renderModeSelect();
      refreshRoleView();
    });
    container.appendChild(btn);
  }
}

function renderAudienceSelect() {
  const container = el("audience-select");
  container.innerHTML = "";
  for (const a of state.audiences) {
    const btn = document.createElement("button");
    btn.textContent = a.name;
    btn.className = state.selectedAudience === a.id ? "active" : "";
    btn.addEventListener("click", () => {
      if (state.selectedAudience === a.id) return;
      state.selectedAudience = a.id;
      state.selectedTechnologies = new Set();
      renderAudienceSelect();
      refreshRoleView();
    });
    container.appendChild(btn);
  }
}

function renderTechSelect() {
  const container = el("tech-select");
  container.innerHTML = "";
  const visible = state.mode === "stig"
    ? state.technologies.filter((t) => t.id in state.stigTechnologies)
    : state.technologies;

  if (state.mode === "stig" && visible.length === 0) {
    const empty = document.createElement("div");
    empty.className = "empty-state";
    empty.textContent = "No STIG-covered technology is available for this role.";
    container.appendChild(empty);
    return;
  }

  for (const t of visible) {
    const label = document.createElement("label");
    const checkbox = document.createElement("input");
    checkbox.type = "checkbox";
    checkbox.value = t.id;
    checkbox.checked = state.selectedTechnologies.has(t.id);
    checkbox.addEventListener("change", () => {
      if (checkbox.checked) state.selectedTechnologies.add(t.id);
      else state.selectedTechnologies.delete(t.id);
      label.className = checkbox.checked ? "checked" : "";
    });
    label.className = checkbox.checked ? "checked" : "";
    label.appendChild(checkbox);
    label.appendChild(document.createTextNode(t.name));
    container.appendChild(label);
  }
}

// Loads the technology list scoped to the current audience (and, in STIG
// mode, further scoped to STIG-covered tech) for the currently open
// control, plus either the NIST role narrative or the STIG caveat note.
async function refreshRoleView() {
  const narrativeEl = el("role-narrative");
  const caveatEl = el("stig-caveat");
  const btn = el("tailor-btn");

  if (state.mode === "stig") {
    narrativeEl.classList.add("hidden");
    caveatEl.classList.remove("hidden");
    caveatEl.textContent =
      "STIG rules come straight from DISA's own STIG/SRG zips, tagged against NIST 800-53 Rev 4 " +
      "via the official DISA CCI crosswalk. " +
      "Rev 4 and Rev 5 base control numbers are almost always the same, but this mapping isn't guaranteed for every control — verify before using as audit evidence.";
    btn.textContent = "Show STIG rules";
  } else {
    caveatEl.classList.add("hidden");
    narrativeEl.classList.remove("hidden");
    narrativeEl.textContent = "Loading...";
    btn.textContent = "Generate implementation guidance";
  }

  const technologies = await api(`/api/technologies?audience=${state.selectedAudience}`);
  state.technologies = technologies;

  if (state.mode === "nist") {
    const tailorData = await api(`/api/controls/${state.selectedControlId}/tailor`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ technologies: [], audience: state.selectedAudience }),
    });
    narrativeEl.textContent = tailorData.intro;
  }

  renderTechSelect();
  renderNarrativeSection();
  el("tailor-results").innerHTML = "";
}

async function refreshControlList() {
  const params = new URLSearchParams();
  if (state.activeFamily) params.set("family", state.activeFamily);
  if (state.query) params.set("q", state.query);
  params.set("enhancements", state.includeEnhancements ? "true" : "false");

  const data = await api(`/api/controls?${params.toString()}`);

  el("list-title").textContent = state.activeFamily
    ? `${state.activeFamily} — ${state.families.find((f) => f.id === state.activeFamily)?.title ?? ""}`
    : "All Controls";
  el("list-count").textContent = `${data.count} control${data.count === 1 ? "" : "s"}`;

  const ul = el("control-list");
  ul.innerHTML = "";
  if (data.count === 0) {
    const empty = document.createElement("div");
    empty.className = "empty-state";
    empty.textContent = "No controls match your search.";
    ul.appendChild(empty);
    return;
  }

  for (const c of data.controls) {
    const li = document.createElement("li");
    const number = document.createElement("span");
    number.className = "ctrl-number";
    number.textContent = c.number;
    const title = document.createElement("span");
    title.className = "ctrl-title";
    title.textContent = c.title;
    li.appendChild(number);
    li.appendChild(title);
    if (c.is_enhancement) {
      const badge = document.createElement("span");
      badge.className = "badge-enh";
      badge.textContent = "enhancement";
      li.appendChild(badge);
    }
    if (c.withdrawn) {
      const badge = document.createElement("span");
      badge.className = "badge-enh";
      badge.textContent = "withdrawn";
      li.appendChild(badge);
    }
    li.addEventListener("click", () => showDetail(c.id));
    ul.appendChild(li);
  }
}

// Direct keyword search over STIG rule id/title/CCI, independent of
// picking a control first - separate from refreshControlList()'s NIST
// control text search, since a keyword like "SSH" is far more likely to
// hit rule titles than the control catalog's abstract control text.
async function refreshStigMatches() {
  const section = el("stig-matches-section");
  const query = state.query.trim();
  if (query.length < 2) {
    section.classList.add("hidden");
    return;
  }

  const data = await api(`/api/stig/search?q=${encodeURIComponent(query)}`);
  section.classList.remove("hidden");
  el("stig-matches-count").textContent = data.truncated
    ? `showing ${data.results.length} of ${data.count}`
    : `${data.count} match${data.count === 1 ? "" : "es"}`;

  const list = el("stig-matches-list");
  list.innerHTML = "";
  if (data.results.length === 0) {
    const empty = document.createElement("div");
    empty.className = "empty-state";
    empty.textContent = "No STIG rules match your search.";
    list.appendChild(empty);
    return;
  }

  for (const rule of data.results) {
    const card = document.createElement("div");
    card.className = "stig-rule";

    const head = document.createElement("div");
    head.className = "stig-rule-head";
    const sev = document.createElement("span");
    sev.className = "sev-badge " + (SEVERITY_CLASS[rule.severity] || "");
    sev.textContent = rule.severity;
    const tech = document.createElement("span");
    tech.className = "tech-tag";
    tech.textContent = rule.technology_name;
    const id = document.createElement("span");
    id.className = "stig-rule-id";
    id.textContent = rule.id;
    head.appendChild(sev);
    head.appendChild(tech);
    head.appendChild(id);

    const title = document.createElement("p");
    title.textContent = rule.title;

    const controls = document.createElement("div");
    controls.className = "stig-match-controls";
    for (const c of rule.nist_controls) {
      const link = document.createElement("button");
      link.className = "control-link";
      link.textContent = c.id ? `${c.number} — ${c.title}` : c.number;
      if (c.id) {
        link.addEventListener("click", () => jumpToStigMatch(c.id, rule.technology));
      } else {
        link.disabled = true;
      }
      controls.appendChild(link);
    }

    card.appendChild(head);
    card.appendChild(title);
    if (rule.nist_controls.length) card.appendChild(controls);
    const fixDetails = buildStigFixDetails(rule.fix);
    if (fixDetails) card.appendChild(fixDetails);
    list.appendChild(card);
  }
}

// Jumps from a STIG search-result hit straight to that control, in STIG
// mode, with the matching technology pre-selected and its rules shown.
// Switches audience to ISSO first since it's the only one guaranteed to
// see every technology - a search hit for e.g. "network" wouldn't even
// have a checkbox to show as checked under the sysadmin-scoped default.
async function jumpToStigMatch(controlId, technology) {
  state.mode = "stig";
  state.selectedAudience = "isso";
  renderModeSelect();
  renderAudienceSelect();
  await showDetail(controlId);
  state.selectedTechnologies = new Set([technology]);
  renderTechSelect();
  await runTailor();
}

async function showDetail(controlId) {
  const control = await api(`/api/controls/${controlId}`);
  state.selectedControlId = controlId;
  state.selectedTechnologies = new Set();

  el("control-list-section").classList.add("hidden");
  el("detail-section").classList.remove("hidden");

  el("detail-title").textContent = `${control.number} — ${control.title}`;

  const withdrawnNote = el("detail-withdrawn");
  if (control.withdrawn) {
    withdrawnNote.classList.remove("hidden");
    withdrawnNote.textContent = control.incorporated_into.length
      ? `Withdrawn: incorporated into ${control.incorporated_into.join(", ")}`
      : "Withdrawn from the catalog.";
  } else {
    withdrawnNote.classList.add("hidden");
  }

  el("detail-statement").textContent = control.statement || "(no statement — see incorporated control)";
  el("detail-guidance").textContent = control.guidance || "(no additional discussion)";

  await refreshRoleView();
}

function showListView() {
  el("detail-section").classList.add("hidden");
  el("control-list-section").classList.remove("hidden");
}

async function runTailor() {
  const resultsEl = el("tailor-results");
  if (state.selectedTechnologies.size === 0) {
    resultsEl.innerHTML = '<div class="error-state">Select at least one technology.</div>';
    return;
  }

  const btn = el("tailor-btn");
  btn.disabled = true;
  btn.textContent = state.mode === "stig" ? "Loading..." : "Generating...";

  try {
    if (state.mode === "stig") {
      await runStig(resultsEl);
    } else {
      await runNistTailor(resultsEl);
    }
  } catch (err) {
    resultsEl.innerHTML = `<div class="error-state">${err.message}</div>`;
  } finally {
    btn.disabled = false;
    btn.textContent = state.mode === "stig" ? "Show STIG rules" : "Generate implementation guidance";
  }
}

async function runNistTailor(resultsEl) {
  const data = await api(`/api/controls/${state.selectedControlId}/tailor`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      technologies: Array.from(state.selectedTechnologies),
      audience: state.selectedAudience,
    }),
  });

  resultsEl.innerHTML = "";
  for (const item of data.items) {
    const card = document.createElement("div");
    card.className = "tech-result";
    const h4 = document.createElement("h4");
    h4.textContent = item.technology_name;
    const p = document.createElement("p");
    p.textContent = item.guidance;
    card.appendChild(h4);
    card.appendChild(p);
    resultsEl.appendChild(card);
  }
}

const SEVERITY_CLASS = { "CAT I": "sev-1", "CAT II": "sev-2", "CAT III": "sev-3" };

// A STIG rule's title is just the "must" requirement - DISA's own fixtext
// (carried through by build_stigs.py as rule.fix) is the actual step-by-step
// remediation, often with real CLI/config examples. Collapsed by default
// since it can run long; <pre> preserves the source's line breaks/indents.
function buildStigFixDetails(fix) {
  if (!fix) return null;
  const details = document.createElement("details");
  details.className = "stig-fix";
  const summary = document.createElement("summary");
  summary.textContent = "How to implement";
  const pre = document.createElement("pre");
  pre.textContent = fix;
  details.appendChild(summary);
  details.appendChild(pre);
  return details;
}

async function runStig(resultsEl) {
  resultsEl.innerHTML = "";
  const techs = Array.from(state.selectedTechnologies);
  const results = await Promise.all(
    techs.map((tech) => api(`/api/controls/${state.selectedControlId}/stig?technology=${tech}`))
  );

  for (const data of results) {
    const group = document.createElement("div");
    group.className = "stig-group";

    const h4 = document.createElement("h4");
    h4.textContent = data.technology_name + (data.source ? ` — ${data.source.title}` : "");
    group.appendChild(h4);

    if (!data.available) {
      const p = document.createElement("p");
      p.className = "empty-state";
      p.textContent = "No STIG crosswalk available for this technology.";
      group.appendChild(p);
    } else if (data.rules.length === 0) {
      const p = document.createElement("p");
      p.className = "empty-state";
      p.textContent = "No STIG rules in this source map to this control.";
      group.appendChild(p);
    } else {
      for (const rule of data.rules) {
        const card = document.createElement("div");
        card.className = "stig-rule";
        const head = document.createElement("div");
        head.className = "stig-rule-head";
        const sev = document.createElement("span");
        sev.className = "sev-badge " + (SEVERITY_CLASS[rule.severity] || "");
        sev.textContent = rule.severity;
        const id = document.createElement("span");
        id.className = "stig-rule-id";
        id.textContent = rule.id;
        head.appendChild(sev);
        head.appendChild(id);
        const title = document.createElement("p");
        title.textContent = rule.title;
        const cci = document.createElement("div");
        cci.className = "stig-cci";
        cci.textContent = rule.cci.join(", ");
        card.appendChild(head);
        card.appendChild(title);
        card.appendChild(cci);
        const fixDetails = buildStigFixDetails(rule.fix);
        if (fixDetails) card.appendChild(fixDetails);
        group.appendChild(card);
      }
    }

    resultsEl.appendChild(group);
  }
}

init().catch((err) => {
  document.body.innerHTML = `<div class="error-state" style="padding:40px;">Failed to load app: ${err.message}. Is the backend running at ${API_BASE}?</div>`;
});
