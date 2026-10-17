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
# Install torch's CPU-only build first. The default PyPI wheel pulls in about 2 GB of CUDA
# libraries, which a slow or unstable link cannot download reliably (one attempt failed a
# hash check on a corrupted transfer). The CPU build is the same torch API without CUDA.
# The extra index is preferred because +cpu is a newer local version than the PyPI build.
# If the PyTorch index is unreachable, the PyPI wheel is used instead.
# The second step then finds torch already satisfied and installs the rest of the extra.
RUN pip install --timeout 900 --retries 10 \
        --extra-index-url https://download.pytorch.org/whl/cpu torch \
    || pip install --timeout 900 --retries 10 torch
RUN pip install --timeout 900 --retries 10 ".[training]"

RUN useradd --create-home --uid 10001 aegis \
    && mkdir -p /app/artifacts \
    && chown -R aegis /app
USER aegis

EXPOSE 8001

HEALTHCHECK --interval=10s --timeout=5s --retries=6 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8001/internal/healthz', timeout=3).status==200 else 1)"

CMD ["uvicorn", "aegis_ml.serving.app:app", "--host", "0.0.0.0", "--port", "8001"]
