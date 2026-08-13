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
   devices, Kubernetes, databases, identity providers, virtualization,
   email).
3. A **NIST / STIG toggle** — switch from the rule-based NIST guidance
   above to the actual DISA STIG rules that map to this control, for
   whichever technology you pick.
4. **Keyword search** — the search box finds matching NIST controls (by
   number, title, or statement text) *and* matching STIG rules (by rule
   ID, title, or CCI) at the same time, so searching e.g. "SSH" surfaces
   both without needing to already know which control governs it. Click
   a STIG match's mapped control to jump straight to it.

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
    Windows, Kubernetes, databases, virtualization, email, cloud, identity);
    **Net Admin** sees network-relevant tech (network devices, cloud,
    identity); **ISSO** always sees everything, and for a cloud platform
    gets both the compute and network guidance combined (labeled) since
    they need full visibility for compliance evidence.
- Where a specific family/technology combination has no hand-authored
  entry yet, the app falls back to a generic translation that still
  incorporates the control's actual statement text, so it never
  dead-ends — but the curated combinations are meaningfully more specific.
- **STIG mode**: unlike the NIST guidance above, STIG rules aren't
  authored by this app — they're parsed straight out of DISA's own STIG
  zips (the XCCDF XML you get from
  [public.cyber.mil](https://public.cyber.mil/stigs/downloads/)) and
  matched to a control by its NIST 800-53 mapping. Every DISA STIG tags
  each rule with a CCI number; those are bridged to NIST 800-53 via
  [MITRE Vulcan](https://github.com/mitre/vulcan)'s DISA CCI crosswalk
  table. See `scripts/build_stigs.py`'s docstring for exactly how.

  | Technology | STIG sources |
  |---|---|
  | Linux | RHEL 8, 9, 10 (merged) |
  | Windows | Server 2022, Server 2025, Windows 11, Server DNS, Defender Firewall (merged) |
  | Network | ~47 documents across Cisco (ACI/ASA/IOS/IOS-XE/IOS-XR/ISE/NX-OS), Juniper (EX/Router/SRX), Dell OS10, plus the generic Firewall/Layer 2 Switch/Network Infrastructure Policy/Network WLAN SRGs |
  | Kubernetes | DISA Kubernetes STIG |
  | Database | Generic Database SRG + MS SQL Server 2016/2022 |
  | Virtualization | VMware vSphere 8.0 (ESXi, vCenter, VCSA subsystems, VM hardening) |
  | Email | Microsoft Exchange 2019 (Mailbox + Edge Server) |
  | AWS/Azure/GCP, identity | Not available — DISA doesn't publish STIGs for these the way it does OS/network/database baselines |

  A STIG zip commonly bundles several role-specific documents (e.g. a
  switch STIG zip has separate L2S/NDM/RTR documents; a firewall vendor
  zip might have Firewall/IPS/NDM/VPN documents) — all of those are
  parsed and merged into their technology's rule set. Microsoft Office
  365 ProPlus was in the source zips but isn't wired in — it's a
  client productivity suite that doesn't fit any technology category
  here yet.

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
| `GET /api/stig/search?q=ssh&technology=linux&technology=network` | Keyword search over STIG rule id/title/CCI, independent of picking a control first — matches `q` as a substring, optionally scoped to one or more `technology` params (omit for all). Each match includes the NIST control(s) it maps to, for deep-linking back into `/api/controls/<id>`. Capped at 150 results (`truncated: true` if more matched). |

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
the STIG/SRG zips you download from
[public.cyber.mil/stigs/downloads](https://public.cyber.mil/stigs/downloads/)
plus MITRE Vulcan's CCI crosswalk table:

```bash
mkdir /tmp/stigs && cd /tmp/stigs
# download whichever STIG/SRG zips you want (DISA also periodically
# publishes a "STIG Library Compilation" zip bundling everything current)
# and drop them all in this directory, unmodified.

git clone --depth 1 https://github.com/mitre/vulcan

python3 scripts/build_stigs.py /tmp/stigs /tmp/stigs/vulcan backend/data/stigs
```

The script unzips each file, reads every `*-xccdf.xml` inside, and sorts
documents into technologies by matching their `<title>` against the rules
in `CATEGORY_RULES` — extend that table (and `TECH_TITLES`) if you add a
zip for a technology the script doesn't already recognize. Regenerating
only leaves out technologies whose zips you didn't provide (it doesn't
delete their existing data), so you can refresh a subset at a time.

Re-run this periodically to pick up new/updated STIG rules — DISA
publishes revisions on a regular cadence.

## Known limitations / next steps

- Tailoring guidance is authored at the **control-family** level, not
  per individual control/enhancement. It's accurate and useful, but a
  security team should review it against their specific environment
  before using it as audit evidence.
- No authentication/persistence layer — it's a reference/browsing tool,
  not a POA&M or SSP system of record.
- STIG mode's NIST crosswalk is Rev 4-based (see above) and covers Linux,
  Windows, network, Kubernetes, database, virtualization, and email — not
  AWS/Azure/GCP or identity, since DISA doesn't publish STIGs for those.
- No automated tests yet. Given the zero-dependency stdlib design, a
  natural next step is a `unittest`-based test module for
  `backend/app.py` and `backend/tailoring.py`.
