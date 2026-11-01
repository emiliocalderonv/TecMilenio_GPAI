"""
Motor de inferencia OVARA (reproduce exactamente el flujo validado en Experimento_CNN):

  ultrasonido → U-Net localiza la lesión (región mayor) → recorte cuadrado con 30 % de margen
             → ensamble de CNN (promedio de probabilidades) → alerta si prob ≥ umbral
  + Grad-CAM promedio del ensamble para mostrar dónde "miró" el modelo.
"""
from __future__ import annotations

import base64
import io
import json
import os
import threading
import time
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F
from PIL import Image, ImageDraw
from scipy import ndimage
from torchvision.transforms import v2 as T

from .arquitecturas import UNetResNet18, capa_gradcam, crear_clasificador

MEDIA, DESV = [0.485, 0.456, 0.406], [0.229, 0.224, 0.225]
TAM_SEG, TAM_CLF, MARGEN = 384, 224, 1.3
TF_SEG = T.Compose([T.ToImage(), T.Resize((TAM_SEG, TAM_SEG)), T.ToDtype(torch.float32, scale=True), T.Normalize(MEDIA, DESV)])
TF_CLF = T.Compose([T.ToImage(), T.Resize((TAM_CLF, TAM_CLF)), T.ToDtype(torch.float32, scale=True), T.Normalize(MEDIA, DESV)])
LADO_MAX_ENTRADA = 2048          # imágenes más grandes se reducen (MMOTU ronda 960 px)
LADO_MAX_SALIDA = 900            # tamaño de las imágenes que se devuelven al navegador


class ModelosNoEncontrados(RuntimeError):
    pass


# ------------------------------------------------------------------------------------------------ utilidades de imagen
def componentes(m: np.ndarray, area_min: float) -> list[np.ndarray]:
    """Regiones detectadas (mayor primero) que ocupen al menos `area_min` de la imagen; huecos rellenos."""
    etiquetas, n = ndimage.label(m)
    if n == 0:
        return []
    tam = np.asarray(ndimage.sum(m, etiquetas, range(1, n + 1)))
    orden = np.argsort(-tam)
    quedan = [k for j, k in enumerate(orden) if j == 0 or tam[k] / m.size >= area_min]
    return [ndimage.binary_fill_holes(etiquetas == (k + 1)).astype(np.uint8) for k in quedan]


