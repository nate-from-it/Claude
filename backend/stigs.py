"""
DISA STIG lookup, keyed off the same NIST 800-53 controls the rest of the
app tailors guidance for. See scripts/build_stigs.py for how the data in
data/stigs/*.json was generated and why.

Coverage is intentionally partial: only technologies with a real,
traceable path from STIG rule to NIST 800-53 control are included.
- linux (RHEL 9), windows (Server 2022): the source STIG tags each rule
  with its NIST 800-53 control directly.
- network (Cisco IOS switches), kubernetes: the source STIG only tags CCI
  numbers; those are bridged to NIST 800-53 via MITRE Vulcan's DISA CCI
  crosswalk table.
- aws/azure/gcp/identity/database: no STIG crosswalk available. DISA
  doesn't publish cloud-platform STIGs the way it does for OS/network
  baselines, and the one available database STIG source (PostgreSQL 9.x)
  has no CCI or NIST tagging at all to bridge from.

Every mapped NIST control ID here is Rev 4 (that's what DISA's STIGs and
CCI list are tagged with). Base control numbers are almost always
unchanged between Rev 4 and Rev 5, so this app uses them directly against
its Rev 5 catalog - callers should surface that as a caveat, not a fact.
"""
import json
import os
import re

DATA_DIR = os.path.join(os.path.dirname(__file__), "data", "stigs")

ENHANCEMENT_SUFFIX_RE = re.compile(r"\(\d+\)$")


def base_control_number(number):
    """'AC-17(2)' -> 'AC-17'. Already-base numbers pass through unchanged."""
    return ENHANCEMENT_SUFFIX_RE.sub("", number)


def load_stigs():
    with open(os.path.join(DATA_DIR, "_meta.json")) as f:
        meta = json.load(f)

    rules_by_tech = {}
    for tech in meta:
        with open(os.path.join(DATA_DIR, f"{tech}.json")) as f:
            rules_by_tech[tech] = json.load(f)

    return meta, rules_by_tech


STIG_META, STIG_RULES = load_stigs()


def stig_technologies():
    """Technologies that have STIG coverage at all."""
    return list(STIG_META.keys())


def rules_for_control(control_number, technology):
    """STIG rules for `technology` whose NIST crosswalk includes this
    control's base number. Returns [] for a technology with no STIG data."""
    rules = STIG_RULES.get(technology)
    if not rules:
        return []
    base = base_control_number(control_number)
    return [r for r in rules if base in r["nist_controls"]]
