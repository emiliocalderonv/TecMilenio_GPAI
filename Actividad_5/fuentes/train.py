"""
train.py — Entrenamiento, ajuste (GridSearchCV + k-fold) y registro en MLflow (OVARA, Actividad 5).

Compara dos clasificadores sobre las características limpias de MMOTU para detectar
ENDOMETRIOMA (quiste de chocolate) frente a otras lesiones ováricas / ovario normal:
    1. Regresión logística (modelo lineal, interpretable)
    2. Random Forest       (ensamble no lineal)

Para cada modelo:
  - Búsqueda de hiperparámetros con GridSearchCV y validación cruzada estratificada k-fold.
  - Métricas estandarizadas en CV (media ± desviación) y en el conjunto de prueba (holdout).
  - Medición de latencia de inferencia y tamaño del modelo.
  - Registro en MLflow: parámetros, métricas, gráficas, tablas, modelo y una corrida
    anidada por cada combinación del grid.

Uso:
    python fuentes/train.py
    python fuentes/train.py --folds 5 --tracking-uri sqlite:///mlflow.db
Ver resultados:
    mlflow ui --backend-store-uri sqlite:///mlflow.db     (abrir http://127.0.0.1:5000)
"""
from __future__ import annotations

import argparse
import json
import os
import pickle
import platform
import tempfile
import time
import warnings
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import mlflow
import mlflow.sklearn
import numpy as np
import pandas as pd
import sklearn
from mlflow.models import infer_signature
from sklearn.ensemble import RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (accuracy_score, average_precision_score, balanced_accuracy_score,
                             classification_report, confusion_matrix, f1_score, precision_score,
                             recall_score, roc_auc_score, roc_curve, precision_recall_curve,
                             ConfusionMatrixDisplay)
from sklearn.model_selection import GridSearchCV, StratifiedKFold
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", message=".*Inferred schema contains integer.*")
warnings.filterwarnings("ignore", message=".*penalty is deprecated.*")   # scikit-learn 1.9: ver deuda técnica en README

RAIZ = Path(__file__).resolve().parents[1]
DATOS_DEF = RAIZ / "datos" / "datos_limp" / "mmotu_caracteristicas.csv"
RESULTADOS_DEF = RAIZ / "resultados"
EXPERIMENTO_DEF = "OVARA-Actividad5-Endometrioma-MMOTU"
SEED = 42
OBJETIVO = "endometrioma"
NO_CARACTERISTICAS = ["archivo", "split", "clase", "clase_nombre", OBJETIVO]

# Colores (paleta categórica validada: azul = regresión logística, naranja = random forest)
COLOR = {"Regresion_Logistica": "#2a78d6", "Random_Forest": "#eb6834"}

# --- Métricas estandarizadas (mismas en CV y en prueba) ------------------------------
SCORING = {
    "accuracy": "accuracy",
    "balanced_accuracy": "balanced_accuracy",
    "precision": "precision",
    "recall": "recall",
    "f1": "f1",
    "roc_auc": "roc_auc",
    "pr_auc": "average_precision",
}
METRICA_SELECCION = "f1"   # métrica con la que GridSearchCV elige el mejor modelo (refit)

# --- Modelos y espacios de búsqueda --------------------------------------------------
def definir_modelos(seed: int = SEED) -> dict:
    return {
        "Regresion_Logistica": (
            Pipeline([
                ("imputar", SimpleImputer(strategy="median")),
                ("escalar", StandardScaler()),
                ("modelo", LogisticRegression(class_weight="balanced", solver="liblinear",
                                              max_iter=5000, random_state=seed)),
            ]),
            {"modelo__C": [0.01, 0.1, 1, 10, 100], "modelo__penalty": ["l1", "l2"]},
        ),
        "Random_Forest": (
            Pipeline([
                ("imputar", SimpleImputer(strategy="median")),
                ("modelo", RandomForestClassifier(class_weight="balanced", random_state=seed, n_jobs=-1)),
            ]),
            {"modelo__n_estimators": [200, 500],
             "modelo__max_depth": [None, 8, 16],
             "modelo__min_samples_leaf": [1, 3, 5],
             "modelo__max_features": ["sqrt", 0.3]},
        ),
    }


