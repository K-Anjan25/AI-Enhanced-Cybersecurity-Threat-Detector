"""MITRE ATT&CK mapper tests."""

from app.services.mitre import map_alert


def test_brute_force_mapping():
    result = map_alert("system_log", "Failed password for root from 10.0.0.1")
    assert result["tactic"] == "Credential Access"
    assert result["technique_id"] == "T1110"


def test_network_scan_mapping():
    result = map_alert("network", "Nmap scan detected", "10.0.0.5", None)
    assert result["technique_id"] == "T1046"


def test_rdp_lateral_movement():
    result = map_alert("network", "connection to rdp", None, "3389")
    assert result["technique_id"] == "T1021"


def test_unclassified_fallback():
    result = map_alert("system_log", "user logged in")
    assert result["tactic"] == "Unclassified"


def test_phishing_mapping():
    result = map_alert("log", "spearphishing email blocked")
    assert result["technique_id"] == "T1566"


def test_int_port_does_not_crash():
    result = map_alert("system_log", "brute force", "10.0.0.9", 22)
    assert result["technique_id"] == "T1110"
