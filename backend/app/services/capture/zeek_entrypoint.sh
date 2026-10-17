#!/bin/bash
set -e

# Refuse the development default password; see docker/.env.example.
if [ -z "${AEGIS_PASSWORD:-}" ] || [ "${AEGIS_PASSWORD}" = "admin123456789" ]; then  # pragma: allowlist secret
    echo "refusing to start: set AEGIS_PASSWORD (AEGIS_BOOTSTRAP_ADMIN_PASSWORD in docker/.env) to a value other than the development default" >&2
    exit 2
fi

INTERFACE="${AEGIS_CAPTURE_INTERFACE:-eth0}"
API_URL="${AEGIS_API_URL:-http://backend:8000}"
LOG_DIR="/tmp/zeek-logs"

echo "============================================"
echo "  AEGIS Zeek Network Analyzer"
echo "============================================"
echo "  Interface: $INTERFACE"
echo "  API:       $API_URL"
echo "============================================"

mkdir -p "$LOG_DIR"
cd "$LOG_DIR"

# Start Zeek in the background, watching the interface
echo "[ZEEK] Starting Zeek on interface $INTERFACE..."
zeek -i "$INTERFACE" local 2>&1 &
ZEEK_PID=$!

# Wait for conn.log to appear
echo "[ZEEK] Waiting for conn.log..."
for i in $(seq 1 60); do
    if [ -f "$LOG_DIR/conn.log" ]; then
        break
    fi
    sleep 1
done

if [ ! -f "$LOG_DIR/conn.log" ]; then
    echo "[ZEEK] ERROR: conn.log not created after 60s"
    kill $ZEEK_PID 2>/dev/null || true
    exit 1
fi

echo "[ZEEK] conn.log found. Starting bridge to $API_URL..."

# Follow conn.log from the start and stream it into the bridge on stdin.
# (zeek_bridge.py has no --log option and reads one pass over a file, so
# tail -F keeps it running as Zeek appends new records.)
tail -n +1 -F "$LOG_DIR/conn.log" | python3 -u /app/zeek_bridge.py \
    --log-type conn \
    --api "$API_URL" \
    --email "${AEGIS_EMAIL:-admin@aegis.local}" \
    --password "${AEGIS_PASSWORD}" &

BRIDGE_PID=$!

# Handle shutdown
cleanup() {
    echo "[ZEEK] Shutting down..."
    kill $BRIDGE_PID 2>/dev/null || true
    kill $ZEEK_PID 2>/dev/null || true
    exit 0
}
trap cleanup SIGTERM SIGINT

# Wait for either process to exit
wait -n $ZEEK_PID $BRIDGE_PID
cleanup
