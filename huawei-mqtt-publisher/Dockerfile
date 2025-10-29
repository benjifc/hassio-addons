ARG BUILD_FROM
FROM ${BUILD_FROM}

# System deps
RUN apk add --no-cache python3 py3-pip python3-dev gcc musl-dev linux-headers

# Venv
RUN python3 -m venv /opt/venv \
 && /opt/venv/bin/pip install --upgrade pip

# Libs (paho 2.x + huawei-solar)
RUN /opt/venv/bin/pip install "paho-mqtt>=2.1.0" "huawei-solar>=2.4.0"

ENV PATH="/opt/venv/bin:${PATH}"

# Tu app
COPY huawei_mqtt.py /app/huawei_mqtt.py

# (Si usas rootfs con s6) Copia rootfs y asegúrate del +x
COPY rootfs /
RUN chmod +x /etc/services.d/huawei-mqtt/run