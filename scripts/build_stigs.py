#!/usr/bin/env python3
"""
Builds backend/data/stigs/<technology>.json from DISA's own STIG downloads
(the XCCDF "Manual" XML inside each STIG/SRG zip from public.cyber.mil)
plus MITRE Vulcan's DISA CCI -> NIST 800-53 Rev 4 crosswalk table, for the
app's NIST / STIG toggle.

Earlier versions of this script parsed community `ansible-lockdown`
automation repos instead, because that was the only source with rules
already tagged with CCI/NIST references. That only covered 5 technologies.
DISA's own XCCDF benchmarks tag every rule with CCI references directly
(<ident system="http://cyber.mil/cci">), so this version reads those
straight from the real STIG zips and needs no ansible dependency at all -
just CCI -> NIST 800-53 resolution via the same Vulcan crosswalk table.

Each rule's <fixtext> - DISA's own step-by-step remediation instructions,
often with real CLI/registry/config examples - is carried through as the
rule's "fix" field, since a bare "must be configured to..." title tells
you the requirement but not how to actually meet it.

A STIG zip commonly bundles more than one XCCDF benchmark document (e.g. a
switch STIG zip usually has separate L2S/NDM/RTR documents; a firewall
vendor zip might have Firewall/IPS/NDM/VPN documents). All of those are
parsed independently and merged. Where the same benchmark exists at more
than one revision (zips can contain a stale copy alongside the current
one - this happened with the VMware vSphere bundle), only the highest
(version, release) is kept, matched by the STIG's own stable Benchmark id.

A technology can be backed by many of these documents (e.g. "network" is
Cisco/Juniper/Dell/generic network device STIGs across ~17 zips) - their
parsed rules are merged into one output file, and each source's
title/release/rule count is kept as a list in _meta.json.

Every mapped NIST control ID is Rev 4 (that's what DISA's STIGs and CCI
list are tagged with). Base control numbers (e.g. AC-17, CM-6) are almost
always unchanged between Rev 4 and Rev 5, so the app uses them directly
against its Rev 5 catalog with a visible caveat in the UI - see
backend/stigs.py.

Usage:
    python3 build_stigs.py <stig_zips_dir> <vulcan_clone_dir> <out_dir>

<stig_zips_dir> should contain the STIG/SRG zip files exactly as downloaded
from https://public.cyber.mil/stigs/downloads/ (any filenames - each is
unzipped and every *-xccdf.xml inside is read). <vulcan_clone_dir> is a
clone of https://github.com/mitre/vulcan (used for
app/lib/cci_map/constants.rb, the CCI -> NIST 800-53 Rev 4 table).

Technologies not covered by any zip you provide are left untouched in
<out_dir> (not deleted) so you can regenerate a subset at a time.
"""
import glob
import json
import os
import re
import shutil
import sys
import tempfile
import zipfile
import xml.etree.ElementTree as ET

XCCDF_NS = "http://checklists.nist.gov/xccdf/1.1"
CCI_LINE_RE = re.compile(r"'(CCI-\d+)':\s*'([^']*)'")
CONTROL_PREFIX_RE = re.compile(r"^([A-Z]{2}-\d+)")
SEVERITY_TO_CAT = {"high": "CAT I", "medium": "CAT II", "low": "CAT III"}


def q(tag):
    return f"{{{XCCDF_NS}}}{tag}"


def parse_cci_to_nist(vulcan_constants_path):
    mapping = {}
    with open(vulcan_constants_path) as f:
        for line in f:
            m = CCI_LINE_RE.search(line)
            if not m:
                continue
            cci, nist_value = m.group(1), m.group(2)
            cm = CONTROL_PREFIX_RE.match(nist_value.strip())
            if cm:
                mapping[cci] = cm.group(1)
    return mapping


