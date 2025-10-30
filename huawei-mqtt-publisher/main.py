#!/usr/bin/env python3
import os, sys, time, json, ssl, logging, math
from typing import Optional, List, Tuple, Any
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

READ_INTERVAL   = env_float("READ_INTERVAL", 1.2)   # descanso entre ciclos
PER_READ_DELAY  = env_float("PER_READ_DELAY", 0.12) # pausa entre lecturas
PERIODIC_EVERY  = env_int("PERIODIC_EVERY", 8)      # cada N ciclos

# Avanzados
FORCE_SYNC              = env_bool("FORCE_SYNC", False)
MAX_REG_READS           = env_int("MAX_REG_READS", 1)  # solo aplica a async si soporta el kwarg
PUBLISH_CHANGED_ONLY    = env_bool("PUBLISH_CHANGED_ONLY", True)
CHANGE_EPS              = env_float("CHANGE_EPS", 0.001)  # umbral cambio float

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

log.info(
    "Config: inverter=%s:%s slave=%s | mqtt=%s:%s client=%s | interval=%.2fs delay=%.2fs | periodic_every=%d | force_sync=%s | max_reg_reads=%d | changed_only=%s eps=%.4f",
    INVERTER_IP, MODBUS_PORT, SLAVE_ID, MQTT_HOST, MQTT_PORT, MQTT_CLIENT_ID,
    READ_INTERVAL, PER_READ_DELAY, PERIODIC_EVERY, FORCE_SYNC, MAX_REG_READS, PUBLISH_CHANGED_ONLY, CHANGE_EPS
)

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
            log.info("⏳ Conectando a MQTT %s:%s ...", MQTT_HOST, MQTT_PORT)
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
def _connect_huawei_sync() -> Tuple[str, Any]:
    for backoff in (1,2,4,8,16,30):
        try:
            log.info("⏳ Conectando Huawei (sync) %s:%s slave=%s ...", INVERTER_IP, MODBUS_PORT, SLAVE_ID)
            cli = HSClientSync(INVERTER_IP, MODBUS_PORT, SLAVE_ID)
            log.info("✅ Huawei conectado (sync) ☑️")
            return ("sync", cli)
        except Exception as e:
            log.warning("Fallo Huawei (sync): %s (reintento en %ss)", e, backoff)
            time.sleep(backoff)
    raise RuntimeError("No se pudo conectar al inversor (sync)")

def _connect_huawei_async() -> Tuple[str, Any]:
    import asyncio
    for backoff in (1,2,4,8,16,30):
        try:
            log.info("⏳ Conectando Huawei (async) %s:%s slave=%s ...", INVERTER_IP, MODBUS_PORT, SLAVE_ID)
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            kwargs = {}
            # MAX_REG_READS si está soportado por tu versión
            try:
                if MAX_REG_READS and MAX_REG_READS > 0:
                    kwargs["max_reg_reads"] = MAX_REG_READS
            except Exception:
                pass
            try:
                cli = loop.run_until_complete(HSClientAsync.create(INVERTER_IP, MODBUS_PORT, SLAVE_ID, **kwargs))
            except TypeError:
                # versión antigua sin max_reg_reads
                cli = loop.run_until_complete(HSClientAsync.create(INVERTER_IP, MODBUS_PORT, SLAVE_ID))
            log.info("✅ Huawei conectado (async) ☑️")
            return ("async", (cli, loop))
        except Exception as e:
            log.warning("Fallo Huawei (async): %s (reintento en %ss)", e, backoff)
            time.sleep(backoff)
    raise RuntimeError("No se pudo conectar al inversor (async)")

def make_huawei_client() -> Tuple[str, Any]:
    if FORCE_SYNC and HSClientSync is not None:
        return _connect_huawei_sync()
    if HSClientSync is not None:
        return _connect_huawei_sync()
    return _connect_huawei_async()

def _read_register(mode: str, client: Any, key) -> Any:
    t0 = time.time()
    if mode == "sync":
        mid = client.get(key, SLAVE_ID)   # sync API
    else:
        cli, loop = client
        mid = loop.run_until_complete(cli.get(key, SLAVE_ID))
    duration = time.time() - t0
    log.debug("Leído %s = %s (%.2fs)", key, getattr(mid, "value", mid), duration)
    return getattr(mid, "value", mid)

# --- cache para publicar solo cambios ---
_last_values: dict[str, Any] = {}

