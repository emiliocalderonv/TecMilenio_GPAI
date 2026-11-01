"""
Prueba de PARIDAD: ¿el modelo empaquetado en Docker da lo mismo que el modelo validado?

Corre el motor del contenedor (CPU) sobre la prueba de MMOTU (469 estudios) y lo compara con las
predicciones que generó validacion_externa.py en el experimento (GPU). Pequeñas diferencias numéricas
son normales (GPU con media precisión vs. CPU, pesos exportados en float16); lo que importa es que
las ALERTAS coincidan y que las métricas sean las mismas.

Uso dentro del contenedor (ver README):
  python paridad.py --mmotu /datos/OTU_2d --referencia /referencia/predicciones.csv --salida /evidencias/paridad.json
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import time
from pathlib import Path

import numpy as np
from PIL import Image

from app.inferencia import MotorOVARA


def auc(y, p):
    """AUC por rangos (Mann-Whitney), sin depender de scikit-learn."""
    orden = np.argsort(p); r = np.empty(len(p)); r[orden] = np.arange(1, len(p) + 1)
    for v in np.unique(p):                       # empates → rango medio
        i = p == v; r[i] = r[i].mean()
    n1 = y.sum(); n0 = len(y) - n1
    return float((r[y == 1].sum() - n1 * (n1 + 1) / 2) / (n1 * n0))


def metricas(y, p, u):
    pred = p >= u; tp = int((pred & (y == 1)).sum()); fp = int((pred & (y == 0)).sum()); fn = int((~pred & (y == 1)).sum())
    return {"TP": tp, "FP": fp, "FN": fn, "TN": int(len(y) - tp - fp - fn), "recall": tp / max(tp + fn, 1),
            "precision": tp / max(tp + fp, 1), "auc": auc(y, p)}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--mmotu", type=Path, required=True, help="carpeta OTU_2d (con images/ y val_cls.txt)")
    ap.add_argument("--referencia", type=Path, required=True, help="predicciones.csv de validacion_externa.py")
    ap.add_argument("--modelos", type=Path, default=Path(os.getenv("OVARA_MODELOS", "/modelos")))
    ap.add_argument("--salida", type=Path, default=Path("paridad.json"))
    ap.add_argument("--max", type=int, default=0, help="limitar el número de imágenes (prueba rápida)")
    args = ap.parse_args()

    with open(args.referencia, encoding="utf-8") as f:
        ref = {r["archivo"]: r for r in csv.DictReader(f)}
    archivos = [a for a in ref if (args.mmotu / "images" / a).exists()]
    if args.max:
        archivos = archivos[:args.max]
    motor = MotorOVARA(args.modelos)
    print(f"Motor: {len(motor.clasificadores)} redes, umbral {motor.umbral:.2f} | imágenes: {len(archivos)}")

    p_doc, p_ref, y, t0 = [], [], [], time.perf_counter()
    for i, a in enumerate(archivos, 1):
        r = motor.analizar(Image.open(args.mmotu / "images" / a), con_gradcam=False)
        p_doc.append(r["probabilidad"]); p_ref.append(float(ref[a]["prob_endometrioma"])); y.append(int(float(ref[a]["endometrioma"])))
        if i % 50 == 0:
            print(f"  {i}/{len(archivos)}")
    seg = time.perf_counter() - t0
    p_doc, p_ref, y = np.array(p_doc), np.array(p_ref), np.array(y)
    u = motor.umbral
    dif = np.abs(p_doc - p_ref)
    coinciden = (p_doc >= u) == (p_ref >= u)
    distintas = [{"archivo": a, "p_docker": float(pd_), "p_referencia": float(pr)}
                 for a, pd_, pr, ok in zip(archivos, p_doc, p_ref, coinciden) if not ok]
    res = {"imagenes": len(archivos), "umbral": u, "segundos_totales": round(seg, 1),
           "ms_por_imagen": round(1000 * seg / len(archivos), 1),
           "diferencia_prob_max": float(dif.max()), "diferencia_prob_media": float(dif.mean()),
           "alertas_coinciden_%": round(100 * float(coinciden.mean()), 2), "alertas_distintas": distintas,
           "metricas_docker": metricas(y, p_doc, u), "metricas_referencia": metricas(y, p_ref, u)}
    res["veredicto"] = ("PARIDAD OK" if res["alertas_coinciden_%"] >= 99.0 and res["diferencia_prob_media"] < 0.01
                        else "REVISAR: el contenedor no reproduce el modelo validado")
    args.salida.parent.mkdir(parents=True, exist_ok=True)
    args.salida.write_text(json.dumps(res, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({k: v for k, v in res.items() if k != "alertas_distintas"}, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
