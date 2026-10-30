#!/bin/bash
# One capture container, several engines. Each engine runs as a pipeline: the engine
# writes its log, `tail -F` follows it, and a bridge posts the records to the AEGIS API.
#
# What runs is set from the control plane (PUT /api/v1/capture/state). This script polls
# that state every AEGIS_CAPTURE_POLL_SECONDS and reconciles to it: it starts the engines
# that are wanted, stops the ones that are not, and restarts one that died while wanted.
# Capture starts stopped. A restart of the container also comes back stopped.
#
# AEGIS_CAPTURE_ENGINES is the allowlist of engines this sensor may run (default
# zeek,suricata). tshark is opt-in: it duplicates zeek's flows.
#   zeek      connection log (conn.log) -> flows
#   suricata  alerts, DNS, HTTP and TLS -> logs
#   tshark    packet-level flow aggregation -> flows
set -euo pipefail

# Refuse the development default password; see docker/.env.example.
if [ -z "${AEGIS_PASSWORD:-}" ] || [ "${AEGIS_PASSWORD}" = "admin123456789" ]; then  # pragma: allowlist secret
    echo "refusing to start: set AEGIS_PASSWORD (AEGIS_BOOTSTRAP_ADMIN_PASSWORD in docker/.env) to a value other than the development default" >&2
    exit 2
fi

ENGINES="${AEGIS_CAPTURE_ENGINES:-zeek,suricata}"
API_URL="${AEGIS_API_URL:-http://backend:8000}"
EMAIL="${AEGIS_EMAIL:-admin@aegis.local}"
APP_DIR="${AEGIS_APP_DIR:-/app}"
POLL_SECONDS="${AEGIS_CAPTURE_POLL_SECONDS:-5}"
# Refuse a typo before anything starts, so a partial engine set is never run.
if [ -z "${ENGINES//[, ]/}" ]; then
    echo "refusing to start: AEGIS_CAPTURE_ENGINES names no engine" >&2
    exit 2
fi
for engine in ${ENGINES//,/ }; do
    case "$engine" in
        zeek|suricata|tshark) ;;
        *)
            echo "refusing to start: unknown engine '$engine' in AEGIS_CAPTURE_ENGINES" >&2
            exit 2
            ;;
    esac
done
ZEEK_IFACE="${AEGIS_ZEEK_INTERFACE:-eth0}"
SURICATA_IFACE="${AEGIS_SURICATA_INTERFACE:-eth0}"
TSHARK_IFACE="${AEGIS_TSHARK_INTERFACE:-any}"
ZEEK_LOG_DIR="/tmp/zeek-logs"
SURICATA_LOG_DIR="/var/log/suricata"
ENGINE_ORDER=(zeek suricata tshark)

declare -A ENGINE_RUNNING=()

cleanup() {
    echo "[CAPTURE] Shutting down..."
    for e in "${ENGINE_ORDER[@]}"; do stop_engine "$e"; done
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
    rm -f "$ZEEK_LOG_DIR/conn.log"  # a fresh log, so tail does not replay the last run
    echo "[ZEEK] Starting on $ZEEK_IFACE"
    # -C: ignore TCP checksums. NIC offload (and Docker Desktop's VM) produces packets
    # with invalid checksums, which Zeek otherwise discards without recording them.
    (cd "$ZEEK_LOG_DIR" && exec zeek -C -i "$ZEEK_IFACE" local) &
    wait_for_file "$ZEEK_LOG_DIR/conn.log" ZEEK || return 1
    tail -n +1 -F "$ZEEK_LOG_DIR/conn.log" | python3 -u "$APP_DIR/zeek_bridge.py" \
        --log-type conn --api "$API_URL" --email "$EMAIL" --password "$AEGIS_PASSWORD" &
}

start_suricata() {
    mkdir -p "$SURICATA_LOG_DIR"
    rm -f "$SURICATA_LOG_DIR/eve.json"
    echo "[SURICATA] Starting on $SURICATA_IFACE"
    # eve-log is enabled by the stock suricata.yaml. Do not override it with --set:
    # outputs is a YAML list in Suricata 6, so "outputs.eve-log.*" fails.
    if [ ! -s /var/lib/suricata/rules/suricata.rules ]; then
        echo "[SURICATA] warning: no rules are loaded, so no alerts will be raised" >&2
    fi
    suricata -i "$SURICATA_IFACE" -l "$SURICATA_LOG_DIR" &
    wait_for_file "$SURICATA_LOG_DIR/eve.json" SURICATA || return 1
    tail -n +1 -F "$SURICATA_LOG_DIR/eve.json" | python3 -u "$APP_DIR/suricata_bridge.py" \
        --api "$API_URL" --email "$EMAIL" --password "$AEGIS_PASSWORD" &
}

