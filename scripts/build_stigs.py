#!/usr/bin/env python3
"""
Builds backend/data/stigs/<technology>.json from DISA STIG source repos
(ansible-lockdown org) plus MITRE Vulcan's DISA CCI -> NIST 800-53 Rev 4
crosswalk table, for the app's NIST / STIG toggle.

Two crosswalk strategies, depending on what the source repo tags rules with:

  "direct" - the STIG source repo tags each rule with its NIST 800-53
             control directly (RHEL, Windows). Used as-is.
  "cci"    - the STIG source repo only tags CCI numbers (Cisco IOS L2S,
             Kubernetes). Each CCI is looked up in the Vulcan crosswalk
             table to find its NIST 800-53 Rev 4 control.

Either way the resulting NIST control IDs are Rev 4 IDs. Base control
numbers (e.g. AC-17, CM-6) are almost always unchanged between Rev 4 and
Rev 5, so the app uses them directly against its Rev 5 catalog with a
visible caveat in the UI - see backend/stigs.py.

Sources (not vendored here; clone fresh to regenerate):
  https://github.com/ansible-lockdown/RHEL9-STIG           (linux)
  https://github.com/ansible-lockdown/Windows-2022-STIG    (windows)
  https://github.com/ansible-lockdown/CISCO-IOS-L2S-STIG   (network - switches)
  https://github.com/ansible-lockdown/KUBERNETES-STIG      (kubernetes)
  https://github.com/mitre/vulcan  ->  app/lib/cci_map/constants.rb
                                        (CCI -> NIST 800-53 Rev 4 table)

Usage:
    python3 build_stigs.py <clone_root> <vulcan_clone_dir> <out_dir>

Where <clone_root> contains the four STIG repos as subdirectories named
exactly: RHEL9-STIG, Windows-2022-STIG, CISCO-IOS-L2S-STIG, KUBERNETES-STIG
(case-insensitive directory match is attempted as a convenience).
"""
import json
import os
import re
import sys

CCI_RE = re.compile(r"CCI-\d+")
SEVERITY_WORD_TO_CAT = {"HIGH": "CAT I", "MEDIUM": "CAT II", "LOW": "CAT III"}
NIST_DIRECT_RE = re.compile(r"NIST800-53R?4?[-_]([A-Z]{2})-?(\d+)")
CCI_LINE_RE = re.compile(r"'(CCI-\d+)':\s*'([^']*)'")
CONTROL_PREFIX_RE = re.compile(r"^([A-Z]{2}-\d+)")

# Ansible task files that are setup/audit plumbing, not STIG rule definitions.
SKIP_FILENAMES = {
    "main.yml", "prelim.yml", "warning_facts.yml", "audit_only.yml",
    "pre_remediation_audit.yml", "post_remediation_audit.yml",
    "fetch_audit_output.yml", "le_audit_setup.yml", "parse_etc_passwd.yml",
    "auditd.yml",
}

# Matches a top-level (column-0) Ansible task name line, e.g.:
#   - name: "HIGH | RHEL-09-215100 | PATCH | RHEL 9 must have ..."
#   - name: HIGH | WN22-AC-000020 | PATCH | Windows Server 2022 must ...
TASK_SPLIT_RE = re.compile(r'^- name:\s*[|>]?\s*"?(HIGH|MEDIUM|LOW)\s*\|\s*([A-Z0-9-]+)\s*\|\s*(.*?)"?\s*$', re.MULTILINE)

TYPE_MARKERS = {"PATCH", "AUDIT", "WARN", "MANUAL", "REVIEW"}


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


def clean_title(raw_title):
    title = raw_title.strip().strip('"').strip()
    tokens = title.split(" | ", 1)
    if len(tokens) == 2 and tokens[0].strip().upper() in TYPE_MARKERS:
        title = tokens[1].strip()
    return title.rstrip(".") + "."


def extract_tags_block(chunk):
    m = re.search(r"\n(\s*)tags:\s*\n((?:\1\s+- .*\n?)+)", chunk)
    if not m:
        return []
    indent_block = m.group(2)
    return [line.strip().lstrip("- ").strip() for line in indent_block.splitlines() if line.strip().startswith("-")]