def parse_xccdf(path):
    """Returns {benchmark_id, title, version, release, rules: [...]} or
    None if this doesn't look like an XCCDF Benchmark document."""
    try:
        root = ET.parse(path).getroot()
    except ET.ParseError:
        return None
    if root.tag != q("Benchmark"):
        return None

    title_el = root.find(q("title"))
    title = title_el.text.strip() if title_el is not None and title_el.text else ""
    version_el = root.find(q("version"))
    version = int(version_el.text) if version_el is not None and (version_el.text or "").strip().isdigit() else 0
    release_el = root.find(q("plain-text[@id='release-info']"))
    release_match = re.search(r"Release:\s*(\d+)", release_el.text or "") if release_el is not None else None
    release = int(release_match.group(1)) if release_match else 0

    rules = []
    for group in root.findall(q("Group")):
        rule = group.find(q("Rule"))
        if rule is None:
            continue
        version_id_el = rule.find(q("version"))
        rule_id = version_id_el.text.strip() if version_id_el is not None and version_id_el.text else rule.get("id")
        rule_title_el = rule.find(q("title"))
        rule_title = (rule_title_el.text or "").strip() if rule_title_el is not None else ""
        severity = SEVERITY_TO_CAT.get((rule.get("severity") or "").lower(), rule.get("severity"))
        cci = sorted({
            ident.text.strip() for ident in rule.findall(q("ident"))
            if ident.get("system") == "http://cyber.mil/cci" and ident.text
        })
        fixtext_el = rule.find(q("fixtext"))
        fix = (fixtext_el.text or "").strip() if fixtext_el is not None else ""
        rules.append({"id": rule_id, "severity": severity, "title": rule_title, "cci": cci, "fix": fix})

    return {
        "benchmark_id": root.get("id") or title,
        "title": title,
        "version": version,
        "release": release,
        "rules": rules,
    }


# Explicit, in-order title matchers. First match wins; anything matching
# nothing is skipped (printed as a warning) rather than silently guessed at.
CATEGORY_RULES = [
    ("kubernetes", ["kubernetes"]),
    ("linux", ["red hat enterprise linux"]),
    ("virtualization", ["vmware vsphere"]),
    ("email", ["microsoft exchange"]),
    (None, ["microsoft office 365"]),  # client productivity suite - no home in this app's tech list yet
    ("database", ["sql server", "database security requirements guide"]),
    ("windows", ["microsoft windows", " windows server", "windows defender firewall"]),
    ("network", [
        "cisco ", "juniper ", "dell os10", "firewall security requirements guide",
        "layer 2 switch security requirements guide", "network infrastructure policy",
        "network wlan",
    ]),
]

# Curated per-technology display titles - auto-joining source titles reads
# fine for 2 sources but not for the ~47 that make up "network" here.
TECH_TITLES = {
    "linux": "DISA RHEL 8/9/10 STIGs",
    "windows": "DISA Windows STIGs (Server 2022/2025, Windows 11, Server DNS, Defender Firewall)",
    "network": "DISA Network Device STIGs (Cisco, Juniper, Dell, generic Network/Firewall/WLAN SRGs)",
    "kubernetes": "DISA Kubernetes STIG",
    "database": "DISA Database STIGs (generic SRG + MS SQL Server 2016/2022)",
    "virtualization": "DISA VMware vSphere 8.0 STIGs",
    "email": "DISA Microsoft Exchange 2019 STIGs",
}


def categorize(title):
    lowered = title.lower()
    for technology, needles in CATEGORY_RULES:
        if any(n in lowered for n in needles):
            return technology
    return "__unmatched__"


def resolve_nist_controls(cci_list, cci_to_nist):
    controls = {cci_to_nist[c] for c in cci_list if c in cci_to_nist}
    return sorted(controls)