def caja_recorte(m: np.ndarray):
    ys, xs = np.where(m > 0)
    if len(ys) == 0:
        return None
    y0, y1, x0, x1 = ys.min(), ys.max(), xs.min(), xs.max()
    lado = int(max(y1 - y0, x1 - x0) * MARGEN) + 16
    cy, cx = (y0 + y1) // 2, (x0 + x1) // 2
    return (int(cx - lado // 2), int(cy - lado // 2), int(cx + lado // 2), int(cy + lado // 2))


def jet(v: np.ndarray) -> np.ndarray:
    """Mapa de color 'jet' (azul → rojo) sin depender de matplotlib. v en [0, 1] → RGB uint8."""
    anclas = np.array([0.0, 0.125, 0.375, 0.625, 0.875, 1.0])
    r = np.interp(v, anclas, [0, 0, 0, 1, 1, 0.5]); g = np.interp(v, anclas, [0, 0, 1, 1, 0, 0])
    b = np.interp(v, anclas, [0.5, 1, 1, 0, 0, 0])
    return (np.stack([r, g, b], -1) * 255).astype(np.uint8)


def a_png64(img: Image.Image) -> str:
    if max(img.size) > LADO_MAX_SALIDA:
        img = img.copy(); img.thumbnail((LADO_MAX_SALIDA, LADO_MAX_SALIDA), Image.LANCZOS)
    buf = io.BytesIO(); img.save(buf, format="PNG", optimize=True)
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def dibujar_contorno(img: Image.Image, m: np.ndarray | None, caja) -> Image.Image:
    out = np.array(img).copy()
    if m is not None and m.any():
        grosor = max(2, round(max(img.size) / 320))
        borde = m.astype(bool) & ~ndimage.binary_erosion(m.astype(bool), iterations=grosor)
        out[borde] = (255, 212, 0)
    res = Image.fromarray(out)
    if caja is not None:
        d = ImageDraw.Draw(res)
        d.rectangle(caja, outline=(0, 200, 255), width=max(1, round(max(img.size) / 480)))
    return res


# ------------------------------------------------------------------------------------------------ motor
class MotorOVARA:
    def __init__(self, dir_modelos: str | Path, modo_prueba: bool = False, hilos: int | None = None):
        self.dir = Path(dir_modelos)
        self.modo_prueba = modo_prueba
        self.dev = torch.device("cpu")
        torch.set_num_threads(hilos or max(1, os.cpu_count() or 1))
        self._lock = threading.Lock()
        t0 = time.perf_counter()
        self.cfg = self._config()
        self.umbral = float(self.cfg["umbral"])
        self.area_min = float(self.cfg.get("area_min", 0.005))
        self.estrategia = self.cfg.get("estrategia", "mayor")
        self.segmentador = self._cargar(UNetResNet18(), self.cfg["segmentador"])
        self.clasificadores = [(c["arch"], self._cargar(crear_clasificador(c["arch"]), c["archivo"])) for c in self.cfg["clasificadores"]]
        self.t_carga = time.perf_counter() - t0

    # -------- carga
    def _config(self) -> dict:
        ruta = self.dir / "modelo_ovara.json"
        if ruta.exists():
            return json.loads(ruta.read_text(encoding="utf-8"))
        if self.modo_prueba:
            return {"version": "modo-prueba", "umbral": 0.28, "estrategia": "mayor", "area_min": 0.005,
                    "segmentador": None, "clasificadores": [{"arch": "resnet18", "archivo": None}] * 2,
                    "descripcion": "Pesos aleatorios: SOLO para probar la integración, no da resultados clínicos"}
        raise ModelosNoEncontrados(
            f"No encontré {ruta}. Copia los pesos en la carpeta 'modelos' (scripts/exportar_modelo.py o "
            f"scripts/descargar_modelos.py) o arranca con OVARA_MODO_PRUEBA=1 para probar sin pesos.")

    def _cargar(self, red: torch.nn.Module, archivo: str | None) -> torch.nn.Module:
        if archivo is None:                              # modo prueba: pesos aleatorios reproducibles
            torch.manual_seed(0)
        else:
            ruta = self.dir / archivo
            if not ruta.exists():
                raise ModelosNoEncontrados(f"Falta el archivo de pesos {ruta}")
            estado = torch.load(ruta, map_location="cpu", weights_only=True)
            red.load_state_dict({k: v.float() if v.is_floating_point() else v for k, v in estado.items()})
        return red.float().to(self.dev).eval()

    # -------- pasos del flujo
    @torch.no_grad()
    def _segmentar(self, img: Image.Image) -> list[np.ndarray]:
        x = TF_SEG(img)[None].to(self.dev)
        p = torch.sigmoid(self.segmentador(x).float())
        p = F.interpolate(p, size=(img.height, img.width), mode="bilinear", align_corners=False)[0, 0]
        return componentes((p >= 0.5).cpu().numpy(), self.area_min)

    def _clasificar(self, recorte: Image.Image, con_gradcam: bool):
        x = TF_CLF(recorte)[None].to(self.dev)
        probs, cams = [], []
        for arch, m in self.clasificadores:
            if not con_gradcam:
                with torch.no_grad():
                    probs.append(float(torch.sigmoid(m(x)).item()))
                continue
            act = {}
            h = capa_gradcam(m, arch).register_forward_hook(lambda _m, _i, o: act.__setitem__("a", o))
            with torch.enable_grad():
                logit = m(x).squeeze()
                g = torch.autograd.grad(logit, act["a"])[0]
            h.remove()
            probs.append(float(torch.sigmoid(logit.detach()).item()))
            cam = torch.relu((g.mean(dim=(2, 3), keepdim=True) * act["a"]).sum(1, keepdim=True))
            cam = F.interpolate(cam, size=(TAM_CLF, TAM_CLF), mode="bilinear", align_corners=False)[0, 0]
            cams.append((cam / (cam.max() + 1e-8)).detach().cpu().numpy())
        cam = np.mean(cams, axis=0) if cams else None
        return np.array(probs), cam

    # -------- API pública
    def analizar(self, img: Image.Image, con_gradcam: bool = True) -> dict:
        img = img.convert("RGB")
        reducida = max(img.size) > LADO_MAX_ENTRADA
        if reducida:
            img.thumbnail((LADO_MAX_ENTRADA, LADO_MAX_ENTRADA), Image.LANCZOS)
        with self._lock:
            t0 = time.perf_counter()
            regiones = self._segmentar(img)
            t1 = time.perf_counter()
            mascara = regiones[0] if regiones else None          # estrategia "mayor" (la validada)
            if self.estrategia == "todas" and len(regiones) > 1:  # analiza cada región y se queda con la más sospechosa
                medias = [self._clasificar(img.crop(caja_recorte(r)), False)[0].mean() for r in regiones]
                mascara = regiones[int(np.argmax(medias))]
            caja = caja_recorte(mascara) if mascara is not None else None
            recorte = img.crop(caja) if caja else img
            probs, cam = self._clasificar(recorte, con_gradcam)
            t2 = time.perf_counter()
        p = float(probs.mean())
        alerta = p >= self.umbral
        votos = int((probs >= self.umbral).sum())

        salida = {
            "probabilidad": round(p, 4), "umbral": self.umbral, "alerta": bool(alerta),
            "mensaje": ("Alerta: hallazgos compatibles con endometrioma. Se sugiere revisión del especialista."
                        if alerta else "Sin alerta de endometrioma en la lesión analizada."),
            "acuerdo": {"redes_en_alerta": votos, "redes_total": len(probs),
                        "desviacion_probabilidades": round(float(probs.std()), 4)},
            "lesion": {"detectada": mascara is not None, "regiones_detectadas": len(regiones),
                       "area_porcentaje": round(100 * float(mascara.mean()), 2) if mascara is not None else 0.0,
                       "caja_recorte": list(caja) if caja else None},
            "imagen": {"ancho": img.width, "alto": img.height, "reducida": reducida},
            "tiempos_ms": {"segmentacion": round(1000 * (t1 - t0), 1), "clasificacion": round(1000 * (t2 - t1), 1),
                           "total": round(1000 * (t2 - t0), 1)},
            "modo_prueba": self.modo_prueba and self.cfg.get("version") == "modo-prueba",
            "imagenes": {"contorno": a_png64(dibujar_contorno(img, mascara, caja)), "recorte": a_png64(recorte)},
        }
        if cam is not None:
            calor = Image.fromarray(jet(cam)).resize(recorte.size, Image.BILINEAR)
            salida["imagenes"]["atencion"] = a_png64(Image.blend(recorte.convert("RGB"), calor, 0.4))
        return salida

    def info(self) -> dict:
        return {"version": self.cfg.get("version"), "descripcion": self.cfg.get("descripcion"),
                "umbral": self.umbral, "estrategia": self.estrategia,
                "redes": [a for a, _ in self.clasificadores], "n_redes": len(self.clasificadores),
                "metricas_validacion": self.cfg.get("metricas_validacion"),
                "fecha_exportacion": self.cfg.get("fecha_exportacion"),
                "modo_prueba": self.cfg.get("version") == "modo-prueba",
                "segundos_carga": round(self.t_carga, 2)}
