#!/bin/bash
# One capture container, several engines. Each engine runs as a pipeline: the engine
# writes its log, `tail -F` follows it, and a bridge posts the records to the AEGIS API.
#
# Engines are chosen with AEGIS_CAPTURE_ENGINES (comma-separated):
#   zeek      connection log (conn.log) -> flows            (default)
#   suricata  alerts, DNS, HTTP and TLS -> logs             (default)
#   tshark    packet-level flow aggregation -> flows        (opt-in: duplicates zeek's flows)
#
# The container exits if any engine or bridge exits, so the restart policy brings the
# whole set back together rather than leaving one engine silently down.
set -euo pipefail

# Refuse the development default password; see docker/.env.example.
if [ -z "${AEGIS_PASSWORD:-}" ] || [ "${AEGIS_PASSWORD}" = "admin123456789" ]; then  # pragma: allowlist secret
    echo "refusing to start: set AEGIS_PASSWORD (AEGIS_BOOTSTRAP_ADMIN_PASSWORD in docker/.env) to a value other than the development default" >&2
    exit 2
fi

ENGINES="${AEGIS_CAPTURE_ENGINES:-zeek,suricata}"
API_URL="${AEGIS_API_URL:-http://backend:8000}"
EMAIL="${AEGIS_EMAIL:-admin@aegis.local}"
ZEEK_IFACE="${AEGIS_ZEEK_INTERFACE:-eth0}"
SURICATA_IFACE="${AEGIS_SURICATA_INTERFACE:-eth0}"
TSHARK_IFACE="${AEGIS_TSHARK_INTERFACE:-any}"
ZEEK_LOG_DIR="/tmp/zeek-logs"
SURICATA_LOG_DIR="/var/log/suricata"

PIDS=()

cleanup() {
    echo "[CAPTURE] Shutting down..."
    for pid in "${PIDS[@]}"; do
        kill "$pid" 2>/dev/null || true
    done
    wait 2>/dev/null || true
}
trap 'cleanup; exit 0' SIGTERM SIGINT

wait_for_file() {
    # $1 = path, $2 = name for messages. Gives the engine 60 s to create its log.
    for _ in $(seq 1 60); do
        [ -f "$1" ] && return 0
        sleep 1
    done
    echo "[$2] ERROR: $1 not created after 60s" >&2
    return 1
}

start_zeek() {
    mkdir -p "$ZEEK_LOG_DIR"
    echo "[ZEEK] Starting on $ZEEK_IFACE"
    # -C: ignore TCP checksums. NIC offload (and Docker Desktop's VM) produces packets
    # with invalid checksums, which Zeek otherwise discards without recording them.
    (cd "$ZEEK_LOG_DIR" && exec zeek -C -i "$ZEEK_IFACE" local) &
    PIDS+=("$!")
    wait_for_file "$ZEEK_LOG_DIR/conn.log" ZEEK || exit 1
    tail -n +1 -F "$ZEEK_LOG_DIR/conn.log" | python3 -u /app/zeek_bridge.py \
        --log-type conn --api "$API_URL" --email "$EMAIL" --password "$AEGIS_PASSWORD" &
    PIDS+=("$!")
}

start_suricata() {
    mkdir -p "$SURICATA_LOG_DIR"
    echo "[SURICATA] Starting on $SURICATA_IFACE"
    # eve-log is enabled by the stock suricata.yaml. Do not override it with --set:
    # outputs is a YAML list in Suricata 6, so "outputs.eve-log.*" fails.
    suricata -i "$SURICATA_IFACE" -l "$SURICATA_LOG_DIR" &
    PIDS+=("$!")
    wait_for_file "$SURICATA_LOG_DIR/eve.json" SURICATA || exit 1
    tail -n +1 -F "$SURICATA_LOG_DIR/eve.json" | python3 -u /app/suricata_bridge.py \
        --api "$API_URL" --email "$EMAIL" --password "$AEGIS_PASSWORD" &
    PIDS+=("$!")
}

start_tshark() {
    echo "[TSHARK] Starting on $TSHARK_IFACE"
    tshark -i "$TSHARK_IFACE" -T fields \
        -e frame.time_epoch -e ip.src -e ip.dst -e tcp.srcport -e tcp.dstport \
        -e udp.srcport -e udp.dstport -e ip.proto -e frame.len -e dns.qry.name -l \
        2>/dev/null | python3 -u /app/tcpdump_bridge.py --format tshark \
        --api "$API_URL" --email "$EMAIL" --password "$AEGIS_PASSWORD" &
    PIDS+=("$!")
}

echo "============================================"
echo "  AEGIS network capture"
echo "  Engines: $ENGINES"
echo "  API:     $API_URL"
echo "============================================"

IFS=',' read -r -a ENGINE_LIST <<< "$ENGINES"
for engine in "${ENGINE_LIST[@]}"; do
    case "$engine" in
        zeek) start_zeek ;;
        suricata) start_suricata ;;
        tshark) start_tshark ;;
        *)
            echo "refusing to start: unknown engine '$engine' in AEGIS_CAPTURE_ENGINES" >&2
            cleanup
            exit 2
            ;;
    esac
done

if [ "${#PIDS[@]}" -eq 0 ]; then
    echo "refusing to start: AEGIS_CAPTURE_ENGINES names no engine" >&2
    exit 2
fi

# Supervise: the first child to exit ends the container (the restart policy restarts it).
wait -n "${PIDS[@]}" || true
echo "[CAPTURE] An engine or bridge exited; stopping the container" >&2
cleanup
exit 1
