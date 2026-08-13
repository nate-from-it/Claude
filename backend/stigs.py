"""
DISA STIG lookup, keyed off the same NIST 800-53 controls the rest of the
app tailors guidance for. See scripts/build_stigs.py for how the data in
data/stigs/*.json was generated and why.

Coverage is intentionally partial: only technologies with a real,
traceable path from STIG rule to NIST 800-53 control are included -
linux, windows, network, kubernetes, database, virtualization, email.
Every rule here comes straight from a real DISA STIG/SRG zip (not a
third-party automation repo); every rule tags CCI numbers, which are
bridged to NIST 800-53 via MITRE Vulcan's DISA CCI crosswalk table.
aws/azure/gcp/identity have no STIG crosswalk available - DISA doesn't
publish STIGs for those the way it does for OS/network/database
baselines.

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


SEVERITY_ORDER = {"CAT I": 0, "CAT II": 1, "CAT III": 2}
SEARCH_RESULT_LIMIT = 150


def search_rules(query, technologies=None):
    """Keyword search over rule id/title/CCI across the given technologies
    (or all STIG-covered technologies if omitted). Matches are plain
    case-insensitive substring checks, sorted by severity then id, and
    capped at SEARCH_RESULT_LIMIT - callers get back the true match count
    plus whether the list was truncated."""
    query = query.strip().lower()
    if not query:
        return 0, False, []

    techs = [t for t in (technologies or STIG_RULES) if t in STIG_RULES]

    matches = []
    for tech in techs:
        for rule in STIG_RULES[tech]:
            haystack = f"{rule['id']} {rule['title']} {' '.join(rule['cci'])}".lower()
            if query in haystack:
                matches.append({**rule, "technology": tech})

    matches.sort(key=lambda r: (SEVERITY_ORDER.get(r["severity"], 9), r["id"]))
    total = len(matches)
    return total, total > SEARCH_RESULT_LIMIT, matches[:SEARCH_RESULT_LIMIT]
