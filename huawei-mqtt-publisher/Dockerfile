FROM ghcr.io/home-assistant/aarch64-base:latest

# System deps
RUN apk add --no-cache python3 py3-pip python3-dev gcc musl-dev linux-headers

# Venv para esquivar PEP 668
RUN python3 -m venv /opt/venv \
 && /opt/venv/bin/pip install --upgrade pip

# Libs (paho 2.x + huawei-solar)
# *Si quieres máxima estabilidad, fija versiones explícitas
RUN /opt/venv/bin/pip install "paho-mqtt>=2.1.0" "huawei-solar>=2.4.0"

ENV PATH="/opt/venv/bin:${PATH}"

# Copias
COPY rootfs /
# Asegúrate de que el servicio es huawei-mqtt:
# /etc/services.d/huawei-mqtt/run
RUN chmod +x /etc/services.d/huawei-mqtt/run