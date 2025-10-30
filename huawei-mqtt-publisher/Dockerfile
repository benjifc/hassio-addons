ARG BUILD_FROM=ghcr.io/home-assistant/aarch64-base:latest
FROM ${BUILD_FROM}

# Paquetes básicos + venv
RUN apk add --no-cache python3 py3-pip py3-virtualenv jq

# Virtualenv
RUN python3 -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Dependencias Python
# (usa la misma lib huawei-solar y paho-mqtt)
RUN pip install --no-cache-dir huawei-solar paho-mqtt

# Copia archivos
COPY run.sh /run
COPY main.py /app/main.py
RUN chmod +x /run

# Entrypoint
CMD ["/run"]