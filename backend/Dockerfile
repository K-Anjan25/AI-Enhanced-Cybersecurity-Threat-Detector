# AEGIS backend image.
# Non-root, no secrets baked in, pinned base tag with an explicit minor version
# (R-08 forbids `latest`). Two stages: the builder installs into a virtualenv, and only
# that virtualenv is copied into the runtime image, so no pip, compiler or cache ships.
FROM python:3.11-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1
RUN python -m venv /opt/venv
ENV PATH=/opt/venv/bin:$PATH

WORKDIR /build
COPY pyproject.toml ./
COPY app ./app
# aegis_ml is the ML package the backend shares with training: the windowing and fusion
# contracts the live Kafka consumer uses (D-085). Only its base install is needed (pydantic,
# fastapi, uvicorn), not torch. The build passes it as the named context `aegis_ml`
# (docker/docker-compose.yml, .github/workflows/release.yml).
COPY --from=aegis_ml . /tmp/aegis-ml
RUN pip install --no-compile /tmp/aegis-ml ".[redis,ws]" \
 && rm -rf /tmp/aegis-ml \
 && rm -rf /opt/venv/lib/python3.11/site-packages/pip \
           /opt/venv/lib/python3.11/site-packages/pip-*.dist-info \
           /opt/venv/lib/python3.11/site-packages/setuptools \
           /opt/venv/lib/python3.11/site-packages/setuptools-*.dist-info \
           /opt/venv/lib/python3.11/site-packages/pkg_resources \
           /opt/venv/lib/python3.11/site-packages/_distutils_hack \
           /opt/venv/lib/python3.11/site-packages/distutils-precedence.pth \
           /opt/venv/bin/pip* \
 && find /opt/venv -depth \( -name __pycache__ -o -name tests -o -name "*.pyi" \) -exec rm -rf {} +

# Fail the build, not the container, when the shared ML contract is missing. The live
# consumer and the scoring worker import these modules at start-up; a build that dropped
# aegis_ml used to ship and then exit on the first import.
RUN python -c "import aegis_ml.data.records, aegis_ml.data.windowing, aegis_ml.scoring.fusion" \
    && python -c "import app.main, app.workers.scoring_worker"

FROM python:3.11-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH=/opt/venv/bin:$PATH

COPY --from=builder /opt/venv /opt/venv

WORKDIR /app
# Migrations, run once per deploy by the chart's migrate Job (alembic upgrade head).
COPY alembic.ini ./
COPY alembic ./alembic

# Run as an unprivileged user (architecture.md §12).
RUN useradd --create-home --uid 10001 aegis
USER aegis

EXPOSE 8000

HEALTHCHECK --interval=10s --timeout=5s --retries=6 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8000/healthz', timeout=3).status==200 else 1)"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
