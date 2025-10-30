#!/usr/bin/with-contenv /bin/sh
set -eu

OPTS="/data/options.json"

val() { jq -r ".${1} // empty" "$OPTS" 2>/dev/null || echo ""; }
val_array_json() { jq -ce ".${1} | select(type==\"array\")" "$OPTS" 2>/dev/null || echo ""; }

# Requeridos
export INVERTER_IP="$(val inverter_ip)"
export MODBUS_SLAVE_ID="$(val modbus_slave_id)"
export MODBUS_PORT="$(val modbus_port)"

export MQTT_HOST="$(val mqtt_host)"
export MQTT_PORT="$(val mqtt_port)"
export MQTT_USERNAME="$(val mqtt_username)"
export MQTT_PASSWORD="$(val mqtt_password)"
export MQTT_QOS="$(val mqtt_qos)"
export MQTT_CLIENT_ID="$(val mqtt_client_id)"

# Opcionales
PROTO="$(val mqtt_protocol)"
TLS="$(val mqtt_tls)"
KEEPALIVE="$(val mqtt_keepalive)"
LOG_LEVEL="$(val log_level)"
READ_INTERVAL="$(val read_interval)"
PER_READ_DELAY="$(val per_read_delay)"

[ -n "${PROTO:-}" ] && export MQTT_PROTOCOL="$PROTO"
[ -n "${TLS:-}" ] && export MQTT_TLS="$TLS"
[ -n "${KEEPALIVE:-}" ] && export MQTT_KEEPALIVE="$KEEPALIVE"
[ -n "${LOG_LEVEL:-}" ] && export LOG_LEVEL="$LOG_LEVEL"
[ -n "${READ_INTERVAL:-}" ] && export READ_INTERVAL="$READ_INTERVAL"
[ -n "${PER_READ_DELAY:-}" ] && export PER_READ_DELAY="$PER_READ_DELAY"

# Arrays
VARS_IMMEDIATE_JSON="$(val_array_json vars_immediate)"
VARS_PERIODIC_JSON="$(val_array_json vars_periodic)"

[ -n "${VARS_IMMEDIATE_JSON:-}" ] && export VARS_IMMEDIATE="$VARS_IMMEDIATE_JSON"
[ -n "${VARS_PERIODIC_JSON:-}" ] && export VARS_PERIODIC="$VARS_PERIODIC_JSON"

echo "[INFO] Starting Huawei Inverter MQTT Publisher (Simple)..."
echo "[INFO] Inverter: ${INVERTER_IP}:${MODBUS_PORT} (slave ${MODBUS_SLAVE_ID})"
echo "[INFO] MQTT: ${MQTT_HOST}:${MQTT_PORT} client=${MQTT_CLIENT_ID}"
[ -n "${VARS_IMMEDIATE_JSON:-}" ] && echo "[INFO] vars_immediate: $(echo "$VARS_IMMEDIATE_JSON" | jq 'length') regs"
[ -n "${VARS_PERIODIC_JSON:-}" ] && echo "[INFO] vars_periodic:  $(echo "$VARS_PERIODIC_JSON" | jq 'length') regs"

exec /opt/venv/bin/python -u /app/main.py