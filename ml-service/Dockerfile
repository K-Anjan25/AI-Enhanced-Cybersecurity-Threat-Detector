# AEGIS ml-service image.
# Model weights are mounted or fetched at runtime, never copied into the image (R-40, R-68).
#
# Size. By default torch is left out. The service then serves the statistical fallback
# (/score/windows answers with the reason). Build with --build-arg WITH_TORCH=1 to add the
# CPU build of torch, which the trained FlowNet needs. The CUDA build from PyPI is never
# installed: it adds several GB, and the CPU index is required, not optional.
FROM python:3.11-slim AS builder
ARG WITH_TORCH=0
ENV PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1
RUN python -m venv /opt/venv
ENV PATH=/opt/venv/bin:$PATH

COPY pyproject.toml /tmp/aegis-ml/
COPY aegis_ml /tmp/aegis-ml/aegis_ml
RUN if [ "$WITH_TORCH" = "1" ]; then \
      pip install --no-compile --timeout 900 --retries 10 \
        --extra-index-url https://download.pytorch.org/whl/cpu torch; \
    fi \
 && extra="" && [ "$WITH_TORCH" = "1" ] && extra="[training]" ; \
    pip install --no-compile --timeout 900 --retries 10 "/tmp/aegis-ml${extra}" \
 && rm -rf /opt/venv/lib/python3.11/site-packages/pip \
           /opt/venv/lib/python3.11/site-packages/pip-*.dist-info \
           /opt/venv/lib/python3.11/site-packages/setuptools \
           /opt/venv/lib/python3.11/site-packages/setuptools-*.dist-info \
           /opt/venv/lib/python3.11/site-packages/pkg_resources \
           /opt/venv/lib/python3.11/site-packages/_distutils_hack \
           /opt/venv/lib/python3.11/site-packages/distutils-precedence.pth \
           /opt/venv/bin/pip* \
 && find /opt/venv -depth \( -name __pycache__ -o -name tests -o -name "*.pyi" \) -exec rm -rf {} + \
 && rm -rf /tmp/aegis-ml

FROM python:3.11-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH=/opt/venv/bin:$PATH

COPY --from=builder /opt/venv /opt/venv

WORKDIR /app
RUN useradd --create-home --uid 10001 aegis \
    && mkdir -p /app/artifacts \
    && chown -R aegis /app

USER aegis

EXPOSE 8001

HEALTHCHECK --interval=10s --timeout=5s --retries=6 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8001/internal/healthz', timeout=3).status==200 else 1)"

CMD ["uvicorn", "aegis_ml.serving.app:app", "--host", "0.0.0.0", "--port", "8001"]
