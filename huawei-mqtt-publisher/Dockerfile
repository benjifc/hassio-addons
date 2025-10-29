ARG BUILD_FROM
FROM ${BUILD_FROM}

# Entorno Python y pip sin caché
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PATH="/opt/venv/bin:${PATH}"

# Dependencias del sistema + venv + libs
RUN apk add --no-cache python3 py3-pip python3-dev gcc musl-dev linux-headers && \
    python3 -m venv /opt/venv && \
    /opt/venv/bin/pip install --upgrade pip && \
    /opt/venv/bin/pip install --no-cache-dir "paho-mqtt>=2.1.0" "huawei-solar>=2.4.0"

# Código de la app
WORKDIR /app
COPY huawei_mqtt.py /app/huawei_mqtt.py

# Archivos s6 (asegúrate de que en el repo esté en rootfs/etc/services.d/huawei-mqtt/run)
COPY rootfs/ /

# Red de seguridad por si la carpeta vino como service.d (sin la 's')
RUN if [ -d /etc/service.d ]; then \
      mkdir -p /etc/services.d && \
      cp -a /etc/service.d/* /etc/services.d/ && \
      rm -rf /etc/service.d ; \
    fi && \
    mkdir -p /etc/services.d/huawei-mqtt && \
    chmod +x /etc/services.d/huawei-mqtt/run

# s6-overlay del base image arrancará /etc/services.d/*/run automáticamente