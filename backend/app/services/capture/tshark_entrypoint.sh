#!/bin/bash
set -e

INTERFACE="${AEGIS_CAPTURE_INTERFACE:-any}"
API_URL="${AEGIS_API_URL:-http://backend:8000}"

echo "============================================"
echo "  AEGIS tshark Packet Capture"
echo "============================================"
echo "  Interface: $INTERFACE"
echo "  API:       $API_URL"
echo "============================================"

# List available interfaces
echo "[TSHARK] Available interfaces:"
tshark -D 2>/dev/null || echo "  (could not list)"

# Start tshark and pipe to bridge
echo "[TSHARK] Starting capture on $INTERFACE..."
echo "[TSHARK] Piping to tcpdump_bridge.py..."

tshark -i "$INTERFACE" \
    -T fields \
    -e frame.time_epoch \
    -e ip.src \
    -e ip.dst \
    -e tcp.srcport \
    -e tcp.dstport \
    -e udp.srcport \
    -e udp.dstport \
    -e ip.proto \
    -e frame.len \
    -e dns.qry.name \
    -l 2>/dev/null | \
python3 -u /app/tcpdump_bridge.py \
    --format tshark \
    --api "$API_URL" \
    --email "${AEGIS_EMAIL:-admin@aegis.local}" \
    --password "${AEGIS_PASSWORD:-admin123456789}"
