#!/usr/bin/with-contenv /bin/sh
set -eu

OPTS="/data/options.json"

# --- Helpers -------------------------------------------------
val() { jq -r ".${1} // empty" "$OPTS" 2>/dev/null || echo ""; }
val_array_json() { jq -ce ".${1} | select(type==\"array\")" "$OPTS" 2>/dev/null || echo ""; }

# --- Requeridos ----------------------------------------------
export INVERTER_IP="$(val inverter_ip)"
export MODBUS_SLAVE_ID="$(val modbus_slave_id)"
export MODBUS_PORT="$(val modbus_port)"

export MQTT_HOST="$(val mqtt_host)"
export MQTT_PORT="$(val mqtt_port)"
export MQTT_USERNAME="$(val mqtt_username)"
export MQTT_PASSWORD="$(val mqtt_password)"
export MQTT_QOS="$(val mqtt_qos)"
export MQTT_CLIENT_ID="$(val mqtt_client_id)"

# --- Opcionales MQTT / logging / ritmo -----------------------
PROTO="$(val mqtt_protocol)"
TLS="$(val mqtt_tls)"
KEEPALIVE="$(val mqtt_keepalive)"
LOG_LEVEL="$(val log_level)"

READ_INTERVAL="$(val read_interval)"
PER_READ_DELAY="$(val per_read_delay)"
PERIODIC_EVERY="$(val periodic_every)"

# --- Flags de comportamiento simple --------------------------
FORCE_SYNC="$(val force_sync)"
MAX_REG_READS="$(val max_reg_reads)"
PUBLISH_CHANGED_ONLY="$(val publish_changed_only)"
CHANGE_EPS="$(val change_eps)"

[ -n "${PROTO:-}" ] && export MQTT_PROTOCOL="$PROTO"
[ -n "${TLS:-}" ] && export MQTT_TLS="$TLS"
[ -n "${KEEPALIVE:-}" ] && export MQTT_KEEPALIVE="$KEEPALIVE"
[ -n "${LOG_LEVEL:-}" ] && export LOG_LEVEL="$LOG_LEVEL"

[ -n "${READ_INTERVAL:-}" ] && export READ_INTERVAL="$READ_INTERVAL"
[ -n "${PER_READ_DELAY:-}" ] && export PER_READ_DELAY="$PER_READ_DELAY"
[ -n "${PERIODIC_EVERY:-}" ] && export PERIODIC_EVERY="$PERIODIC_EVERY"

[ -n "${FORCE_SYNC:-}" ] && export FORCE_SYNC="$FORCE_SYNC"
[ -n "${MAX_REG_READS:-}" ] && export MAX_REG_READS="$MAX_REG_READS"
[ -n "${PUBLISH_CHANGED_ONLY:-}" ] && export PUBLISH_CHANGED_ONLY="$PUBLISH_CHANGED_ONLY"
[ -n "${CHANGE_EPS:-}" ] && export CHANGE_EPS="$CHANGE_EPS"

# --- Arrays --------------------------------------------------
VARS_IMMEDIATE_JSON="$(val_array_json vars_immediate)"
VARS_PERIODIC_JSON="$(val_array_json vars_periodic)"

[ -n "${VARS_IMMEDIATE_JSON:-}" ] && export VARS_IMMEDIATE="$VARS_IMMEDIATE_JSON"
[ -n "${VARS_PERIODIC_JSON:-}" ] && export VARS_PERIODIC="$VARS_PERIODIC_JSON"

# --- Log de arranque ----------------------------------------
echo "[INFO] Starting Huawei Inverter MQTT Publisher (Simple)..."
echo "[INFO] Inverter: ${INVERTER_IP}:${MODBUS_PORT} (slave ${MODBUS_SLAVE_ID})"
echo "[INFO] MQTT: ${MQTT_HOST}:${MQTT_PORT} client=${MQTT_CLIENT_ID}"
[ -n "${MQTT_PROTOCOL:-}" ] && echo "[INFO] MQTT protocol=${MQTT_PROTOCOL}"
[ -n "${MQTT_TLS:-}" ] && echo "[INFO] MQTT TLS=${MQTT_TLS}"
[ -n "${MQTT_KEEPALIVE:-}" ] && echo "[INFO] MQTT keepalive=${MQTT_KEEPALIVE}"
[ -n "${LOG_LEVEL:-}" ] && echo "[INFO] Log level=${LOG_LEVEL}"
[ -n "${READ_INTERVAL:-}" ] && echo "[INFO] read_interval=${READ_INTERVAL}s"
[ -n "${PER_READ_DELAY:-}" ] && echo "[INFO] per_read_delay=${PER_READ_DELAY}s"
[ -n "${PERIODIC_EVERY:-}" ] && echo "[INFO] periodic_every=${PERIODIC_EVERY} ciclos"
[ -n "${FORCE_SYNC:-}" ] && echo "[INFO] force_sync=${FORCE_SYNC}"
[ -n "${MAX_REG_READS:-}" ] && echo "[INFO] max_reg_reads=${MAX_REG_READS}"
[ -n "${PUBLISH_CHANGED_ONLY:-}" ] && echo "[INFO] publish_changed_only=${PUBLISH_CHANGED_ONLY}"
[ -n "${CHANGE_EPS:-}" ] && echo "[INFO] change_eps=${CHANGE_EPS}"

[ -n "${VARS_IMMEDIATE_JSON:-}" ] && echo "[INFO] vars_immediate: $(echo "$VARS_IMMEDIATE_JSON" | jq 'length') regs"
[ -n "${VARS_PERIODIC_JSON:-}" ] && echo "[INFO] vars_periodic:  $(echo "$VARS_PERIODIC_JSON" | jq 'length') regs"

# --- Lanzar servicio ----------------------------------------
exec /opt/venv/bin/python -u /app/main.py