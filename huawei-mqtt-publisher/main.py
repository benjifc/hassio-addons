#!/usr/bin/env python3
import os, sys, time, json, ssl, logging
from typing import Optional, List
from datetime import datetime

from huawei_solar import register_names as rn
try:
    from huawei_solar import HuaweiSolar as HSClientSync
except Exception:
    HSClientSync = None
from huawei_solar import AsyncHuaweiSolar as HSClientAsync
import paho.mqtt.client as mqtt

# ---------- utils ----------
def _clean(s: Optional[str]) -> Optional[str]:
    return None if s is None else str(s).strip().strip('"').strip("'")

def env_str(name: str, default: str) -> str:
    v = os.getenv(name); v = _clean(v) if v is not None else default
    return v if v != "" else default

def env_int(name: str, default: int) -> int:
    v = os.getenv(name)
    try:
        return int(float(_clean(v))) if v is not None and _clean(v) != "" else int(default)
    except Exception:
        return int(default)

def env_float(name: str, default: float) -> float:
    v = os.getenv(name)
    try:
        return float(_clean(v)) if v is not None and _clean(v) != "" else float(default)
    except Exception:
        return float(default)

def env_bool(name: str, default: bool) -> bool:
    v = os.getenv(name)
    if v is None: return default
    x = _clean(v).lower()
    if x in ("1","true","yes","on"): return True
    if x in ("0","false","no","off"): return False
    return default

def _parse_log_level(s: str, default=logging.INFO) -> int:
    if not s: return default
    s = str(s).strip().upper()
    if s.isdigit():
        try: return int(s)
        except: return default
    return getattr(logging, s, default)

LOG_LEVEL = _parse_log_level(env_str("LOG_LEVEL", "INFO"))

logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)-15s %(levelname)-8s %(message)s",
    stream=sys.stdout,
)
log = logging.getLogger("huawei_simple")

# --- ENV base ---
INVERTER_IP     = env_str("INVERTER_IP", "192.168.1.102")
MODBUS_PORT     = env_int("MODBUS_PORT", 502)
SLAVE_ID        = env_int("MODBUS_SLAVE_ID", 1)

MQTT_HOST       = env_str("MQTT_HOST", "core-mosquitto")
MQTT_PORT       = env_int("MQTT_PORT", 1883)
MQTT_USER       = env_str("MQTT_USERNAME", "")
MQTT_PASS       = env_str("MQTT_PASSWORD", "")
MQTT_QOS        = env_int("MQTT_QOS", 1)
MQTT_CLIENT_ID  = env_str("MQTT_CLIENT_ID", "huawei-mqtt-publisher-simple")
MQTT_PROTOCOL_S = env_str("MQTT_PROTOCOL", "311")
MQTT_TLS        = env_bool("MQTT_TLS", False)
MQTT_KEEPALIVE  = env_int("MQTT_KEEPALIVE", 60)

READ_INTERVAL   = env_float("READ_INTERVAL", 7.0)
PER_READ_DELAY  = env_float("PER_READ_DELAY", 0.4)

# --- Mapear arrays de ENV a objetos rn.X ---
def map_registers(env_name: str, defaults: List):
    raw = os.getenv(env_name, "")
    if not raw:
        log.info("%s no definido; usando defaults (%d regs)", env_name, len(defaults))
        return defaults
    try:
        names = json.loads(raw)
    except Exception:
        log.warning("ENV %s con JSON inválido, uso defaults.", env_name)
        return defaults
    out, unknown = [], []
    for n in names:
        if not isinstance(n, str): continue
        key = n.strip().upper()
        reg = getattr(rn, key, None)
        if reg is None: unknown.append(n)
        else: out.append(reg)
    if unknown:
        log.warning("Registros desconocidos en %s: %s", env_name, ", ".join(unknown))
    log.info("%s cargado: %d registros (%d desconocidos)", env_name, len(out), len(unknown))
    return out or defaults

DEFAULT_IMM = [
    rn.INPUT_POWER, rn.ACTIVE_POWER, rn.POWER_FACTOR,
    rn.GRID_VOLTAGE, rn.GRID_CURRENT, rn.GRID_FREQUENCY
]
DEFAULT_PER = [
    rn.DEVICE_STATUS, rn.INTERNAL_TEMPERATURE,
    rn.DAILY_YIELD_ENERGY, rn.MONTHLY_YIELD_ENERGY, rn.YEARLY_YIELD_ENERGY
]

VARS_IMMEDIATE = map_registers("VARS_IMMEDIATE", DEFAULT_IMM)
VARS_PERIODIC  = map_registers("VARS_PERIODIC",  DEFAULT_PER)

log.info("Config: inverter=%s:%s slave=%s | mqtt=%s:%s client=%s | interval=%.2fs delay=%.2fs",
         INVERTER_IP, MODBUS_PORT, SLAVE_ID, MQTT_HOST, MQTT_PORT, MQTT_CLIENT_ID,
         READ_INTERVAL, PER_READ_DELAY)

# --- MQTT (bloqueante mínimo) ---
def pick_protocol():
    if str(MQTT_PROTOCOL_S).lower() in ("311","v311","3.1.1","mqttv311"):
        return mqtt.MQTTv311
    return getattr(mqtt, "MQTTv5", mqtt.MQTTv311)

