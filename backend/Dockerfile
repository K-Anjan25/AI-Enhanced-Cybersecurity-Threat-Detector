# AEGIS backend image.
# Non-root, no secrets baked in, pinned base digest-less tag with an explicit
# minor version (R-08 forbids `latest`).
FROM python:3.11-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Install dependencies first so the layer caches independently of source edits.
COPY pyproject.toml ./
COPY app ./app
# aegis_ml is the ML package the backend shares with training: the windowing and
# fusion contracts the live Kafka consumer uses (D-085). Only its base install is
# needed (pydantic, fastapi, uvicorn), not torch. The build passes it as the named
# context `aegis_ml` (docker/docker-compose.yml, .github/workflows/release.yml).
COPY --from=aegis_ml . /tmp/aegis-ml
RUN pip install --no-cache-dir /tmp/aegis-ml ".[redis]" \
    && rm -rf /tmp/aegis-ml

# Fail the build, not the container, when the shared ML contract is missing. The live
# consumer and the scoring worker import these modules at start-up; a build that
# dropped aegis_ml used to ship and then exit on the first import.
RUN python -c "import aegis_ml.data.records, aegis_ml.data.windowing, aegis_ml.scoring.fusion" \
    && python -c "import app.main, app.workers.scoring_worker"

# Run as an unprivileged user (architecture.md §12).
RUN useradd --create-home --uid 10001 aegis
USER aegis

EXPOSE 8000

HEALTHCHECK --interval=10s --timeout=5s --retries=6 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8000/healthz', timeout=3).status==200 else 1)"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
