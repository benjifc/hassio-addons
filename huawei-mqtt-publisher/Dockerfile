# ---- Base de Home Assistant ----
# Para builds locales, da un valor por defecto. El Supervisor lo sobreescribirá.
ARG BUILD_FROM=ghcr.io/home-assistant/aarch64-base:latest
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
# jq se usa para leer /data/options.json; no instales bashio.
RUN apk add --no-cache python3 py3-pip python3-dev gcc musl-dev linux-headers jq

# ---- Entorno virtual Python ----
RUN python3 -m venv /opt/venv \
 && /opt/venv/bin/pip install --upgrade pip

# ---- Librerías necesarias ----
RUN /opt/venv/bin/pip install "paho-mqtt>=2.1.0" "huawei-solar>=2.4.0"

# ---- Variables de entorno ----
ENV PATH="/opt/venv/bin:${PATH}"

# ---- Copiar aplicación Python ----
COPY huawei_mqtt.py /app/huawei_mqtt.py

# ---- Servicio s6: leer opciones con jq y exportarlas ----
RUN mkdir -p /etc/services.d/huawei-mqtt && \
cat > /etc/services.d/huawei-mqtt/run <<'EOF'
#!/usr/bin/with-contenv /bin/sh
set -eu

OPTS=/data/options.json
val(){ jq -r ".${1} // empty" "$OPTS"; }

# Exportar configuración
export INVERTER_IP="$(val inverter_ip)"
export MQTT_HOST="$(val mqtt_host)"
export MQTT_USERNAME="$(val mqtt_username)"
export MQTT_PASSWORD="$(val mqtt_password)"
export MQTT_PORT="$(val mqtt_port)"
export MODBUS_SLAVE_ID="$(val modbus_slave_id)"
export MODBUS_PORT="$(val modbus_port)"
export MQTT_QOS="$(val mqtt_qos)"
export MQTT_CLIENT_ID="$(val mqtt_client_id)"

# Campos opcionales
PROTO="$(val mqtt_protocol)"
TLS="$(val mqtt_tls)"
KA="$(val mqtt_keepalive)"
[ -n "$PROTO" ] && export MQTT_PROTOCOL="$PROTO"
[ -n "$TLS" ] && export MQTT_TLS="$TLS"
[ -n "$KA" ] && export MQTT_KEEPALIVE="$KA"

# Ejecutar servicio principal
exec /opt/venv/bin/python -u /app/huawei_mqtt.py
EOF

# 🔧 Asegurar formato LF (sin \r) y permisos
RUN sed -i 's/\r$//' /etc/services.d/huawei-mqtt/run && chmod +x /etc/services.d/huawei-mqtt/run