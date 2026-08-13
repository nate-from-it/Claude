"""
Generates ATO/A&A documentation narratives for the ISSO audience: an SSP
implementation statement when a control is fully met, or a POA&M-style
gap/compensating-control narrative when it isn't.

Like the rest of the app's guidance, this is template-driven from the
existing tailoring knowledge base - not an LLM call - so it's
deterministic and free to run. It's meant as a structured first draft for
the ISSO to review, fill in the org-specific blanks, and finalize, not a
final artifact.
"""
import datetime

from tailoring import TECHNOLOGIES, tailor_control

# One-sentence, family-level starting point for "what compensating
# controls typically apply here" when a control isn't fully met. Not
# exhaustive or authoritative - the narrative explicitly frames it as a
# suggestion the ISSO confirms or replaces with what's actually in place.
COMPENSATING_CONTROL_SUGGESTIONS = {
    "AC": "temporary manual approval/review of access requests, tightened network segmentation limiting reachability of the affected system, and more frequent access recertification",
    "AT": "supplemental ad hoc briefings or reminders to affected personnel and increased supervisory oversight until formal training is current",
    "AU": "increased manual log review frequency and temporary alerting rules covering the gap until automated logging/retention is fully in place",
    "CA": "an interim risk acceptance memo and more frequent manual status checks until the formal assessment/authorization activity is complete",
    "CM": "manual change-approval review and periodic manual configuration audits until automated baseline enforcement is in place",
    "CP": "documented manual failover/recovery procedures and more frequent tabletop exercises until the automated capability is implemented",
    "IA": "additional manual identity verification steps and closer monitoring of the affected accounts until strong authentication is enforced",
    "IR": "designated on-call manual escalation procedures and closer monitoring until the automated detection/response capability is operational",
    "MA": "supervised/escorted maintenance sessions and manual logging of maintenance activity until automated controls are in place",
    "MP": "manual media handling/tracking procedures and restricted physical access until automated controls are implemented",
    "PE": "additional manual physical access logging or guard/escort procedures until the automated physical control is in place",
    "PL": "an interim documented plan or memo covering the gap until the formal planning artifact is finalized",
    "PM": "interim manual tracking by the program office until the formal program-level control is fully established",
    "PS": "manual supervisory review of affected personnel actions until the automated personnel security control is in place",
    "PT": "manual review of the affected processing activity and restricted access to the data until automated privacy controls are implemented",
    "RA": "an interim manual risk assessment and closer monitoring until the formal, tool-supported risk assessment is complete",
    "SA": "manual contract/acquisition review checkpoints until the automated acquisition control is enforced",
    "SC": "compensating network-layer restrictions (e.g. additional segmentation or filtering) until the system/communications control is fully implemented",
    "SI": "increased manual monitoring/scanning frequency until the automated integrity control is in place",
    "SR": "manual supplier/vendor review checkpoints and heightened scrutiny of the affected supply chain element until the formal control is implemented",
}

STIG_EVIDENCE_CITATION_LIMIT = 10


def _tech_scope_phrase(tech_names):
    if not tech_names:
        return "the in-scope environment"
    if len(tech_names) == 1:
        return tech_names[0]
    return ", ".join(tech_names[:-1]) + " and " + tech_names[-1]


def _trim(text, limit=300):
    text = (text or "").strip().replace("\n", " ")
    return text if len(text) <= limit else text[: limit - 3] + "..."


def generate_narrative(control, technologies, status, stig_rule_ids_by_tech=None):
    """
    control: flat control dict (id/number/title/family/statement)
    technologies: list of technology keys, already validated/filtered
    status: "met" or "not_met"
    stig_rule_ids_by_tech: optional {technology: [rule_id, ...]} cited as
        configuration evidence for "met" narratives when available
    """
    stig_rule_ids_by_tech = stig_rule_ids_by_tech or {}
    today = datetime.date.today().isoformat()
    tailored = tailor_control(control, technologies, "isso")
    scope = _tech_scope_phrase([TECHNOLOGIES.get(t, t) for t in technologies])
    number, title = control.get("number", ""), control.get("title", "")

    lines = [f"{number} — {title}"]

    if status == "met":
        lines += [
            "Status: Implemented",
            f"Environment: {scope}",
            f"Reviewed: {today}",
            "",
            "Implementation summary:",
            tailored["intro"],
            "",
            "Technical implementation:",
        ]
        for item in tailored["items"]:
            lines.append(f"- {item['technology_name']}: {item['guidance']}")
            rule_ids = stig_rule_ids_by_tech.get(item["technology"]) or []
            if rule_ids:
                shown = ", ".join(rule_ids[:STIG_EVIDENCE_CITATION_LIMIT])
                extra = (
                    f" (+{len(rule_ids) - STIG_EVIDENCE_CITATION_LIMIT} more)"
                    if len(rule_ids) > STIG_EVIDENCE_CITATION_LIMIT
                    else ""
                )
                lines.append(f"  Configuration evidence: DISA STIG rules {shown}{extra}.")
        statement = _trim(control.get("statement"))
        if statement:
            lines += ["", f'This satisfies the control requirement: "{statement}"']
    else:
        suggestion = COMPENSATING_CONTROL_SUGGESTIONS.get(
            control.get("family"),
            "compensating procedural or technical controls appropriate to this control family",
        )
        lines += [
            "Status: Partially Implemented / Planned",
            f"Environment: {scope}",
            f"Reviewed: {today}",
            "",
            "Implementation gap:",
            f"{number} is not fully implemented for {scope}. "
            "[ISSO: describe the specific requirement(s) not yet met].",
            "",
            "Compensating/mitigating controls:",
            f"Controls typically applicable to this family include {suggestion}. "
            "[ISSO: confirm which are actually in place, or describe the actual compensating controls used].",
            "",
            "Planned remediation and target completion date:",
            "[ISSO: describe the remediation plan and target date].",
            "",
            "Residual risk determination:",
            "[ISSO: Low/Moderate/High], accepted by [Authorizing Official] pending remediation.",
        ]

    return "\n".join(lines)
