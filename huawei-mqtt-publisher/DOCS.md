# 🟩 Huawei Inverter MQTT Publisher (simple)

Publica en tiempo real los datos de tu inversor **Huawei SUN2000** (y compatibles) hacia **MQTT**, utilizando el protocolo **Modbus TCP**.  
Está diseñado para ser **ligero, fiable y fácil de integrar** con Home Assistant o cualquier otro sistema que lea MQTT.

---

## 🚀 Características

- 📡 **Lectura directa del inversor Huawei** (vía Modbus TCP)  
- 🔄 **Publicación automática en MQTT** con etiquetas del tipo:  
  `inverter/Huawei/ACTIVE_POWER`, `inverter/Huawei/GRID_VOLTAGE`, etc.
- ⚙️ Compatible con **core-mosquitto** y brokers externos  
- ⚡ **Modo “solo cambios”** para reducir tráfico MQTT  
- 🧠 **Reconexión automática y detección de conflictos** (p. ej., si la app FusionSolar interfiere)  
- 🔒 **Exclusividad local**: impide que dos instancias del add-on se conecten al mismo inversor a la vez  
- 🩺 Publica estado de salud en `inverter/Huawei/health`  
- 🟢 Extremadamente ligero: sin hilos, sin callbacks, con un único bucle síncrono controlado

---

## ⚙️ Configuración

### 🔌 Conexión Modbus

| Parámetro | Tipo | Ejemplo | Descripción |
|------------|------|----------|-------------|
| **inverter_ip** | str | `192.168.1.102` | IP del inversor Huawei (SUN2000, FusionHome, etc.) |
| **modbus_port** | int/str | `502` o `"auto"` | Puerto Modbus TCP. Usa `"auto"` para que detecte automáticamente entre 502 y 6607. |
| **modbus_slave_id** | int | `1` | ID del esclavo Modbus (normalmente 1 si hay SDongle, 0 si conectas directamente al AP del inversor). |

> 💡 Si el inversor no responde en el puerto 502, prueba el 6607 o usa `"auto"`.

---

### 🌐 Conexión MQTT

| Parámetro | Tipo | Ejemplo | Descripción |
|------------|------|----------|-------------|
| **mqtt_host** | str | `core-mosquitto` | Dirección del broker MQTT. |
| **mqtt_port** | int | `1883` | Puerto MQTT. Usa `8883` para TLS. |
| **mqtt_username** | str | `usuario` | Usuario MQTT (opcional). |
| **mqtt_password** | password | `******` | Contraseña MQTT (opcional). |
| **mqtt_qos** | int | `0` o `1` | Nivel de QoS (recomendado 0 o 1). |
| **mqtt_client_id** | str | `huawei-mqtt-publisher` | Identificador del cliente MQTT. |
| **mqtt_protocol** | list(311\|5) | `311` | Versión del protocolo MQTT. |
| **mqtt_tls** | bool | `false` | Habilita conexión TLS. |
| **mqtt_keepalive** | int | `60` | Intervalo de *keepalive* (en segundos). |

---

### 🧩 Parámetros de lectura

| Parámetro | Tipo | Por defecto | Descripción |
|------------|------|--------------|--------------|
| **read_interval** | float | `1.2` | Tiempo de espera entre ciclos completos de lectura (en segundos). |
| **per_read_delay** | float | `0.12` | Pausa entre cada lectura Modbus individual (para evitar saturar el inversor). |
| **periodic_every** | int | `8` | Número de ciclos tras los cuales se leen los registros “periódicos” (energías, estado, etc.). |

---

### ⚙️ Parámetros avanzados

| Parámetro | Tipo | Por defecto | Descripción |
|------------|------|--------------|-------------|
| **force_sync** | bool | `true` | Fuerza el modo síncrono (más estable en Raspberry Pi y contenedores pequeños). |
| **max_reg_reads** | int | `1` | Máx. de registros leídos por petición (solo para modo asíncrono). |
| **publish_changed_only** | bool | `true` | Publica en MQTT solo si el valor ha cambiado significativamente. |
| **change_eps** | float | `0.01` | Umbral mínimo de cambio (para valores float). Cambios menores se ignoran. |

