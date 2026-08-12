# NIST 800-53 Rev 5 Control Translator

Browse the full NIST SP 800-53 Revision 5 control catalog and get a full
role narrative plus technology-specific implementation guidance tailored to
your role: **System Administrator**, **Network Administrator**, or **ISSO**.

## Why it exists

NIST 800-53 controls are written for auditors, not for the people who
actually configure firewalls, IAM policies, and OS baselines. This tool
takes a control (e.g. `AC-17 Remote Access`) and translates it into:

1. A **role narrative** — how to interpret this control family in your
   role, and what you specifically need to do to meet it.
2. **Technology-specific guidance** — concrete implementation steps for the
   technologies you actually run (AWS, Azure, GCP, Linux, Windows, network
   devices, Kubernetes, databases, identity providers).
3. A **NIST / STIG toggle** — switch from the rule-based NIST guidance
   above to the actual DISA STIG rules that map to this control, for
   whichever OS/device you pick (Linux, Windows, network switches,
   Kubernetes).

## How it works

- **Catalog**: the full official NIST OSCAL rev5 catalog (1,196 base
  controls + enhancements) is flattened into one JSON file per control
  family under `backend/data/families/` (plus a `_meta.json` index) by
  `scripts/build_catalog.py`. Splitting per family keeps each file small
  and reviewable instead of one large blob. See that script's docstring
  for the source and how to regenerate it if NIST publishes an update.
- **Tailoring**: guidance is **rule-based**, not an LLM call. It's built
  from a curated knowledge base in `backend/tailoring.py`:
  - `AUDIENCE_NARRATIVE[family][audience]` is a full paragraph — how to
    interpret the control family in that role, and what to actually do.
  - `FAMILY_TECH_GUIDANCE[family][technology]` is the concrete how-to. For
    AWS/Azure/GCP specifically, it's split into a `sysadmin` (compute)
    variant and a `netadmin` (network) variant, since cloud platforms span
    both domains.
  - `TECH_AUDIENCE[technology]` controls which roles even see a given
    technology as an option: **Sysadmin** sees host/platform tech (Linux,
    Windows, Kubernetes, databases, cloud, identity); **Net Admin** sees
    network-relevant tech (network devices, cloud, identity); **ISSO**
    always sees everything, and for a cloud platform gets both the compute
    and network guidance combined (labeled) since they need full visibility
    for compliance evidence.
- Where a specific family/technology combination has no hand-authored
  entry yet, the app falls back to a generic translation that still
  incorporates the control's actual statement text, so it never
  dead-ends — but the curated combinations are meaningfully more specific.
