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
mqtt_client_id = os.getenv("MQTT_CLIENT_ID", "huawei-mqtt-publisher")

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
        # MQTT v5 por defecto en paho 2.x
        client = mqtt.Client(
            client_id=mqtt_client_id,
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
            protocol=mqtt.MQTTv5,
            transport="tcp",
        )
        # Backoff interno de paho para reconexiones automáticas
        client.reconnect_delay_set(min_delay=1, max_delay=30)
    else:
        client = mqtt.Client(client_id=mqtt_client_id)  # paho 1.x (MQTT v3.1.1)
    client.enable_logger(log)  # integra logs del cliente en nuestro logger
    return client

def _set_mqtt_callbacks(client):
    client.connected_flag = False

    if USE_V2:
        # v2 signatures: (client, userdata, flags, reasonCode, properties)
        def on_connect(client, userdata, flags, reasonCode, properties):
            if int(reasonCode) == 0:
                client.connected_flag = True
                log.info("MQTT connected OK (v2), rc=%s", reasonCode)
            else:
                log.warning("MQTT connect failed (v2), rc=%s", reasonCode)

        def on_disconnect(client, userdata, reasonCode, properties):
            client.connected_flag = False
            log.warning("MQTT disconnected (v2), rc=%s", reasonCode)

    else:
        # v1 signatures: (client, userdata, flags, rc)
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

async def _connect_mqtt_with_retries():
    backoff = 1
    client = _mk_client()
    _set_mqtt_callbacks(client)

    if mqtt_user:
        client.username_pw_set(mqtt_user, mqtt_pass)

    # Last Will (opcional): marca offline si el contenedor muere
    try:
        client.will_set("inversor/Huawei/status", payload="offline", qos=1, retain=True)
    except Exception:
        pass

    client.loop_start()

    while not shutdown_event.is_set():
        try:
            connect_fn = getattr(client, "connect_async", None) or client.connect
            log.info("Connecting MQTT to %s:%d ...", mqtt_host, broker_port)
            if USE_V2:
                # MQTT v5 permite properties; aquí no son necesarios
                connect_fn(mqtt_host, broker_port, keepalive=60)
            else:
                connect_fn(mqtt_host, broker_port, keepalive=60)

            # Esperar hasta 30s por conexión
            for _ in range(30):
                if getattr(client, "connected_flag", False):
                    # Publica online si quieres un heartbeat retained
                    try:
                        client.publish("inversor/Huawei/status", "online", qos=1, retain=True)
                    except Exception:
                        pass
                    log.info("MQTT connected")
                    return client
                await asyncio.sleep(1)

            log.error("MQTT connection timeout; retrying in %ss", backoff)
        except Exception as e:
            log.error("MQTT connect error: %s; retrying in %ss", e, backoff)

        await asyncio.sleep(backoff)
        backoff = min(backoff * 60 // 2, 60) if backoff < 2 else min(backoff * 2, 60)  # acelera a 2 y duplica

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
        # Si el broker se cayó, espera a que paho lo recupere (o que el lazo superior reinicie)
        if hasattr(mqtt_client, "is_connected") and not mqtt_client.is_connected():
            log.warning("MQTT not connected, waiting...")
            await asyncio.sleep(1)
            continue

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
            log.info("Publishing offline and shutting down MQTT loop...")
            try:
                mqtt_client.publish("inversor/Huawei/status", "offline", qos=1, retain=True)
            except Exception:
                pass
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