def cargar_datos(ruta: Path = DATOS_DEF):
    df = pd.read_csv(ruta)
    feats = [c for c in df.columns if c not in NO_CARACTERISTICAS]
    tr, te = df[df.split == "train"], df[df.split == "test"]
    X = df[feats].astype(float)   # todas las características como float (firma de MLflow consistente)
    return X[df.split == "train"], tr[OBJETIVO].values, X[df.split == "test"], te[OBJETIVO].values, feats


def metricas(y, pred, prob) -> dict:
    return {
        "accuracy": accuracy_score(y, pred),
        "balanced_accuracy": balanced_accuracy_score(y, pred),
        "precision": precision_score(y, pred, zero_division=0),
        "recall": recall_score(y, pred, zero_division=0),
        "f1": f1_score(y, pred, zero_division=0),
        "roc_auc": roc_auc_score(y, prob),
        "pr_auc": average_precision_score(y, prob),
    }


def medir_latencia(modelo, X, n=200) -> dict:
    est = modelo.named_steps["modelo"]
    if hasattr(est, "n_jobs"):   # en inferencia de 1 muestra, el paralelismo solo agrega sobrecarga
        est.n_jobs = 1
    fila = X.iloc[[0]]
    for _ in range(10):
        modelo.predict_proba(fila)
    t = []
    for i in range(n):
        f = X.iloc[[i % len(X)]]
        t0 = time.perf_counter(); modelo.predict_proba(f); t.append((time.perf_counter() - t0) * 1000)
    t0 = time.perf_counter(); modelo.predict_proba(X); lote = time.perf_counter() - t0
    return {"latencia_ms_media": float(np.mean(t)), "latencia_ms_p95": float(np.percentile(t, 95)),
            "throughput_muestras_s": float(len(X) / lote),
            "tamano_modelo_kb": len(pickle.dumps(modelo)) / 1024}


def importancias(modelo, feats) -> pd.DataFrame:
    est = modelo.named_steps["modelo"]
    if hasattr(est, "coef_"):
        val, tipo = est.coef_[0], "coeficiente_estandarizado"
    else:
        val, tipo = est.feature_importances_, "importancia_gini"
    df = pd.DataFrame({"caracteristica": feats, tipo: val})
    return df.reindex(df[tipo].abs().sort_values(ascending=False).index).reset_index(drop=True)


# --- Gráficas ------------------------------------------------------------------------
def _estilo(ax):
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(alpha=0.25, linewidth=0.6)


def grafica_matriz(y, pred, nombre, ruta):
    fig, ax = plt.subplots(figsize=(4.2, 3.6))
    ConfusionMatrixDisplay(confusion_matrix(y, pred), display_labels=["Otra lesión", "Endometrioma"]).plot(
        ax=ax, cmap="Blues", colorbar=False)
    ax.set_title(f"Matriz de confusión — {nombre.replace('_', ' ')}")
    fig.tight_layout(); fig.savefig(ruta, dpi=150); plt.close(fig)


def grafica_curvas(y, prob, nombre, ruta):
    # Curvas calculadas a mano: compatible con cualquier versión de scikit-learn
    fpr, tpr, _ = roc_curve(y, prob)
    prec, rec, _ = precision_recall_curve(y, prob)
    etiqueta = nombre.replace("_", " ")
    fig, ax = plt.subplots(1, 2, figsize=(9, 3.8))
    ax[0].plot(fpr, tpr, color=COLOR[nombre], lw=2, label=f"{etiqueta} (AUC = {roc_auc_score(y, prob):.3f})")
    ax[0].plot([0, 1], [0, 1], ls="--", c="#9a9a9a", lw=1, label="Azar")
    ax[1].step(rec, prec, where="post", color=COLOR[nombre], lw=2,
               label=f"{etiqueta} (AP = {average_precision_score(y, prob):.3f})")
    ax[1].axhline(y.mean(), ls="--", c="#9a9a9a", lw=1, label="Azar")
    ax[0].set(title="Curva ROC", xlabel="Tasa de falsos positivos", ylabel="Tasa de verdaderos positivos (recall)")
    ax[1].set(title="Curva precisión–recall", xlabel="Recall", ylabel="Precisión")
    for a in ax:
        _estilo(a); a.legend(loc="lower right" if a is ax[0] else "upper right", frameon=False, fontsize=9)
    fig.tight_layout(); fig.savefig(ruta, dpi=150); plt.close(fig)


