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
RUN pip install --no-cache-dir .

# Run as an unprivileged user (architecture.md §12).
RUN useradd --create-home --uid 10001 aegis
USER aegis

EXPOSE 8000

HEALTHCHECK --interval=10s --timeout=5s --retries=6 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8000/healthz', timeout=3).status==200 else 1)"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
