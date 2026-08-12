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

## Known limitations / next steps

- Tailoring guidance is authored at the **control-family** level, not
  per individual control/enhancement. It's accurate and useful, but a
  security team should review it against their specific environment
  before using it as audit evidence.
- No authentication/persistence layer — it's a reference/browsing tool,
  not a POA&M or SSP system of record.
- No automated tests yet. Given the zero-dependency stdlib design, a
  natural next step is a `unittest`-based test module for
  `backend/app.py` and `backend/tailoring.py`.
