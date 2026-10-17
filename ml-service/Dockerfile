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
# The training extra carries torch, which the trained FlowNet needs to score. Without it the
# service still starts and serves /models, but /score/windows answers 503 with the reason.
# torch is ~550 MB of wheel plus CUDA dependencies. On a slow link a single read can time
# out, so the download gets a long timeout and retries, and BuildKit's pip cache keeps the
# wheels that did finish, so a retry does not start from zero.
RUN --mount=type=cache,target=/root/.cache/pip \
    PIP_NO_CACHE_DIR=0 pip install --timeout 900 --retries 10 ".[training]"

RUN useradd --create-home --uid 10001 aegis \
    && mkdir -p /app/artifacts \
    && chown -R aegis /app
USER aegis

EXPOSE 8001

HEALTHCHECK --interval=10s --timeout=5s --retries=6 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8001/internal/healthz', timeout=3).status==200 else 1)"

CMD ["uvicorn", "aegis_ml.serving.app:app", "--host", "0.0.0.0", "--port", "8001"]
