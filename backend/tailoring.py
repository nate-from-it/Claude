"""
Rule-based tailoring engine.

Translates a NIST 800-53 rev5 control into role-specific, technology-specific
implementation guidance. This is deliberately NOT an LLM call: guidance is
built from a curated knowledge base (FAMILY_TECH_GUIDANCE, AUDIENCE_INTRO) so
output is deterministic, reviewable, and free to run.

Two layers combine for each (control, technology, audience):
  1. AUDIENCE_INTRO[family][audience]   - frames *whose* job this is and why
  2. FAMILY_TECH_GUIDANCE[family][tech] - the concrete technical how-to

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
}

AUDIENCES = {
    "sysadmin": "System Administrator",
    "netadmin": "Network Administrator",
    "isso": "ISSO",
}

AUDIENCE_FOCUS = {
    "sysadmin": "the hosts, OS, and application accounts you manage day to day",
    "netadmin": "the network path: segmentation, perimeter devices, and traffic monitoring",
    "isso": "documenting how the control is satisfied, collecting evidence, and tracking exceptions in the SSP/POA&M",
}

# ---------------------------------------------------------------------------
# Layer 1: who owns this family, per audience (used as the opening framing)
# ---------------------------------------------------------------------------
AUDIENCE_INTRO = {
    "AC": {
        "sysadmin": "You own account provisioning/deprovisioning and enforcing least privilege on the systems you administer.",
        "netadmin": "You own restricting network access paths so only authorized traffic can reach protected resources.",
        "isso": "You own maintaining the access control policy, reviewing account/role assignments, and evidencing least privilege for the assessor.",
    },
    "AT": {
        "sysadmin": "You deliver role-based technical training (secure configuration, incident reporting) for staff you manage.",
        "netadmin": "You deliver technical training on network security tools and incident escalation to network staff.",
        "isso": "You own the security/privacy awareness and training program, records, and compliance tracking.",
    },
    "AU": {
        "sysadmin": "You configure host and application logging, retention, and protection of audit records.",
        "netadmin": "You configure logging on network devices and ensure logs reach the central log pipeline.",
        "isso": "You define the audit strategy, review audit reduction/reporting, and confirm coverage in the SSP.",
    },
    "CA": {
        "sysadmin": "You provide evidence of technical control implementation for assessments and remediate host findings.",
        "netadmin": "You provide network architecture diagrams and remediate network-layer assessment findings.",
        "isso": "You own the assessment plan, POA&Ms, continuous monitoring strategy, and authorization package.",
    },
    "CM": {
        "sysadmin": "You build and maintain hardened host baselines and manage the OS/application change process.",
        "netadmin": "You maintain network device baseline configs and manage network change control.",
        "isso": "You own the configuration management plan and the baseline/change records used as audit evidence.",
    },
    "CP": {
        "sysadmin": "You implement backup, restore, and system recovery procedures for the hosts you manage.",
        "netadmin": "You implement network failover/redundancy and alternate connectivity for contingency operations.",
        "isso": "You own the contingency plan, test schedule, and after-action documentation.",
    },
    "IA": {
        "sysadmin": "You configure authentication (passwords, MFA, service accounts) on the hosts and apps you manage.",
        "netadmin": "You configure device/administrator authentication (TACACS+/RADIUS, MFA) on network infrastructure.",
        "isso": "You own the identification and authentication policy and evidence of MFA/PKI coverage.",
    },
    "IR": {
        "sysadmin": "You detect, contain, and eradicate incidents on the hosts and applications you manage.",
        "netadmin": "You isolate compromised network segments and support forensics at the network layer.",
        "isso": "You own the incident response plan, reporting timelines (e.g., US-CERT), and lessons-learned tracking.",
    },
    "MA": {
        "sysadmin": "You control who performs maintenance on systems and sanitize media/tools used for it.",
        "netadmin": "You control remote/local maintenance access to network devices and log maintenance sessions.",
        "isso": "You own the maintenance policy and records of approved maintenance personnel and tools.",
    },
    "MP": {
        "sysadmin": "You control access to, and sanitize/destroy, digital media on the systems you manage.",
        "netadmin": "You control media used in network devices (e.g., config backups, firmware media).",
        "isso": "You own the media protection policy and sanitization/destruction records.",
    },
    "PE": {
        "sysadmin": "You ensure server-room/rack access controls and environmental protections for hosts you manage are followed.",
        "netadmin": "You ensure physical access to network closets/racks and cabling is controlled and monitored.",
        "isso": "You own the physical/environmental protection policy and facility access records.",
    },
    "PL": {
        "sysadmin": "You provide system-level input (architecture, data flows) for the security/privacy plans.",
        "netadmin": "You provide network topology and boundary information for the security/privacy plans.",
        "isso": "You own authoring, maintaining, and getting approval for the system security and privacy plans.",
    },
    "PM": {
        "sysadmin": "You feed asset and system inventory data into the organization-wide security program.",
        "netadmin": "You feed network asset and topology data into the organization-wide security program.",
        "isso": "You own program-level artifacts (risk management strategy, inventories, security architecture) reporting to the CISO/AO.",
    },
    "PS": {
        "sysadmin": "You promptly disable/transfer accounts on personnel status change notices for systems you manage.",
        "netadmin": "You promptly revoke device/VPN access on personnel status change notices.",
        "isso": "You own the personnel security policy, screening records, and termination/transfer checklists.",
    },
    "PT": {
        "sysadmin": "You configure systems that process PII per approved authority-to-process and retention/consent settings.",
        "netadmin": "You ensure PII in transit is routed and monitored per approved data-flow mappings.",
        "isso": "You own the PII processing policy, data mapping, and consent/authority-to-collect documentation.",
    },
    "RA": {
        "sysadmin": "You patch and remediate vulnerabilities identified by scans on the hosts you manage.",
        "netadmin": "You remediate vulnerabilities on network devices and validate scan coverage of network segments.",
        "isso": "You own the risk assessment process, risk register, and vulnerability scan reporting cadence.",
    },
    "SA": {
        "sysadmin": "You apply secure configuration/hardening requirements when deploying acquired or developed systems.",
        "netadmin": "You validate that acquired network devices/services meet security requirements before deployment.",
        "isso": "You own security requirements in acquisition documents, SDLC gates, and supplier assessments.",
    },
    "SC": {
        "sysadmin": "You configure host-level protections (encryption, boundary services, isolation) on systems you manage.",
        "netadmin": "You own the network boundary: firewalls, segmentation, encryption of data in transit, and DoS protections.",
        "isso": "You own the system and communications protection policy and evidence of boundary/encryption controls.",
    },
    "SI": {
        "sysadmin": "You patch systems, run malware protection, and act on flaw/error monitoring for hosts you manage.",
        "netadmin": "You deploy network-based intrusion detection/prevention and monitor for network anomalies.",
        "isso": "You own the flaw remediation and system monitoring policy and evidence of patch/AV compliance.",
    },
    "SR": {
        "sysadmin": "You verify integrity (e.g., checksums, signed packages) of software/hardware you install.",
        "netadmin": "You verify integrity of firmware/software delivered for network devices before install.",
        "isso": "You own the supply chain risk management plan and supplier/component risk assessments.",
    },
}

# ---------------------------------------------------------------------------
# Layer 2: concrete technology-specific guidance, per family
# ---------------------------------------------------------------------------
FAMILY_TECH_GUIDANCE = {
    "AC": {
        "aws": "Use IAM users/roles/groups with least-privilege policies and permission boundaries; enforce with SCPs in AWS Organizations; review with IAM Access Analyzer and Access Advisor.",
        "azure": "Use Azure AD (Entra ID) role-based access control (RBAC) and Privileged Identity Management (PIM) for just-in-time elevation; enforce with Conditional Access policies.",
        "gcp": "Use Cloud IAM roles (prefer predefined/custom over primitive roles) and Organization Policy constraints; review with Policy Analyzer and IAM Recommender.",
        "linux": "Enforce least privilege with sudoers rules, groups, and SELinux/AppArmor; disable unused accounts; use PAM for access restrictions.",
        "windows": "Use Active Directory security groups, Group Policy, and delegated OU permissions; restrict local Administrators group membership.",
        "network": "Use ACLs, VLAN segmentation, and 802.1X port-based access control to restrict which devices/users reach network segments.",
        "kubernetes": "Use Kubernetes RBAC (Roles/ClusterRoles), namespaces for isolation, and NetworkPolicies to restrict pod-to-pod access.",
        "database": "Use database roles/grants with least privilege, row-level security where supported, and separate application vs. admin accounts.",
        "identity": "Centralize authorization decisions in the IdP; use group/attribute-based access control (ABAC) and enforce via SAML/OIDC claims.",
    },
    "AT": {
        "aws": "Track completion of AWS-specific secure-usage training (IAM, S3 exposure risks) via your LMS; tie to onboarding/offboarding workflows.",
        "azure": "Track Azure-specific security training (RBAC, Conditional Access) completion tied to role assignment in Azure AD.",
        "gcp": "Track GCP-specific security training (IAM, VPC-SC) completion tied to project access grants.",
        "linux": "Provide hands-on training on hardening baselines, patching, and log review for Linux administrators.",
        "windows": "Provide hands-on training on AD hardening, GPO management, and Windows event log review.",
        "network": "Provide hands-on training on firewall rule review, network monitoring tools, and incident escalation paths.",
        "kubernetes": "Provide training on container/image security, RBAC, and secrets management for platform engineers.",
        "database": "Provide training on secure database configuration, encryption, and privileged access monitoring for DBAs.",
        "identity": "Provide training on phishing-resistant MFA, credential hygiene, and social engineering for all users via the IdP-driven campaign tooling.",
    },
    "AU": {
        "aws": "Enable CloudTrail (multi-region, log-file validation), VPC Flow Logs, and S3/CloudWatch log delivery; centralize in a log archive account with S3 Object Lock for retention.",
        "azure": "Enable Azure Monitor diagnostic settings, Activity Log, and NSG flow logs; ship to a central Log Analytics workspace with immutable storage.",
        "gcp": "Enable Cloud Audit Logs (Admin Activity, Data Access) and VPC Flow Logs; route to a centralized, access-controlled log sink.",
        "linux": "Configure auditd rules for security-relevant events; ship logs via rsyslog/journald to a central SIEM; protect log files with restrictive permissions.",
        "windows": "Enable Advanced Audit Policy and forward Security event logs (4624/4625/4720, etc.) to a central SIEM via WEF or an agent.",
        "network": "Enable syslog on firewalls/routers/switches with timestamps (NTP-synced) and forward to the central log collector.",
        "kubernetes": "Enable Kubernetes audit logging (audit-policy.yaml) and ship container stdout/stderr and API server audit logs to a central log store.",
        "database": "Enable native database audit logging (e.g., pgaudit, SQL Server Audit) for DDL/DML on sensitive tables; ship to a central log store.",
        "identity": "Enable IdP sign-in and audit logs (successful/failed auth, admin actions, MFA events) and forward to the SIEM.",
    },
    "CA": {
        "aws": "Use AWS Config conformance packs and Security Hub standards to continuously evidence control status for the ATO package.",
        "azure": "Use Microsoft Defender for Cloud regulatory compliance dashboard and Azure Policy to evidence control status.",
        "gcp": "Use Security Command Center findings and Policy Intelligence to evidence control status for assessments.",
        "linux": "Provide vulnerability scan and configuration baseline reports (e.g., OpenSCAP) as assessment evidence.",
        "windows": "Provide SCAP/Group Policy compliance reports as assessment evidence.",
        "network": "Provide network diagrams, firewall rule reviews, and boundary scan results as assessment evidence.",
        "kubernetes": "Provide cluster CIS Benchmark scan results and admission-controller policy reports as assessment evidence.",
        "database": "Provide database configuration and access review reports as assessment evidence.",
        "identity": "Provide access review/attestation reports and MFA coverage metrics from the IdP as assessment evidence.",
    },
    "CM": {
        "aws": "Define golden AMIs/Launch Templates, enforce with AWS Config rules and drift detection, manage change via CloudFormation/Terraform with peer-reviewed pull requests.",
        "azure": "Use Azure Image Builder for golden images, Azure Policy for drift enforcement, and ARM/Bicep/Terraform for reviewed change.",
        "gcp": "Use Packer-built golden images, Org Policy for drift prevention, and Deployment Manager/Terraform for reviewed change.",
        "linux": "Maintain a CIS/DISA STIG hardened baseline image; manage config with Ansible/Puppet/Chef under version control; use AIDE/Tripwire for drift detection.",
        "windows": "Maintain a STIG-hardened baseline image; manage config with Group Policy/DSC under version control; monitor for unauthorized changes.",
        "network": "Maintain versioned 'golden' device configs; use a config management tool (e.g., Ansible, RANCID) with change approval and automated backups before/after changes.",
        "kubernetes": "Pin base images, use admission controllers (OPA/Gatekeeper) to block non-compliant manifests, and manage manifests via GitOps with review.",
        "database": "Maintain a hardened database configuration baseline (CIS benchmark) and manage schema/config changes via reviewed migrations.",
        "identity": "Maintain baseline IdP policy configuration (Conditional Access/app registrations) under change control with peer review.",
    },
    "CP": {
        "aws": "Use cross-region backups (AWS Backup), multi-AZ/multi-region architectures, and documented, tested runbooks with defined RTO/RPO.",
        "azure": "Use Azure Backup/Site Recovery across regions and documented, tested failover runbooks with defined RTO/RPO.",
        "gcp": "Use scheduled snapshots/cross-region storage replication and documented, tested failover runbooks with defined RTO/RPO.",
        "linux": "Automate backups (e.g., to object storage), test restores on a schedule, and document recovery runbooks.",
        "windows": "Use Windows Server Backup/VSS and Active Directory system state backups; test forest/domain recovery procedures.",
        "network": "Maintain redundant paths/devices (dual ISPs, HSRP/VRRP) and current backups of device configs for rapid re-provisioning.",
        "kubernetes": "Back up cluster state (etcd) and persistent volumes (e.g., Velero); test cluster rebuild from backups.",
        "database": "Automate database backups with point-in-time recovery and periodically test restores against RTO/RPO targets.",
        "identity": "Maintain a documented recovery/break-glass procedure for IdP outage, including emergency access accounts.",
    },
    "IA": {
        "aws": "Require MFA for IAM users and root; prefer IAM Identity Center (SSO) with federated identity over long-lived access keys; rotate/eliminate static credentials.",
        "azure": "Enforce MFA and passwordless/phishing-resistant auth via Conditional Access; use managed identities instead of stored credentials.",
        "gcp": "Enforce 2-Step Verification (security keys) via context-aware access; use Workload Identity Federation instead of service account keys.",
        "linux": "Enforce SSH key-based auth (disable password auth), integrate with centralized IdP (SSSD/LDAP), and require MFA for privileged/remote logins (PAM modules).",
        "windows": "Enforce Windows Hello for Business or smart card (PIV/CAC) logon, strong password/Kerberos policy via GPO, and MFA for privileged accounts.",
        "network": "Require named individual admin accounts (no shared credentials) with MFA via TACACS+/RADIUS integration; disable default/vendor accounts.",
        "kubernetes": "Integrate cluster authentication with the corporate IdP (OIDC) rather than static kubeconfig tokens; require MFA for kubectl/console access.",
        "database": "Require unique database logins tied to the IdP (avoid shared 'sa'/'root' use), enforce strong authentication for privileged DB accounts.",
        "identity": "Deploy phishing-resistant MFA (FIDO2/PIV) as the IdP's primary factor and enforce it for all privileged and remote access.",
    },
    "IR": {
        "aws": "Use GuardDuty/Security Hub for detection, automate containment (isolate instance via SG change, quarantine IAM credentials) with Lambda/SSM runbooks.",
        "azure": "Use Microsoft Sentinel/Defender for detection and Logic Apps playbooks for automated containment actions.",
        "gcp": "Use Security Command Center/Chronicle for detection and Cloud Functions for automated containment playbooks.",
        "linux": "Use host IDS (e.g., OSSEC/Wazuh) for detection; maintain tested isolation procedures (network quarantine, forensic snapshot) for compromised hosts.",
        "windows": "Use Defender for Endpoint/EDR for detection; maintain tested isolation procedures and volatile-memory capture guidance.",
        "network": "Maintain pre-approved isolation actions (VLAN quarantine, ACL block) for compromised segments and packet-capture procedures for forensics.",
        "kubernetes": "Maintain procedures to isolate a compromised pod/node (network policy quarantine, cordon/drain) and capture forensic data before termination.",
        "database": "Maintain procedures to detect anomalous query patterns and to isolate/lock a compromised database account without destroying evidence.",
        "identity": "Maintain procedures to force sign-out and revoke tokens/sessions for compromised identities and to review conditional access logs during an incident.",
    },
    "MA": {
        "aws": "Restrict maintenance actions (e.g., SSM Session Manager) to approved roles, log all sessions, and avoid direct SSH/RDP where possible.",
        "azure": "Restrict maintenance access via Just-In-Time VM Access and Azure Bastion; log all privileged sessions.",
        "gcp": "Restrict maintenance access via IAP tunneling with time-bound access; log all privileged sessions.",
        "linux": "Log all privileged maintenance sessions (e.g., via auditd/session recording), require approval for out-of-band maintenance tools/media.",
        "windows": "Log all privileged maintenance sessions (e.g., via PowerShell transcription), require approval for vendor remote maintenance.",
        "network": "Log all console/remote maintenance sessions on devices; require change tickets and time-bound access for vendor maintenance.",
        "kubernetes": "Restrict node/cluster maintenance (kubectl exec, node SSH) to approved roles with session logging.",
        "database": "Restrict and log privileged maintenance sessions (patching, schema changes) with approval workflow.",
        "identity": "Log and review all administrative maintenance actions performed in the IdP admin console.",
    },
    "MP": {
        "aws": "Use S3 default encryption + versioning + MFA delete for stored media equivalents; enforce EBS volume encryption and secure deletion via crypto-shredding on termination.",
        "azure": "Use Storage Service Encryption and soft-delete/immutable storage; ensure disk encryption at rest with crypto-shredding on deletion.",
        "gcp": "Use default encryption at rest and Object Versioning; ensure persistent disk encryption with crypto-shredding on deletion.",
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
        "aws": "Document the AWS account/VPC architecture and data flows in the System Security Plan; keep architecture diagrams current with Infrastructure-as-Code.",
        "azure": "Document the subscription/VNet architecture and data flows in the System Security Plan, kept current with IaC.",
        "gcp": "Document the project/VPC architecture and data flows in the System Security Plan, kept current with IaC.",
        "linux": "Document host roles, network diagrams, and data flows for on-prem/hybrid Linux systems in the SSP.",
        "windows": "Document AD forest/domain topology and data flows in the SSP.",
        "network": "Provide current network topology diagrams and boundary descriptions for the SSP's authorization boundary.",
        "kubernetes": "Document cluster architecture (namespaces, network policies, ingress boundaries) in the SSP.",
        "database": "Document database placement, data classification, and data flows in the SSP.",
        "identity": "Document the identity architecture (IdP, federation, trust relationships) in the SSP.",
    },
    "PM": {
        "aws": "Maintain an accurate AWS resource inventory (Config aggregator, Resource Explorer) feeding the org-wide system inventory.",
        "azure": "Maintain an accurate Azure Resource Graph inventory feeding the org-wide system inventory.",
        "gcp": "Maintain an accurate Cloud Asset Inventory feeding the org-wide system inventory.",
        "linux": "Feed host inventory/CMDB data (e.g., from configuration management tooling) into the org-wide system inventory.",
        "windows": "Feed AD computer/device inventory into the org-wide system inventory.",
        "network": "Feed network device inventory (NCM/IPAM) into the org-wide system inventory.",
        "kubernetes": "Feed cluster/workload inventory into the org-wide system inventory.",
        "database": "Feed database instance inventory into the org-wide system inventory.",
        "identity": "Feed identity/account inventory and org structure into the org-wide risk management program.",
    },
    "PS": {
        "aws": "Automate account deprovisioning by wiring HR offboarding to IAM Identity Center deactivation.",
        "azure": "Automate account deprovisioning by wiring HR offboarding to Azure AD lifecycle workflows.",
        "gcp": "Automate account deprovisioning by wiring HR offboarding to Cloud Identity deactivation.",
        "linux": "Wire HR offboarding events to automated local/LDAP account disable on Linux hosts.",
        "windows": "Wire HR offboarding events to automated AD account disable/OU move workflows.",
        "network": "Revoke named network device admin credentials immediately on personnel transfer/termination notices.",
        "kubernetes": "Revoke cluster RBAC bindings tied to the departing user's identity immediately on offboarding.",
        "database": "Revoke database accounts tied to the departing user's identity immediately on offboarding.",
        "identity": "Trigger automatic account disable and session/token revocation in the IdP on termination/transfer notice.",
    },
    "PT": {
        "aws": "Tag and isolate PII-processing workloads (dedicated accounts/VPCs), and restrict/monitor access with IAM policies scoped to authorized purpose.",
        "azure": "Tag and isolate PII-processing workloads (dedicated subscriptions/resource groups) with scoped RBAC.",
        "gcp": "Tag and isolate PII-processing workloads (dedicated projects) with scoped IAM.",
        "linux": "Restrict file-system and application access to PII data stores to authorized service accounts only.",
        "windows": "Restrict file-share/application access to PII data stores to authorized security groups only.",
        "network": "Ensure PII data flows are routed through approved, monitored paths (e.g., not over unencrypted links).",
        "kubernetes": "Restrict which namespaces/workloads can mount PII-bearing volumes or secrets.",
        "database": "Apply column-level encryption/masking and scoped grants for tables containing PII.",
        "identity": "Ensure consent/purpose attributes are enforced in access policies before releasing PII-scoped claims.",
    },
    "RA": {
        "aws": "Run Inspector/Security Hub vulnerability scans continuously; track findings to remediation SLAs in the risk register.",
        "azure": "Run Defender for Cloud vulnerability assessments continuously; track findings to remediation SLAs.",
        "gcp": "Run Security Command Center vulnerability findings continuously; track to remediation SLAs.",
        "linux": "Run authenticated vulnerability scans (e.g., Nessus/OpenVAS) on a defined cadence; track findings to remediation SLAs.",
        "windows": "Run authenticated vulnerability scans and WSUS/patch compliance reports; track findings to remediation SLAs.",
        "network": "Run scans against network device management interfaces and firmware versions; track findings to remediation SLAs.",
        "kubernetes": "Scan container images and running workloads (e.g., Trivy) for CVEs; block deploys with critical findings via admission control.",
        "database": "Run database-specific vulnerability/configuration scans; track findings to remediation SLAs.",
        "identity": "Assess risk of stale/orphaned accounts and excessive privileges via periodic IdP access reviews.",
    },
    "SA": {
        "aws": "Bake security requirements into Landing Zone/Control Tower guardrails applied to every new account.",
        "azure": "Bake security requirements into Azure Landing Zone policies applied to every new subscription.",
        "gcp": "Bake security requirements into an Organization Policy/landing zone applied to every new project.",
        "linux": "Bake security requirements into the base image/build pipeline so every new host inherits hardening.",
        "windows": "Bake security requirements into the base image and AD provisioning workflow.",
        "network": "Require security review/sign-off before new network devices or circuits are provisioned.",
        "kubernetes": "Require images to pass a security gate (signed, scanned, from an approved registry) before deployment.",
        "database": "Require new database instances to be provisioned from a hardened template with encryption enabled by default.",
        "identity": "Require new applications to integrate via the approved SSO/OIDC pattern before go-live.",
    },
    "SC": {
        "aws": "Use Security Groups/NACLs for boundary control, KMS for encryption at rest, TLS via ACM for in-transit, and PrivateLink/VPC endpoints to avoid public exposure.",
        "azure": "Use NSGs/Azure Firewall for boundary control, Key Vault/platform encryption at rest, TLS everywhere, and Private Link to avoid public exposure.",
        "gcp": "Use VPC firewall rules/Cloud Armor for boundary control, CMEK for encryption at rest, TLS everywhere, and Private Google Access/VPC-SC.",
        "linux": "Enable full-disk/at-rest encryption (LUKS), enforce TLS for services, use host-based firewalls (nftables/iptables), and isolate services via containers/namespaces.",
        "windows": "Enable BitLocker, enforce TLS (schannel) for services, use Windows Defender Firewall, and IPsec for internal segmentation.",
        "network": "Own perimeter firewalls, segmentation (VLANs/zones), IPS, and encrypted site-to-site/VPN links; block unneeded ports/protocols by default.",
        "kubernetes": "Enforce mTLS between services (service mesh), NetworkPolicies for pod segmentation, and encrypt secrets at rest (KMS provider).",
        "database": "Enforce TLS for client connections, transparent data encryption (TDE) at rest, and network-level restriction to app-tier only.",
        "identity": "Enforce TLS/OIDC token encryption and short-lived tokens; restrict IdP admin endpoints to a management network.",
    },
    "SI": {
        "aws": "Enable GuardDuty and Inspector for continuous flaw/threat detection; automate patching via Systems Manager Patch Manager.",
        "azure": "Enable Defender for Cloud for continuous flaw/threat detection; automate patching via Update Management.",
        "gcp": "Enable Security Command Center for continuous flaw/threat detection; automate patching via VM Manager patch jobs.",
        "linux": "Automate patch management (unattended-upgrades/yum-cron with testing gate), run host-based malware/rootkit detection, and validate input on exposed services.",
        "windows": "Automate patching via WSUS/Windows Update for Business, run endpoint protection (Defender), and monitor for unauthorized changes.",
        "network": "Keep firmware/IOS patched on a tested schedule; deploy IDS/IPS signatures and monitor for anomalous traffic patterns.",
        "kubernetes": "Scan and patch base images regularly, use runtime security tooling (e.g., Falco) to detect anomalous container behavior.",
        "database": "Apply database engine patches on a tested schedule and monitor for anomalous query/error patterns.",
        "identity": "Monitor sign-in risk signals (impossible travel, leaked credentials) and auto-remediate via risk-based Conditional Access.",
    },
    "SR": {
        "aws": "Use AWS Artifact and Marketplace vendor security reviews; verify AMI/package provenance and signatures before use.",
        "azure": "Use Microsoft's Trust Center attestations and verify Marketplace image provenance before use.",
        "gcp": "Use Google's compliance reports and verify Marketplace image provenance before use.",
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


def tailor_control(control, technologies, audience):
    """
    control: flat control dict from data/controls.json
    technologies: list of technology keys (see TECHNOLOGIES)
    audience: one of AUDIENCES keys
    Returns a dict: {audience, intro, items: [{technology, guidance}]}
    """
    family = control.get("family")
    intro = AUDIENCE_INTRO.get(family, {}).get(
        audience,
        f"As the {AUDIENCES.get(audience, audience)}, focus on {AUDIENCE_FOCUS.get(audience, '')}.",
    )

    items = []
    for tech in technologies:
        if tech not in TECHNOLOGIES:
            continue
        family_map = FAMILY_TECH_GUIDANCE.get(family, {})
        guidance = family_map.get(tech) or generic_guidance(control, tech)
        items.append({"technology": tech, "technology_name": TECHNOLOGIES[tech], "guidance": guidance})

    return {
        "audience": audience,
        "audience_name": AUDIENCES.get(audience, audience),
        "intro": intro,
        "items": items,
    }