def parse_stig_dir(tasks_dir):
    """Returns a list of {id, severity, title, cci: [...], nist_direct: [...]}."""
    rules = {}
    for root, _dirs, files in os.walk(tasks_dir):
        for fname in files:
            if not fname.endswith(".yml") or fname.lower() in SKIP_FILENAMES:
                continue
            path = os.path.join(root, fname)
            with open(path, errors="replace") as f:
                text = f.read()

            matches = list(TASK_SPLIT_RE.finditer(text))
            for i, m in enumerate(matches):
                severity_word, rule_id, raw_title = m.group(1), m.group(2), m.group(3)
                start = m.start()
                end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
                chunk = text[start:end]

                tags = extract_tags_block(chunk)
                cci = sorted(set(CCI_RE.findall(" ".join(tags))))
                nist_direct = sorted({
                    f"{fm.group(1)}-{fm.group(2)}" for fm in (NIST_DIRECT_RE.match(t) for t in tags) if fm
                })

                if rule_id not in rules:
                    rules[rule_id] = {
                        "id": rule_id,
                        "severity": SEVERITY_WORD_TO_CAT.get(severity_word, severity_word),
                        "title": clean_title(raw_title),
                        "cci": cci,
                        "nist_direct": nist_direct,
                    }
                else:
                    # Merge additional CCI/NIST tags seen on repeated sub-task mentions.
                    rules[rule_id]["cci"] = sorted(set(rules[rule_id]["cci"]) | set(cci))
                    rules[rule_id]["nist_direct"] = sorted(set(rules[rule_id]["nist_direct"]) | set(nist_direct))
    return list(rules.values())


def resolve_nist_controls(rule, crosswalk_type, cci_to_nist):
    if crosswalk_type == "direct":
        return rule["nist_direct"]
    controls = set()
    for cci in rule["cci"]:
        control = cci_to_nist.get(cci)
        if control:
            controls.add(control)
    return sorted(controls)


SOURCES = [
    {
        "technology": "linux",
        "dirname_candidates": ["RHEL9-STIG", "rhel9-stig"],
        "crosswalk_type": "direct",
        "title": "DISA Red Hat Enterprise Linux 9 STIG",
        "source_url": "https://github.com/ansible-lockdown/RHEL9-STIG",
    },
    {
        "technology": "windows",
        "dirname_candidates": ["Windows-2022-STIG", "windows-2022-stig"],
        "crosswalk_type": "direct",
        "title": "DISA Windows Server 2022 STIG",
        "source_url": "https://github.com/ansible-lockdown/Windows-2022-STIG",
    },
    {
        "technology": "network",
        "dirname_candidates": ["CISCO-IOS-L2S-STIG", "cisco-ios-l2s-stig"],
        "crosswalk_type": "cci",
        "title": "DISA Cisco IOS Switch (L2S) STIG",
        "source_url": "https://github.com/ansible-lockdown/CISCO-IOS-L2S-STIG",
    },
    {
        "technology": "kubernetes",
        "dirname_candidates": ["KUBERNETES-STIG", "kubernetes-stig"],
        "crosswalk_type": "cci",
        "title": "DISA Kubernetes STIG",
        "source_url": "https://github.com/ansible-lockdown/KUBERNETES-STIG",
    },
]


def find_dir(clone_root, candidates):
    for name in candidates:
        path = os.path.join(clone_root, name)
        if os.path.isdir(path):
            return path
    return None


def main():
    if len(sys.argv) != 4:
        print(__doc__)
        sys.exit(1)

    clone_root, vulcan_dir, out_dir = sys.argv[1], sys.argv[2], sys.argv[3]
    os.makedirs(out_dir, exist_ok=True)

    constants_path = os.path.join(vulcan_dir, "app", "lib", "cci_map", "constants.rb")
    cci_to_nist = parse_cci_to_nist(constants_path)
    print(f"Parsed {len(cci_to_nist)} CCI -> NIST 800-53 Rev 4 mappings from Vulcan.")

    meta = {}
    for src in SOURCES:
        tasks_dir_root = find_dir(clone_root, src["dirname_candidates"])
        if not tasks_dir_root:
            print(f"WARNING: could not find clone for {src['technology']} ({src['dirname_candidates']}), skipping")
            continue
        tasks_dir = os.path.join(tasks_dir_root, "tasks")

        raw_rules = parse_stig_dir(tasks_dir)
        out_rules = []
        for rule in raw_rules:
            nist_controls = resolve_nist_controls(rule, src["crosswalk_type"], cci_to_nist)
            out_rules.append({
                "id": rule["id"],
                "severity": rule["severity"],
                "title": rule["title"],
                "cci": rule["cci"],
                "nist_controls": nist_controls,
            })
        out_rules.sort(key=lambda r: r["id"])

        mapped = sum(1 for r in out_rules if r["nist_controls"])
        print(f"{src['technology']}: {len(out_rules)} rules parsed, {mapped} with a resolved NIST 800-53 control")

        with open(os.path.join(out_dir, f"{src['technology']}.json"), "w") as f:
            json.dump(out_rules, f, separators=(",", ":"))

        meta[src["technology"]] = {
            "title": src["title"],
            "source_url": src["source_url"],
            "crosswalk_type": src["crosswalk_type"],
            "rule_count": len(out_rules),
        }

    with open(os.path.join(out_dir, "_meta.json"), "w") as f:
        json.dump(meta, f, separators=(",", ":"))
    print(f"Wrote {out_dir}")


if __name__ == "__main__":
    main()
