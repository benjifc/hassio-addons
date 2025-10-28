#!/bin/bash

# Cargar variables de entorno desde el add-on
export INVERTER_IP="{{ inverter_ip }}"
export MODBUS_PORT="{{ modbus_port }}"
export MODBUS_SLAVE_ID="{{ modbus_slave_id }}"
export MQTT_HOST="{{ mqtt_host }}"
export MQTT_PORT="{{ mqtt_port }}"
export MQTT_USERNAME="{{ mqtt_username }}"
export MQTT_PASSWORD="{{ mqtt_password }}"

# Ejecutar el script Python
exec python3 /huawei_mqtt.py