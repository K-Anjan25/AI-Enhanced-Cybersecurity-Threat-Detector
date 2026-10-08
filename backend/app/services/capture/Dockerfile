FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && \
    apt-get install -y --no-install-recommends libpcap-dev && \
    rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir scapy

COPY app/services/capture/capture_service.py .

# Capture needs NET_ADMIN to sniff packets
# Run with: docker run --cap-add=NET_ADMIN --network=host

CMD ["python", "-u", "capture_service.py"]