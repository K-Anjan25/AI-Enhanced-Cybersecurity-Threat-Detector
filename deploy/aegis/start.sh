#!/bin/bash
# Start the whole AEGIS stack in one container (see deploy/aegis/Dockerfile).
#
# Order: ML service starts, migrations run, then the backend, then nginx on $PORT.
# If any process exits, the script exits and the platform restarts the container,
# so a dead backend or ML service cannot hide behind a healthy-looking nginx.
set -euo pipefail

PORT="${PORT:-8080}"
export AEGIS_ML_SERVICE_URL="${AEGIS_ML_SERVICE_URL:-http://127.0.0.1:8001}"

RUN_DIR=/tmp/aegis-run
mkdir -p "$RUN_DIR/client" "$RUN_DIR/proxy"
# nginx.conf listens on the placeholder port; put in the real one. Writes only to /tmp,
# because the container runs as an unprivileged user.
sed "s/__PORT__/${PORT}/" /opt/aegis/nginx.conf > "$RUN_DIR/nginx.conf"

pids=()
stop_all() {
  for pid in "${pids[@]}"; do kill -TERM "$pid" 2>/dev/null || true; done
  wait || true
}
# Platform stop (SIGTERM): a clean exit.
trap 'stop_all; exit 0' TERM INT

cd /app

python -m uvicorn aegis_ml.serving.app:app --host 127.0.0.1 --port 8001 &
pids+=("$!")

# Migrations finish before the API accepts requests. A failed migration stops the container.
alembic upgrade head

python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 &
pids+=("$!")

nginx -c "$RUN_DIR/nginx.conf" -g 'daemon off;' &
pids+=("$!")

# Returns as soon as any of the three exits; then stop the rest and fail.
wait -n "${pids[@]}" || true
echo "a process exited; stopping the container" >&2
stop_all
exit 1
