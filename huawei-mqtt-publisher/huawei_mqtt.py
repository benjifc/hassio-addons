#!/usr/bin/env python3
import asyncio
import os
import sys
import signal
import logging
import ssl
from typing import Optional

from huawei_solar import AsyncHuaweiSolar, register_names as rn
import paho.mqtt.client as mqtt

# --- Logging docker-friendly ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)-15s %(threadName)-15s %(levelname)-8s %(module)-15s:%(lineno)-8s %(message)s",
    stream=sys.stdout,
)
log = logging.getLogger(__name__)
logging.getLogger("huawei_solar").setLevel(logging.WARNING)

# ---------- Utilidades de entorno ----------
def _clean(s: Optional[str]) -> Optional[str]:
    if s is None:
        return None
    return str(s).strip().strip('"').strip("'")

def env_str(name: str, default: str) -> str:
    val = os.getenv(name)
    val = _clean(val) if val is not None else default
    return val if val != "" else default

def env_int(name: str, default: int) -> int:
    val = os.getenv(name)
    if val is None or _clean(val) == "":
        return int(default)
    try:
        return int(_clean(val))
    except Exception:
        log.warning("Env %s tenía valor no entero %r, uso %s", name, val, default)
        return int(default)

def env_bool(name: str, default: bool) -> bool:
    val = os.getenv(name)
    if val is None:
        return default
    v = _clean(val).lower()
    if v in ("1", "true", "yes", "on"):
        return True
    if v in ("0", "false", "no", "off"):
        return False
    return default

# --- Lectura de entorno exportado por run ---
inverter_ip     = env_str("INVERTER_IP", "192.168.1.102")
mqtt_host       = env_str("MQTT_HOST", "192.168.1.132")
mqtt_user       = env_str("MQTT_USERNAME", "kuser")
mqtt_pass       = env_str("MQTT_PASSWORD", "")
broker_port     = env_int("MQTT_PORT", 1883)
slave_id        = env_int("MODBUS_SLAVE_ID", 1)
port            = env_int("MODBUS_PORT", 502)
pub_qos         = env_int("MQTT_QOS", 1)
mqtt_client_id  = env_str("MQTT_CLIENT_ID", "huawei-mqtt-publisher")
mqtt_protocol_s = env_str("MQTT_PROTOCOL", "v5")
mqtt_tls        = env_bool("MQTT_TLS", False)
mqtt_keepalive  = env_int("MQTT_KEEPALIVE", 60)

# --- Configuración efectiva (sin password) ---
log.info(
    "Config: inverter_ip=%s modbus_port=%s slave_id=%s | mqtt: host=%s port=%s user=%s qos=%s client_id=%s proto=%s tls=%s keepalive=%s",
    inverter_ip, port, slave_id, mqtt_host, broker_port, mqtt_user, pub_qos,
    mqtt_client_id, mqtt_protocol_s, mqtt_tls, mqtt_keepalive
)

# --- Variables a leer ---

VARS_IMMEDIATE = [
    # PV strings
    rn.PV_01_VOLTAGE, rn.PV_01_CURRENT,
    rn.PV_02_VOLTAGE, rn.PV_02_CURRENT,
    rn.INPUT_POWER,  # Potencia total desde los paneles solares

    # Red y potencia
    rn.GRID_VOLTAGE, rn.GRID_CURRENT,
    rn.ACTIVE_POWER, rn.REACTIVE_POWER,
    rn.POWER_FACTOR, rn.GRID_FREQUENCY,

    # Si hay contador SDongle o DDSU666-H
    rn.POWER_METER_ACTIVE_POWER,
    rn.POWER_METER_REACTIVE_POWER,


]


