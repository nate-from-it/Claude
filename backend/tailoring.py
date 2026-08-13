"""
Rule-based tailoring engine.

Translates a NIST 800-53 rev5 control into role-specific, technology-specific
implementation guidance. This is deliberately NOT an LLM call: guidance is
built from a curated knowledge base (FAMILY_TECH_GUIDANCE, AUDIENCE_NARRATIVE)
so output is deterministic, reviewable, and free to run.

Three things combine for each (control, technologies, audience):
  1. AUDIENCE_NARRATIVE[family][audience] - how to interpret this control
     family in this role, and what you specifically need to do to meet it.
  2. TECH_AUDIENCE[tech]                  - which role(s) a technology is
     even relevant to. ISSO always sees every technology; Sysadmin and
     Net Admin each see only their own slice.
  3. FAMILY_TECH_GUIDANCE[family][tech]   - the concrete technical how-to.
     For AWS/Azure/GCP, this is itself split into a "sysadmin" (compute)
     and "netadmin" (network) variant, since cloud platforms span both
     domains; ISSO gets both, labeled.

If a (family, tech) pair has no authored guidance, a generic fallback is
generated from the control's own statement text so the app never dead-ends.
"""

TECHNOLOGIES = {
    "aws": "Amazon Web Services (AWS)",
    "azure": "Microsoft Azure",
    "gcp": "Google Cloud Platform (GCP)",
    "linux": "Linux / Unix Servers",
    "windows": "Windows Server / Active Directory",
    "network": "Network Devices (Firewalls, Routers, Switches)",
    "kubernetes": "Kubernetes / Containers",
    "database": "Databases (RDBMS)",
    "identity": "Identity Provider / SSO / MFA",
    "virtualization": "Virtualization (Hypervisors)",
    "email": "Email / Messaging Servers",
}

AUDIENCES = {
    "sysadmin": "System Administrator",
    "netadmin": "Network Administrator",
    "isso": "ISSO",
}

# Which role(s) each technology is shown to. ISSO is not listed here because
# ISSO always sees every technology, regardless of this map — see
# technologies_for_audience().
TECH_AUDIENCE = {
    "aws": {"sysadmin", "netadmin"},
    "azure": {"sysadmin", "netadmin"},
    "gcp": {"sysadmin", "netadmin"},
    "linux": {"sysadmin"},
    "windows": {"sysadmin"},
    "kubernetes": {"sysadmin"},
    "database": {"sysadmin"},
    "identity": {"sysadmin", "netadmin"},
    "network": {"netadmin"},
    "virtualization": {"sysadmin"},
    "email": {"sysadmin"},
}


def technologies_for_audience(audience):
    """Ordered list of technology keys visible to a given audience."""
    if audience == "isso":
        return list(TECHNOLOGIES.keys())
    return [t for t in TECHNOLOGIES if audience in TECH_AUDIENCE.get(t, set())]