def _changed(name: str, new_val: Any) -> bool:
    if name not in _last_values:
        _last_values[name] = new_val
        return True
    old = _last_values[name]
    # comparar floats con EPS
    try:
        if isinstance(new_val, (int, float)) and isinstance(old, (int, float)):
            if math.isnan(float(new_val)) and math.isnan(float(old)):
                return False
            if abs(float(new_val) - float(old)) >= CHANGE_EPS:
                _last_values[name] = new_val
                return True
            return False
    except Exception:
        pass
    if new_val != old:
        _last_values[name] = new_val
        return True
    return False

def _publish(mqttc: mqtt.Client, topic: str, payload: str):
    try:
        mqttc.publish(topic, payload, qos=MQTT_QOS)
    except Exception as e:
        log.warning("⚠️ Fallo publicando %s: %s", topic, e)

def _safe_read_and_publish(mode, hclient, mqttc, key, prefix="inverter/Huawei/") -> bool:
    """Devuelve True si leyó y publicó (o decidió no publicar por unchanged); False si falló lectura."""
    name = str(key)
    try:
        val = _read_register(mode, hclient, key)
        topic = f"{prefix}{name}"
        if PUBLISH_CHANGED_ONLY:
            if _changed(name, val):
                _publish(mqttc, topic, str(val))
                log.debug("📤 %s => %s", topic, val)
            else:
                log.debug("⏭️  %s sin cambios (skip)", topic)
        else:
            _publish(mqttc, topic, str(val))
            log.debug("📤 %s => %s", topic, val)
        return True
    except Exception as e:
        log.warning("🛑 Lectura fallida (%s): %s", name, e)
        return False

def _reconnect_huawei(mode_client: Tuple[str, Any]) -> Tuple[str, Any]:
    log.info("🔄 Reintentando conexión al inversor...")
    try:
        # intenta cerrar si es async
        mode, cli = mode_client
        if mode != "sync":
            try:
                c, loop = cli
                loop.run_until_complete(c.stop())
            except Exception:
                pass
    except Exception:
        pass
    return make_huawei_client()

def main():
    start_time = datetime.now()
    log.info("=== ✅ Huawei MQTT Publisher (simple) iniciado a las %s ===", start_time.strftime("%H:%M:%S"))
    mqttc = mqtt_connect_blocking()
    mode_client = make_huawei_client()
    mode, hclient = mode_client

    periodic_tick = 0
    read_ok_total = read_fail_total = 0
    consecutive_fail_reads = 0
    FAIL_RECONNECT_THRESHOLD = 6  # si fallan muchas seguidas, reconecta inversor

    while True:
        cycle_start = time.time()
        ok = fail = 0
        log.info("--- Ciclo de lectura iniciado ---")

        # Inmediatos (rápidos)
        for key in VARS_IMMEDIATE:
            if _safe_read_and_publish(mode, hclient, mqttc, key):
                ok += 1; read_ok_total += 1; consecutive_fail_reads = 0
            else:
                fail += 1; read_fail_total += 1; consecutive_fail_reads += 1
            time.sleep(PER_READ_DELAY)

            if consecutive_fail_reads >= FAIL_RECONNECT_THRESHOLD:
                log.warning("🧯 Demasiados fallos consecutivos de lectura (%d). Reconectando inversor.", consecutive_fail_reads)
                mode_client = _reconnect_huawei(mode_client)
                mode, hclient = mode_client
                consecutive_fail_reads = 0
                # pequeña pausa tras reconectar
                time.sleep(0.5)

        # Periódicos cada N ciclos
        periodic_tick += 1
        if periodic_tick >= PERIODIC_EVERY:
            log.info("→ Lectura periódica (tick=%s)", periodic_tick)
            for key in VARS_PERIODIC:
                if _safe_read_and_publish(mode, hclient, mqttc, key):
                    ok += 1; read_ok_total += 1; consecutive_fail_reads = 0
                else:
                    fail += 1; read_fail_total += 1; consecutive_fail_reads += 1
                time.sleep(PER_READ_DELAY)

                if consecutive_fail_reads >= FAIL_RECONNECT_THRESHOLD:
                    log.warning("🧯 Demasiados fallos consecutivos (periódicos). Reconectando inversor.")
                    mode_client = _reconnect_huawei(mode_client)
                    mode, hclient = mode_client
                    consecutive_fail_reads = 0
                    time.sleep(0.5)

            periodic_tick = 0

        elapsed = time.time() - cycle_start
        log.info("Fin de ciclo (%.2fs). OK=%d, Fail=%d | Totales OK=%d Fail=%d ✅",
                 elapsed, ok, fail, read_ok_total, read_fail_total)

        # descanso entre ciclos
        time.sleep(READ_INTERVAL)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log.info("🛑 Interrumpido por el usuario; apagando limpiamente...")
        pass