"""An archive record must point at a file that exists.

Two features logged a destination they never wrote to: retention archival
claimed an `s3://archive/...` path, and compliance export claimed `/tmp/...`
with status "success". In both cases the log is the evidence an auditor reads,
so a success record pointing at nothing is worse than no export at all.
"""

import json

import pytest

from app.services import archive_store

ORG = 1


@pytest.fixture(autouse=True)
def _isolated_archive_root(tmp_path, monkeypatch):
    """Never write into the real archive directory from a test."""
    monkeypatch.setattr(archive_store, "ARCHIVE_ROOT", tmp_path / "archives")
    yield


# ---------------------------------------------------------------------------
# The file is really written
# ---------------------------------------------------------------------------

def test_local_write_creates_a_readable_file():
    result = archive_store.store(
        org_id=ORG, category="retention/alerts", name="2026-01-01.json",
        payload=b'{"hello":"world"}',
    )

    assert result["stored"] is True
    assert result["destination"] == "local"

    from pathlib import Path

    written = Path(result["path"])
    assert written.exists(), "the path in the record must be a real file"
    assert json.loads(written.read_text()) == {"hello": "world"}


def test_path_traversal_in_the_name_is_neutralised():
    result = archive_store.store(
        org_id=ORG, category="retention/../../etc", name="../../passwd",
        payload=b"x",
    )

    assert result["stored"] is True
    assert "/etc/passwd" not in result["path"]
    assert str(archive_store.ARCHIVE_ROOT) in result["path"]


def test_a_write_failure_is_reported_as_a_failure(monkeypatch):
    """Never a success record for a write that did not happen."""
    def _boom(*a, **kw):
        raise OSError("disk full")

    monkeypatch.setattr(archive_store.Path, "write_bytes", _boom)

    result = archive_store.store(
        org_id=ORG, category="retention/alerts", name="x.json", payload=b"x"
    )
    assert result["stored"] is False
    assert "disk full" in result["error"]


def test_configured_s3_without_boto3_fails_rather_than_writing_locally(monkeypatch):
    """Silently redirecting compliance evidence to disk would be a surprise."""
    from app.core.config import settings

    for name, value in (
        ("S3_ENDPOINT", "https://s3.example"), ("S3_BUCKET", "evidence"),
        ("S3_ACCESS_KEY", "k"), ("S3_SECRET_KEY", "s"),
    ):
        monkeypatch.setattr(settings, name, value, raising=False)

    result = archive_store.store(
        org_id=ORG, category="compliance/soc2", name="evidence.pdf", payload=b"%PDF"
    )
    assert result["stored"] is False
    assert "boto3" in result["error"]


def test_destination_is_describable_before_writing():
    described = archive_store.describe_destination()
    assert described["kind"] == "local"
    assert "No object storage is configured" in described["note"]


# ---------------------------------------------------------------------------
# Retention archival
# ---------------------------------------------------------------------------

def test_retention_archive_writes_the_rows_it_counts(db_session):
    from datetime import datetime, timedelta, timezone
    from pathlib import Path

    from app.models import SecurityAlert
    from app.services import data_lifecycle_service

    old = datetime.now(timezone.utc) - timedelta(days=400)
    for i in range(3):
        db_session.add(
            SecurityAlert(org_id=ORG, severity="LOW", source="t", message=f"old{i}", created_at=old)
        )
    db_session.commit()

    res = data_lifecycle_service.archive_old_data(db_session, ORG, data_type="alerts")

    assert res["status"] == "archived"
    assert res["archived_count"] == 3
    written = Path(res["path"])
    assert written.exists()
    records = json.loads(written.read_text())
    assert len(records) == 3
    assert {r["message"] for r in records} == {"old0", "old1", "old2"}


def test_retention_archive_says_when_nothing_is_eligible(db_session):
    from app.services import data_lifecycle_service

    res = data_lifecycle_service.archive_old_data(db_session, ORG, data_type="alerts")
    assert res["status"] == "nothing_eligible"
    assert res["archived_count"] == 0


def test_retention_archive_logs_failure_without_claiming_success(db_session, monkeypatch):
    from datetime import datetime, timedelta, timezone

    from app.models import SecurityAlert
    from app.models.data_lifecycle import DataArchiveLog
    from app.services import data_lifecycle_service

    db_session.add(
        SecurityAlert(
            org_id=ORG, severity="LOW", source="t", message="old",
            created_at=datetime.now(timezone.utc) - timedelta(days=400),
        )
    )
    db_session.commit()

    monkeypatch.setattr(
        archive_store, "store",
        lambda **kw: {"stored": False, "destination": "local", "path": None,
                      "url": None, "error": "disk full"},
    )

    res = data_lifecycle_service.archive_old_data(db_session, ORG, data_type="alerts")

    assert res["status"] == "failed"
    assert res["archived_count"] == 0
    log = db_session.query(DataArchiveLog).order_by(DataArchiveLog.id.desc()).first()
    assert log.status == "failed"
    assert log.archive_path is None


def test_a_large_backlog_is_capped_and_says_so(db_session, monkeypatch):
    """A first run on a big tenant must not build the whole payload in memory."""
    from datetime import datetime, timedelta, timezone

    from app.models import SecurityAlert
    from app.services import data_lifecycle_service

    monkeypatch.setattr(data_lifecycle_service, "_ARCHIVE_BATCH", 5)
    old = datetime.now(timezone.utc) - timedelta(days=400)
    db_session.bulk_save_objects([
        SecurityAlert(org_id=ORG, severity="LOW", source="t", message=f"e{i}", created_at=old)
        for i in range(12)
    ])
    db_session.commit()

    res = data_lifecycle_service.archive_old_data(db_session, ORG, data_type="alerts")

    assert res["archived_count"] == 5
    assert res["eligible_count"] == 12
    assert res["truncated"] is True


# ---------------------------------------------------------------------------
# Compliance export
# ---------------------------------------------------------------------------

def test_compliance_export_writes_a_real_pdf(db_session):
    from pathlib import Path

    from app.models.compliance_pack import ComplianceExportLog
    from app.services import compliance_pack_service

    res = compliance_pack_service.export_to_s3(db_session, ORG, "SOC2", b"%PDF-1.4 real")

    assert res["stored"] is True
    written = Path(res["path"])
    assert written.exists(), "the export log used to point at a file never written"
    assert written.read_bytes() == b"%PDF-1.4 real"

    log = db_session.query(ComplianceExportLog).order_by(ComplianceExportLog.id.desc()).first()
    assert log.status == "success"
    assert log.file_path == res["path"]


def test_compliance_export_records_failure_honestly(db_session, monkeypatch):
    from app.models.compliance_pack import ComplianceExportLog
    from app.services import compliance_pack_service

    monkeypatch.setattr(
        archive_store, "store",
        lambda **kw: {"stored": False, "destination": "s3", "path": None,
                      "url": None, "error": "bucket unreachable"},
    )

    res = compliance_pack_service.export_to_s3(db_session, ORG, "SOC2", b"%PDF")

    assert res["stored"] is False
    log = db_session.query(ComplianceExportLog).order_by(ComplianceExportLog.id.desc()).first()
    assert log.status == "failed"
    assert log.file_path is None