def grafica_importancias(imp, nombre, ruta, top=12):
    col = imp.columns[1]
    d = imp.head(top).iloc[::-1]
    fig, ax = plt.subplots(figsize=(6, 4.2))
    ax.barh(d.caracteristica, d[col], color=COLOR[nombre], height=0.6)
    ax.axvline(0, color="#6b6b6b", lw=0.8)
    ax.set_title(f"Top {top} características — {nombre.replace('_', ' ')}")
    ax.set_xlabel(col.replace("_", " ")); _estilo(ax)
    fig.tight_layout(); fig.savefig(ruta, dpi=150); plt.close(fig)


# --- Entrenamiento + registro ---------------------------------------------------------
def _log_modelo(modelo, X):
    firma = infer_signature(X, modelo.predict_proba(X)[:, 1])
    base = dict(signature=firma, input_example=X.head(3))
    intentos = [
        # MLflow >= 3.x serializa con skops y exige declarar los tipos internos como confiables.
        # Es seguro: los modelos los genera este mismo script (no vienen de una fuente externa).
        dict(name="modelo", skops_trusted_types=["numpy.dtype", "sklearn.tree._tree.Tree"], **base),
        dict(name="modelo", **base),
        dict(artifact_path="modelo", **base),   # MLflow 2.x
    ]
    for kw in intentos:
        try:
            return mlflow.sklearn.log_model(modelo, **kw)
        except TypeError:
            continue
    raise RuntimeError("No se pudo registrar el modelo en MLflow")


def entrenar_y_registrar(nombre, pipe, grid, Xtr, ytr, Xte, yte, feats, folds, seed, salida: Path) -> dict:
    cv = StratifiedKFold(n_splits=folds, shuffle=True, random_state=seed)
    gs = GridSearchCV(pipe, grid, scoring=SCORING, refit=METRICA_SELECCION, cv=cv, n_jobs=-1,
                      return_train_score=True)
    with mlflow.start_run(run_name=nombre) as run:
        mlflow.set_tags({"modelo": nombre, "tarea": "clasificacion_binaria", "objetivo": OBJETIVO,
                         "dataset": "MMOTU OTU_2d (caracteristicas)", "validacion": f"StratifiedKFold k={folds}",
                         "busqueda": "GridSearchCV", "metrica_seleccion": METRICA_SELECCION})
        t0 = time.perf_counter(); gs.fit(Xtr, ytr); t_ent = time.perf_counter() - t0
        res = pd.DataFrame(gs.cv_results_)

        # Corridas anidadas: una por combinación del grid
        for i, fila in res.iterrows():
            with mlflow.start_run(run_name=f"{nombre}_comb_{i:02d}", nested=True):
                mlflow.log_params({k.replace("param_modelo__", ""): fila[k] for k in res.columns if k.startswith("param_")})
                mlflow.log_metrics({f"cv_{m}_media": fila[f"mean_test_{m}"] for m in SCORING})
                mlflow.log_metric("rank_f1", int(fila[f"rank_test_{METRICA_SELECCION}"]))

        best = gs.best_estimator_
        i = gs.best_index_
        cv_m = {f"cv_{m}_media": res.loc[i, f"mean_test_{m}"] for m in SCORING}
        cv_m |= {f"cv_{m}_std": res.loc[i, f"std_test_{m}"] for m in SCORING}
        cv_m["cv_f1_train_media"] = res.loc[i, "mean_train_f1"]   # para detectar sobreajuste

        prob = best.predict_proba(Xte)[:, 1]; pred = (prob >= 0.5).astype(int)
        test_m = {f"test_{k}": v for k, v in metricas(yte, pred, prob).items()}
        lat = medir_latencia(best, Xte)

        mlflow.log_params({k.replace("modelo__", ""): v for k, v in gs.best_params_.items()})
        mlflow.log_params({"k_folds": folds, "seed": seed, "n_train": len(ytr), "n_test": len(yte),
                           "n_caracteristicas": len(feats), "umbral": 0.5,
                           "combinaciones_grid": len(res)})
        mlflow.log_metrics({**cv_m, **test_m, **lat, "tiempo_busqueda_s": t_ent})

        d = salida / nombre; d.mkdir(parents=True, exist_ok=True)
        res.to_csv(d / "cv_resultados.csv", index=False)
        imp = importancias(best, feats); imp.to_csv(d / "importancias.csv", index=False)
        (d / "reporte_clasificacion.txt").write_text(
            classification_report(yte, pred, target_names=["Otra lesión", "Endometrioma"], digits=3), encoding="utf-8")
        grafica_matriz(yte, pred, nombre, d / "matriz_confusion.png")
        grafica_curvas(yte, prob, nombre, d / "curvas_roc_pr.png")
        grafica_importancias(imp, nombre, d / "importancias.png")
        mlflow.log_artifacts(str(d), artifact_path="resultados")
        _log_modelo(best, Xtr)

        return {"modelo": nombre, "run_id": run.info.run_id, "estimador": best, "mejores_parametros": gs.best_params_,
                **cv_m, **test_m, **lat, "tiempo_busqueda_s": t_ent}