VARS_PERIODIC = [
    # Estado general y diagnósticos
    rn.DEVICE_STATUS,
    rn.FAULT_CODE,
    rn.INTERNAL_TEMPERATURE,
    rn.EFFICIENCY,
    rn.DAY_ACTIVE_POWER_PEAK,
    rn.INSULATION_RESISTANCE,

    # Energía diaria y total
    rn.DAILY_YIELD_ENERGY,
    rn.ACCUMULATED_YIELD_ENERGY,
    rn.GRID_EXPORTED_ENERGY,
    rn.GRID_ACCUMULATED_ENERGY,

    # Totales de generación y exportación
    rn.TOTAL_FEED_IN_TO_GRID,
    rn.TOTAL_SUPPLY_FROM_GRID,

    # Producción acumulada y actual
    rn.PV_YIELD_TODAY,
    rn.INVERTER_ENERGY_YIELD_TODAY,
    rn.INVERTER_TOTAL_ENERGY_YIELD,

    # Energía mensual y anual
    rn.MONTHLY_YIELD_ENERGY,
    rn.YEARLY_YIELD_ENERGY,
]
# --- Señales ---
shutdown_event = asyncio.Event()

def _signal_handler():
    log.info("Received shutdown signal")
    shutdown_event.set()

# --- Detección de versión de Paho ---
CallbackAPIVersion = getattr(mqtt, "CallbackAPIVersion", None)
USE_V2 = CallbackAPIVersion is not None

def _pick_protocol():
    if mqtt_protocol_s.lower() in ("v311", "311", "3.1.1", "mqttv311"):
        return mqtt.MQTTv311
    return getattr(mqtt, "MQTTv5", mqtt.MQTTv311)

def _mk_client():
    if USE_V2:
        client = mqtt.Client(
            client_id=mqtt_client_id,
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
            protocol=_pick_protocol(),
            transport="tcp",
        )
        client.reconnect_delay_set(min_delay=1, max_delay=30)
    else:
        client = mqtt.Client(client_id=mqtt_client_id, protocol=mqtt.MQTTv311)
    client.enable_logger(log)
    return client

def _set_mqtt_callbacks(client):
    client.connected_flag = False

    if USE_V2:
        def on_connect(client, userdata, flags, reasonCode, properties):
            rc = getattr(reasonCode, "value", reasonCode)
            if rc == 0:
                client.connected_flag = True
                log.info("MQTT connected OK (v2), rc=%s", rc)
            else:
                log.warning("MQTT connect failed (v2), rc=%s", rc)

        def on_disconnect(client, userdata, reasonCode, properties):
            rc = getattr(reasonCode, "value", reasonCode)
            client.connected_flag = False
            log.warning("MQTT disconnected (v2), rc=%s", rc)
    else:
        def on_connect(client, userdata, flags, rc):
            if rc == 0:
                client.connected_flag = True
                log.info("MQTT connected OK (v1), rc=%s", rc)
            else:
                log.warning("MQTT connect failed (v1), rc=%s", rc)

        def on_disconnect(client, userdata, rc):
            client.connected_flag = False
            log.warning("MQTT disconnected (v1), rc=%s", rc)

    client.on_connect = on_connect
    client.on_disconnect = on_disconnect

# --- Conexión MQTT con reintentos ---
async def _connect_mqtt_with_retries():
    backoff = 1
    client = _mk_client()
    _set_mqtt_callbacks(client)

    if mqtt_user:
        client.username_pw_set(mqtt_user, mqtt_pass)

    if mqtt_tls:
        try:
            client.tls_set(cert_reqs=ssl.CERT_NONE)
            client.tls_insecure_set(True)
            log.info("MQTT TLS enabled (insecure mode)")
        except Exception as e:
            log.error("Failed to enable TLS: %s", e)

    try:
        client.will_set("inversor/Huawei/status", "offline", qos=1, retain=True)
    except Exception:
        pass

    client.loop_start()
    while not shutdown_event.is_set():
        try:
            connect_fn = getattr(client, "connect_async", None) or client.connect
            log.info("Connecting MQTT to %s:%d ...", mqtt_host, broker_port)
            connect_fn(mqtt_host, broker_port, keepalive=mqtt_keepalive)
            for _ in range(30):
                if getattr(client, "connected_flag", False):
                    client.publish("inversor/Huawei/status", "online", qos=1, retain=True)
                    log.info("MQTT connected")
                    return client
                await asyncio.sleep(1)
            log.error("MQTT connection timeout; retrying in %ss", backoff)
        except Exception as e:
            log.error("MQTT connect error: %s; retrying in %ss", e, backoff)
        await asyncio.sleep(backoff)
        backoff = min(backoff * 2, 60)

    client.loop_stop()
    raise asyncio.CancelledError()

