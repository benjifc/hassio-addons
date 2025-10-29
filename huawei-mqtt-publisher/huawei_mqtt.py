import asyncio
import os
import sys
import signal
import logging
import time

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

# --- Env ---
inverter_ip  = os.getenv("INVERTER_IP", "192.168.1.102")
mqtt_host    = os.getenv("MQTT_HOST", "192.168.1.132")
mqtt_user    = os.getenv("MQTT_USERNAME", "kuser")
mqtt_pass    = os.getenv("MQTT_PASSWORD", "")
broker_port  = int(os.getenv("MQTT_PORT", 1883))
slave_id     = int(os.getenv("MODBUS_SLAVE_ID", 1))
port         = int(os.getenv("MODBUS_PORT", 502))
pub_qos      = int(os.getenv("MQTT_QOS", 1))

# --- Vars a leer ---
VARS_IMMEDIATE = [
    rn.PV_01_VOLTAGE, rn.PV_01_CURRENT, rn.PV_02_VOLTAGE, rn.PV_02_CURRENT,
    rn.INPUT_POWER, rn.GRID_VOLTAGE, rn.GRID_CURRENT, rn.ACTIVE_POWER,
    rn.GRID_A_VOLTAGE, rn.ACTIVE_GRID_A_CURRENT, rn.POWER_METER_ACTIVE_POWER,
]
VARS_PERIODIC = [
    rn.DAY_ACTIVE_POWER_PEAK, rn.EFFICIENCY, rn.INTERNAL_TEMPERATURE,
    rn.INSULATION_RESISTANCE, rn.DEVICE_STATUS, rn.FAULT_CODE,
    rn.ACCUMULATED_YIELD_ENERGY, rn.DAILY_YIELD_ENERGY,
    rn.GRID_EXPORTED_ENERGY, rn.GRID_ACCUMULATED_ENERGY,
]

# --- Señales ---
shutdown_event = asyncio.Event()

def _signal_handler():
    log.info("Received shutdown signal")
    try:
        shutdown_event.set()
    except Exception:
        pass

# paho 1.x vs 2.x detection
CallbackAPIVersion = getattr(mqtt, "CallbackAPIVersion", None)
USE_V2 = CallbackAPIVersion is not None  # paho >= 2.0

def _mk_client():
    if USE_V2:
        # API v2: callbacks con reasonCode y properties
        client = mqtt.Client(
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
            protocol=mqtt.MQTTv311,
            transport="tcp",
        )
    else:
        client = mqtt.Client()  # paho 1.x
    return client

def _set_mqtt_callbacks(client):
    client.connected_flag = False

    if USE_V2:
        def on_connect(client, userdata, flags, reasonCode, properties):
            if int(reasonCode) == 0:
                client.connected_flag = True
                log.info("MQTT connected OK (v2), rc=%s", reasonCode)
            else:
                log.warning("MQTT connect failed (v2), rc=%s", reasonCode)
    else:
        def on_connect(client, userdata, flags, rc):
            if rc == 0:
                client.connected_flag = True
                log.info("MQTT connected OK (v1), rc=%s", rc)
            else:
                log.warning("MQTT connect failed (v1), rc=%s", rc)

    client.on_connect = on_connect

async def _connect_mqtt_with_retries():
    backoff = 1
    client = _mk_client()
    _set_mqtt_callbacks(client)

    if mqtt_user:
        client.username_pw_set(mqtt_user, mqtt_pass)

    # Usar loop_start para callbacks en hilo propio
    client.loop_start()

    while not shutdown_event.is_set():
        try:
            # connect_async existe en paho 1.6+; en 2.x también. Si falla, usa connect.
            connect_fn = getattr(client, "connect_async", None) or client.connect
            log.info("Connecting MQTT to %s:%d ...", mqtt_host, broker_port)
            connect_fn(mqtt_host, broker_port, keepalive=60)

            # Esperar hasta 30s por conexión
            for _ in range(30):
                if getattr(client, "connected_flag", False):
                    log.info("MQTT connected")
                    return client
                await asyncio.sleep(1)

            log.error("MQTT connection timeout; retrying in %ss", backoff)
        except Exception as e:
            log.error("MQTT connect error: %s; retrying in %ss", e, backoff)

        await asyncio.sleep(backoff)
        backoff = min(backoff * 2, 60)

    # Si nos piden apagar antes de conectar:
    try:
        client.loop_stop()
    except Exception:
        pass
    raise asyncio.CancelledError()

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

async def _modbus_loop(huawei_client, mqtt_client):
    periodic_ctr = 0
    while not shutdown_event.is_set():
        # Inmediatas
        for key in VARS_IMMEDIATE:
            try:
                mid = await huawei_client.get(key, slave_id)
                topic = f"inversor/Huawei/{key}"
                payload = str(mid.value)
                mqtt_client.publish(topic=topic, payload=payload, qos=pub_qos, retain=False)
            except Exception as e:
                log.error("Error reading %s: %s", key, e)

        # Periódicas
        periodic_ctr += 1
        if periodic_ctr > 5:
            for key in VARS_PERIODIC:
                try:
                    mid = await huawei_client.get(key, slave_id)
                    topic = f"inversor/Huawei/{key}"
                    payload = str(mid.value)
                    mqtt_client.publish(topic=topic, payload=payload, qos=pub_qos, retain=False)
                except Exception as e:
                    log.error("Error reading %s: %s", key, e)
            periodic_ctr = 0

        await asyncio.sleep(1)

async def _run_once():
    mqtt_client = await _connect_mqtt_with_retries()
    huawei_client = await _connect_huawei_with_retries()

    try:
        await _modbus_loop(huawei_client, mqtt_client)
    finally:
        try:
            log.info("Shutting down MQTT loop...")
            mqtt_client.disconnect()
            mqtt_client.loop_stop()
        except Exception as e:
            log.warning("Error shutting down MQTT: %s", e)
        try:
            log.info("Stopping Huawei client...")
            await huawei_client.stop()
        except Exception as e:
            log.warning("Error stopping Huawei client: %s", e)

async def main():
    loop = asyncio.get_running_loop()
    try:
        loop.add_signal_handler(signal.SIGINT, _signal_handler)
        loop.add_signal_handler(signal.SIGTERM, _signal_handler)
    except NotImplementedError:
        pass

    # No salgas: reintenta bloques enteros con backoff si algo rompe
    backoff = 1
    while not shutdown_event.is_set():
        try:
            await _run_once()  # Solo retorna si shutdown_event o excepción
        except asyncio.CancelledError:
            break
        except Exception as e:
            log.error("Top-level error: %s; restarting in %ss", e, backoff)
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 60)
        else:
            # Si _run_once retorna “limpio” sin shutdown, reiniciamos tras breve espera
            await asyncio.sleep(2)
            backoff = 1

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass