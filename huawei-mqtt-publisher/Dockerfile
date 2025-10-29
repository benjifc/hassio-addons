# ---- Base de Home Assistant ----
ARG BUILD_FROM
FROM ${BUILD_FROM}

# ---- Metadatos opcionales ----
ARG BUILD_ARCH
ARG BUILD_VERSION
LABEL io.hass.arch="${BUILD_ARCH}" \
      io.hass.version="${BUILD_VERSION}" \
      io.hass.type="addon" \
      io.hass.name="Huawei Inverter MQTT Publisher" \
      io.hass.description="Publica datos del inversor Huawei Solar en MQTT usando Modbus TCP." \
      io.hass.url="https://github.com/benjifc/hassio-addons"

# ---- Dependencias del sistema ----
RUN apk add --no-cache python3 py3-pip python3-dev gcc musl-dev linux-headers

# ---- Entorno virtual Python ----
RUN python3 -m venv /opt/venv \
 && /opt/venv/bin/pip install --upgrade pip

# ---- Librerías necesarias ----
RUN /opt/venv/bin/pip install "paho-mqtt>=2.1.0" "huawei-solar>=2.4.0"

ENV PATH="/opt/venv/bin:${PATH}"

# ---- Copiar aplicación ----
COPY huawei_mqtt.py /app/huawei_mqtt.py

# ---- Crear servicio s6 con bashio ----
RUN mkdir -p /etc/services.d/huawei-mqtt \
 && printf '#!/usr/bin/with-contenv bashio\n\
set -e\n\
export INVERTER_IP=\"$(bashio::config '\''inverter_ip'\'')\"\n\
export MQTT_HOST=\"$(bashio::config '\''mqtt_host'\'')\"\n\
export MQTT_USERNAME=\"$(bashio::config '\''mqtt_username'\'')\"\n\
export MQTT_PASSWORD=\"$(bashio::config '\''mqtt_password'\'')\"\n\
export MQTT_PORT=\"$(bashio::config '\''mqtt_port'\'')\"\n\
export MODBUS_SLAVE_ID=\"$(bashio::config '\''modbus_slave_id'\'')\"\n\
export MODBUS_PORT=\"$(bashio::config '\''modbus_port'\'')\"\n\
export MQTT_QOS=\"$(bashio::config '\''mqtt_qos'\'')\"\n\
export MQTT_CLIENT_ID=\"$(bashio::config '\''mqtt_client_id'\'')\"\n\
if bashio::config.has '\''mqtt_protocol'\''; then export MQTT_PROTOCOL=\"$(bashio::config '\''mqtt_protocol'\'')\"; fi\n\
if bashio::config.has '\''mqtt_tls'\''; then export MQTT_TLS=\"$(bashio::config '\''mqtt_tls'\'')\"; fi\n\
if bashio::config.has '\''mqtt_keepalive'\''; then export MQTT_KEEPALIVE=\"$(bashio::config '\''mqtt_keepalive'\'')\"; fi\n\
exec /opt/venv/bin/python -u /app/huawei_mqtt.py\n' \
> /etc/services.d/huawei-mqtt/run \
 && chmod +x /etc/services.d/huawei-mqtt/run