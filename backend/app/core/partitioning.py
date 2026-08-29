"""Phase 73: DB partitioning for time-series tables.

Implements monthly RANGE partitioning for security_alerts, audit_logs, scanned_alerts, hunt_executions.
For SQLite tests, this is a no-op. For Postgres, creates partitions if DB_PARTITIONING_ENABLED.

Usage:
- Call ensure_partitions(engine, org_id=None) on startup or via cron monthly.
- Creates partitions for current month + next 2 months.
"""

import logging
from datetime import datetime, timezone, timedelta
from sqlalchemy import text

_LOGGER = logging.getLogger("app")

PARTITIONED_TABLES = [
    "security_alerts",
    "audit_logs",
    "scanned_alerts",
    "hunt_executions",
    "vuln_scans",
    "event_bus_messages",
]

def _month_range(year: int, month: int):
    """Return start and end date for month."""
    start = datetime(year, month, 1, tzinfo=timezone.utc)
    if month == 12:
        end = datetime(year+1, 1, 1, tzinfo=timezone.utc)
    else:
        end = datetime(year, month+1, 1, tzinfo=timezone.utc)
    return start, end

def ensure_partitions(engine, months_ahead: int = 3) -> None:
    """Create monthly partitions for next N months. Postgres only, idempotent."""
    try:
        dialect = engine.dialect.name
        if dialect != "postgresql":
            _LOGGER.info(f"Partitioning skipped for dialect {dialect} (only postgres)")
            return

        from app.core.config import settings
        if not getattr(settings, "DB_PARTITIONING_ENABLED", False):
            _LOGGER.info("Partitioning disabled via DB_PARTITIONING_ENABLED=False")
            return

        now = datetime.now(timezone.utc)
        with engine.begin() as conn:
            # Check if parent tables are partitioned, if not, convert
            for table in PARTITIONED_TABLES:
                # Check if table exists and is partitioned
                try:
                    # Create parent as partitioned if not already
                    # This is a best-effort: we assume tables were created with partitioning via migration
                    # Here we just ensure child partitions exist
                    for i in range(months_ahead):
                        target = now + timedelta(days=30*i)
                        year, month = target.year, target.month
                        start, end = _month_range(year, month)
                        partition_name = f"{table}_p{year}{month:02d}"
                        # Create partition table
                        conn.execute(text(f"""
                            CREATE TABLE IF NOT EXISTS {partition_name} PARTITION OF {table}
                            FOR VALUES FROM ('{start.date()}') TO ('{end.date()}')
                        """))
                        _LOGGER.info(f"Ensured partition {partition_name}")
                except Exception as exc:
                    _LOGGER.warning(f"Partition creation for {table} failed: {exc}")
    except Exception as exc:
        _LOGGER.warning(f"ensure_partitions failed: {exc}")

def get_partition_pruning_hint(org_id: int, start_date: datetime, end_date: datetime) -> str:
    """Return SQL hint for partition pruning (for documentation)."""
    return f"/* Partition pruning: org_id={org_id}, {start_date} to {end_date} */"
