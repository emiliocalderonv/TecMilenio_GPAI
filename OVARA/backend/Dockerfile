# OVARA · backend de inferencia (FastAPI + PyTorch CPU)
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