def main():
    if len(sys.argv) != 4:
        print(__doc__)
        sys.exit(1)

    zips_dir, vulcan_dir, out_dir = sys.argv[1], sys.argv[2], sys.argv[3]
    os.makedirs(out_dir, exist_ok=True)

    constants_path = os.path.join(vulcan_dir, "app", "lib", "cci_map", "constants.rb")
    cci_to_nist = parse_cci_to_nist(constants_path)
    print(f"Parsed {len(cci_to_nist)} CCI -> NIST 800-53 Rev 4 mappings from Vulcan.")

    zip_paths = sorted(glob.glob(os.path.join(zips_dir, "*.zip")))
    if not zip_paths:
        print(f"WARNING: no .zip files found in {zips_dir}")

    with tempfile.TemporaryDirectory() as tmp:
        for zpath in zip_paths:
            dest = os.path.join(tmp, os.path.splitext(os.path.basename(zpath))[0])
            with zipfile.ZipFile(zpath) as zf:
                zf.extractall(dest)

        xccdf_paths = glob.glob(os.path.join(tmp, "**", "*-xccdf.xml"), recursive=True)
        print(f"Found {len(xccdf_paths)} XCCDF documents across {len(zip_paths)} zips.")

        parsed = [b for b in (parse_xccdf(p) for p in xccdf_paths) if b]

    # Dedup: same benchmark_id can appear at multiple revisions (a zip can
    # bundle a stale copy alongside the current one) - keep the highest.
    latest_by_id = {}
    for b in parsed:
        existing = latest_by_id.get(b["benchmark_id"])
        if existing is None or (b["version"], b["release"]) > (existing["version"], existing["release"]):
            latest_by_id[b["benchmark_id"]] = b

    by_technology = {}
    unmatched = []
    for b in latest_by_id.values():
        tech = categorize(b["title"])
        if tech is None:
            continue
        if tech == "__unmatched__":
            unmatched.append(b["title"])
            continue
        by_technology.setdefault(tech, []).append(b)

    if unmatched:
        print("WARNING: no technology mapping for these benchmark titles, skipped:")
        for t in unmatched:
            print(f"  - {t}")

    meta = {}
    for technology, benchmarks in by_technology.items():
        out_rules = []
        used_sources = []
        for b in sorted(benchmarks, key=lambda b: b["title"]):
            src_rules = []
            for rule in b["rules"]:
                nist_controls = resolve_nist_controls(rule["cci"], cci_to_nist)
                src_rules.append({
                    "id": rule["id"],
                    "severity": rule["severity"],
                    "title": rule["title"],
                    "cci": rule["cci"],
                    "nist_controls": nist_controls,
                    "fix": rule["fix"],
                })
            mapped = sum(1 for r in src_rules if r["nist_controls"])
            print(f"{technology} ({b['title']} V{b['version']}R{b['release']}): "
                  f"{len(src_rules)} rules parsed, {mapped} with a resolved NIST 800-53 control")
            out_rules.extend(src_rules)
            used_sources.append({
                "title": b["title"],
                "release": f"V{b['version']}R{b['release']}",
                "crosswalk_type": "cci",
                "rule_count": len(src_rules),
            })

        out_rules.sort(key=lambda r: r["id"])

        with open(os.path.join(out_dir, f"{technology}.json"), "w") as f:
            json.dump(out_rules, f, separators=(",", ":"))

        meta[technology] = {
            "title": TECH_TITLES.get(technology, technology),
            "source_url": "https://public.cyber.mil/stigs/downloads/",
            "sources": used_sources,
            "crosswalk_type": "cci",
            "rule_count": len(out_rules),
        }

    # Preserve _meta.json / *.json entries for technologies not touched by
    # this run (e.g. regenerating only a subset of zips).
    meta_path = os.path.join(out_dir, "_meta.json")
    existing_meta = {}
    if os.path.exists(meta_path):
        with open(meta_path) as f:
            existing_meta = json.load(f)
    existing_meta.update(meta)

    with open(meta_path, "w") as f:
        json.dump(existing_meta, f, separators=(",", ":"))
    print(f"Wrote {out_dir} ({len(meta)} technologies updated, {len(existing_meta)} total)")


if __name__ == "__main__":
    main()