---

### 🧮 Variables de lectura

Puedes personalizar qué registros Modbus se leen y publican.

#### 🔹 VARS_IMMEDIATE  
Datos de actualización rápida (cada ciclo):  

```yaml
vars_immediate:
  - INPUT_POWER
  - ACTIVE_POWER
  - POWER_FACTOR
  - GRID_VOLTAGE
  - GRID_CURRENT
  - GRID_FREQUENCY
```

#### 🔹 VARS_PERIODIC  
Datos de actualización más lenta (cada *periodic_every* ciclos):  

```yaml
vars_periodic:
  - DEVICE_STATUS
  - INTERNAL_TEMPERATURE
  - DAILY_YIELD_ENERGY
  - MONTHLY_YIELD_ENERGY
  - YEARLY_YIELD_ENERGY
  - EFFICIENCY
```

> 🧠 Estos nombres corresponden directamente a los registros definidos en `huawei_solar.register_names`.  
> Si introduces uno incorrecto, se mostrará un aviso en los logs.

---

## 📊 Topics MQTT publicados

| Topic | Descripción | Ejemplo de valor |
|--------|--------------|------------------|
| `inverter/Huawei/ACTIVE_POWER` | Potencia activa instantánea | `-1234.5` |
| `inverter/Huawei/GRID_VOLTAGE` | Tensión de red | `230.4` |
| `inverter/Huawei/INTERNAL_TEMPERATURE` | Temperatura interna del inversor | `41.2` |
| `inverter/Huawei/DAILY_YIELD_ENERGY` | Energía diaria generada (kWh) | `6.73` |
| `inverter/Huawei/status` | Estado del add-on | `online ✅ / offline` |
| `inverter/Huawei/health` | Telemetría JSON con métricas internas | `{"ok_total":56,"fail_total":1,"conflicts":0}` |

---

## 🩻 Supervisión y logs

- Los mensajes de log muestran:
  - `Leído ... = ...` → lectura correcta  
  - `Lectura fallida (...)` → fallo puntual (se reintenta)  
  - `🚨 Posible conflicto de conexión Modbus` → otro cliente (app o integración) está usando Modbus  
  - `✅ Huawei conectado (sync)` → conexión establecida correctamente

- En caso de conflicto repetido, el add-on:
  - Espera unos segundos (*cooldown*)  
  - Cierra y reabre la conexión Modbus automáticamente

---

## 🧰 Consejos y resolución de problemas

| Problema | Posible causa | Solución |
|-----------|----------------|-----------|
| ⚠️ `Cancel send, because not connected!` | Otro cliente (app FusionSolar, HA integration, EVCC...) ocupa el puerto Modbus. | Cierra la app o usa solo este add-on. |
| 💤 Lecturas muy lentas | Intervalos demasiado cortos o congestión. | Aumenta `per_read_delay` (0.3–0.5) y `read_interval` (10–15 s). |
| 🔒 Error de lockfile | Otra instancia del add-on está corriendo. | Detén el add-on duplicado o reinicia el host. |
| ❌ No conecta al inversor | Puerto incorrecto o firewall. | Usa `"auto"` en `modbus_port` o prueba `6607`. |
| 🛑 MQTT error | Broker no accesible. | Verifica `mqtt_host`, usuario/contraseña y puerto. |

---

## 📦 Integración con Home Assistant

Una vez publicados los valores en MQTT, puedes usar la integración **MQTT Sensor**:

```yaml
sensor:
  - platform: mqtt
    name: "Huawei Active Power"
    state_topic: "inverter/Huawei/ACTIVE_POWER"
    unit_of_measurement: "W"
```

O importar el conjunto completo de topics a través de un *discovery template* (ver ejemplos en la wiki).

---

## 📚 Créditos y compatibilidad

- Basado en la librería [**wlcrs/huawei_solar**](https://github.com/wlcrs/huawei_solar)  
- Probado con inversores **Huawei SUN2000-3KTL-M1**, **SUN2000-5KTL-M1** y **SUN2000-6KTL-L1**  
- Compatible con **Raspberry Pi 4/5**, **NUC**, y **Home Assistant OS ≥ 2024.10**

---
