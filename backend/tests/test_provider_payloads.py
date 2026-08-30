"""Timestamp extraction checked against realistic provider payloads.

The connector timestamp mappings were written from provider documentation
rather than observed traffic, which left a real risk: if a field name is wrong
for an actual payload, ``event_time`` stays NULL, those alerts drop out of the
detection-latency sample, and the only symptom is a smaller ``n`` — which reads
as a quiet period rather than a broken mapping.

Verifying against live tenants needs paid or trial accounts (Slack audit logs
require Enterprise Grid; Entra sign-in logs require a P1 licence). What does not
need an account is the payload *shape*: every provider documents it, and the
push-ingest endpoint parses through exactly the same code as polling.

So these fixtures are realistic event bodies in each provider's documented
shape, exercised through the real normalisers. They cannot prove a provider
sends what its documentation claims. They do prove that when it does, we read
it correctly — and they will fail loudly if someone edits a field name.

Sources, for anyone re-checking them later:
  * GitHub code scanning alert   — docs.github.com REST code-scanning
  * Slack audit log entry        — api.slack.com/admins/audit-logs
  * Google Workspace activity    — developers.google.com/admin-sdk/reports
  * Microsoft Graph signIn       — learn.microsoft.com Graph signin resource
  * Generic webhook              — our own documented push shape
"""

from datetime import datetime, timezone

import pytest

from app.services.connector_service import (
    _normalize_azuread_event,
    _normalize_event,
    _normalize_github_alert,
    _normalize_gworkspace_event,
    _normalize_slack_audit_event,
    _resolve_zone,
)

# --- Realistic payloads, trimmed to the fields we read -----------------------

GITHUB_CODE_SCANNING = {
    "number": 4,
    "created_at": "2026-02-19T14:26:03Z",
    "updated_at": "2026-02-19T14:30:00Z",
    "state": "open",
    "rule": {
        "id": "js/zipslip",
        "severity": "error",
        "description": "Arbitrary file write during zip extraction",
    },
    "tool": {"name": "CodeQL"},
    "repository": {"full_name": "acme/payments-api"},
    "html_url": "https://github.com/acme/payments-api/security/code-scanning/4",
}

SLACK_AUDIT_ENTRY = {
    "id": "0123a45b-6c7d-8900-e12f-3456789a012b",
    "date_create": 1771511163,  # 2026-02-19T14:26:03Z
    "action": "user_login_failed",
    "actor": {
        "type": "user",
        "user": {
            "id": "W123AB456",
            "name": "Jo Bloggs",
            "email": "jo@acme.com",
        },
    },
    "entity": {"type": "user"},
    "context": {"ip_address": "203.0.113.9", "ua": "Mozilla/5.0"},
}

GWORKSPACE_ACTIVITY = {
    "kind": "admin#reports#activity",
    "id": {
        "time": "2026-02-19T14:26:03.000Z",
        "uniqueQualifier": "-1234567890",
        "applicationName": "login",
        "customerId": "C03az79cb",
    },
    "actor": {"email": "jo@acme.com", "profileId": "1234567890"},
    "ipAddress": "203.0.113.9",
    "events": [
        {
            "type": "login",
            "name": "login_failure",
            "parameters": [{"name": "login_type", "value": "google_password"}],
        }
    ],
}

AZUREAD_SIGNIN = {
    "id": "66ea54eb-blah-4d4a-a3d1-1e5a1a1b1c1d",
    "createdDateTime": "2026-02-19T14:26:03Z",
    "userPrincipalName": "jo@acme.com",
    "userDisplayName": "Jo Bloggs",
    "appDisplayName": "Microsoft Office 365 Portal",
    "ipAddress": "203.0.113.9",
    "status": {"errorCode": 50126, "failureReason": "Invalid username or password"},
    "location": {"city": "London", "countryOrRegion": "GB"},
}

AZUREAD_AUDIT = {
    "id": "Directory_ABC123",
    "activityDateTime": "2026-02-19T14:26:03Z",
    "activityDisplayName": "Add member to role",
    "result": "success",
    "initiatedBy": {"user": {"userPrincipalName": "admin@acme.com"}},
}

GENERIC_WEBHOOK = {
    "message": "Multiple failed logins from a single address",
    "severity": "HIGH",
    "source_ip": "203.0.113.9",
    "timestamp": "2026-02-19T14:26:03Z",
    "mitre_technique_id": "T1110",
}

EXPECTED = datetime(2026, 2, 19, 14, 26, 3, tzinfo=timezone.utc)