# ---------------------------------------------------------------------------
# Layer 1: full per-role narrative, per family - how to interpret the
# control family in this role, and what to actually do to meet it.
# ---------------------------------------------------------------------------
AUDIENCE_NARRATIVE = {
    "AC": {
        "sysadmin": "Access Control means enforcing least privilege and accountability for every account on the systems you run. To meet this control, provision accounts only after approval, assign the minimum privileges needed for the job, review account lists on a set schedule, and disable or remove accounts immediately when access is no longer needed.",
        "netadmin": "For you, Access Control is about making sure the network itself only lets authorized traffic and authorized administrators through. To meet this control, segment the network so access follows least privilege, restrict administrative access to network gear to named individuals, and log every change to access rules so you can show who could reach what and when.",
        "isso": "Access Control requires the organization to have a documented policy for who gets access and why, and evidence that it's actually followed. Your job is to maintain that policy, run periodic access reviews with system and network owners, confirm privileged accounts are justified, and keep the evidence trail (approvals, review records) that an assessor will ask for.",
    },
    "AT": {
        "sysadmin": "This control requires that people with elevated technical responsibilities actually know how to do their job securely, not just have a policy that says they should. You need to complete and keep records of role-based training on the secure configuration and incident-reporting procedures relevant to the systems you administer, and repeat it on the required cycle.",
        "netadmin": "Awareness and Training means network staff are trained specifically on the tools and escalation paths they'll use during a real incident. You need to complete training on your monitoring/firewall tooling and the incident escalation process, and keep training records current for anyone with network security responsibilities.",
        "isso": "This control is about proving the whole security and privacy training program actually runs: general awareness for everyone, role-based training for technical staff, and records to show both happened on schedule. You own designing the training curriculum, tracking completion organization-wide, and producing training records as audit evidence.",
    },
    "AU": {
        "sysadmin": "Audit and Accountability means every security-relevant action on your systems needs to be logged, protected from tampering, and kept long enough to be useful during an investigation. You need to turn on the right logging (auth events, privilege changes, process execution), make sure logs ship to a protected central location, and set retention to match policy.",
        "netadmin": "For the network layer, this control means you can reconstruct what happened on the wire: who connected, when, and through which device. You need to enable logging on firewalls/routers/switches, keep clocks synchronized so logs correlate correctly, and forward logs to the central collector instead of only storing them locally on the device.",
        "isso": "This control requires a defined audit strategy — what gets logged, why, for how long, and who reviews it — not just logs existing somewhere. You own writing that strategy, confirming log coverage matches it, and reviewing/reporting on audit findings on the required cadence.",
    },
    "CA": {
        "sysadmin": "This control is the formal process of proving your systems meet their security requirements, so you need to be ready to produce evidence, not just implement controls silently. When an assessment happens, provide configuration evidence for your systems and fix findings assigned to you within the agreed timeline.",
        "netadmin": "For you, this control means the network architecture and boundary controls need to be assessable — documented and demonstrable, not just working. Keep network diagrams current, be ready to walk an assessor through boundary protections, and remediate network findings on schedule.",
        "isso": "You own this control end to end: building the assessment plan, coordinating the actual assessment, tracking findings in the POA&M, and maintaining the authorization package that lets the system operate. This is the control that turns everyone else's work into a defensible authorization decision.",
    },
    "CM": {
        "sysadmin": "Configuration Management means every system you run starts from a known-good, hardened baseline and any change to it goes through a controlled process. You need to build and maintain that baseline, route changes through change control instead of ad hoc edits, and be able to show what changed, when, and who approved it.",
        "netadmin": "This control requires network device configurations to be version-controlled and changed deliberately, not edited live without a record. You need to keep a baseline config for each device class, back up configs before and after changes, and route changes through the same approval process as everything else.",
        "isso": "You need the configuration management plan itself, plus the records that prove baselines exist and changes were controlled. Maintain that plan, audit that change records match what actually happened on systems and network devices, and flag drift as a finding.",
    },
    "CP": {
        "sysadmin": "Contingency Planning means your systems can actually be recovered within the time the business needs, not just that backups exist somewhere. You need working, tested backup/restore procedures with a real RTO/RPO, and you need to have actually run a restore recently enough to trust it.",
        "netadmin": "For the network, this control means connectivity itself survives a failure — redundant paths, redundant devices, and a way to rebuild device configs quickly. You need failover tested, not just designed, and current config backups for every managed device.",
        "isso": "You own the contingency plan document, the test schedule, and the after-action reports from each test. Your job is making sure contingency plans exist for every system in scope, get tested on schedule, and that lessons learned actually get fed back into the plan.",
    },
    "IA": {
        "sysadmin": "This control means every account and process on your systems is uniquely identifiable and provably who it claims to be — no shared logins, no unverified access. You need unique accounts per user/service, strong authentication (ideally MFA) especially for privileged access, and disabled default/vendor credentials.",
        "netadmin": "For network infrastructure, this control means administrative access to devices is individually attributable and strongly authenticated, typically via a centralized AAA service. You need named admin accounts (not shared 'admin'), MFA on device management access, and default credentials disabled everywhere.",
        "isso": "You own the identification and authentication policy and the evidence that MFA and unique-identity requirements are actually enforced across systems, network devices, and privileged accounts. Track coverage gaps and drive them to closure.",
    },
    "IR": {
        "sysadmin": "Incident Response means you can detect, contain, and clean up an incident on your systems using a tested playbook, not improvise in the moment. You need working detection tooling, a tested isolation/containment procedure, and to actually follow your organization's reporting timeline when something happens.",
        "netadmin": "For you, this control means you can isolate a compromised segment fast and preserve evidence while doing it. You need pre-approved containment actions (segment isolation, ACL blocks) ready to execute, and packet-capture/forensic procedures that don't destroy evidence.",
        "isso": "You own the incident response plan, the reporting timelines to leadership and outside bodies, and the after-action process that turns each incident into a lessons-learned update. Make sure the plan is realistic and current, not just a document.",
    },
    "MA": {
        "sysadmin": "Maintenance means controlling who can touch your systems for upkeep and making sure maintenance tools/media aren't a backdoor. You need to restrict and log maintenance sessions, and vet/sanitize any tools or media used for maintenance before and after use.",
        "netadmin": "For network devices, this control means remote and local maintenance access is restricted, logged, and time-bound. You need session logging for console/remote maintenance and change tickets for vendor maintenance windows.",
        "isso": "You own the maintenance policy and the records of who's approved to perform maintenance, with what tools, on what systems. Confirm those records match what's actually happening in practice.",
    },
    "MP": {
        "sysadmin": "Media Protection means anything holding data at rest — disks, backups, removable media — is encrypted, controlled, and properly destroyed when retired. You need encryption at rest enabled by default and a real sanitization step (not just deletion) before reuse or disposal.",
        "netadmin": "For you, this control extends to device-level media: config backups, firmware images, anything that could leak network design if it walked out the door. Sanitize device storage before disposal or RMA, same as any other media.",
        "isso": "You own the media protection policy and the sanitization/destruction records that prove media was handled correctly at end of life. That paper trail is what an assessor will ask for.",
    },
    "PE": {
        "sysadmin": "For cloud-hosted systems this is largely inherited from the provider, but for anything on-prem, you're responsible for confirming physical access to the server room is controlled and environmental protections (power, cooling, fire suppression) are in place. Document the shared-responsibility boundary clearly in the SSP so it's obvious what you own versus the provider.",
        "netadmin": "This control means network closets and racks need their own access control, separate from general server room access, with entry logged. Confirm cabling and device access is physically restricted, not just the server room door.",
        "isso": "You own documenting the physical/environmental protection policy and collecting facility access records as evidence, including confirming what's inherited from a cloud provider versus what your organization is directly responsible for.",
    },
    "PL": {
        "sysadmin": "This control requires an accurate, current System Security Plan, and you're the source of truth for the system-level facts in it — architecture, data flows, what's actually running. Keep your part of the SSP accurate as things change; don't let it go stale.",
        "netadmin": "Your contribution here is the network topology and boundary information that defines the system's authorization boundary. Keep diagrams and boundary descriptions current so the SSP reflects the actual network, not last year's design.",
        "isso": "You own authoring, maintaining, and getting approval for the security and privacy plans. This is the document everything else in the authorization package hangs off of, so it needs to stay synchronized with reality.",
    },
    "PM": {
        "sysadmin": "This is an organization-level control, but your role is making sure the systems you manage are accurately represented in the org-wide inventory and risk picture. Keep your asset/system inventory data current and feed it up when asked.",
        "netadmin": "Your contribution is accurate network asset and topology data flowing into the organization's risk management program. Keep device inventory current rather than letting it drift from reality.",
        "isso": "You own program-level artifacts — risk management strategy, system inventories, security architecture — that report up to the CISO/AO. This control is about the organization having its house in order at the program level, above any single system.",
    },
    "PS": {
        "sysadmin": "This control means account lifecycle follows personnel status in near-real time — no lingering access after someone leaves or changes roles. You need to act immediately on termination/transfer notices for the systems you manage, not on a delayed batch cycle.",
        "netadmin": "Same principle for network and VPN access: device credentials and remote access tied to a departing employee need to be revoked immediately, not left active. Treat termination notices as immediate action items.",
        "isso": "You own the personnel security policy, screening records, and the termination/transfer checklist that other roles execute against. Your job is making sure that checklist is actually followed, with evidence, every time.",
    },
    "PT": {
        "sysadmin": "If your systems handle PII, this control means configuration needs to match an approved authority to collect/process that data — retention settings, consent flags, access restrictions — not just general security best practice. Confirm your systems are configured to the specific PII handling requirements documented for them.",
        "netadmin": "Your responsibility is making sure PII in transit stays on approved, monitored paths and isn't inadvertently exposed on unencrypted or unmonitored links. Validate data-flow mappings against what's actually happening on the network.",
        "isso": "You own the PII processing policy, the data mapping, and the documentation of authority to collect. This control exists to make sure PII isn't processed anywhere the organization hasn't explicitly authorized and disclosed.",
    },
    "RA": {
        "sysadmin": "Risk Assessment means vulnerabilities found by scanning actually get fixed on your systems within the agreed SLA, not just logged and forgotten. You need to patch and remediate findings assigned to you and keep evidence of closure.",
        "netadmin": "For network devices, this control means scans actually cover your infrastructure (management interfaces, firmware) and findings get remediated on the same SLA as everything else. Validate scan coverage includes network segments, not just servers.",
        "isso": "You own the risk assessment process itself — the risk register, the scan reporting cadence, and making sure findings translate into tracked remediation, not just a report nobody acts on.",
    },
    "SA": {
        "sysadmin": "This control means security requirements get baked into systems before they're deployed, not bolted on afterward. Apply hardening/configuration requirements as part of your standard deployment process for any acquired or developed system.",
        "netadmin": "Same principle for network equipment and services: validate security requirements are met before a device or circuit goes into production, not after. Require sign-off before new network infrastructure is provisioned.",
        "isso": "You own making sure security requirements are written into acquisition documents and SDLC gates in the first place, and that supplier assessments happen before, not after, a purchase. This control fails quietly if it's skipped early in the process.",
    },
    "SC": {
        "sysadmin": "This control means the systems you run protect data at rest and in transit and are properly isolated from things they shouldn't be able to reach. You need encryption enabled, TLS enforced on services, and host-level isolation (firewalls, containers/namespaces) configured correctly.",
        "netadmin": "This is core network-admin territory: the perimeter, segmentation, encrypted transit, and DoS protections are yours to own. You need firewalls and segmentation actively enforced, not just configured once and forgotten, and encrypted links for anything crossing a trust boundary.",
        "isso": "You own the system and communications protection policy and the evidence that boundary and encryption controls are actually in place across both the host and network layers. This control spans both roles, so your job includes making sure nothing falls in the gap between them.",
    },
    "SI": {
        "sysadmin": "This control means known flaws get patched and malware gets detected on your systems on a schedule you can defend, not reactively. You need automated patch management, host-based malware protection, and a process for acting on flaw reports.",
        "netadmin": "For the network layer, this means you're watching for anomalous traffic and have IDS/IPS actively deployed, not just installed. Keep device firmware patched on schedule and act on network-based intrusion signals.",
        "isso": "You own the flaw remediation and system monitoring policy, plus the evidence that patch and antivirus/EDR compliance is being tracked across the environment, not assumed.",
    },
    "SR": {
        "sysadmin": "This control means you verify the integrity of software and hardware before you install it — signed packages, trusted sources, known provenance — rather than trusting whatever shows up. Check signatures and use vetted repositories as standard practice.",
        "netadmin": "Same for network gear: firmware and hardware need to come through the vendor's authorized channel with verified signatures before you put them into production. Don't install unverified firmware, even under deadline pressure.",
        "isso": "You own the supply chain risk management plan and the supplier/component risk assessments that decide what's trusted in the first place. This control is about the organization's vendor decisions, which everyone else's verification steps depend on.",
    },
}

