#!/bin/sh
# Replay a capture file through Suricata and send the result to AEGIS.
#
# Runs inside the capture image, which already has Suricata and the bridges. Nothing is
# captured live, so the sensor's own interface and host networking are not involved.
#
#   usage: replay_pcap.sh /pcaps/<file>.pcap
#
# Needs AEGIS_EMAIL and AEGIS_PASSWORD (the same values the capture service uses) and
# AEGIS_API_URL (default http://backend:8000, the compose service name on the project network).
set -eu

PCAP="${1:?usage: replay_pcap.sh /pcaps/<file>.pcap}"
API="${AEGIS_API_URL:-http://backend:8000}"
APP="${AEGIS_APP_DIR:-/app}"

if [ ! -s "$PCAP" ]; then
    echo "replay: $PCAP is missing or empty" >&2
    exit 2
fi

OUT="$(mktemp -d)"
trap 'rm -rf "$OUT"' EXIT

# Offline mode: Suricata reads the file instead of a live interface and writes eve.json.
if ! suricata -r "$PCAP" -l "$OUT" -c /etc/suricata/suricata.yaml >"$OUT/suricata.log" 2>&1; then
    echo "replay: suricata failed; last lines:" >&2
    tail -n 20 "$OUT/suricata.log" >&2
    exit 1
fi
if [ ! -s "$OUT/eve.json" ]; then
    echo "replay: suricata produced no eve.json" >&2
    exit 1
fi

echo "replay: $(wc -l <"$OUT/eve.json") eve events from $PCAP"
python3 -u "$APP/suricata_bridge.py" --flows --file "$OUT/eve.json" \
    --api "$API" --email "${AEGIS_EMAIL:?set AEGIS_EMAIL}" --password "${AEGIS_PASSWORD:?set AEGIS_PASSWORD}"
