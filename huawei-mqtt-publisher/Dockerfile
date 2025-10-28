ARG BUILD_FROM
FROM $BUILD_FROM

# Instalar dependencias
RUN apk add --no-cache python3 python3-dev py3-pip gcc musl-dev linux-headers

# Copiar el script
COPY run.sh /
COPY huawei_mqtt.py /

# Instalar dependencias de Python
RUN pip3 install --no-cache-dir huawei-solar paho-mqtt

# Permisos
RUN chmod +x /run.sh

# Ejecutar
CMD [ "/run.sh" ]