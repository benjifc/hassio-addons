ARG BUILD_FROM=ghcr.io/home-assistant/aarch64-base:latest
FROM $BUILD_FROM

ENV LANG=C.UTF-8

# Copia el sistema s6
COPY rootfs /
RUN chmod +x /etc/services.d/huawei/run /etc/services.d/huawei/finish || true

# Instalar dependencias del sistema
RUN apk add --no-cache \
    python3 \
    python3-dev \
    py3-pip \
    gcc \
    musl-dev \
    linux-headers

# Instalar paquetes Python
RUN pip3 install --no-cache-dir huawei-solar paho-mqtt

# Copiar el script Python
COPY huawei_mqtt.py /