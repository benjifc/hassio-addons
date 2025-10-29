ARG BUILD_FROM
FROM $BUILD_FROM

ENV LANG C.UTF-8

# Copy script
COPY rootfs /

# Instalar dependencias del sistema
RUN apk add --no-cache \
    python3 \
    python3-dev \
    py3-pip \
    gcc \
    musl-dev \
    linux-headers

# Instalar paquetes Python
RUN pip3 install --no-cache-dir --break-system-packages huawei-solar paho-mqtt

# Copiar el script Python
COPY huawei_mqtt.py /

RUN chmod +x /etc/services.d/huawei/run
RUN chmod +x /etc/services.d/huawei/finish
# ¡NO usar CMD! Dejamos que s6 inicie el servicio.
# El script se ejecutará desde rootfs/etc/services.d/...