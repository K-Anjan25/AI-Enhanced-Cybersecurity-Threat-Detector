#!/usr/bin/env python3
"""Windows Event Log / syslog feeder for AEGIS.

Reads system logs from:
  - Windows Event Log (Security, System, Application)
  - Linux syslog / journalctl
  - Custom log files

Sends them to AEGIS /api/v1/ingest/logs endpoint.
"""

import json
import os
import platform
import subprocess
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone

API_BASE = os.environ.get("AEGIS_API", "http://localhost:8000")
EMAIL = os.environ.get("AEGIS_EMAIL", "admin@aegis.local")
PASSWORD = os.environ.get("AEGIS_PASSWORD", "admin123456789")
TOKEN = None
BATCH_SIZE = 50
INTERVAL = 10  # seconds between batches


def auth() -> str:
    """Get auth token."""
    global TOKEN
    if TOKEN:
        return TOKEN
    data = json.dumps({"email": EMAIL, "password": PASSWORD}).encode()
    req = urllib.request.Request(
        f"{API_BASE}/api/v1/auth/login",
        data=data,
        headers={"Content-Type": "application/json"},
    )
    try:
        resp = urllib.request.urlopen(req)
        result = json.loads(resp.read())
        TOKEN = result["access_token"]
        return TOKEN
    except Exception as e:
        print(f"Auth failed: {e}", file=sys.stderr)
        return ""


def send_logs(logs: list[dict]) -> dict | None:
    """Send a batch of log records to AEGIS."""
    token = auth()
    if not token:
        return None
    # Send as NDJSON
    body = "\n".join(json.dumps(log) for log in logs)
    req = urllib.request.Request(
        f"{API_BASE}/api/v1/ingest/logs",
        data=body.encode(),
        headers={
            "Content-Type": "application/x-ndjson",
            "Authorization": f"Bearer {token}",
        },
    )
    try:
        resp = urllib.request.urlopen(req)
        return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        print(f"Send failed: {e.code} {e.read().decode()}", file=sys.stderr)
        if e.code == 401:
            global TOKEN
            TOKEN = None
        return None
    except Exception as e:
        print(f"Send error: {e}", file=sys.stderr)
        return None


def get_windows_events(log_name: str = "Security", count: int = 50) -> list[dict]:
    """Read Windows Event Log entries using PowerShell."""
    if platform.system() != "Windows":
        return []
    try:
        ps_cmd = (
            f'Get-WinEvent -LogName {log_name} -MaxEvents {count} '
            f'| Select-Object TimeCreated, Id, LevelDisplayName, ProviderName, Message '
            f'| ConvertTo-Json -Compress'
        )
        result = subprocess.run(
            ["powershell", "-Command", ps_cmd],
            capture_output=True, text=True, timeout=30
        )
        if result.returncode != 0:
            return []
        events = json.loads(result.stdout)
        if isinstance(events, dict):
            events = [events]
        logs = []
        for evt in events:
            level_map = {"Critical": "critical", "Error": "error", "Warning": "warning",
                        "Information": "info", "Verbose": "debug"}
            level = level_map.get(evt.get("LevelDisplayName", ""), "info")
            ts = evt.get("TimeCreated", "")
            logs.append({
                "ts": ts,
                "level": level,
                "host": platform.node(),
                "service": f"windows/{log_name}",
                "message": f"[EventID:{evt.get('Id',0)}] {evt.get('ProviderName','')}: {evt.get('Message','')[:500]}",
                "source": "windows_eventlog",
                "metadata": {
                    "event_id": evt.get("Id"),
                    "provider": evt.get("ProviderName"),
                    "log_name": log_name,
                }
            })
        return logs
    except Exception as e:
        print(f"Windows Event Log read error: {e}", file=sys.stderr)
        return []


def get_linux_syslog(count: int = 50) -> list[dict]:
    """Read recent syslog entries."""
    if platform.system() != "Linux":
        return []
    try:
        result = subprocess.run(
            ["journalctl", "--no-pager", "-n", str(count), "--output=json"],
            capture_output=True, text=True, timeout=30
        )
        if result.returncode != 0:
            # Try /var/log/syslog
            try:
                with open("/var/log/syslog") as f:
                    lines = f.readlines()[-count:]
                return [{
                    "ts": datetime.now(timezone.utc).isoformat(),
                    "level": "info",
                    "host": platform.node(),
                    "service": "syslog",
                    "message": line.strip()[:500],
                    "source": "linux_syslog",
                } for line in lines if line.strip()]
            except FileNotFoundError:
                return []
        logs = []
        for line in result.stdout.strip().split("\n"):
            if not line:
                continue
            try:
                entry = json.loads(line)
                ts = entry.get("__REALTIME_TIMESTAMP", "")
                if ts:
                    ts = datetime.fromtimestamp(int(ts) / 1_000_000, tz=timezone.utc).isoformat()
                priority = entry.get("PRIORITY", 6)
                level_map = {0: "critical", 1: "critical", 2: "critical", 3: "error",
                            4: "warning", 5: "warning", 6: "info", 7: "debug"}
                logs.append({
                    "ts": ts or datetime.now(timezone.utc).isoformat(),
                    "level": level_map.get(priority, "info"),
                    "host": entry.get("_HOSTNAME", platform.node()),
                    "service": entry.get("SYSLOG_IDENTIFIER", "journal"),
                    "message": entry.get("MESSAGE", "")[:500],
                    "source": "linux_journal",
                    "metadata": {
                        "pid": entry.get("_PID"),
                        "unit": entry.get("_SYSTEMD_UNIT"),
                    }
                })
            except json.JSONDecodeError:
                continue
        return logs
    except Exception as e:
        print(f"Linux syslog read error: {e}", file=sys.stderr)
        return []


