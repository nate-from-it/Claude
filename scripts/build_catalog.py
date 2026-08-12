#!/usr/bin/env python3
"""
Flattens the official NIST SP 800-53 rev5 OSCAL catalog JSON into a compact,
app-friendly set of per-family JSON files used by the translator backend
(backend/data/families/<FAMILY>.json, plus a families/_meta.json index).
Split per-family (rather than one big controls.json) so each file stays
small and reviewable.

Source catalog (not vendored here due to size): NIST's oscal-content repo,
nist.gov/SP800-53/rev5/json/NIST_SP-800-53_rev5_catalog-min.json
https://github.com/usnistgov/oscal-content

Usage:
    python3 build_catalog.py /path/to/NIST_SP-800-53_rev5_catalog-min.json ../backend/data/families
"""
import json
import os
import re
import sys


def is_withdrawn(node):
    return any(p.get("name") == "status" and p.get("value") == "withdrawn" for p in node.get("props", []))


def param_labels(node):
    labels = {}
    for p in node.get("params", []):
        if "label" in p:
            labels[p["id"]] = p["label"]
        elif "select" in p:
            choices = p["select"].get("choice", [])
            labels[p["id"]] = " | ".join(choices)
    return labels


INSERT_RE = re.compile(r"\{\{\s*insert:\s*param,\s*([\w.-]+)\s*\}\}")
MD_LINK_RE = re.compile(r"\[([^\]]+)\]\(#[\w.-]+\)")


def resolve_prose(prose, labels):
    if not prose:
        return ""

    def repl(m):
        pid = m.group(1)
        label = labels.get(pid, pid)
        return f"[{label}]"

    prose = INSERT_RE.sub(repl, prose)
    prose = MD_LINK_RE.sub(r"\1", prose)
    return prose


def flatten_statement(part, labels, depth=0):
    lines = []
    label = next((p["value"] for p in part.get("props", []) if p.get("name") == "label"), None)
    prose = resolve_prose(part.get("prose"), labels)
    if prose:
        indent = "  " * depth
        prefix = f"{label} " if label else ""
        lines.append(f"{indent}{prefix}{prose}")
    for child in part.get("parts", []):
        if child.get("name") == "item":
            lines.extend(flatten_statement(child, labels, depth + 1 if label else depth))
    return lines


def find_part(parts, name):
    return next((p for p in parts if p.get("name") == name), None)


def build_control(node, family_id, family_title, parent_number=None, parent_id=None):
    withdrawn = is_withdrawn(node)
    labels = param_labels(node)
    parts = node.get("parts", [])

    statement_lines = []
    stmt = find_part(parts, "statement")
    if stmt:
        statement_lines = flatten_statement(stmt, labels)

    guidance_part = find_part(parts, "guidance")
    guidance = resolve_prose(guidance_part.get("prose"), labels) if guidance_part else ""

    raw_id = node["id"]  # e.g. "ac-1" or "ac-2.1"
    if "." in raw_id:
        base, enh = raw_id.split(".", 1)
        number = f"{base.upper()}({enh})"
    else:
        number = raw_id.upper()

    incorporated_into = []
    if withdrawn:
        for link in node.get("links", []):
            if link.get("rel") == "incorporated-into":
                incorporated_into.append(link.get("href", "").lstrip("#").upper())

    record = {
        "id": raw_id,
        "number": number,
        "family": family_id.upper(),
        "family_title": family_title,
        "title": node.get("title", ""),
        "is_enhancement": parent_id is not None,
        "parent_id": parent_id,
        "withdrawn": withdrawn,
        "incorporated_into": incorporated_into,
        "statement": "\n".join(statement_lines),
        "guidance": guidance.strip(),
    }

    out = [record]
    for child in node.get("controls", []):
        out.extend(build_control(child, family_id, family_title, number, raw_id))
    return out


def main():
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(1)

    src_path, out_dir = sys.argv[1], sys.argv[2]
    with open(src_path) as f:
        data = json.load(f)

    catalog = data["catalog"]
    controls_by_family = {}
    families = []
    for group in catalog["groups"]:
        family_id = group["id"]
        family_title = group["title"]
        families.append({"id": family_id.upper(), "title": family_title})
        family_controls = []
        for control in group.get("controls", []):
            family_controls.extend(build_control(control, family_id, family_title))
        controls_by_family[family_id.upper()] = family_controls

    total = sum(len(v) for v in controls_by_family.values())
    active = sum(1 for v in controls_by_family.values() for c in v if not c["withdrawn"])
    print(f"Parsed {total} total control records, {active} active (non-withdrawn).")

    os.makedirs(out_dir, exist_ok=True)
    meta = {"source": "NIST SP 800-53 Rev. 5, OSCAL catalog (usnistgov/oscal-content)", "families": families}
    with open(os.path.join(out_dir, "_meta.json"), "w") as f:
        json.dump(meta, f, separators=(",", ":"))

    for family_id, family_controls in controls_by_family.items():
        with open(os.path.join(out_dir, f"{family_id}.json"), "w") as f:
            json.dump(family_controls, f, separators=(",", ":"))

    print(f"Wrote {len(controls_by_family)} family files + _meta.json to {out_dir}")


if __name__ == "__main__":
    main()