# --- Each provider's documented timestamp is read correctly ------------------

@pytest.mark.parametrize(
    "name,normalized",
    [
        ("github", _normalize_github_alert(GITHUB_CODE_SCANNING)),
        ("slack", _normalize_slack_audit_event(SLACK_AUDIT_ENTRY)),
        ("gworkspace", _normalize_gworkspace_event(GWORKSPACE_ACTIVITY)),
        ("azuread-signin", _normalize_azuread_event(AZUREAD_SIGNIN)),
        ("azuread-audit", _normalize_azuread_event(AZUREAD_AUDIT)),
        ("generic", _normalize_event(GENERIC_WEBHOOK)),
    ],
)
def test_event_time_is_extracted(name, normalized):
    assert normalized is not None, f"{name}: payload was rejected outright"
    got = normalized.get("event_time")
    assert got is not None, (
        f"{name}: no event_time extracted. The field mapping is wrong for this "
        "shape, and alerts from this source would silently leave the "
        "detection-latency sample."
    )
    assert got == EXPECTED, f"{name}: parsed {got}, expected {EXPECTED}"


# --- The rest of the mapping still works on the same payloads ----------------

def test_github_carries_severity_and_repository():
    n = _normalize_github_alert(GITHUB_CODE_SCANNING)
    assert n["severity"] == "HIGH"  # "error" maps to HIGH
    assert "payments-api" in n["message"]


def test_slack_extracts_the_actor_and_address():
    n = _normalize_slack_audit_event(SLACK_AUDIT_ENTRY)
    assert "jo@acme.com" in n["message"]
    assert n["source_ip"] == "203.0.113.9"
    assert n["severity"] == "HIGH"  # a failed login is not routine


def test_gworkspace_extracts_the_actor_and_address():
    n = _normalize_gworkspace_event(GWORKSPACE_ACTIVITY)
    assert "jo@acme.com" in n["message"]
    assert n["source_ip"] == "203.0.113.9"


def test_azuread_signin_reports_the_failure():
    n = _normalize_azuread_event(AZUREAD_SIGNIN)
    assert "jo@acme.com" in n["message"]
    assert n["source_ip"] == "203.0.113.9"
    assert n["severity"] == "HIGH"


# --- Shape drift is caught, not silently dropped -----------------------------

def test_a_renamed_timestamp_field_yields_no_event_time():
    """If a provider renames its field, we must get NULL — never a wrong time.

    This is the failure mode per-source coverage reporting is designed to make
    visible: the source shows 0% and the operator is told to check the mapping.
    """
    drifted = dict(GITHUB_CODE_SCANNING)
    drifted.pop("created_at")
    drifted.pop("updated_at")
    drifted["published_at"] = "2026-02-19T14:26:03Z"  # a field we do not read

    n = _normalize_github_alert(drifted)
    assert n["event_time"] is None


def test_a_provider_sending_local_time_needs_its_zone_declared():
    """Without an offset there is no way to tell local time from UTC."""
    naive = dict(GITHUB_CODE_SCANNING, created_at="2026-02-19T09:26:03")

    as_utc = _normalize_github_alert(naive)["event_time"]
    assert as_utc.isoformat() == "2026-02-19T09:26:03+00:00"

    as_declared = _normalize_github_alert(
        naive, tz=_resolve_zone("America/New_York")
    )["event_time"]
    assert as_declared.isoformat() == "2026-02-19T14:26:03+00:00"


# --- End to end through the push endpoint, no provider account required ------

def test_push_ingest_records_event_time_from_a_real_payload(client, admin_headers, db_session):
    """The route an operator can use to verify a mapping without credentials.

    Configure the connector, POST a captured payload to the webhook, and check
    that event_time landed. This exercises the same normaliser the poller uses.
    """
    from app.models import SecurityAlert

    saved = client.put(
        "/api/v1/connectors/okta/config",
        headers=admin_headers,
        json={"mode": "push", "ingest_token": "verify-me"},
    )
    assert saved.status_code == 200

    posted = client.post(
        "/api/v1/connectors/ingest/okta",
        headers={"X-Connector-Token": "verify-me"},
        json={"events": [GENERIC_WEBHOOK]},
    )
    assert posted.status_code == 201, posted.text
    assert posted.json()["ingested"] == 1

    alert = (
        db_session.query(SecurityAlert)
        .filter(SecurityAlert.source == "okta")
        .order_by(SecurityAlert.id.desc())
        .first()
    )
    assert alert is not None
    assert alert.event_time is not None, "the webhook path must record event_time too"