# ---------------------------------------------------------------------------
# Layer 2: concrete technology-specific guidance, per family.
#
# For "aws" / "azure" / "gcp", the value is usually a dict of
# {"sysadmin": "<compute-focused guidance>", "netadmin": "<network-focused
# guidance>"} since cloud platforms span both domains. Where the split
# wouldn't mean anything (e.g. PE, which is about physical data-center
# custody regardless of role), the value is a single string used for every
# audience instead.
# ---------------------------------------------------------------------------
FAMILY_TECH_GUIDANCE = {
    "AC": {
        "aws": {"sysadmin": "Use IAM users/roles/groups with least-privilege policies and permission boundaries; enforce with SCPs in AWS Organizations; review with IAM Access Analyzer and Access Advisor.", "netadmin": "Restrict the network paths that can reach management interfaces: put admin access behind Security Groups/NACLs limited to a bastion or Session Manager, and use VPC endpoint policies to keep traffic off the public internet."},
        "azure": {"sysadmin": "Use Azure AD (Entra ID) role-based access control (RBAC) and Privileged Identity Management (PIM) for just-in-time elevation; enforce with Conditional Access policies.", "netadmin": "Restrict management-plane access with NSGs and Azure Firewall rules, and require Azure Bastion or a jump host instead of exposing RDP/SSH directly."},
        "gcp": {"sysadmin": "Use Cloud IAM roles (prefer predefined/custom over primitive roles) and Organization Policy constraints; review with Policy Analyzer and IAM Recommender.", "netadmin": "Restrict management access with VPC firewall rules and Identity-Aware Proxy instead of exposing instances with public IPs."},
        "linux": "Enforce least privilege with sudoers rules, groups, and SELinux/AppArmor; disable unused accounts; use PAM for access restrictions.",
        "windows": "Use Active Directory security groups, Group Policy, and delegated OU permissions; restrict local Administrators group membership.",
        "network": "Use ACLs, VLAN segmentation, and 802.1X port-based access control to restrict which devices/users reach network segments.",
        "kubernetes": "Use Kubernetes RBAC (Roles/ClusterRoles), namespaces for isolation, and NetworkPolicies to restrict pod-to-pod access.",
        "database": "Use database roles/grants with least privilege, row-level security where supported, and separate application vs. admin accounts.",
        "identity": "Centralize authorization decisions in the IdP; use group/attribute-based access control (ABAC) and enforce via SAML/OIDC claims.",
    },
    "AT": {
        "aws": {"sysadmin": "Track completion of AWS-specific secure-usage training (IAM, S3 exposure risks) via your LMS; tie to onboarding/offboarding workflows.", "netadmin": "Track completion of AWS networking training (VPC design, Security Groups, Transit Gateway) for staff who manage your cloud network architecture."},
        "azure": {"sysadmin": "Track Azure-specific security training (RBAC, Conditional Access) completion tied to role assignment in Azure AD.", "netadmin": "Track completion of Azure networking training (VNets, NSGs, Azure Firewall) for staff who manage cloud network architecture."},
        "gcp": {"sysadmin": "Track GCP-specific security training (IAM, VPC-SC) completion tied to project access grants.", "netadmin": "Track completion of GCP networking training (VPC design, firewall rules, VPC-SC) for staff who manage cloud network architecture."},
        "linux": "Provide hands-on training on hardening baselines, patching, and log review for Linux administrators.",
        "windows": "Provide hands-on training on AD hardening, GPO management, and Windows event log review.",
        "network": "Provide hands-on training on firewall rule review, network monitoring tools, and incident escalation paths.",
        "kubernetes": "Provide training on container/image security, RBAC, and secrets management for platform engineers.",
        "database": "Provide training on secure database configuration, encryption, and privileged access monitoring for DBAs.",
        "identity": "Provide training on phishing-resistant MFA, credential hygiene, and social engineering for all users via the IdP-driven campaign tooling.",
    },
    "AU": {
        "aws": {"sysadmin": "Enable CloudTrail (multi-region, log-file validation) to capture API and console activity, and ship it to a centralized, access-controlled log archive account with retention locks.", "netadmin": "Enable VPC Flow Logs and load balancer/WAF access logs to capture network traffic patterns, and route them into the same centralized log pipeline as host logs."},
        "azure": {"sysadmin": "Enable Azure Monitor diagnostic settings and the Activity Log to capture resource and admin activity, shipped to a central Log Analytics workspace with immutable storage.", "netadmin": "Enable NSG flow logs and Azure Firewall logs to capture network traffic patterns, routed into the same central Log Analytics workspace."},
        "gcp": {"sysadmin": "Enable Cloud Audit Logs (Admin Activity, Data Access) to capture resource and admin activity, routed to a centralized, access-controlled log sink.", "netadmin": "Enable VPC Flow Logs and firewall rule logging to capture network traffic patterns, routed into the same centralized log sink."},
        "linux": "Configure auditd rules for security-relevant events; ship logs via rsyslog/journald to a central SIEM; protect log files with restrictive permissions.",
        "windows": "Enable Advanced Audit Policy and forward Security event logs (4624/4625/4720, etc.) to a central SIEM via WEF or an agent.",
        "network": "Enable syslog on firewalls/routers/switches with timestamps (NTP-synced) and forward to the central log collector.",
        "kubernetes": "Enable Kubernetes audit logging (audit-policy.yaml) and ship container stdout/stderr and API server audit logs to a central log store.",
        "database": "Enable native database audit logging (e.g., pgaudit, SQL Server Audit) for DDL/DML on sensitive tables; ship to a central log store.",
        "identity": "Enable IdP sign-in and audit logs (successful/failed auth, admin actions, MFA events) and forward to the SIEM.",
    },
    "CA": {
        "aws": {"sysadmin": "Use AWS Config conformance packs and Security Hub standards against your compute resources (EC2, IAM, S3) to continuously evidence control status for the ATO package.", "netadmin": "Use Security Hub's network reachability findings and Config rules for VPC/Security Group compliance to evidence that boundary controls match policy."},
        "azure": {"sysadmin": "Use Microsoft Defender for Cloud's regulatory compliance dashboard against compute and identity resources to evidence control status.", "netadmin": "Use Azure Policy and Defender for Cloud network findings against NSGs and Azure Firewall to evidence boundary controls match policy."},
        "gcp": {"sysadmin": "Use Security Command Center findings against compute and IAM resources, with Policy Intelligence, to evidence control status.", "netadmin": "Use Security Command Center's network findings and VPC Service Controls posture to evidence boundary controls match policy."},
        "linux": "Provide vulnerability scan and configuration baseline reports (e.g., OpenSCAP) as assessment evidence.",
        "windows": "Provide SCAP/Group Policy compliance reports as assessment evidence.",
        "network": "Provide network diagrams, firewall rule reviews, and boundary scan results as assessment evidence.",
        "kubernetes": "Provide cluster CIS Benchmark scan results and admission-controller policy reports as assessment evidence.",
        "database": "Provide database configuration and access review reports as assessment evidence.",
        "identity": "Provide access review/attestation reports and MFA coverage metrics from the IdP as assessment evidence.",
    },
    "CM": {
        "aws": {"sysadmin": "Define golden AMIs/Launch Templates, enforce with AWS Config rules and drift detection, manage change via CloudFormation/Terraform with peer-reviewed pull requests.", "netadmin": "Manage VPC, Security Group, and routing configuration as reviewed Infrastructure-as-Code (Terraform/CloudFormation), with AWS Config rules to detect drift from the approved network baseline."},
        "azure": {"sysadmin": "Use Azure Image Builder for golden images, Azure Policy for drift enforcement, and ARM/Bicep/Terraform for reviewed change.", "netadmin": "Manage VNet, NSG, and Azure Firewall configuration as reviewed IaC (Bicep/Terraform), with Azure Policy to detect drift from the approved network baseline."},
        "gcp": {"sysadmin": "Use Packer-built golden images, Org Policy for drift prevention, and Deployment Manager/Terraform for reviewed change.", "netadmin": "Manage VPC, firewall rule, and routing configuration as reviewed IaC (Terraform/Deployment Manager), with Org Policy to detect drift from the approved network baseline."},
        "linux": "Maintain a CIS/DISA STIG hardened baseline image; manage config with Ansible/Puppet/Chef under version control; use AIDE/Tripwire for drift detection.",
        "windows": "Maintain a STIG-hardened baseline image; manage config with Group Policy/DSC under version control; monitor for unauthorized changes.",
        "network": "Maintain versioned 'golden' device configs; use a config management tool (e.g., Ansible, RANCID) with change approval and automated backups before/after changes.",
        "kubernetes": "Pin base images, use admission controllers (OPA/Gatekeeper) to block non-compliant manifests, and manage manifests via GitOps with review.",
        "database": "Maintain a hardened database configuration baseline (CIS benchmark) and manage schema/config changes via reviewed migrations.",
        "identity": "Maintain baseline IdP policy configuration (Conditional Access/app registrations) under change control with peer review.",
    },
    "CP": {
        "aws": {"sysadmin": "Use cross-region backups (AWS Backup), multi-AZ/multi-region architectures, and documented, tested runbooks with defined RTO/RPO.", "netadmin": "Design network connectivity (VPN/Direct Connect, route tables) with redundant paths across AZs/regions, and keep tested runbooks for re-establishing connectivity after a failure."},
        "azure": {"sysadmin": "Use Azure Backup/Site Recovery across regions and documented, tested failover runbooks with defined RTO/RPO.", "netadmin": "Design ExpressRoute/VPN connectivity with redundant circuits and routes across regions, with tested runbooks for re-establishing connectivity after a failure."},
        "gcp": {"sysadmin": "Use scheduled snapshots/cross-region storage replication and documented, tested failover runbooks with defined RTO/RPO.", "netadmin": "Design Cloud Interconnect/VPN connectivity with redundant paths across regions, with tested runbooks for re-establishing connectivity after a failure."},
        "linux": "Automate backups (e.g., to object storage), test restores on a schedule, and document recovery runbooks.",
        "windows": "Use Windows Server Backup/VSS and Active Directory system state backups; test forest/domain recovery procedures.",
        "network": "Maintain redundant paths/devices (dual ISPs, HSRP/VRRP) and current backups of device configs for rapid re-provisioning.",
        "kubernetes": "Back up cluster state (etcd) and persistent volumes (e.g., Velero); test cluster rebuild from backups.",
        "database": "Automate database backups with point-in-time recovery and periodically test restores against RTO/RPO targets.",
        "identity": "Maintain a documented recovery/break-glass procedure for IdP outage, including emergency access accounts.",
    },
    "IA": {
        "aws": {"sysadmin": "Require MFA for IAM users and root; prefer IAM Identity Center (SSO) with federated identity over long-lived access keys; rotate/eliminate static credentials.", "netadmin": "Require MFA for any console/API access used to manage network resources (VPC, Transit Gateway, Direct Connect), and avoid long-lived keys for network automation."},
        "azure": {"sysadmin": "Enforce MFA and passwordless/phishing-resistant auth via Conditional Access; use managed identities instead of stored credentials.", "netadmin": "Require MFA for accounts with Network Contributor or similar network-management roles, and prefer managed identities over stored credentials for network automation."},
        "gcp": {"sysadmin": "Enforce 2-Step Verification (security keys) via context-aware access; use Workload Identity Federation instead of service account keys.", "netadmin": "Require 2-Step Verification for accounts with Network Admin roles, and use Workload Identity Federation rather than service account keys for network automation."},
        "linux": "Enforce SSH key-based auth (disable password auth), integrate with centralized IdP (SSSD/LDAP), and require MFA for privileged/remote logins (PAM modules).",
        "windows": "Enforce Windows Hello for Business or smart card (PIV/CAC) logon, strong password/Kerberos policy via GPO, and MFA for privileged accounts.",
        "network": "Require named individual admin accounts (no shared credentials) with MFA via TACACS+/RADIUS integration; disable default/vendor accounts.",
        "kubernetes": "Integrate cluster authentication with the corporate IdP (OIDC) rather than static kubeconfig tokens; require MFA for kubectl/console access.",
        "database": "Require unique database logins tied to the IdP (avoid shared 'sa'/'root' use), enforce strong authentication for privileged DB accounts.",
        "identity": "Deploy phishing-resistant MFA (FIDO2/PIV) as the IdP's primary factor and enforce it for all privileged and remote access.",
    },
    "IR": {
        "aws": {"sysadmin": "Use GuardDuty/Security Hub for host and workload detection, and automate containment (isolate instance via SG change, quarantine IAM credentials) with Lambda/SSM runbooks.", "netadmin": "Use VPC Flow Logs and GuardDuty network findings to detect anomalous traffic, and maintain a pre-approved runbook to isolate a VPC/subnet via routing or Security Group changes."},
        "azure": {"sysadmin": "Use Microsoft Defender for endpoint/workload detection, and Logic Apps playbooks to automate host-level containment actions.", "netadmin": "Use NSG flow logs and Sentinel network analytics to detect anomalous traffic, with a pre-approved runbook to isolate a VNet/subnet via NSG changes."},
        "gcp": {"sysadmin": "Use Security Command Center/Chronicle for workload detection, and Cloud Functions playbooks to automate host-level containment actions.", "netadmin": "Use VPC Flow Logs and Chronicle network analytics to detect anomalous traffic, with a pre-approved runbook to isolate a VPC/subnet via firewall rule changes."},
        "linux": "Use host IDS (e.g., OSSEC/Wazuh) for detection; maintain tested isolation procedures (network quarantine, forensic snapshot) for compromised hosts.",
        "windows": "Use Defender for Endpoint/EDR for detection; maintain tested isolation procedures and volatile-memory capture guidance.",
        "network": "Maintain pre-approved isolation actions (VLAN quarantine, ACL block) for compromised segments and packet-capture procedures for forensics.",
        "kubernetes": "Maintain procedures to isolate a compromised pod/node (network policy quarantine, cordon/drain) and capture forensic data before termination.",
        "database": "Maintain procedures to detect anomalous query patterns and to isolate/lock a compromised database account without destroying evidence.",
        "identity": "Maintain procedures to force sign-out and revoke tokens/sessions for compromised identities and to review conditional access logs during an incident.",
    },
    "MA": {
        "aws": {"sysadmin": "Restrict maintenance actions (e.g., SSM Session Manager) to approved roles, log all sessions, and avoid direct SSH/RDP where possible.", "netadmin": "Restrict maintenance access to VPC/network resources to approved roles via scoped IAM policies, and log all changes made through the console or CLI."},
        "azure": {"sysadmin": "Restrict maintenance access via Just-In-Time VM Access and Azure Bastion; log all privileged sessions.", "netadmin": "Restrict maintenance access to network resources (VNets, NSGs) to approved roles via scoped RBAC, and log all changes through Azure Activity Log."},
        "gcp": {"sysadmin": "Restrict maintenance access via IAP tunneling with time-bound access; log all privileged sessions.", "netadmin": "Restrict maintenance access to network resources to approved roles via scoped IAM, and log all changes through Cloud Audit Logs."},
        "linux": "Log all privileged maintenance sessions (e.g., via auditd/session recording), require approval for out-of-band maintenance tools/media.",
        "windows": "Log all privileged maintenance sessions (e.g., via PowerShell transcription), require approval for vendor remote maintenance.",
        "network": "Log all console/remote maintenance sessions on devices; require change tickets and time-bound access for vendor maintenance.",
        "kubernetes": "Restrict node/cluster maintenance (kubectl exec, node SSH) to approved roles with session logging.",
        "database": "Restrict and log privileged maintenance sessions (patching, schema changes) with approval workflow.",
        "identity": "Log and review all administrative maintenance actions performed in the IdP admin console.",
    },
    "MP": {
        "aws": {"sysadmin": "Use S3 default encryption + versioning + MFA delete for stored media equivalents; enforce EBS volume encryption and secure deletion via crypto-shredding on termination.", "netadmin": "Ensure exported network configs (VPC flow log archives, Transit Gateway/Direct Connect configs) are encrypted at rest and disposed of via crypto-shredding, same as any other sensitive export."},
        "azure": {"sysadmin": "Use Storage Service Encryption and soft-delete/immutable storage; ensure disk encryption at rest with crypto-shredding on deletion.", "netadmin": "Ensure exported network configs (NSG rules, VNet peering configs) are encrypted at rest and disposed of via crypto-shredding, same as any other sensitive export."},
        "gcp": {"sysadmin": "Use default encryption at rest and Object Versioning; ensure persistent disk encryption with crypto-shredding on deletion.", "netadmin": "Ensure exported network configs (firewall rules, VPC peering configs) are encrypted at rest and disposed of via crypto-shredding, same as any other sensitive export."},
        "linux": "Encrypt removable/backup media (LUKS), label sensitivity, and use secure-wipe tools (e.g., shred, nvme-cli sanitize) before reuse/disposal.",
        "windows": "Enforce BitLocker on removable media, and use certified sanitization tools before reuse/disposal of drives.",
        "network": "Sanitize/destroy device storage (flash/NVRAM) containing configs before device disposal or return to vendor (RMA).",
        "kubernetes": "Ensure persistent volume data is encrypted at rest and volumes are securely wiped/deleted when PVCs are removed.",
        "database": "Encrypt database backups/exports at rest and securely erase decommissioned backup media.",
        "identity": "Ensure exported identity data (bulk exports, backups) is encrypted and disposed of per the media protection policy.",
    },
    "PE": {
        "aws": "Rely on AWS's physical/environmental controls (SOC 2 report) for data centers; document the shared-responsibility boundary in the SSP.",
        "azure": "Rely on Microsoft's physical/environmental controls (SOC 2/ISO 27001) for data centers; document the shared-responsibility boundary in the SSP.",
        "gcp": "Rely on Google's physical/environmental controls (SOC 2/ISO 27001) for data centers; document the shared-responsibility boundary in the SSP.",
        "linux": "For on-prem hosts, use badge/biometric access to the server room, visitor logs, and environmental monitoring (temp/humidity/fire suppression).",
        "windows": "For on-prem hosts, use badge/biometric access to the server room, visitor logs, and environmental monitoring (temp/humidity/fire suppression).",
        "network": "Secure network closets/racks with locked enclosures and badge access separate from general server room access; log entry.",
        "kubernetes": "For on-prem clusters, apply the same physical controls as the underlying host infrastructure (server room access, environmental monitoring).",
        "database": "For on-prem database servers, apply server room physical access controls and environmental monitoring.",
        "identity": "Physically secure on-prem IdP infrastructure (e.g., AD domain controllers) equivalent to other Tier-0 assets.",
    },
    "PL": {
        "aws": {"sysadmin": "Document the AWS account and compute/storage architecture in the System Security Plan, kept current with Infrastructure-as-Code.", "netadmin": "Document the AWS VPC topology and data flows (subnets, routing, peering, Transit Gateway) in the System Security Plan, kept current with IaC."},
        "azure": {"sysadmin": "Document the Azure subscription and compute/storage architecture in the System Security Plan, kept current with IaC.", "netadmin": "Document the Azure VNet topology and data flows (subnets, peering, ExpressRoute) in the System Security Plan, kept current with IaC."},
        "gcp": {"sysadmin": "Document the GCP project and compute/storage architecture in the System Security Plan, kept current with IaC.", "netadmin": "Document the GCP VPC topology and data flows (subnets, peering, Interconnect) in the System Security Plan, kept current with IaC."},
        "linux": "Document host roles, network diagrams, and data flows for on-prem/hybrid Linux systems in the SSP.",
        "windows": "Document AD forest/domain topology and data flows in the SSP.",
        "network": "Provide current network topology diagrams and boundary descriptions for the SSP's authorization boundary.",
        "kubernetes": "Document cluster architecture (namespaces, network policies, ingress boundaries) in the SSP.",
        "database": "Document database placement, data classification, and data flows in the SSP.",
        "identity": "Document the identity architecture (IdP, federation, trust relationships) in the SSP.",
    },
    "PM": {
        "aws": {"sysadmin": "Maintain an accurate AWS resource inventory (Config aggregator, Resource Explorer) feeding the org-wide system inventory.", "netadmin": "Maintain an accurate inventory of VPCs, subnets, and network connections (Transit Gateway, Direct Connect) feeding the org-wide network topology picture."},
        "azure": {"sysadmin": "Maintain an accurate Azure Resource Graph inventory feeding the org-wide system inventory.", "netadmin": "Maintain an accurate inventory of VNets and network connections (ExpressRoute, peerings) feeding the org-wide network topology picture."},
        "gcp": {"sysadmin": "Maintain an accurate Cloud Asset Inventory feeding the org-wide system inventory.", "netadmin": "Maintain an accurate inventory of VPCs and network connections (Interconnect, peerings) feeding the org-wide network topology picture."},
        "linux": "Feed host inventory/CMDB data (e.g., from configuration management tooling) into the org-wide system inventory.",
        "windows": "Feed AD computer/device inventory into the org-wide system inventory.",
        "network": "Feed network device inventory (NCM/IPAM) into the org-wide system inventory.",
        "kubernetes": "Feed cluster/workload inventory into the org-wide system inventory.",
        "database": "Feed database instance inventory into the org-wide system inventory.",
        "identity": "Feed identity/account inventory and org structure into the org-wide risk management program.",
    },
    "PS": {
        "aws": {"sysadmin": "Automate account deprovisioning by wiring HR offboarding to IAM Identity Center deactivation.", "netadmin": "Automate revocation of network-management role assignments (VPC/Transit Gateway admin access) by wiring HR offboarding to IAM Identity Center deactivation."},
        "azure": {"sysadmin": "Automate account deprovisioning by wiring HR offboarding to Azure AD lifecycle workflows.", "netadmin": "Automate revocation of Network Contributor role assignments by wiring HR offboarding to Azure AD lifecycle workflows."},
        "gcp": {"sysadmin": "Automate account deprovisioning by wiring HR offboarding to Cloud Identity deactivation.", "netadmin": "Automate revocation of Network Admin role assignments by wiring HR offboarding to Cloud Identity deactivation."},
        "linux": "Wire HR offboarding events to automated local/LDAP account disable on Linux hosts.",
        "windows": "Wire HR offboarding events to automated AD account disable/OU move workflows.",
        "network": "Revoke named network device admin credentials immediately on personnel transfer/termination notices.",
        "kubernetes": "Revoke cluster RBAC bindings tied to the departing user's identity immediately on offboarding.",
        "database": "Revoke database accounts tied to the departing user's identity immediately on offboarding.",
        "identity": "Trigger automatic account disable and session/token revocation in the IdP on termination/transfer notice.",
    },
    "PT": {
        "aws": {"sysadmin": "Tag and isolate PII-processing compute/storage (dedicated accounts, encrypted S3/RDS) with IAM policies scoped to authorized purpose.", "netadmin": "Isolate PII-processing workloads in dedicated VPCs with restrictive Security Groups/NACLs so PII traffic can't reach unauthorized network paths."},
        "azure": {"sysadmin": "Tag and isolate PII-processing compute/storage (dedicated resource groups, encrypted storage) with scoped RBAC.", "netadmin": "Isolate PII-processing workloads in dedicated subnets with restrictive NSGs so PII traffic can't reach unauthorized network paths."},
        "gcp": {"sysadmin": "Tag and isolate PII-processing compute/storage (dedicated projects, encrypted storage) with scoped IAM.", "netadmin": "Isolate PII-processing workloads in dedicated VPCs with restrictive firewall rules so PII traffic can't reach unauthorized network paths."},
        "linux": "Restrict file-system and application access to PII data stores to authorized service accounts only.",
        "windows": "Restrict file-share/application access to PII data stores to authorized security groups only.",
        "network": "Ensure PII data flows are routed through approved, monitored paths (e.g., not over unencrypted links).",
        "kubernetes": "Restrict which namespaces/workloads can mount PII-bearing volumes or secrets.",
        "database": "Apply column-level encryption/masking and scoped grants for tables containing PII.",
        "identity": "Ensure consent/purpose attributes are enforced in access policies before releasing PII-scoped claims.",
    },
    "RA": {
        "aws": {"sysadmin": "Run Inspector/Security Hub vulnerability scans continuously; track findings to remediation SLAs in the risk register.", "netadmin": "Confirm Inspector network reachability scans cover all VPCs and that internet-facing paths are included; track network findings to the same remediation SLAs."},
        "azure": {"sysadmin": "Run Defender for Cloud vulnerability assessments continuously; track findings to remediation SLAs.", "netadmin": "Confirm Defender for Cloud's network security assessments cover all VNets and internet-facing paths; track network findings to the same remediation SLAs."},
        "gcp": {"sysadmin": "Run Security Command Center vulnerability findings continuously; track to remediation SLAs.", "netadmin": "Confirm Security Command Center's network exposure findings cover all VPCs and internet-facing paths; track network findings to the same remediation SLAs."},
        "linux": "Run authenticated vulnerability scans (e.g., Nessus/OpenVAS) on a defined cadence; track findings to remediation SLAs.",
        "windows": "Run authenticated vulnerability scans and WSUS/patch compliance reports; track findings to remediation SLAs.",
        "network": "Run scans against network device management interfaces and firmware versions; track findings to remediation SLAs.",
        "kubernetes": "Scan container images and running workloads (e.g., Trivy) for CVEs; block deploys with critical findings via admission control.",
        "database": "Run database-specific vulnerability/configuration scans; track findings to remediation SLAs.",
        "identity": "Assess risk of stale/orphaned accounts and excessive privileges via periodic IdP access reviews.",
    },
    "SA": {
        "aws": {"sysadmin": "Bake compute/IAM security requirements into Landing Zone/Control Tower guardrails applied to every new account.", "netadmin": "Bake network security requirements (mandatory Security Groups, no public subnets by default) into Landing Zone/Control Tower guardrails applied to every new account."},
        "azure": {"sysadmin": "Bake compute/identity security requirements into Azure Landing Zone policies applied to every new subscription.", "netadmin": "Bake network security requirements (mandatory NSGs, hub-spoke topology) into Azure Landing Zone policies applied to every new subscription."},
        "gcp": {"sysadmin": "Bake compute/IAM security requirements into an Organization Policy/landing zone applied to every new project.", "netadmin": "Bake network security requirements (mandatory firewall rules, Shared VPC) into an Organization Policy/landing zone applied to every new project."},
        "linux": "Bake security requirements into the base image/build pipeline so every new host inherits hardening.",
        "windows": "Bake security requirements into the base image and AD provisioning workflow.",
        "network": "Require security review/sign-off before new network devices or circuits are provisioned.",
        "kubernetes": "Require images to pass a security gate (signed, scanned, from an approved registry) before deployment.",
        "database": "Require new database instances to be provisioned from a hardened template with encryption enabled by default.",
        "identity": "Require new applications to integrate via the approved SSO/OIDC pattern before go-live.",
    },
    "SC": {
        "aws": {"netadmin": "Use Security Groups/NACLs for boundary control, KMS for encryption at rest, TLS via ACM for in-transit, and PrivateLink/VPC endpoints to avoid public exposure.", "sysadmin": "Enable encryption at rest by default (EBS, S3, RDS with KMS) on every workload you run, and terminate TLS on the application/instance itself where PrivateLink/ACM alone isn't enough."},
        "azure": {"netadmin": "Use NSGs/Azure Firewall for boundary control, Key Vault/platform encryption at rest, TLS everywhere, and Private Link to avoid public exposure.", "sysadmin": "Enable encryption at rest by default (managed disks, storage accounts with Key Vault) on every workload you run, and enforce TLS at the application layer."},
        "gcp": {"netadmin": "Use VPC firewall rules/Cloud Armor for boundary control, CMEK for encryption at rest, TLS everywhere, and Private Google Access/VPC-SC.", "sysadmin": "Enable encryption at rest by default (persistent disks, Cloud Storage with CMEK) on every workload you run, and enforce TLS at the application layer."},
        "linux": "Enable full-disk/at-rest encryption (LUKS), enforce TLS for services, use host-based firewalls (nftables/iptables), and isolate services via containers/namespaces.",
        "windows": "Enable BitLocker, enforce TLS (schannel) for services, use Windows Defender Firewall, and IPsec for internal segmentation.",
        "network": "Own perimeter firewalls, segmentation (VLANs/zones), IPS, and encrypted site-to-site/VPN links; block unneeded ports/protocols by default.",
        "kubernetes": "Enforce mTLS between services (service mesh), NetworkPolicies for pod segmentation, and encrypt secrets at rest (KMS provider).",
        "database": "Enforce TLS for client connections, transparent data encryption (TDE) at rest, and network-level restriction to app-tier only.",
        "identity": "Enforce TLS/OIDC token encryption and short-lived tokens; restrict IdP admin endpoints to a management network.",
    },
    "SI": {
        "aws": {"sysadmin": "Enable GuardDuty and Inspector for continuous flaw/threat detection; automate patching via Systems Manager Patch Manager.", "netadmin": "Monitor GuardDuty network findings and VPC Flow Log anomalies for signs of compromise, and keep any network appliance AMIs/firmware on a tested patch schedule."},
        "azure": {"sysadmin": "Enable Defender for Cloud for continuous flaw/threat detection; automate patching via Update Management.", "netadmin": "Monitor Defender network alerts and NSG flow log anomalies for signs of compromise, and keep network virtual appliances on a tested patch schedule."},
        "gcp": {"sysadmin": "Enable Security Command Center for continuous flaw/threat detection; automate patching via VM Manager patch jobs.", "netadmin": "Monitor Security Command Center network alerts and VPC Flow Log anomalies for signs of compromise, and keep network virtual appliances on a tested patch schedule."},
        "linux": "Automate patch management (unattended-upgrades/yum-cron with testing gate), run host-based malware/rootkit detection, and validate input on exposed services.",
        "windows": "Automate patching via WSUS/Windows Update for Business, run endpoint protection (Defender), and monitor for unauthorized changes.",
        "network": "Keep firmware/IOS patched on a tested schedule; deploy IDS/IPS signatures and monitor for anomalous traffic patterns.",
        "kubernetes": "Scan and patch base images regularly, use runtime security tooling (e.g., Falco) to detect anomalous container behavior.",
        "database": "Apply database engine patches on a tested schedule and monitor for anomalous query/error patterns.",
        "identity": "Monitor sign-in risk signals (impossible travel, leaked credentials) and auto-remediate via risk-based Conditional Access.",
    },
    "SR": {
        "aws": {"sysadmin": "Use AWS Artifact and Marketplace vendor security reviews; verify AMI/package provenance and signatures before use.", "netadmin": "Verify the provenance of any network virtual appliance (firewall, VPN gateway) purchased through Marketplace, and confirm it's from a vetted vendor with current attestations."},
        "azure": {"sysadmin": "Use Microsoft's Trust Center attestations and verify Marketplace image provenance before use.", "netadmin": "Verify the provenance of any network virtual appliance purchased through Azure Marketplace, and confirm it's from a vetted vendor with current attestations."},
        "gcp": {"sysadmin": "Use Google's compliance reports and verify Marketplace image provenance before use.", "netadmin": "Verify the provenance of any network virtual appliance purchased through GCP Marketplace, and confirm it's from a vetted vendor with current attestations."},
        "linux": "Verify package signatures (GPG) and use trusted repositories only; track upstream CVEs for third-party packages.",
        "windows": "Verify signed installers/drivers and use WSUS-approved sources only; track vendor security bulletins.",
        "network": "Verify firmware signatures and obtain hardware/firmware only through the vendor's authorized supply chain.",
        "kubernetes": "Verify container image signatures (e.g., cosign) and restrict deployments to images from an approved, scanned registry.",
        "database": "Verify database software/extension provenance and apply vendor security patches promptly.",
        "identity": "Assess the IdP vendor's own supply chain/security posture (SOC 2, incident history) as part of vendor risk management.",
    },
}


