"""MITRE ATT&CK mapping for detections.

Maps an alert (alert_type + message) to a MITRE ATT&CK tactic and technique
via lightweight keyword rules. In production this can be upgraded to a full
MITRE ATT&CK dataset feed; the interface (``map_alert``) stays the same.
"""

from __future__ import annotations

from typing import Optional

# (tactic, technique_id, technique_name) <- keyword triggers
_RULES: list[tuple[tuple[str, str, str], tuple[str, ...]]] = [
    (("Initial Access", "T1190", "Exploit Public-Facing Application"), ("exploit", "cve", "rce", "remote code")),
    (("Initial Access", "T1078", "Valid Accounts"), ("valid account", "valid credential", "stolen credential")),
    (("Credential Access", "T1110", "Brute Force"), ("brute", "failed login", "failed password", "password spray")),
    (("Credential Access", "T1558", "Steal or Forge Kerberos Tickets"), ("kerberos", "golden ticket", "silver ticket")),
    (("Credential Access", "T1621", "Multi-Factor Authentication Request Generation"), ("mfa", "2fa", "push spam")),
    (("Persistence", "T1547", "Boot or Logon Autostart Execution"), ("autorun", "registry run", "startup")),
    (("Persistence", "T1053", "Scheduled Task/Job"), ("scheduled task", "cron job", "schtasks")),
    (("Privilege Escalation", "T1068", "Exploitation for Privilege Escalation"), ("privilege escalation", "sudo", "uac bypass")),
    (("Defense Evasion", "T1070", "Indicator Removal"), ("clearing logs", "log tampering", "timestomp")),
    (("Defense Evasion", "T1027", "Obfuscated Files or Information"), ("obfuscated", "polymorphic", "packed")),
    (("Discovery", "T1046", "Network Service Discovery"), ("port scan", "service scan", "nmap")),
    (("Discovery", "T1087", "Account Discovery"), ("account enumeration", "user enumeration")),
    (("Lateral Movement", "T1021", "Remote Services"), ("rdp", "smb", "wmi", "winrm", "ps exec")),
    (("Lateral Movement", "T1550", "Use Alternate Authentication Material"), ("pass the hash", "pth", "pass the ticket")),
    (("Collection", "T1005", "Data from Local System"), ("data collection", "sensitive file", "credential dump")),
    (("Exfiltration", "T1041", "Exfiltration Over C2 Channel"), ("exfil", "exfiltration", "data staging")),
    (("Command and Control", "T1071", "Application Layer Protocol"), ("c2", "beacon", "command and control", "dns tunnel")),
    (("Impact", "T1486", "Data Encrypted for Impact"), ("ransomware", "encrypted files", "lockbit")),
    (("Impact", "T1499", "Endpoint Denial of Service"), ("ddos", "denial of service", "flood")),
    (("Execution", "T1059", "Command and Scripting Interpreter"), ("powershell", "cmd.exe", "bash -c", "wscript", "script execution")),
    (("Execution", "T1204", "User Execution"), ("malicious attachment", "macro enabled", "phishing link")),
    (("Initial Access", "T1566", "Phishing"), ("phishing", "spoofed", "spearphishing")),
    (("Credential Access", "T1555", "Credentials from Password Stores"), ("credential vault", "password store", "sam dump")),
    (("Command and Control", "T1105", "Ingress Tool Transfer"), ("tool download", "payload download", "wget", "certutil")),
]

# Network-flow oriented rules keyed on protocol / fields.
_NETWORK_RULES: list[tuple[tuple[str, str, str], tuple[str, ...]]] = [
    (("Lateral Movement", "T1021", "Remote Services"), ("3389", "1433", "445", "5985")),
    (("Discovery", "T1046", "Network Service Discovery"), ("scan", "probe")),
    (("Impact", "T1499", "Endpoint Denial of Service"), ("flood", "ddos", "syn")),
]


def map_alert(alert_type: str | None, message: str | None, source_ip: str | None = None, src_port: str | None = None) -> dict:
    """Return a MITRE ATT&CK mapping ``{tactic, technique_id, technique}``.

    Matches are keyword-based and best-effort; unknown patterns map to
    ``"Unclassified"`` so every alert still carries ATT&CK metadata.
    """
    text = ((message or "") + " " + (source_ip or "") + " " + (src_port or "")).lower()
    for (tactic, tech_id, tech_name), keywords in _RULES:
        if any(k in text for k in keywords):
            return {"tactic": tactic, "technique_id": tech_id, "technique": tech_name}

    if alert_type == "network":
        for (tactic, tech_id, tech_name), keywords in _NETWORK_RULES:
            if any(k in text for k in keywords):
                return {"tactic": tactic, "technique_id": tech_id, "technique": tech_name}

    return {"tactic": "Unclassified", "technique_id": "N/A", "technique": "Unclassified"}
