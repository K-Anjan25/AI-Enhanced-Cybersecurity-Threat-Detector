#!/bin/bash
set -e

INTERFACE="${AEGIS_CAPTURE_INTERFACE:-eth0}"
API_URL="${AEGIS_API_URL:-http://backend:8000}"
LOG_DIR="/var/log/suricata"

echo "============================================"
echo "  AEGIS Suricata IDS"
echo "============================================"
echo "  Interface: $INTERFACE"
echo "  API:       $API_URL"
echo "============================================"

mkdir -p "$LOG_DIR"

# Start Suricata in the background
echo "[SURICATA] Starting Suricata IDS on $INTERFACE..."
suricata -i "$INTERFACE" -l "$LOG_DIR" \
    --set outputs.eve-log.enabled=yes \
    --set outputs.eve-log.filetype=regular \
    2>&1 &

SURICATA_PID=$!

# Wait for eve.json to appear
echo "[SURICATA] Waiting for eve.json..."
for i in $(seq 1 60); do
    if [ -f "$LOG_DIR/eve.json" ]; then
        break
    fi
    sleep 1
done

if [ ! -f "$LOG_DIR/eve.json" ]; then
    echo "[SURICATA] ERROR: eve.json not created after 60s"
    kill $SURICATA_PID 2>/dev/null || true
    exit 1
fi

echo "[SURICATA] eve.json found. Starting bridge to $API_URL..."

# Run the bridge
python3 -u /app/suricata_bridge.py \
    --api "$API_URL" \
    --email "${AEGIS_EMAIL:-admin@aegis.local}" \
    --password "${AEGIS_PASSWORD:-admin123456789}" \
    --log "$LOG_DIR/eve.json" &

BRIDGE_PID=$!

# Handle shutdown
cleanup() {
    echo "[SURICATA] Shutting down..."
    kill $BRIDGE_PID 2>/dev/null || true
    kill $SURICATA_PID 2>/dev/null || true
    exit 0
}
trap cleanup SIGTERM SIGINT

wait -n $SURICATA_PID $BRIDGE_PID
cleanup