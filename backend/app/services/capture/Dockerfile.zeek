FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive

# Install Zeek and Python
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        curl gnupg2 ca-certificates \
        python3 python3-pip libpcap-dev dos2unix && \
    echo 'deb http://download.opensuse.org/repositories/security:/zeek/xUbuntu_22.04/ /' | \
        tee /etc/apt/sources.list.d/security:zeek.list && \
    curl -fsSL https://download.opensuse.org/repositories/security:zeek/xUbuntu_22.04/Release.key | \
        gpg --dearmor | tee /etc/apt/trusted.gpg.d/security_zeek.gpg > /dev/null && \
    apt-get update && \
    apt-get install -y zeek && \
    rm -rf /var/lib/apt/lists/*

ENV PATH="/opt/zeek/bin:${PATH}"

WORKDIR /app

COPY app/services/capture/bridges/zeek_bridge.py .
COPY app/services/capture/zeek_entrypoint.sh .

RUN dos2unix zeek_entrypoint.sh && chmod +x zeek_entrypoint.sh

CMD ["./zeek_entrypoint.sh"]
