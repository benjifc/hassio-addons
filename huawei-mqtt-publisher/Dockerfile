ARG BUILD_FROM
FROM ${BUILD_FROM}

# Paquetes del sistema (compilar dependencias si hace falta)
RUN apk add --no-cache python3 python3-dev gcc musl-dev linux-headers

# Crear venv y meterlo en el PATH
ENV VIRTUAL_ENV=/opt/venv
ENV PATH="$VIRTUAL_ENV/bin:$PATH"

# Crear venv e instalar dependencias Python dentro del venv
RUN python3 -m venv "$VIRTUAL_ENV" \
 && pip install --upgrade pip \
 && pip install --no-cache-dir huawei-solar paho-mqtt

# Copiar rootfs (s6-overlay) y asegurarte de permisos de los servicios
COPY rootfs /
RUN chmod +x /etc/services.d/huawei/run /etc/services.d/huawei/finish || true