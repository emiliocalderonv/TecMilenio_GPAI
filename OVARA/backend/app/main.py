"""API de inferencia OVARA (FastAPI). La consume el frontend Node.js."""
from __future__ import annotations

import io
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.responses import JSONResponse
from PIL import Image, UnidentifiedImageError

from .inferencia import ModelosNoEncontrados, MotorOVARA

VERSION_API = "1.0.0"
MAX_BYTES = int(os.getenv("OVARA_MAX_MB", "10")) * 1024 * 1024
TIPOS = {"image/jpeg", "image/png", "image/bmp", "image/tiff", "image/webp"}
log = logging.getLogger("ovara")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
estado: dict = {"motor": None, "error": None}

AVISO = ("Demo académico (Tecmilenio · Gestión de Proyectos de IA). No es un dispositivo médico ni sustituye "
         "el juicio clínico. Modelo entrenado y evaluado solo con MMOTU (un centro); pendiente validación externa.")


def iniciar_motor():
    try:
        motor = MotorOVARA(os.getenv("OVARA_MODELOS", "/modelos"),
                           modo_prueba=os.getenv("OVARA_MODO_PRUEBA", "0") == "1",
                           hilos=int(os.getenv("OVARA_HILOS", "0")) or None)
        estado.update(motor=motor, error=None)
        log.info("Modelo cargado: %s redes, umbral %.2f, %.1f s", len(motor.clasificadores), motor.umbral, motor.t_carga)
    except ModelosNoEncontrados as e:
        estado.update(motor=None, error=str(e))
        log.error(str(e))


@asynccontextmanager
async def ciclo_vida(_app: FastAPI):
    iniciar_motor()
    yield


app = FastAPI(title="OVARA · API de inferencia", version=VERSION_API, lifespan=ciclo_vida,
              description="Segmentación (U-Net) + ensamble de CNN para alerta de endometrioma en ultrasonido. " + AVISO)


@app.get("/health")
def salud():
    m = estado["motor"]
    cuerpo = {"estado": "ok" if m else "sin_modelo", "version_api": VERSION_API, "modelo_cargado": m is not None,
              "modo_prueba": bool(m and m.info()["modo_prueba"]), "error": estado["error"]}
    return JSONResponse(cuerpo, status_code=200 if m else 503)


@app.get("/info")
def info():
    m = estado["motor"]
    if not m:
        raise HTTPException(503, estado["error"] or "Modelo no cargado")
    return {**m.info(), "version_api": VERSION_API, "aviso": AVISO}


@app.post("/predict")
async def predecir(imagen: UploadFile = File(..., description="Ultrasonido en modo B (jpg/png)"),
                   gradcam: bool = Query(True, description="Calcular mapa de atención (más lento)")):
    m = estado["motor"]
    if not m:
        raise HTTPException(503, estado["error"] or "Modelo no cargado")
    if imagen.content_type not in TIPOS:
        raise HTTPException(415, f"Tipo de archivo no soportado ({imagen.content_type}). Usa JPG o PNG.")
    datos = await imagen.read(MAX_BYTES + 1)
    if len(datos) > MAX_BYTES:
        raise HTTPException(413, f"La imagen supera {MAX_BYTES // (1024 * 1024)} MB")
    try:
        img = Image.open(io.BytesIO(datos)); img.load()
    except (UnidentifiedImageError, OSError):
        raise HTTPException(422, "No se pudo leer la imagen")
    from starlette.concurrency import run_in_threadpool
    resultado = await run_in_threadpool(m.analizar, img, gradcam)
    log.info("predict %s → p=%.3f alerta=%s (%.0f ms)", imagen.filename, resultado["probabilidad"],
             resultado["alerta"], resultado["tiempos_ms"]["total"])
    return {"archivo": imagen.filename, **resultado, "aviso": AVISO}