def graficas_comparativas(estimadores: dict, Xte, yte, salida: Path):
    """Curvas ROC/PR superpuestas y matrices de confusión lado a lado (conjunto de prueba)."""
    probs = {n: e.predict_proba(Xte)[:, 1] for n, e in estimadores.items()}
    fig, ax = plt.subplots(1, 2, figsize=(10, 4))
    for n, p in probs.items():
        fpr, tpr, _ = roc_curve(yte, p); pr, rc, _ = precision_recall_curve(yte, p); lab = n.replace("_", " ")
        ax[0].plot(fpr, tpr, color=COLOR[n], lw=2, label=f"{lab} (AUC {roc_auc_score(yte, p):.3f})")
        ax[1].step(rc, pr, where="post", color=COLOR[n], lw=2, label=f"{lab} (AP {average_precision_score(yte, p):.3f})")
    ax[0].plot([0, 1], [0, 1], ls="--", c="#9a9a9a", lw=1, label="Azar")
    ax[1].axhline(yte.mean(), ls="--", c="#9a9a9a", lw=1, label="Azar")
    ax[0].set(title="Curva ROC (prueba)", xlabel="Tasa de falsos positivos", ylabel="Recall")
    ax[1].set(title="Curva precisión–recall (prueba)", xlabel="Recall", ylabel="Precisión")
    for a in ax:
        _estilo(a); a.legend(frameon=False, fontsize=9)
    fig.tight_layout(); fig.savefig(salida / "comparacion_roc_pr.png", dpi=150); plt.close(fig)

    fig, ax = plt.subplots(1, 2, figsize=(8.5, 3.6))
    for a, (n, p) in zip(ax, probs.items()):
        ConfusionMatrixDisplay(confusion_matrix(yte, p >= 0.5), display_labels=["Otra lesión", "Endometrioma"]).plot(
            ax=a, cmap="Blues", colorbar=False)
        a.set(title=n.replace("_", " "), xlabel="Predicción", ylabel="Real")
    fig.tight_layout(); fig.savefig(salida / "matrices_confusion.png", dpi=150); plt.close(fig)


