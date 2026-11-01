"""Pruebas de la API en modo prueba (pesos aleatorios): validan contrato, errores y tiempos, no la medicina."""
import io
import os

import numpy as np
import pytest
from PIL import Image

os.environ.setdefault("OVARA_MODO_PRUEBA", "1")
os.environ.setdefault("OVARA_MODELOS", "/ruta/que/no/existe")

from fastapi.testclient import TestClient  # noqa: E402

from app.inferencia import caja_recorte, componentes, jet  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture(scope="module")
def cliente():
    with TestClient(app) as c:
        yield c


def ultrasonido_sintetico(ancho=640, alto=480) -> bytes:
    rng = np.random.default_rng(0)
    a = (rng.random((alto, ancho)) * 90).astype(np.uint8)
    yy, xx = np.mgrid[:alto, :ancho]
    a[((yy - alto / 2) ** 2 / 90 ** 2 + (xx - ancho / 2) ** 2 / 130 ** 2) < 1] = 40   # "quiste" oscuro
    buf = io.BytesIO(); Image.fromarray(a).convert("RGB").save(buf, format="JPEG"); return buf.getvalue()


def test_health(cliente):
    r = cliente.get("/health")
    assert r.status_code == 200
    assert r.json()["modelo_cargado"] is True and r.json()["modo_prueba"] is True


def test_info(cliente):
    j = cliente.get("/info").json()
    assert j["umbral"] == 0.28 and j["n_redes"] >= 1 and "aviso" in j


def test_predict_contrato(cliente):
    r = cliente.post("/predict", files={"imagen": ("prueba.jpg", ultrasonido_sintetico(), "image/jpeg")})
    assert r.status_code == 200, r.text
    j = r.json()
    assert 0.0 <= j["probabilidad"] <= 1.0
    assert j["alerta"] == (j["probabilidad"] >= j["umbral"])
    assert j["acuerdo"]["redes_total"] >= 1
    for k in ("contorno", "recorte", "atencion"):
        assert j["imagenes"][k].startswith("data:image/png;base64,")
    assert j["tiempos_ms"]["total"] > 0


def test_predict_sin_gradcam(cliente):
    r = cliente.post("/predict?gradcam=false", files={"imagen": ("p.png", ultrasonido_sintetico(320, 240), "image/png")})
    assert r.status_code == 200 and "atencion" not in r.json()["imagenes"]


def test_rechaza_no_imagen(cliente):
    r = cliente.post("/predict", files={"imagen": ("x.txt", b"hola", "text/plain")})
    assert r.status_code == 415


def test_rechaza_imagen_corrupta(cliente):
    r = cliente.post("/predict", files={"imagen": ("x.jpg", b"no soy jpg", "image/jpeg")})
    assert r.status_code == 422


def test_utilidades():
    m = np.zeros((100, 100), np.uint8); m[10:30, 10:30] = 1; m[60:62, 60:62] = 1
    regs = componentes(m, area_min=0.005)
    assert len(regs) == 1 and regs[0].sum() == 400          # la región diminuta (0.04 %) se descarta
    caja = caja_recorte(regs[0])
    assert caja[2] - caja[0] == caja[3] - caja[1]           # recorte cuadrado
    assert jet(np.array([0.0, 1.0])).shape == (2, 3)