start_tshark() {
    echo "[TSHARK] Starting on $TSHARK_IFACE"
    tshark -i "$TSHARK_IFACE" -T fields \
        -e frame.time_epoch -e ip.src -e ip.dst -e tcp.srcport -e tcp.dstport \
        -e udp.srcport -e udp.dstport -e ip.proto -e frame.len -e dns.qry.name -l \
        2>/dev/null | python3 -u "$APP_DIR/tcpdump_bridge.py" --format tshark \
        --api "$API_URL" --email "$EMAIL" --password "$AEGIS_PASSWORD" &
}

start_engine() {
    case "$1" in
        zeek) start_zeek ;;
        suricata) start_suricata ;;
        tshark) start_tshark ;;
    esac
}

# Stop an engine and its bridge. Patterns match the command lines started above.
stop_engine() {
    case "$1" in
        zeek)
            pkill -f "zeek -C -i" || true
            pkill -f "zeek_bridge.py" || true
            pkill -f "tail -n +1 -F $ZEEK_LOG_DIR/conn.log" || true
            ;;
        suricata)
            pkill -x suricata || true
            pkill -f "suricata_bridge.py" || true
            pkill -f "tail -n +1 -F $SURICATA_LOG_DIR/eve.json" || true
            ;;
        tshark)
            pkill -x tshark || true
            pkill -f "tcpdump_bridge.py --format tshark" || true
            ;;
    esac
    ENGINE_RUNNING[$1]=0
}

engine_healthy() {
    case "$1" in
        zeek) pgrep -f "zeek -C -i" >/dev/null && pgrep -f "zeek_bridge.py" >/dev/null ;;
        suricata) pgrep -x suricata >/dev/null && pgrep -f "suricata_bridge.py" >/dev/null ;;
        tshark) pgrep -x tshark >/dev/null && pgrep -f "tcpdump_bridge.py --format tshark" >/dev/null ;;
        *) return 1 ;;
    esac
}

allowed_engine() {
    case ",$ENGINES," in
        *",$1,"*) return 0 ;;
    esac
    return 1
}

reconcile_once() {
    local state running version engines e
    if ! state="$(python3 -u "$APP_DIR/capture_state.py" 2>/tmp/aegis-capture-state.err)" \
        || ! [[ "$state" =~ ^[01]\ [0-9]+\ [a-z,-]+$ ]]; then
        echo "[CAPTURE] control plane unavailable; keeping the current engines ($(tail -n 1 /tmp/aegis-capture-state.err 2>/dev/null))" >&2
        return 0
    fi
    read -r running version engines <<< "$state"

    local -A want=()
    if [ "$running" = "1" ] && [ "$engines" != "-" ]; then
        for e in ${engines//,/ }; do want[$e]=1; done
    fi

    for e in "${ENGINE_ORDER[@]}"; do
        if [ "${ENGINE_RUNNING[$e]:-0}" = 1 ] && [ -z "${want[$e]:-}" ]; then
            echo "[CAPTURE] stopping $e (control state v$version)"
            stop_engine "$e"
        fi
    done

    for e in "${ENGINE_ORDER[@]}"; do
        [ -n "${want[$e]:-}" ] || continue
        if ! allowed_engine "$e"; then
            echo "[CAPTURE] $e is wanted but is not in AEGIS_CAPTURE_ENGINES; not starting it" >&2
            continue
        fi
        if [ "${ENGINE_RUNNING[$e]:-0}" = 1 ] && ! engine_healthy "$e"; then
            echo "[CAPTURE] $e exited; restarting it"
            stop_engine "$e"
        fi
        if [ "${ENGINE_RUNNING[$e]:-0}" != 1 ]; then
            echo "[CAPTURE] starting $e (control state v$version)"
            if start_engine "$e"; then
                ENGINE_RUNNING[$e]=1
            else
                echo "[CAPTURE] $e did not start; retrying on the next poll" >&2
                stop_engine "$e"
            fi
        fi
    done
    return 0
}

echo "============================================"
echo "  AEGIS network capture"
echo "  Allowed engines: $ENGINES"
echo "  API:             $API_URL (poll ${POLL_SECONDS}s)"
echo "============================================"

while true; do
    reconcile_once
    sleep "$POLL_SECONDS" &
    wait $! || true
done