def make_mqtt():
    log.debug("Creando cliente MQTT (proto=%s)...", MQTT_PROTOCOL_S)
    client = mqtt.Client(client_id=MQTT_CLIENT_ID, protocol=pick_protocol(), transport="tcp")
    if MQTT_USER:
        log.debug("Usando credenciales MQTT: %s", MQTT_USER)
        client.username_pw_set(MQTT_USER, MQTT_PASS)
    if MQTT_TLS:
        log.debug("TLS activado (modo inseguro)")
        client.tls_set(cert_reqs=ssl.CERT_NONE)
        client.tls_insecure_set(True)
    client.will_set("inverter/Huawei/status", "offline", qos=1, retain=True)
    return client

def mqtt_connect_blocking():
    client = make_mqtt()
    client.enable_logger(log)
    client.loop_start()
    for backoff in (1,2,4,8,16,30):
        try:
            log.info("MQTT conectando a %s:%s ...", MQTT_HOST, MQTT_PORT)
            client.connect(MQTT_HOST, MQTT_PORT, keepalive=MQTT_KEEPALIVE)
            time.sleep(1.0)
            client.publish("inverter/Huawei/status", "online", qos=1, retain=True)
            log.info("✅ MQTT conectado correctamente")
            return client
        except Exception as e:
            log.warning("🛑 MQTT fallo conexión: %s (reintento en %ss)", e, backoff)
            time.sleep(backoff)
    raise RuntimeError("🛑 No se pudo conectar a MQTT")

# --- Cliente Huawei ---
def make_huawei_client():
    if HSClientSync is not None:
        for backoff in (1,2,4,8,16,30):
            try:
                log.info("Conectando Huawei (sync) %s:%s slave=%s ...", INVERTER_IP, MODBUS_PORT, SLAVE_ID)
                cli = HSClientSync(INVERTER_IP, MODBUS_PORT, SLAVE_ID)
                log.info("✅ Huawei conectado (sync)")
                return ("sync", cli)
            except Exception as e:
                log.warning("Fallo Huawei (sync): %s (reintento en %ss)", e, backoff)
                time.sleep(backoff)
        raise RuntimeError("No se pudo conectar al inversor (sync)")
    else:
        import asyncio
        for backoff in (1,2,4,8,16,30):
            try:
                log.info("Conectando Huawei (async) %s:%s slave=%s ...", INVERTER_IP, MODBUS_PORT, SLAVE_ID)
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                cli = loop.run_until_complete(HSClientAsync.create(INVERTER_IP, MODBUS_PORT, SLAVE_ID))
                log.info("✅ Huawei conectado (async)")
                return ("async", (cli, loop))
            except Exception as e:
                log.warning("Fallo Huawei (async): %s (reintento en %ss)", e, backoff)
                time.sleep(backoff)
        raise RuntimeError("No se pudo conectar al inversor (async)")

def read_register(mode, client, key):
    t0 = time.time()
    if mode == "sync":
        mid = client.get(key, SLAVE_ID)
    else:
        cli, loop = client
        mid = loop.run_until_complete(cli.get(key, SLAVE_ID))
    duration = time.time() - t0
    log.debug("Leído %s = %s (%.2fs)", key, mid.value, duration)
    return mid.value

def main():
    start_time = datetime.now()
    log.info("=== ✅ Huawei MQTT Publisher (simple) iniciado a las %s ===", start_time.strftime("%H:%M:%S"))
    mqttc = mqtt_connect_blocking()
    mode, hclient = make_huawei_client()

    periodic_tick = 0
    read_ok = read_fail = 0

    while True:
        cycle_start = time.time()
        log.info("--- Ciclo de lectura iniciado ---")
        # Inmediatos
        for key in VARS_IMMEDIATE:
            try:
                val = read_register(mode, hclient, key)
                mqttc.publish(f"inverter/Huawei/{key}", str(val), qos=MQTT_QOS)
                read_ok += 1
            except Exception as e:
                log.warning("🛑 Lectura inmediata fallida (%s): %s", key, e)
                read_fail += 1
            time.sleep(PER_READ_DELAY)

        # Periódicos cada 5 ciclos
        periodic_tick += 1
        if periodic_tick >= 5:
            log.info("→ Lectura periódica (tick=%s)", periodic_tick)
            for key in VARS_PERIODIC:
                try:
                    val = read_register(mode, hclient, key)
                    mqttc.publish(f"inverter/Huawei/{key}", str(val), qos=MQTT_QOS)
                    read_ok += 1
                except Exception as e:
                    log.warning("🛑 Lectura periódica fallida (%s): %s", key, e)
                    read_fail += 1
                time.sleep(PER_READ_DELAY)
            periodic_tick = 0

        elapsed = time.time() - cycle_start
        log.info("Fin de ciclo (%.2fs). OK=%d, Fail=%d", elapsed, read_ok, read_fail)
        time.sleep(READ_INTERVAL)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log.info("🛑 Interrumpido por el usuario; apagando limpiamente...")
        pass