"""
eda.py — Visualizaciones exploratorias de la tabla limpia (patrones y anomalías). OVARA, Actividad 5.

Genera en resultados/eda/:
  1_distribucion_clases.png      cuántas imágenes hay de cada tipo de lesión
  2_caracteristicas_clave.png    las 4 medidas que más separan endometrioma del resto
  3_correlaciones.png            medidas redundantes (muy correlacionadas)
  4_valores_atipicos.png         porcentaje de valores atípicos (regla IQR) por medida
  resumen_eda.json

Uso: python fuentes/eda.py
"""
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

RAIZ = Path(__file__).resolve().parents[1]
DATOS = RAIZ / "datos" / "datos_limp" / "mmotu_caracteristicas.csv"
SALIDA = RAIZ / "resultados" / "eda"
AZUL, GRIS, TINTA = "#2a78d6", "#a3a3a3", "#1a1a19"
NO_FEATS = ["archivo", "split", "clase", "clase_nombre", "endometrioma", "img_alto", "img_ancho"]
NOMBRES = {"quiste_chocolate": "Quiste de chocolate\n(endometrioma)", "teratoma": "Teratoma", "ovario_normal": "Ovario normal",
           "cistoadenoma_seroso": "Cistoadenoma seroso", "cistoadenoma_mucinoso": "Cistoadenoma mucinoso",
           "tumor_celulas_teca": "Tumor de células de la teca", "quiste_simple": "Quiste simple",
           "seroso_alto_grado": "Seroso de alto grado"}


def _estilo(ax):
    ax.spines[["top", "right"]].set_visible(False)


def main():
    SALIDA.mkdir(parents=True, exist_ok=True)
    df = pd.read_csv(DATOS)
    feats = [c for c in df.columns if c not in NO_FEATS]
    tr = df[df.split == "train"]
    resumen = {}

    # 1. Distribución de clases
    vc = df.clase_nombre.value_counts().sort_values()
    fig, ax = plt.subplots(figsize=(7.5, 3.8))
    colores = [AZUL if c == "quiste_chocolate" else GRIS for c in vc.index]
    ax.barh([NOMBRES[c] for c in vc.index], vc.values, color=colores, height=0.65)
    for y, v in enumerate(vc.values):
        ax.text(v + 4, y, str(v), va="center", fontsize=9, color=TINTA)
    ax.set_xlabel("Número de imágenes"); ax.set_title("Imágenes por tipo de lesión (MMOTU, 1,469 ultrasonidos)")
    _estilo(ax); ax.grid(axis="x", alpha=0.25)
    fig.tight_layout(); fig.savefig(SALIDA / "1_distribucion_clases.png", dpi=150); plt.close(fig)
    resumen["por_clase"] = vc.sort_values(ascending=False).to_dict()

    # 2. Características que más separan (diferencia de medias estandarizada, solo entrenamiento)
    pos, neg = tr[tr.endometrioma == 1], tr[tr.endometrioma == 0]
    d = ((pos[feats].mean() - neg[feats].mean()) / tr[feats].std()).sort_values(key=abs, ascending=False)
    continuas = [f for f in d.index if df[f].nunique() > 10]   # omite medidas discretas (p. ej. n_regiones)
    top = continuas[:4]
    resumen["diferencia_estandarizada_top"] = d.head(8).round(3).to_dict()
    fig, axs = plt.subplots(1, 4, figsize=(13, 3.4))
    for ax, f in zip(axs, top):
        b = ax.boxplot([neg[f], pos[f]], patch_artist=True, widths=0.5, medianprops=dict(color=TINTA),
                       flierprops=dict(markersize=2.5, alpha=0.35))
        for p, c in zip(b["boxes"], (GRIS, AZUL)):
            p.set_facecolor(c); p.set_alpha(0.85)
        ax.set_xticks([1, 2], ["Otra lesión", "Endometrioma"]); ax.set_title(f, fontsize=10)
        _estilo(ax); ax.grid(axis="y", alpha=0.25)
    fig.suptitle("Medidas con mayor diferencia entre endometrioma y otras lesiones", y=1.03)
    fig.tight_layout(); fig.savefig(SALIDA / "2_caracteristicas_clave.png", dpi=150, bbox_inches="tight"); plt.close(fig)

    # 3. Correlaciones
    corr = tr[feats].corr()
    fig, ax = plt.subplots(figsize=(8.5, 7.2))
    im = ax.imshow(corr, cmap="RdBu_r", vmin=-1, vmax=1)
    ax.set_xticks(range(len(feats)), feats, rotation=90, fontsize=7); ax.set_yticks(range(len(feats)), feats, fontsize=7)
    fig.colorbar(im, ax=ax, fraction=0.04, label="Correlación de Pearson")
    ax.set_title("Correlación entre las 30 medidas (entrenamiento)")
    fig.tight_layout(); fig.savefig(SALIDA / "3_correlaciones.png", dpi=150); plt.close(fig)
    pares = [(a, b, corr.loc[a, b]) for i, a in enumerate(feats) for b in feats[i + 1:] if abs(corr.loc[a, b]) >= 0.9]
    resumen["pares_muy_correlacionados"] = [{"a": a, "b": b, "r": round(float(r), 3)} for a, b, r in
                                            sorted(pares, key=lambda x: -abs(x[2]))]

    # 4. Valores atípicos (regla IQR, 1.5 x rango intercuartílico)
    q1, q3 = df[feats].quantile(0.25), df[feats].quantile(0.75)
    iqr = q3 - q1
    atip = ((df[feats] < q1 - 1.5 * iqr) | (df[feats] > q3 + 1.5 * iqr)).mean().sort_values(ascending=False) * 100
    resumen["pct_atipicos"] = atip.round(1).to_dict()
    resumen["filas_con_algun_atipico_pct"] = round(float(((df[feats] < q1 - 1.5 * iqr) | (df[feats] > q3 + 1.5 * iqr)).any(axis=1).mean() * 100), 1)
    a = atip.head(12).iloc[::-1]
    fig, ax = plt.subplots(figsize=(7, 4))
    ax.barh(a.index, a.values, color=AZUL, height=0.6)
    for y, v in enumerate(a.values):
        ax.text(v + 0.3, y, f"{v:.1f} %", va="center", fontsize=8, color=TINTA)
    ax.set_xlabel("% de imágenes con valor atípico"); ax.set_title("Medidas con más valores atípicos (regla IQR)")
    _estilo(ax); ax.grid(axis="x", alpha=0.25)
    fig.tight_layout(); fig.savefig(SALIDA / "4_valores_atipicos.png", dpi=150); plt.close(fig)

    resumen["frac_doppler_imagenes_con_color_pct"] = round(float((df.frac_doppler > 0.01).mean() * 100), 1)
    (SALIDA / "resumen_eda.json").write_text(json.dumps(resumen, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({k: v for k, v in resumen.items() if k != "pct_atipicos"}, indent=1, ensure_ascii=False)[:2500])


if __name__ == "__main__":
    main()