def comparacion_estadistica(estimadores: dict, Xtr, ytr, Xte, yte, seed: int, salida: Path,
                            repeticiones: int = 10, folds: int = 5, n_boot: int = 2000) -> dict:
    """Compara los dos modelos con pruebas pareadas.

    1. Validación cruzada repetida (folds x repeticiones) sobre entrenamiento, con los mismos folds para ambos modelos:
       prueba t corregida de Nadeau-Bengio (corrige la dependencia entre folds) y prueba de Wilcoxon.
    2. Conjunto de prueba: prueba de McNemar (errores discordantes) e intervalos bootstrap al 95 %
       de la diferencia en F1, recall y ROC-AUC.
    """
    from scipy import stats
    from sklearn.base import clone
    from sklearn.model_selection import RepeatedStratifiedKFold

    (n_a, est_a), (n_b, est_b) = list(estimadores.items())[:2]
    rskf = RepeatedStratifiedKFold(n_splits=folds, n_repeats=repeticiones, random_state=seed)
    filas = []
    for k, (itr, iva) in enumerate(rskf.split(Xtr, ytr)):
        for nombre, est in ((n_a, est_a), (n_b, est_b)):
            m = clone(est).fit(Xtr.iloc[itr], ytr[itr])
            p = m.predict_proba(Xtr.iloc[iva])[:, 1]
            filas.append({"fold": k, "modelo": nombre, "f1": f1_score(ytr[iva], p >= 0.5),
                          "recall": recall_score(ytr[iva], p >= 0.5), "roc_auc": roc_auc_score(ytr[iva], p)})
    cvr = pd.DataFrame(filas)
    cvr.to_csv(salida / "cv_repetida_por_fold.csv", index=False)

    resultado, ratio = {}, 1 / (folds - 1)       # n_prueba / n_entrenamiento en cada fold
    for met in ("f1", "recall", "roc_auc"):
        piv = cvr.pivot(index="fold", columns="modelo", values=met)
        d = (piv[n_b] - piv[n_a]).values
        n = len(d)
        t = d.mean() / np.sqrt((1 / n + ratio) * d.var(ddof=1))
        p_t = 2 * stats.t.sf(abs(t), df=n - 1)
        p_w = stats.wilcoxon(d).pvalue
        resultado[met] = {f"media_{n_a}": piv[n_a].mean(), f"media_{n_b}": piv[n_b].mean(),
                          "diferencia_media": d.mean(), "t_corregida": t, "p_t_corregida": p_t, "p_wilcoxon": p_w}

    # Conjunto de prueba
    pa, pb = est_a.predict_proba(Xte)[:, 1], est_b.predict_proba(Xte)[:, 1]
    ya, yb = pa >= 0.5, pb >= 0.5
    ok_a, ok_b = ya == yte, yb == yte
    solo_a, solo_b = int((ok_a & ~ok_b).sum()), int((~ok_a & ok_b).sum())
    p_mcnemar = stats.binomtest(min(solo_a, solo_b), solo_a + solo_b, 0.5).pvalue if solo_a + solo_b else 1.0
    rng = np.random.default_rng(seed)
    boot = {"f1": [], "recall": [], "roc_auc": []}
    for _ in range(n_boot):
        i = rng.integers(0, len(yte), len(yte))
        if yte[i].min() == yte[i].max():
            continue
        boot["f1"].append(f1_score(yte[i], yb[i]) - f1_score(yte[i], ya[i]))
        boot["recall"].append(recall_score(yte[i], yb[i]) - recall_score(yte[i], ya[i]))
        boot["roc_auc"].append(roc_auc_score(yte[i], pb[i]) - roc_auc_score(yte[i], pa[i]))
    resultado["prueba"] = {"mcnemar_solo_acierta_" + n_a: solo_a, "mcnemar_solo_acierta_" + n_b: solo_b,
                           "p_mcnemar": p_mcnemar}
    for met, v in boot.items():
        resultado["prueba"][f"dif_{met}_IC95"] = [float(np.percentile(v, 2.5)), float(np.percentile(v, 97.5))]

    # Gráfica: distribución por fold
    fig, axs = plt.subplots(1, 3, figsize=(11, 3.6))
    for ax, met, tit in zip(axs, ("f1", "recall", "roc_auc"), ("F1", "Recall", "ROC-AUC")):
        datos = [cvr[cvr.modelo == n][met] for n in (n_a, n_b)]
        b = ax.boxplot(datos, patch_artist=True, widths=0.5, medianprops=dict(color="#1a1a19"))
        for parche, n in zip(b["boxes"], (n_a, n_b)):
            parche.set_facecolor(COLOR[n]); parche.set_alpha(0.8)
        ax.set_xticks([1, 2], [n_a.replace("_", " "), n_b.replace("_", " ")])
        r = resultado[met]
        ax.set_title(f"{tit}  (p = {r['p_t_corregida']:.3f})"); _estilo(ax)
    fig.suptitle(f"Validación cruzada repetida ({folds} folds × {repeticiones} repeticiones)", y=1.02)
    fig.tight_layout(); fig.savefig(salida / "comparacion_estadistica.png", dpi=150, bbox_inches="tight"); plt.close(fig)

    def _limpio(o):
        if isinstance(o, dict): return {k: _limpio(v) for k, v in o.items()}
        if isinstance(o, list): return [_limpio(v) for v in o]
        return float(o) if isinstance(o, (np.floating, np.integer)) else o
    resultado = _limpio(resultado)
    (salida / "comparacion_estadistica.json").write_text(json.dumps(resultado, indent=2), encoding="utf-8")

    with mlflow.start_run(run_name="Comparacion_estadistica"):
        mlflow.set_tags({"tipo": "comparacion", "modelos": f"{n_a} vs {n_b}",
                         "metodo": "t corregida Nadeau-Bengio + Wilcoxon + McNemar + bootstrap"})
        mlflow.log_params({"repeticiones": repeticiones, "folds": folds, "n_bootstrap": n_boot})
        for met in ("f1", "recall", "roc_auc"):
            mlflow.log_metrics({f"{met}_diferencia_media": resultado[met]["diferencia_media"],
                                f"{met}_p_t_corregida": resultado[met]["p_t_corregida"],
                                f"{met}_p_wilcoxon": resultado[met]["p_wilcoxon"]})
        mlflow.log_metric("p_mcnemar", resultado["prueba"]["p_mcnemar"])
        for f in ("comparacion_estadistica.json", "comparacion_estadistica.png", "cv_repetida_por_fold.csv",
                  "comparacion_roc_pr.png", "matrices_confusion.png"):
            mlflow.log_artifact(str(salida / f), artifact_path="comparacion")
    return resultado