# --- Conexión al inversor Huawei ---
async def _connect_huawei_with_retries():
    backoff = 1
    while not shutdown_event.is_set():
        try:
            log.info("Connecting to Huawei inverter %s:%d (slave_id=%d)", inverter_ip, port, slave_id)
            huawei_client = await AsyncHuaweiSolar.create(inverter_ip, port, slave_id)
            log.info("Huawei inverter connected")
            return huawei_client
        except Exception as e:
            log.error("Huawei connect error: %s; retrying in %ss", e, backoff)
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 60)
    raise asyncio.CancelledError()

# --- Bucle principal de publicación ---
async def _modbus_loop(huawei_client, mqtt_client):
    periodic_ctr = 0
    energia_importada = 0.0
    energia_exportada = 0.0

    while not shutdown_event.is_set():
        if hasattr(mqtt_client, "is_connected") and not mqtt_client.is_connected():
            log.warning("MQTT not connected, waiting...")
            await asyncio.sleep(1)
            continue

        try:
            # === LECTURAS BASE ===
            active_power = ((await huawei_client.get(rn.ACTIVE_POWER, slave_id)).value) / 1000  # W
            meter_power  = ((await huawei_client.get(rn.POWER_METER_ACTIVE_POWER, slave_id)).value * -1 ) / 1000 # kW (+importa / -exporta)

            # === SENSORES DERIVADOS ===

            # Consumo casa instantáneo (kW)
            consumo_casa = abs(active_power - meter_power)

            # Importación/exportación (kW)
            import_w = max(meter_power, 0)
            export_w = max(-meter_power, 0)

            # Publica todos los sensores derivados
            mqtt_client.publish("inversor/Huawei/consumo_casa_w", f"{consumo_casa:.0f}", qos=pub_qos)
            mqtt_client.publish("inversor/Huawei/red_import_w", f"{import_w:.0f}", qos=pub_qos)
            mqtt_client.publish("inversor/Huawei/red_export_w", f"{export_w:.0f}", qos=pub_qos)


        except Exception as e:
            log.error("Error en cálculo derivado: %s", e)

        # LECTURAS PERIÓDICAS ORIGINALES
        periodic_ctr += 1
        if periodic_ctr > 5:
            for key in VARS_PERIODIC:
                try:
                    mid = await huawei_client.get(key, slave_id)
                    mqtt_client.publish(f"inversor/Huawei/{key}", str(mid.value), qos=pub_qos)
                except Exception as e:
                    log.error("Error reading %s: %s", key, e)
            periodic_ctr = 0

        await asyncio.sleep(1)
# --- Ciclo completo ---
async def _run_once():
    mqtt_client = await _connect_mqtt_with_retries()
    huawei_client = await _connect_huawei_with_retries()
    try:
        await _modbus_loop(huawei_client, mqtt_client)
    finally:
        log.info("Publishing offline and shutting down...")
        try:
            mqtt_client.publish("inversor/Huawei/status", "offline", qos=1, retain=True)
            mqtt_client.disconnect()
            mqtt_client.loop_stop()
        except Exception:
            pass
        try:
            await huawei_client.stop()
        except Exception:
            pass

# --- Main ---
async def main():
    loop = asyncio.get_running_loop()
    try:
        loop.add_signal_handler(signal.SIGINT, _signal_handler)
        loop.add_signal_handler(signal.SIGTERM, _signal_handler)
    except NotImplementedError:
        pass

    backoff = 1
    while not shutdown_event.is_set():
        try:
            await _run_once()
        except asyncio.CancelledError:
            break
        except Exception as e:
            log.error("Top-level error: %s; restarting in %ss", e, backoff)
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 60)
        else:
            await asyncio.sleep(2)
            backoff = 1

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass