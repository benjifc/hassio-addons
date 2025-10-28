import time
import asyncio
import signal
import os
import sys
import logging

from huawei_solar import AsyncHuaweiSolar, register_names as rn
import paho.mqtt.client as mqtt

# --- Configuración de logging (Docker-friendly) ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)-15s %(threadName)-15s %(levelname)-8s %(module)-15s:%(lineno)-8s %(message)s',
    stream=sys.stdout  # Asegura salida a stdout (capturado por Docker)
)
log = logging.getLogger(__name__)

# Silenciar logs INFO de la librería huawei_solar (opcional)
logging.getLogger("huawei_solar").setLevel(logging.WARNING)

# --- Variables de entorno ---
inverter_ip = os.getenv('INVERTER_IP', '192.168.1.102')
mqtt_host = os.getenv('MQTT_HOST', '192.168.1.132')
mqtt_username = os.getenv('MQTT_USERNAME', 'kuser')
mqtt_password = os.getenv('MQTT_PASSWORD', '')
broker_port = int(os.getenv('MQTT_PORT', 1883))
slave_id = int(os.getenv('MODBUS_SLAVE_ID', 1))
port = int(os.getenv('MODBUS_PORT', 502))

async def modbusAccess(huawei_client, slave_id, mqtt_client):
    vars_inmediate = [
        rn.PV_01_VOLTAGE, rn.PV_01_CURRENT, rn.PV_02_VOLTAGE, rn.PV_02_CURRENT,
        rn.INPUT_POWER, rn.GRID_VOLTAGE, rn.GRID_CURRENT, rn.ACTIVE_POWER,
        rn.GRID_A_VOLTAGE, rn.ACTIVE_GRID_A_CURRENT, rn.POWER_METER_ACTIVE_POWER
    ]

    vars_periodic = [
        rn.DAY_ACTIVE_POWER_PEAK, rn.EFFICIENCY, rn.INTERNAL_TEMPERATURE,
        rn.INSULATION_RESISTANCE, rn.DEVICE_STATUS, rn.FAULT_CODE,
        rn.ACCUMULATED_YIELD_ENERGY, rn.DAILY_YIELD_ENERGY,
        rn.GRID_EXPORTED_ENERGY, rn.GRID_ACCUMULATED_ENERGY
    ]

    cont = 0
    try:
        while True:
            for key in vars_inmediate:
                try:
                    mid = await huawei_client.get(key, slave_id)
                    topic = f"inversor/Huawei/{key}"
                    payload = str(mid.value)
                    mqtt_client.publish(topic=topic, payload=payload, qos=1, retain=False)
                    log.info("MQTT published: %s = %s", topic, payload)
                except Exception as e:
                    log.error("Error reading %s: %s", key, e)

            if cont > 5:
                for key in vars_periodic:
                    try:
                        mid = await huawei_client.get(key, slave_id)
                        topic = f"inversor/Huawei/{key}"
                        payload = str(mid.value)
                        mqtt_client.publish(topic=topic, payload=payload, qos=1, retain=False)
                        log.info("MQTT published: %s = %s", topic, payload)
                    except Exception as e:
                        log.error("Error reading %s: %s", key, e)
                cont = 0

            cont += 1
            await asyncio.sleep(1)
    except asyncio.CancelledError:
        log.info("Modbus access task cancelled")
        raise

def on_connect(client, userdata, flags, rc):
    if rc == 0:
        client.connected_flag = True
        log.info("MQTT connected OK")
    else:
        log.warning("MQTT connection failed, rc=%s", rc)

async def main():
    # --- MQTT setup ---
    clientMQTT = mqtt.Client()
    clientMQTT.connected_flag = False
    clientMQTT.on_connect = on_connect
    clientMQTT.loop_start()

    log.info("Connecting to MQTT broker %s:%s", mqtt_host, broker_port)
    if mqtt_username:
        clientMQTT.username_pw_set(username=mqtt_username, password=mqtt_password)
    clientMQTT.connect(mqtt_host, broker_port)

    # wait until connected
    for _ in range(30):
        if getattr(clientMQTT, "connected_flag", False):
            break
        log.info("Waiting for MQTT connection...")
        await asyncio.sleep(1)
    else:
        log.error("MQTT connection timeout")
        clientMQTT.loop_stop()
        return

    log.info("START MODBUS...")
    huawei_client = await AsyncHuaweiSolar.create(inverter_ip, port, slave_id)

    loop = asyncio.get_running_loop()
    shutdown_event = asyncio.Event()

    def _signal_handler():
        log.info("Received shutdown signal")
        shutdown_event.set()

    try:
        loop.add_signal_handler(signal.SIGINT, _signal_handler)
        loop.add_signal_handler(signal.SIGTERM, _signal_handler)
    except NotImplementedError:
        log.debug("loop.add_signal_handler not supported")

    modbus_task = asyncio.create_task(modbusAccess(huawei_client, slave_id, clientMQTT))
    shutdown_task = asyncio.create_task(shutdown_event.wait())

    done, pending = await asyncio.wait(
        [modbus_task, shutdown_task],
        return_when=asyncio.FIRST_COMPLETED
    )

    if shutdown_task in done:
        log.info("Shutdown event triggered, cancelling modbus task...")
        if not modbus_task.done():
            modbus_task.cancel()
            try:
                await modbus_task
            except asyncio.CancelledError:
                log.info("Modbus task cancelled cleanly")

    for t in pending:
        t.cancel()
        try:
            await t
        except asyncio.CancelledError:
            pass

    log.info("Shutting down MQTT and Huawei client...")
    try:
        clientMQTT.disconnect()
        clientMQTT.loop_stop()
    except Exception as e:
        log.warning("Error shutting down MQTT client: %s", e)

    try:
        await huawei_client.stop()
    except Exception as e:
        log.warning("Error stopping Huawei client: %s", e)

if __name__ == "__main__":
    asyncio.run(main())