# Huawei Inverter MQTT Publisher

Publica en tiempo real los datos de tu inversor Huawei Solar en MQTT.

## Configuración

- **inverter_ip**: IP del inversor Huawei (ej: 192.168.1.102)
- **modbus_port**: Puerto Modbus TCP (normalmente 502)
- **modbus_slave_id**: ID del esclavo Modbus (normalmente 1)
- **mqtt_host**: Host del broker MQTT (usa `core-mosquitto` si usas el add-on oficial)
- **mqtt_port**: Puerto MQTT (1883 o 8883 para TLS)
- **mqtt_username / password**: Credenciales MQTT