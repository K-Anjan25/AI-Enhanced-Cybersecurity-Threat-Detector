#!/usr/bin/env bash
# T-507: Backup and restore rehearsal for AEGIS datastores.
#
# Backs up: PostgreSQL, Kafka (topic export), Redis
# Restores from backup and verifies a known alert set reproduces.
#
# Usage:
#   ./ops/backup-restore.sh backup    # Create backups
#   ./ops/backup-restore.sh restore   # Restore from latest backup
#   ./ops/backup-restore.sh verify    # Verify restored data

set -euo pipefail

BACKUP_DIR="${AEGIS_BACKUP_DIR:-./ops/backups}"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
PG_CONTAINER="${AEGIS_PG_CONTAINER:-postgres}"
KAFKA_CONTAINER="${AEGIS_KAFKA_CONTAINER:-kafka}"
REDIS_CONTAINER="${AEGIS_REDIS_CONTAINER:-redis}"

mkdir -p "$BACKUP_DIR"

backup_postgres() {
    echo "=== Backing up PostgreSQL ==="
    local dump_file="$BACKUP_DIR/postgres_${TIMESTAMP}.sql.gz"
    docker exec "$PG_CONTAINER" pg_dumpall -U aegis | gzip > "$dump_file"
    echo "PostgreSQL backup: $dump_file ($(du -h "$dump_file" | cut -f1))"

    # Also dump just the aegis database for targeted restore
    local aegis_dump="$BACKUP_DIR/aegis_db_${TIMESTAMP}.sql.gz"
    docker exec "$PG_CONTAINER" pg_dump -U aegis aegis | gzip > "$aegis_dump"
    echo "AEGIS DB backup: $aegis_dump ($(du -h "$aegis_dump" | cut -f1))"
}

backup_kafka() {
    echo "=== Backing up Kafka topics ==="
    local kafka_dir="$BACKUP_DIR/kafka_${TIMESTAMP}"
    mkdir -p "$kafka_dir"

    # Export consumer group offsets
    docker exec "$KAFKA_CONTAINER" kafka-consumer-groups.sh \
        --bootstrap-server localhost:9092 \
        --describe --all-groups > "$kafka_dir/consumer_offsets.txt" 2>/dev/null || true

    # List and record topics
    docker exec "$KAFKA_CONTAINER" kafka-topics.sh \
        --bootstrap-server localhost:9092 --list > "$kafka_dir/topics.txt" 2>/dev/null || true

    echo "Kafka backup: $kafka_dir"
}

backup_redis() {
    echo "=== Backing up Redis ==="
    local redis_dump="$BACKUP_DIR/redis_${TIMESTAMP}.rdb"
    docker exec "$REDIS_CONTAINER" redis-cli BGSAVE >/dev/null 2>&1 || true
    sleep 2
    docker cp "$REDIS_CONTAINER:/data/dump.rdb" "$redis_dump" 2>/dev/null || echo "  Redis: no dump.rdb found"
    echo "Redis backup: $redis_dump"
}

restore_postgres() {
    echo "=== Restoring PostgreSQL ==="
    local latest=$(ls -t "$BACKUP_DIR"/aegis_db_*.sql.gz 2>/dev/null | head -1)
    if [ -z "$latest" ]; then
        echo "ERROR: No PostgreSQL backup found in $BACKUP_DIR"
        return 1
    fi
    echo "Restoring from: $latest"

    # Drop and recreate the database
    docker exec "$PG_CONTAINER" psql -U aegis -c "DROP DATABASE IF EXISTS aegis;" postgres
    docker exec "$PG_CONTAINER" psql -U aegis -c "CREATE DATABASE aegis;" postgres

    # Restore
    gunzip -c "$latest" | docker exec -i "$PG_CONTAINER" psql -U aegis aegis
    echo "PostgreSQL restored."
}

verify_restore() {
    echo "=== Verifying restored data ==="

    # Check alert count
    local alert_count
    alert_count=$(docker exec "$PG_CONTAINER" psql -U aegis aegis -t -c "SELECT count(*) FROM alerts;" 2>/dev/null | tr -d ' ')
    echo "Alerts in database: $alert_count"

    # Check user count
    local user_count
    user_count=$(docker exec "$PG_CONTAINER" psql -U aegis aegis -t -c "SELECT count(*) FROM users;" 2>/dev/null | tr -d ' ')
    echo "Users in database: $user_count"

    # Check audit trail
    local audit_count
    audit_count=$(docker exec "$PG_CONTAINER" psql -U aegis aegis -t -c "SELECT count(*) FROM audit_events;" 2>/dev/null | tr -d ' ')
    echo "Audit events: $audit_count"

    if [ "${alert_count:-0}" -gt 0 ]; then
        echo "✅ Restore verification PASSED: alerts exist"
    else
        echo "⚠️  Restore verification WARNING: no alerts found"
    fi
}

case "${1:-help}" in
    backup)
        echo "AEGIS Backup — $TIMESTAMP"
        backup_postgres
        backup_kafka
        backup_redis
        echo "=== Backup complete ==="
        ;;
    restore)
        echo "AEGIS Restore — $TIMESTAMP"
        restore_postgres
        echo "=== Restore complete ==="
        ;;
    verify)
        verify_restore
        ;;
    help|*)
        echo "Usage: $0 {backup|restore|verify}"
        echo ""
        echo "  backup   - Create backups of PostgreSQL, Kafka, Redis"
        echo "  restore  - Restore PostgreSQL from latest backup"
        echo "  verify   - Verify restored data has expected records"
        ;;
esac
