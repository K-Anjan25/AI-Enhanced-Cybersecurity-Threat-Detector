# AEGIS: one image that runs the whole product, for a single Render service.
#
# Inside the container:
#   nginx        serves the dashboard on $PORT and proxies /api, /metrics, /healthz
#   backend      FastAPI on 127.0.0.1:8000, migrations first (alembic upgrade head)
#   ml-service   scoring on 127.0.0.1:8001, reachable only from inside the container
#
# Size. The default build leaves out PyTorch. Without it the ML service serves the
# statistical fallback (see ml-service/aegis_ml/serving/scoring.py), and the image stays
# small. To ship the trained FlowNet model, build with --build-arg WITH_TORCH=1. That
# adds the CPU build of torch, several hundred MB. The CUDA build from PyPI is never used:
# it adds several GB.
#
# Build from the repository root: docker build -f deploy/aegis/Dockerfile .

# ---- dashboard: compile the static bundle; node_modules never leaves this stage ----
FROM node:22-alpine AS dashboard
WORKDIR /app
COPY dashboard/package.json dashboard/package-lock.json ./
RUN npm ci
COPY dashboard/index.html dashboard/tsconfig.json dashboard/vite.config.ts ./
COPY dashboard/postcss.config.js dashboard/tailwind.config.js ./
COPY dashboard/public ./public
COPY dashboard/src ./src
RUN npm run build

# ---- python: install into a virtualenv that the runtime stage copies as one directory ----
FROM python:3.11-slim AS builder
ARG WITH_TORCH=0
ENV PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1
RUN python -m venv /opt/venv
ENV PATH=/opt/venv/bin:$PATH

COPY ml-service /tmp/aegis-ml
COPY backend/pyproject.toml /tmp/aegis-backend/
COPY backend/app /tmp/aegis-backend/app

# --no-compile skips .pyc files; they are rebuilt on first import and cost space.
# The CPU index is preferred for torch, so the CUDA build is never selected. No PyPI fallback.
RUN if [ "$WITH_TORCH" = "1" ]; then \
      pip install --no-compile --timeout 900 --retries 10 \
        --extra-index-url https://download.pytorch.org/whl/cpu torch; \
    fi \
 && extra="" && [ "$WITH_TORCH" = "1" ] && extra="[training]" ; \
    pip install --no-compile --timeout 900 --retries 10 \
      "/tmp/aegis-ml${extra}" "/tmp/aegis-backend[redis,ws]"

# Remove what the running service does not need: the installer, build tooling,
# caches, type stubs and test suites shipped inside packages.
RUN rm -rf /opt/venv/lib/python3.11/site-packages/pip \
           /opt/venv/lib/python3.11/site-packages/pip-*.dist-info \
           /opt/venv/lib/python3.11/site-packages/setuptools \
           /opt/venv/lib/python3.11/site-packages/setuptools-*.dist-info \
           /opt/venv/lib/python3.11/site-packages/pkg_resources \
           /opt/venv/lib/python3.11/site-packages/_distutils_hack \
           /opt/venv/lib/python3.11/site-packages/distutils-precedence.pth \
           /opt/venv/bin/pip* \
 && find /opt/venv -depth \( -name __pycache__ -o -name tests -o -name "*.pyi" \) -exec rm -rf {} + \
 && rm -rf /tmp/aegis-ml /tmp/aegis-backend

# Fail the build, not the container, when an import the start script needs is missing.
RUN python -c "import aegis_ml.data.records, aegis_ml.scoring.fusion" \
    && python -c "import app.main"

# ---- runtime: no compiler, no pip, only what the stack runs ----
FROM python:3.11-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH=/opt/venv/bin:$PATH

# nginx-light is the Debian build without the optional modules this config does not use.
RUN apt-get update \
    && apt-get install -y --no-install-recommends nginx-light \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* /var/cache/apt/archives/*

COPY --from=builder /opt/venv /opt/venv

WORKDIR /app
COPY backend/alembic.ini ./
COPY backend/alembic ./alembic

COPY --from=dashboard /app/dist /opt/aegis/dashboard
COPY deploy/aegis/nginx.conf /opt/aegis/nginx.conf
COPY deploy/aegis/start.sh /opt/aegis/start.sh
# nginx creates its cache directories under /var/lib/nginx when it starts, even when the
# config does not use them, so the unprivileged user needs those paths.
RUN chmod 0755 /opt/aegis/start.sh \
    && useradd --create-home --uid 10001 aegis \
    && mkdir -p /app/artifacts \
    && mkdir -p /var/lib/nginx /var/log/nginx \
    && chown -R aegis /app /var/lib/nginx /var/log/nginx

USER aegis

ENV AEGIS_ML_SERVICE_URL=http://127.0.0.1:8001

# Render sets PORT. The default is only for running the image locally.
ENV PORT=8080
EXPOSE 8080

HEALTHCHECK --interval=15s --timeout=5s --retries=6 \
  CMD python -c "import os,urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:'+os.environ.get('PORT','8080')+'/healthz', timeout=3).status==200 else 1)"

CMD ["/opt/aegis/start.sh"]
