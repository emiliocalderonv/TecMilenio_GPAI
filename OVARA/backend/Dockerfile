# =============================================================================
# OVARA · backend de inferencia (FastAPI + PyTorch CPU)
#
# Forma recomendada de ejecutarlo: junto con el frontend, desde la carpeta OVARA
#     iniciar_demo.bat                      (todo en un paso)
#     docker compose up --build -d          (manual)  ->  http://localhost:3000
#
# Ejecutarlo solo (sin frontend), desde la carpeta OVARA:
#   1) Pesos del modelo:   python scripts/descargar_modelos.py
#   2) Construir:          docker build -t ovara-backend:1.0.0 ./backend
#   3) Ejecutar (Windows): docker run --rm -p 8000:8000 -v "%cd%\modelos:/modelos:ro" ovara-backend:1.0.0
#      (Linux / macOS):    docker run --rm -p 8000:8000 -v "$PWD/modelos:/modelos:ro" ovara-backend:1.0.0
#   4) Probar:             http://localhost:8000/docs   (POST /predict con una imagen)
#   Sin pesos (solo para probar la integración):  docker run --rm -p 8000:8000 -e OVARA_MODO_PRUEBA=1 ovara-backend:1.0.0
#   Pruebas unitarias:     docker run --rm -e OVARA_MODO_PRUEBA=1 ovara-backend:1.0.0 python -m pytest -q tests
# =============================================================================
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    OVARA_MODELOS=/modelos

WORKDIR /app

# 1) PyTorch CPU (rueda oficial, sin CUDA: imagen más ligera y corre en cualquier equipo)
RUN pip install --index-url https://download.pytorch.org/whl/cpu torch==2.8.0 torchvision==0.23.0

# 2) Resto de dependencias
COPY requirements.txt .
RUN pip install -r requirements.txt

# 3) Código
COPY app ./app
COPY tests ./tests
COPY paridad.py .

RUN useradd --create-home --uid 1000 ovara && chown -R ovara /app
USER ovara

EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=5s --start-period=90s --retries=5 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8000/health', timeout=4).status == 200 else 1)"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
