ARG BUILD_FROM
FROM ${BUILD_FROM}

# Herramientas base para compilar wheels si hace falta
RUN apk add --no-cache python3 python3-dev gcc musl-dev linux-headers

# Virtualenv en /opt/venv y PATH
ENV VIRTUAL_ENV=/opt/venv
ENV PATH="$VIRTUAL_ENV/bin:$PATH"

# Crear venv e instalar deps dentro del venv (evita PEP 668)
RUN python3 -m venv "$VIRTUAL_ENV" \
 && pip install --upgrade pip \
 && pip install --no-cache-dir huawei-solar paho-mqtt

# Copia tu script a /app (ajusta el nombre si es distinto)
COPY huawei_mqtt_publisher.py /app/

# Copia s6 services y da permisos (RUTA CORRECTA)
COPY rootfs/ /
RUN chmod +x /etc/services.d/huawei-mqtt/run /etc/services.d/huawei-mqtt/finish || true