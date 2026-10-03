# AEGIS ml-service image.
# Model weights are mounted or fetched at runtime, never copied into the image
# (R-40, R-68).
FROM python:3.11-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY pyproject.toml ./
COPY aegis_ml ./aegis_ml
RUN pip install --no-cache-dir .

RUN useradd --create-home --uid 10001 aegis \
    && mkdir -p /app/artifacts \
    && chown -R aegis /app
USER aegis

EXPOSE 8001

HEALTHCHECK --interval=10s --timeout=5s --retries=6 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8001/internal/healthz', timeout=3).status==200 else 1)"

CMD ["uvicorn", "aegis_ml.serving.app:app", "--host", "0.0.0.0", "--port", "8001"]
