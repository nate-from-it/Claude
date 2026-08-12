const API_BASE = window.NIST_API_BASE || "http://localhost:5057";

const state = {
  families: [],
  audiences: [],
  technologies: [], // scoped to the current audience
  activeFamily: null,
  query: "",
  includeEnhancements: true,
  selectedControlId: null,
  selectedTechnologies: new Set(),
  selectedAudience: "sysadmin",
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
  const [families, audiences] = await Promise.all([api("/api/families"), api("/api/audiences")]);
  state.families = families;
  state.audiences = audiences;

  renderFamilyList();
  renderAudienceSelect();
  await refreshControlList();

  el("search").addEventListener("input", debounce((e) => {
    state.query = e.target.value;
    refreshControlList();
  }, 250));

  el("toggle-enhancements").addEventListener("change", (e) => {
    state.includeEnhancements = e.target.checked;
    refreshControlList();
  });

  el("back-btn").addEventListener("click", () => showListView());
  el("tailor-btn").addEventListener("click", runTailor);
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
  for (const t of state.technologies) {
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

// Loads the role narrative + the technology list scoped to the current
// audience for the currently open control. ISSO sees every technology;
// Sysadmin/Net Admin each see only the technologies relevant to their role.
async function refreshRoleView() {
  const narrativeEl = el("role-narrative");
  narrativeEl.textContent = "Loading...";

  const [technologies, tailorData] = await Promise.all([
    api(`/api/technologies?audience=${state.selectedAudience}`),
    api(`/api/controls/${state.selectedControlId}/tailor`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ technologies: [], audience: state.selectedAudience }),
    }),
  ]);

  state.technologies = technologies;
  narrativeEl.textContent = tailorData.intro;
  renderTechSelect();
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
  btn.textContent = "Generating...";

  try {
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
  } catch (err) {
    resultsEl.innerHTML = `<div class="error-state">${err.message}</div>`;
  } finally {
    btn.disabled = false;
    btn.textContent = "Generate implementation guidance";
  }
}

init().catch((err) => {
  document.body.innerHTML = `<div class="error-state" style="padding:40px;">Failed to load app: ${err.message}. Is the backend running at ${API_BASE}?</div>`;
});