def ejecutar(datos: Path = DATOS_DEF, folds: int = 5, seed: int = SEED, tracking_uri: str | None = None,
             experimento: str = EXPERIMENTO_DEF, salida: Path = RESULTADOS_DEF) -> pd.DataFrame:
    salida.mkdir(parents=True, exist_ok=True)
    tracking_uri = tracking_uri or f"sqlite:///{(RAIZ / 'mlflow.db').as_posix()}"
    mlflow.set_tracking_uri(tracking_uri)
    if mlflow.get_experiment_by_name(experimento) is None:
        mlflow.create_experiment(experimento, artifact_location=(RAIZ / "mlruns").resolve().as_uri())
    mlflow.set_experiment(experimento)

    Xtr, ytr, Xte, yte, feats = cargar_datos(datos)
    print(f"Entrenamiento: {len(ytr)} ({ytr.sum()} endometriomas) | Prueba: {len(yte)} ({yte.sum()} endometriomas)"
          f" | {len(feats)} características | k={folds}")
    filas = []
    for nombre, (pipe, grid) in definir_modelos(seed).items():
        print(f"\n>> {nombre}: {np.prod([len(v) for v in grid.values()])} combinaciones x {folds} folds")
        r = entrenar_y_registrar(nombre, pipe, grid, Xtr, ytr, Xte, yte, feats, folds, seed, salida)
        print(f"   mejores parámetros: {r['mejores_parametros']}")
        print(f"   CV F1 {r['cv_f1_media']:.3f} ± {r['cv_f1_std']:.3f} | Prueba F1 {r['test_f1']:.3f} "
              f"| Recall {r['test_recall']:.3f} | AUC {r['test_roc_auc']:.3f} | {r['latencia_ms_media']:.2f} ms")
        filas.append(r)

    estimadores = {r["modelo"]: r.pop("estimador") for r in filas}
    comp = pd.DataFrame(filas).set_index("modelo")
    comp.to_csv(salida / "comparacion_modelos.csv")

    print("\n>> Comparación estadística (validación cruzada repetida + prueba)...")
    graficas_comparativas(estimadores, Xte, yte, salida)
    est = comparacion_estadistica(estimadores, Xtr, ytr, Xte, yte, seed, salida)
    for met in ("f1", "recall", "roc_auc"):
        r = est[met]
        print(f"   {met}: diferencia media RF - RL = {r['diferencia_media']:+.3f} | p (t corregida) = {r['p_t_corregida']:.4f}"
              f" | p (Wilcoxon) = {r['p_wilcoxon']:.4f}")
    print(f"   McNemar en prueba: p = {est['prueba']['p_mcnemar']:.4f}")
    (salida / "entorno.json").write_text(json.dumps({
        "python": platform.python_version(), "sklearn": sklearn.__version__, "mlflow": mlflow.__version__,
        "sistema": platform.platform(), "tracking_uri": tracking_uri, "experimento": experimento}, indent=2))
    print(f"\nComparación guardada en {salida / 'comparacion_modelos.csv'}")
    print(f"MLflow: mlflow ui --backend-store-uri {tracking_uri}")
    return comp


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--datos", type=Path, default=DATOS_DEF)
    ap.add_argument("--folds", type=int, default=5)
    ap.add_argument("--seed", type=int, default=SEED)
    ap.add_argument("--tracking-uri", default=None, help="por defecto sqlite:///<Actividad5>/mlflow.db")
    ap.add_argument("--experimento", default=EXPERIMENTO_DEF)
    a = ap.parse_args()
    ejecutar(a.datos, a.folds, a.seed, a.tracking_uri, a.experimento)