- **STIG mode**: unlike the NIST guidance above, STIG rules aren't
  authored by this app — they're ingested from DISA's actual STIG source
  repos (`scripts/build_stigs.py`, see that script's docstring for
  sources) and matched to a control by its NIST 800-53 mapping. Coverage
  is intentionally partial:

  | Technology | STIG source | Crosswalk |
  |---|---|---|
  | Linux | DISA RHEL 9 STIG | Direct — the source tags each rule with its NIST 800-53 control |
  | Windows | DISA Windows Server 2022 STIG | Direct |
  | Network | DISA Cisco IOS **Switch** (L2S) STIG | Bridged — the source only tags CCI numbers; those are resolved to a NIST 800-53 control via [MITRE Vulcan](https://github.com/mitre/vulcan)'s DISA CCI crosswalk table |
  | Kubernetes | DISA Kubernetes STIG | Bridged, same as above |
  | AWS/Azure/GCP, identity, database, Cisco **routers** | — | Not available. DISA doesn't publish cloud-platform STIGs the way it does OS/network baselines; the router STIG source repo is an empty stub; and the one database STIG source (PostgreSQL 9.x) has no CCI or NIST tagging at all to bridge from. |

  Every mapped NIST control ID is **Rev 4** (that's what DISA's STIGs and
  CCI list are tagged with) — the app matches it directly against its Rev
  5 catalog. Base control numbers (e.g. `AC-17`, `CM-6`) are almost always
  unchanged between revisions, so this is normally reliable, but it isn't
  guaranteed for every control — the UI surfaces this as a standing
  caveat in STIG mode, not a footnote.

## Stack

Zero third-party dependencies, by design (this keeps it trivially easy to
run anywhere, including network-restricted environments):

- **Backend**: Python 3 standard library only (`http.server`). No `pip
  install` required.
- **Frontend**: a single-page vanilla HTML/CSS/JS app. No build step, no
  `npm install` required.

## Running it locally

```bash
# Terminal 1 - backend API (default :5057)
cd backend
python3 app.py

# Terminal 2 - frontend (any static file server works, e.g.)
cd frontend
python3 -m http.server 5173
```

Then open `http://localhost:5173`. If you serve the backend on a
different host/port, set it before the app script loads:

```html
<script>window.NIST_API_BASE = "http://your-backend-host:5057";</script>
<script src="app.js"></script>
```

## API

| Endpoint | Description |
|---|---|
| `GET /api/health` | Liveness + loaded control count |
| `GET /api/families` | 20 control families with active-control counts |
| `GET /api/technologies?audience=sysadmin` | Technology categories, scoped to a role (omit `audience` or pass `isso` for the full list) |
| `GET /api/audiences` | Supported audience roles |
| `GET /api/controls?family=AC&q=remote&enhancements=true&withdrawn=false` | Search/browse controls |
| `GET /api/controls/<id>` | Full control detail (official statement + discussion) |
| `POST /api/controls/<id>/tailor` | Body: `{"technologies": ["aws","network"], "audience": "netadmin"}` — returns the role narrative plus tailored per-technology guidance. Pass `"technologies": []` to get just the narrative (used by the UI as soon as a role is picked, before any technology is selected). |
| `GET /api/stig-technologies` | Technologies with STIG coverage, with source title/URL/crosswalk type/rule count |
| `GET /api/controls/<id>/stig?technology=linux` | STIG rules for that technology that map to this control. `available: false` for a technology with no STIG coverage. |

## Extending the tailoring knowledge base

`backend/tailoring.py` has three things worth knowing about:

- `AUDIENCE_NARRATIVE[family][audience]` — the full "how to interpret this
  control and what to do" narrative, per role.
- `FAMILY_TECH_GUIDANCE[family][technology]` — the concrete "how" for a
  given family on a given technology. For `aws`/`azure`/`gcp` this is a
  `{"sysadmin": ..., "netadmin": ...}` dict rather than a plain string;
  everything else is a plain string shared across the roles that can see it.
- `TECH_AUDIENCE[technology]` — which role(s) see that technology as an
  option at all (ISSO is implicit — it always sees every technology, see
  `technologies_for_audience()`).

Add or refine entries there — no code changes needed elsewhere. If you
want to go deeper than family-level guidance (e.g. control-specific
guidance for `AC-2` vs. the rest of the `AC` family), key an entry by the
control's `id` (e.g. `"ac-2"`) and look it up before the family-level
fallback in `resolve_tech_guidance()`.

## Regenerating the control catalog

`backend/data/families/*.json` is generated, not hand-written. NIST's
official machine-readable catalog lives at
[usnistgov/oscal-content](https://github.com/usnistgov/oscal-content)
(`nist.gov/SP800-53/rev5/json/NIST_SP-800-53_rev5_catalog-min.json`).

```bash
git clone --depth 1 https://github.com/usnistgov/oscal-content /tmp/oscal-content
python3 scripts/build_catalog.py \
  /tmp/oscal-content/nist.gov/SP800-53/rev5/json/NIST_SP-800-53_rev5_catalog-min.json \
  backend/data/families
```

## Regenerating the STIG data

`backend/data/stigs/*.json` is generated by `scripts/build_stigs.py` from
four `ansible-lockdown` STIG repos plus MITRE Vulcan's CCI crosswalk table:

```bash
mkdir /tmp/stigs && cd /tmp/stigs
git clone --depth 1 https://github.com/ansible-lockdown/RHEL9-STIG
git clone --depth 1 https://github.com/ansible-lockdown/Windows-2022-STIG
git clone --depth 1 https://github.com/ansible-lockdown/CISCO-IOS-L2S-STIG
git clone --depth 1 https://github.com/ansible-lockdown/KUBERNETES-STIG
git clone --depth 1 https://github.com/mitre/vulcan

python3 scripts/build_stigs.py /tmp/stigs /tmp/stigs/vulcan backend/data/stigs
```

Re-run this periodically to pick up new/updated STIG rules — the source
repos are actively maintained by DISA/community contributors.

## Known limitations / next steps

- Tailoring guidance is authored at the **control-family** level, not
  per individual control/enhancement. It's accurate and useful, but a
  security team should review it against their specific environment
  before using it as audit evidence.
- No authentication/persistence layer — it's a reference/browsing tool,
  not a POA&M or SSP system of record.
- STIG mode's NIST crosswalk is Rev 4-based (see above) and covers only
  Linux, Windows, network switches, and Kubernetes — not cloud platforms,
  identity, databases, or routers. Extending it further needs a STIG
  source with real CCI or NIST tagging to ingest from; see
  `scripts/build_stigs.py` for the ones already evaluated (including
  which ones don't have usable tagging and were excluded).
- No automated tests yet. Given the zero-dependency stdlib design, a
  natural next step is a `unittest`-based test module for
  `backend/app.py` and `backend/tailoring.py`.
