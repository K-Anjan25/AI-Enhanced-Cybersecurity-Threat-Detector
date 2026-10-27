#!/bin/sh
# Start command for the Render backend service (see render.yaml).
# Runs migrations, then starts the API. A script file avoids the shell quoting
# problems of a long inline dockerCommand on Render.
set -e
cd /app
alembic upgrade head
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
