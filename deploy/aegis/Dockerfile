# AEGIS: one image that runs the whole product, for a single Render service.
#
# Inside the container:
#   nginx        serves the dashboard on $PORT and proxies /api, /metrics, /healthz
#   backend      FastAPI on 127.0.0.1:8000, migrations first (alembic upgrade head)
#   ml-service   scoring on 127.0.0.1:8001, reachable only from inside the container
#
# Only nginx listens on the public port, so the ML service is no longer exposed.
# Build from the repository root: docker build -f deploy/aegis/Dockerfile .
# The Compose and Kubernetes deployments keep their separate images (backend/, ml-service/).

FROM node:22-alpine AS dashboard
WORKDIR /app
COPY dashboard/package.json dashboard/package-lock.json ./
RUN npm ci
# Only the sources the build reads, so a local node_modules is never copied in.
COPY dashboard/index.html dashboard/tsconfig.json dashboard/vite.config.ts ./
COPY dashboard/postcss.config.js dashboard/tailwind.config.js ./
COPY dashboard/public ./public
COPY dashboard/src ./src
RUN npm run build

FROM python:3.11-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends nginx \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# The CPU build of torch first, so the training extra does not pull the CUDA libraries.
# Same approach and fallback as ml-service/Dockerfile.
COPY ml-service /tmp/aegis-ml
RUN pip install --timeout 900 --retries 10 \
        --extra-index-url https://download.pytorch.org/whl/cpu torch \
    || pip install --timeout 900 --retries 10 torch

# Backend sources, then both packages. The backend needs the shared ML contract (aegis_ml).
COPY backend/pyproject.toml ./
COPY backend/app ./app
COPY backend/alembic.ini ./
COPY backend/alembic ./alembic
RUN pip install --timeout 900 --retries 10 "/tmp/aegis-ml[training]" ".[redis,ws]" \
    && rm -rf /tmp/aegis-ml

# Fail the build, not the container, when an import the start script needs is missing.
RUN python -c "import aegis_ml.data.records, aegis_ml.scoring.fusion" \
    && python -c "import app.main"

COPY --from=dashboard /app/dist /opt/aegis/dashboard
COPY deploy/aegis/nginx.conf /opt/aegis/nginx.conf
COPY deploy/aegis/start.sh /opt/aegis/start.sh
RUN chmod 0755 /opt/aegis/start.sh \
    && useradd --create-home --uid 10001 aegis \
    && mkdir -p /app/artifacts \
    && chown -R aegis /app

USER aegis

ENV AEGIS_ML_SERVICE_URL=http://127.0.0.1:8001

# Render sets PORT. The default is only for running the image locally.
ENV PORT=8080
EXPOSE 8080

HEALTHCHECK --interval=15s --timeout=5s --retries=6 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:'+__import__('os').environ.get('PORT','8080')+'/healthz', timeout=3).status==200 else 1)"

CMD ["/opt/aegis/start.sh"]
