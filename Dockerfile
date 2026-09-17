# Imagen del ideador de contenido.
#
# Un solo proceso: el API y el worker viven juntos. El worker es un bucle
# asyncio que arranca con la aplicación (ver app/main.py).
#
# IMPORTANTE: un solo proceso de uvicorn, sin --workers. Cada proceso
# levantaría su propio bucle, y aunque no se duplicaría el trabajo (tomar una
# generación es atómico en la base), el límite de "máximo 2 generaciones a la
# vez" pasaría a contar por proceso en vez de en total, y el gasto se
# multiplicaría por el número de procesos.

FROM python:3.12-slim

# PYTHONUNBUFFERED para que los logs salgan en EasyPanel en el momento, no
# cuando se llene el buffer.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Las dependencias en su propia capa: mientras requirements.txt no cambie,
# Docker reutiliza esta capa y el despliegue tarda segundos en vez de minutos.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ ./app/
COPY prompts/ ./prompts/

# No corre como root: si alguien lograra ejecutar algo dentro del contenedor,
# no tendría permisos para tocar el sistema.
RUN useradd --create-home --uid 1000 adlek && chown -R adlek:adlek /app
USER adlek

EXPOSE 8000

# EasyPanel usa esta comprobación para saber si la app está viva y para no
# mandar tráfico a un contenedor que todavía está arrancando.
HEALTHCHECK --interval=30s --timeout=10s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/salud', timeout=5)"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
