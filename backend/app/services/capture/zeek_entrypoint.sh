#!/bin/bash
set -e

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

# Run the bridge in the foreground, tailing conn.log
# The bridge reads new lines and sends them to AEGIS
python3 -u /app/zeek_bridge.py \
    --api "$API_URL" \
    --email "${AEGIS_EMAIL:-admin@aegis.local}" \
    --password "${AEGIS_PASSWORD:-admin123456789}" \
    --log "$LOG_DIR/conn.log" &

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