def generate_network_logs() -> list[dict]:
    """Generate realistic network/security log entries for demo."""
    import random
    import socket
    now = datetime.now(timezone.utc)
    hostname = socket.gethostname()
    entries = []

    # Firewall logs
    firewall_actions = [
        ("BLOCK", "TCP", 443, "External IP attempted connection to blocked port"),
        ("ALLOW", "TCP", 80, "HTTP traffic to web server"),
        ("BLOCK", "UDP", 53, "DNS query blocked by policy"),
        ("ALLOW", "TCP", 22, "SSH connection from admin workstation"),
        ("BLOCK", "TCP", 3389, "RDP attempt from unknown source"),
        ("ALERT", "TCP", 4444, "Suspicious port 4444 connection detected"),
    ]
    for _ in range(random.randint(3, 8)):
        action, proto, port, msg = random.choice(firewall_actions)
        src_ip = f"192.168.{random.randint(1,254)}.{random.randint(1,254)}"
        dst_ip = f"10.0.{random.randint(0,255)}.{random.randint(1,254)}"
        entries.append({
            "ts": now.isoformat(),
            "level": "warning" if action == "BLOCK" else "info",
            "host": hostname,
            "service": "firewall",
            "message": f"{action} {proto} {src_ip}:{random.randint(1024,65535)} -> {dst_ip}:{port} - {msg}",
            "source": "firewall",
            "metadata": {"action": action, "proto": proto, "src_ip": src_ip, "dst_ip": dst_ip, "port": port}
        })

    # IDS/IPS logs
    signatures = [
        ("ET MALWARE", "critical", "Cobalt Strike Beacon detected"),
        ("ET SCAN", "warning", "Nmap SYN scan detected"),
        ("GPL ATTACK", "high", "SQL injection attempt"),
        ("ET TROJAN", "critical", "Known C2 domain contacted"),
        ("ET INFO", "info", "User-Agent known scanner"),
        ("SURICATA TLS", "info", "TLS certificate anomaly"),
    ]
    for _ in range(random.randint(2, 5)):
        sig, severity, desc = random.choice(signatures)
        src_ip = f"{random.randint(10,200)}.{random.randint(0,255)}.{random.randint(0,255)}.{random.randint(1,254)}"
        entries.append({
            "ts": now.isoformat(),
            "level": severity,
            "host": hostname,
            "service": "suricata",
            "message": f"[{sig}] {desc} - src:{src_ip} dst:10.0.0.{random.randint(1,50)} sid:{random.randint(2000000,2999999)}",
            "source": "ids",
            "metadata": {"signature": sig, "severity": severity}
        })

    # Authentication logs
    auth_events = [
        ("error", "Failed password for admin from 203.0.113.42 port 22 ssh2"),
        ("warning", "Failed login attempt for user 'root' from 198.51.100.10"),
        ("info", "Accepted publickey for deploy from 10.0.1.5 port 54321"),
        ("warning", "Account lockout: too many failed attempts for 'admin'"),
        ("error", "PAM authentication failure; logname= uid=0 euid=0"),
        ("info", "Session opened for user aegis by (uid=0)"),
    ]
    for _ in range(random.randint(2, 6)):
        level, msg = random.choice(auth_events)
        entries.append({
            "ts": now.isoformat(),
            "level": level,
            "host": hostname,
            "service": "sshd",
            "message": msg,
            "source": "auth",
        })

    # DNS logs
    suspicious_domains = [
        "malware-c2.evil.com", "data-exfil.bad.net", "cryptominer.shady.org",
        "phishing-login.fake.com", "botnet-cnc.dark.net",
    ]
    for _ in range(random.randint(1, 3)):
        domain = random.choice(suspicious_domains)
        entries.append({
            "ts": now.isoformat(),
            "level": "warning",
            "host": hostname,
            "service": "dns",
            "message": f"Query for suspicious domain: {domain} from 192.168.1.{random.randint(10,50)}",
            "source": "dns",
            "metadata": {"domain": domain, "query_type": "A"}
        })

    return entries


def main():
    """Main loop: read logs and send to AEGIS."""
    print(f"AEGIS Log Feeder")
    print(f"API: {API_BASE}")
    print(f"Platform: {platform.system()}")
    print()

    # Authenticate
    token = auth()
    if not token:
        print("ERROR: Could not authenticate. Check AEGIS_EMAIL and AEGIS_PASSWORD.", file=sys.stderr)
        sys.exit(1)
    print("Authenticated successfully.")
    print()

    mode = sys.argv[1] if len(sys.argv) > 1 else "auto"
    total_sent = 0

    try:
        while True:
            logs = []

            if mode == "windows" or (mode == "auto" and platform.system() == "Windows"):
                logs.extend(get_windows_events("Security", 20))
                logs.extend(get_windows_events("System", 10))
                logs.extend(get_windows_events("Application", 10))
                print(f"[Windows] Read {len(logs)} event log entries")

            elif mode == "linux" or (mode == "auto" and platform.system() == "Linux"):
                logs.extend(get_linux_syslog(40))
                print(f"[Linux] Read {len(logs)} syslog entries")

            elif mode == "network" or mode == "auto":
                logs.extend(generate_network_logs())
                print(f"[Network] Generated {len(logs)} security log entries")

            if logs:
                result = send_logs(logs)
                if result:
                    accepted = result.get("accepted", 0)
                    total_sent += accepted
                    print(f"  Sent: {accepted}/{len(logs)} accepted (total: {total_sent})")
                else:
                    print(f"  Failed to send batch")
            else:
                print(f"  No logs to send")

            time.sleep(INTERVAL)

    except KeyboardInterrupt:
        print(f"\nStopped. Total logs sent: {total_sent}")


if __name__ == "__main__":
    main()