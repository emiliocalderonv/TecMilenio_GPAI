"""
datos_prep.py — Limpieza de datos y extracción de características (OVARA, Actividad 5).

Convierte el dataset de ultrasonido MMOTU (imágenes + máscara de la lesión) en una
tabla limpia de características interpretables para clasificar si la lesión ovárica
es un ENDOMETRIOMA ("quiste de chocolate", clase 0 de MMOTU) o no.

Entrada : datos/datos_ini/MMOTU/OTU_2d/{images, annotations, train_cls.txt, val_cls.txt}
Salida  : datos/datos_limp/mmotu_caracteristicas.csv
          datos/datos_limp/reporte_limpieza.json

Uso:
    python fuentes/datos_prep.py
    python fuentes/datos_prep.py --origen <ruta OTU_2d> --destino <ruta datos_limp>
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
from PIL import Image, UnidentifiedImageError
from scipy import stats
from skimage import measure, morphology
from skimage.feature import graycomatrix, graycoprops

RAIZ = Path(__file__).resolve().parents[1]
ORIGEN_DEF = RAIZ / "datos" / "datos_ini" / "MMOTU" / "OTU_2d"
DESTINO_DEF = RAIZ / "datos" / "datos_limp"

# Clases de MMOTU (OTU_2d). La clase 0 es el quiste de chocolate = endometrioma.
CLASES_MMOTU = {
    0: "quiste_chocolate", 1: "cistoadenoma_seroso", 2: "teratoma",
    3: "tumor_celulas_teca", 4: "quiste_simple", 5: "ovario_normal",
    6: "cistoadenoma_mucinoso", 7: "seroso_alto_grado",
}
CLASE_ENDOMETRIOMA = 0
MIN_AREA_REL = 0.001     # máscaras más pequeñas (<0.1 % de la imagen) se consideran inválidas
ANILLO_PX = 15           # grosor del anillo alrededor de la lesión para medir contraste
NIVELES_GLCM = 32


# ----------------------------------------------------------------------------- carga
def cargar_listas(origen: Path) -> pd.DataFrame:
    """Lee las listas oficiales de MMOTU (archivo y clase) y conserva su partición."""
    filas = []
    for split, nombre in (("train", "train_cls.txt"), ("test", "val_cls.txt")):
        for linea in (origen / nombre).read_text().splitlines():
            partes = linea.split()
            if len(partes) == 2:
                filas.append({"archivo": partes[0], "clase": int(partes[1]), "split": split})
    return pd.DataFrame(filas)


def cargar_par(origen: Path, archivo: str):
    """Devuelve (imagen RGB uint8, máscara bool, nota). nota != '' indica un problema."""
    stem = Path(archivo).stem
    p_img, p_mask = origen / "images" / archivo, origen / "annotations" / f"{stem}_binary.PNG"
    if not p_img.exists():
        return None, None, "imagen_faltante"
    if not p_mask.exists():
        return None, None, "mascara_faltante"
    try:
        img = np.array(Image.open(p_img).convert("RGB"))
        mask = np.array(Image.open(p_mask))
    except (UnidentifiedImageError, OSError):
        return None, None, "archivo_corrupto"
    if mask.ndim == 3:
        mask = mask[..., 0]
    nota = ""
    if mask.shape != img.shape[:2]:
        # Corrección: se reescala la máscara al tamaño de la imagen (vecino más cercano)
        mask = np.array(Image.fromarray(mask).resize(img.shape[1::-1], Image.NEAREST))
        nota = "mascara_reescalada"
    return img, mask > 0, nota


# ------------------------------------------------------------------- características
def _forma(mask: np.ndarray, h: int, w: int) -> dict:
    diag = float(np.hypot(h, w))
    etiquetas = measure.label(mask)
    props = sorted(measure.regionprops(etiquetas), key=lambda r: r.area, reverse=True)
    r = props[0]  # región principal
    area, perim = float(mask.sum()), float(measure.perimeter(mask))
    return {
        "area_rel": area / (h * w),
        "n_regiones": len(props),
        "perimetro_rel": perim / diag,
        "circularidad": float(4 * np.pi * r.area / max(r.perimeter, 1) ** 2),
        "solidez": float(r.solidity),
        "extension": float(r.extent),
        "excentricidad": float(r.eccentricity),
        "eje_mayor_rel": float(r.major_axis_length) / diag,
        "eje_menor_rel": float(r.minor_axis_length) / diag,
        "relacion_aspecto": float(r.major_axis_length / max(r.minor_axis_length, 1e-6)),
    }


def _intensidad(gris: np.ndarray, mask: np.ndarray) -> dict:
    v = gris[mask].astype(np.float64)
    hist = np.bincount(v.astype(np.uint8), minlength=256) / v.size
    anillo = morphology.binary_dilation(mask, morphology.disk(ANILLO_PX)) & ~mask
    fuera = gris[anillo].astype(np.float64) if anillo.any() else v
    return {
        "int_media": v.mean(), "int_std": v.std(), "int_mediana": np.median(v),
        "int_p10": np.percentile(v, 10), "int_p90": np.percentile(v, 90),
        "int_cv": v.std() / (v.mean() + 1e-6),
        "int_asimetria": float(stats.skew(v)), "int_curtosis": float(stats.kurtosis(v)),
        "int_entropia": float(-(hist[hist > 0] * np.log2(hist[hist > 0])).sum()),
        "contraste_borde": v.mean() - fuera.mean(),
        "razon_borde": v.mean() / (fuera.mean() + 1e-6),
    }


def _textura(gris: np.ndarray, mask: np.ndarray) -> dict:
    """GLCM calculada SOLO con pares de píxeles dentro de la lesión (nivel 0 = fuera)."""
    ys, xs = np.where(mask)
    y0, y1, x0, x1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
    rec, m = gris[y0:y1, x0:x1], mask[y0:y1, x0:x1]
    q = (rec.astype(np.int32) * (NIVELES_GLCM - 1) // 255 + 1) * m  # 1..N dentro, 0 fuera
    glcm = graycomatrix(q.astype(np.uint8), distances=[1, 3], angles=[0, np.pi / 4, np.pi / 2, 3 * np.pi / 4],
                        levels=NIVELES_GLCM + 1, symmetric=True, normed=False).astype(np.float64)
    glcm = glcm[1:, 1:]                       # descarta pares que tocan el fondo
    glcm /= np.maximum(glcm.sum(axis=(0, 1), keepdims=True), 1)
    return {f"glcm_{p}": float(graycoprops(glcm, p).mean())
            for p in ("contrast", "dissimilarity", "homogeneity", "energy", "correlation", "ASM")}


def _color(img: np.ndarray, mask: np.ndarray) -> dict:
    """Fracción de píxeles con color (Doppler) dentro y alrededor de la lesión → vascularidad."""
    rgb = img.astype(np.int16)
    sat = rgb.max(axis=2) - rgb.min(axis=2)
    zona = morphology.binary_dilation(mask, morphology.disk(ANILLO_PX))
    return {"frac_doppler": float((sat[zona] > 40).mean())}


def extraer_caracteristicas(img: np.ndarray, mask: np.ndarray) -> dict:
    h, w = mask.shape
    # Recorte a la lesión + margen: mismas medidas, ~10x más rápido que trabajar la imagen completa
    ys, xs = np.where(mask)
    m = ANILLO_PX + 2
    y0, y1 = max(ys.min() - m, 0), min(ys.max() + m + 1, h)
    x0, x1 = max(xs.min() - m, 0), min(xs.max() + m + 1, w)
    img, mask = img[y0:y1, x0:x1], mask[y0:y1, x0:x1]
    gris = np.array(Image.fromarray(img).convert("L"))
    return {**_forma(mask, h, w), **_intensidad(gris, mask), **_textura(gris, mask), **_color(img, mask),
            "img_alto": h, "img_ancho": w}


# ------------------------------------------------------------------------- limpieza
def limpiar(origen: Path = ORIGEN_DEF, destino: Path = DESTINO_DEF, verbose: bool = True) -> pd.DataFrame:
    destino.mkdir(parents=True, exist_ok=True)
    listas = cargar_listas(origen)
    reporte = {"registros_iniciales": int(len(listas)), "descartes": {}, "correcciones": {}}

    def descartar(motivo):
        reporte["descartes"][motivo] = reporte["descartes"].get(motivo, 0) + 1

    filas, hashes = [], {}
    for i, r in enumerate(listas.itertuples(index=False), 1):
        if r.clase not in CLASES_MMOTU:
            descartar("clase_invalida"); continue
        img, mask, nota = cargar_par(origen, r.archivo)
        if img is None:
            descartar(nota); continue
        h = hashlib.md5(img.tobytes()).hexdigest()
        if h in hashes:                       # imagen duplicada exacta
            descartar("duplicado"); continue
        hashes[h] = r.archivo
        if mask.mean() < MIN_AREA_REL:
            descartar("mascara_vacia_o_minima"); continue
        if nota:
            reporte["correcciones"][nota] = reporte["correcciones"].get(nota, 0) + 1
        feats = extraer_caracteristicas(img, mask)
        filas.append({"archivo": r.archivo, "split": r.split, "clase": r.clase,
                      "clase_nombre": CLASES_MMOTU[r.clase],
                      "endometrioma": int(r.clase == CLASE_ENDOMETRIOMA), **feats})
        if verbose and i % 200 == 0:
            print(f"  procesadas {i}/{len(listas)}")

    df = pd.DataFrame(filas)
    num = df.select_dtypes("number").columns
    inf = np.isinf(df[num]).sum().sum()
    df[num] = df[num].replace([np.inf, -np.inf], np.nan)
    nulos = int(df[num].isna().sum().sum())
    if nulos:  # imputación por mediana del conjunto de entrenamiento (evita fuga de información)
        med = df.loc[df.split == "train", num].median()
        df[num] = df[num].fillna(med)
    reporte["correcciones"]["infinitos_a_nulo"] = int(inf)
    reporte["correcciones"]["nulos_imputados_mediana_train"] = nulos
    df = df.round(6)

    reporte.update({
        "registros_finales": int(len(df)),
        "n_caracteristicas": int(len([c for c in df.columns if c not in ("archivo", "split", "clase", "clase_nombre", "endometrioma")])),
        "por_split": df.groupby("split").endometrioma.agg(["count", "sum"]).rename(columns={"count": "total", "sum": "endometriomas"}).to_dict("index"),
        "por_clase": df.clase_nombre.value_counts().to_dict(),
    })
    df.to_csv(destino / "mmotu_caracteristicas.csv", index=False, encoding="utf-8")
    (destino / "reporte_limpieza.json").write_text(json.dumps(reporte, indent=2, ensure_ascii=False), encoding="utf-8")
    if verbose:
        print(json.dumps(reporte, indent=2, ensure_ascii=False))
    return df


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--origen", type=Path, default=ORIGEN_DEF)
    ap.add_argument("--destino", type=Path, default=DESTINO_DEF)
    a = ap.parse_args()
    limpiar(a.origen, a.destino)