def get_control_number_and_title(control):
    return control.get("number", ""), control.get("title", "")


def generic_guidance(control, tech):
    number, title = get_control_number_and_title(control)
    tech_name = TECHNOLOGIES.get(tech, tech)
    statement = (control.get("statement") or "").strip().replace("\n", " ")
    if len(statement) > 220:
        statement = statement[:217] + "..."
    return (
        f"No pre-authored {tech_name} guidance exists yet for {number}. "
        f"Translate the control statement into {tech_name} configuration and document how it is enforced: \"{statement}\""
    )


def resolve_tech_guidance(family, tech, audience, control):
    entry = FAMILY_TECH_GUIDANCE.get(family, {}).get(tech)
    if entry is None:
        return generic_guidance(control, tech)

    if isinstance(entry, str):
        return entry

    # entry is a dict split by audience (currently only aws/azure/gcp)
    if audience == "isso":
        parts = []
        if entry.get("sysadmin"):
            parts.append("Compute/host: " + entry["sysadmin"])
        if entry.get("netadmin"):
            parts.append("Network: " + entry["netadmin"])
        return " ".join(parts) if parts else generic_guidance(control, tech)

    return entry.get(audience) or entry.get("sysadmin") or entry.get("netadmin") or generic_guidance(control, tech)


def tailor_control(control, technologies, audience):
    """
    control: flat control dict from data/controls.json
    technologies: list of technology keys (see TECHNOLOGIES). May be empty
        to request just the narrative with no per-technology items.
    audience: one of AUDIENCES keys
    Returns a dict: {audience, intro, items: [{technology, guidance}]}
    """
    family = control.get("family")
    narrative = AUDIENCE_NARRATIVE.get(family, {}).get(
        audience,
        f"As the {AUDIENCES.get(audience, audience)}, focus on the parts of this control that fall under your role.",
    )

    allowed = set(technologies_for_audience(audience))

    items = []
    for tech in technologies:
        if tech not in TECHNOLOGIES:
            continue
        if tech not in allowed:
            continue
        guidance = resolve_tech_guidance(family, tech, audience, control)
        items.append({"technology": tech, "technology_name": TECHNOLOGIES[tech], "guidance": guidance})

    return {
        "audience": audience,
        "audience_name": AUDIENCES.get(audience, audience),
        "intro": narrative,
        "items": items,
    }
