# CHANGELOG · Actividad 5 — OVARA

Formato basado en [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/) con versionado semántico
(MAYOR.MENOR.PARCHE). Fechas en formato AAAA-MM-DD.

---

## [1.0.0] — 2026-10-18 · Reporte final

### Resumen

Se compararon **regresión logística** y **Random Forest** para clasificar lesiones ováricas en ultrasonido como
**endometrioma** o **no endometrioma**, a partir de 30 medidas extraídas de la lesión segmentada (MMOTU, 1,469 imágenes,
23 % endometriomas). Ambos modelos se ajustaron con **GridSearchCV + validación cruzada estratificada de 5 folds**, se compararon
estadísticamente y se registraron en **MLflow** (49 corridas: 2 principales, 46 del grid y 1 de comparación).

| Métrica (prueba, n = 469) | Regresión logística | Random Forest |
|---|---|---|
| F1 en CV (media ± desv.) | 0.616 ± 0.029 | **0.709 ± 0.045** |
| Accuracy | 0.770 | **0.855** |
| Precision | 0.506 | **0.733** |
| Recall (sensibilidad) | **0.736** | 0.600 |
| F1-score | 0.600 | **0.660** |
| ROC-AUC | 0.828 | **0.865** |
| PR-AUC | 0.611 | **0.741** |
| Brecha F1 entrenamiento – validación | **0.03** | 0.29 |

**Comparación estadística** (validación cruzada repetida 5 × 10, prueba t corregida de Nadeau-Bengio):
Random Forest mejor en F1 (+0.086, p = 0.002) y ROC-AUC (+0.035, p = 0.001); regresión logística mejor en recall con
umbral 0.5 (+0.094, p = 0.004). En prueba, McNemar p < 0.001 (el Random Forest acierta 58 casos que la regresión logística falla,
y al revés solo 18).

### Conclusiones

- El **Random Forest es el mejor modelo en general**: separa mejor las clases (mayor ROC-AUC y PR-AUC) y la diferencia es
  estadísticamente significativa.
- Con el umbral estándar de 0.5 es **conservador**: detecta 60 % de los endometriomas, contra 74 % de la regresión logística.
  Como el modelo ordena mejor los casos, basta con bajar su umbral: con 0.30 (elegido en validación cruzada) detecta 80 %
  de los endometriomas en prueba con precisión de 0.56, superando a la regresión logística en ambas medidas.
- **Recomendación:** Random Forest con umbral ajustado como modelo candidato para OVARA; la regresión logística se conserva como
  línea base interpretable, estable y muy ligera (3 KB, ~1.5 ms).
- Las medidas más útiles son de **ecogenicidad y textura** (variación de brillo, entropía, homogeneidad): el endometrioma se ve
  más uniforme que otras lesiones, lo que coincide con su aspecto clínico de "vidrio esmerilado".

### Siguientes pasos

1. Incorporar el ajuste de umbral al pipeline y registrarlo en MLflow.
2. Reducir el sobreajuste del Random Forest (limitar profundidad u hojas mínimas con un criterio de recall).
3. Entrenar el modelo de segmentación (U-Net) que genere la máscara automáticamente y evaluar la cadena completa.

---

## [0.4.0] — 2026-10-18 · Comparación estadística y visualizaciones

### Añadido
- `train.py`: comparación estadística (validación cruzada repetida 5 × 10, t corregida, Wilcoxon, McNemar, bootstrap) registrada
  como corrida `Comparacion_estadistica` en MLflow; curvas ROC/PR superpuestas y matrices de confusión lado a lado.
- `fuentes/eda.py`: distribución de clases, medidas clave, correlaciones y valores atípicos.
- `resultados/mlflow_evidencias/`: capturas de la interfaz de MLflow.

### Cambiado
- `scikit-learn` fijado en 1.9.1 y `mlflow` en 3.17.1: el Random Forest daba resultados distintos con scikit-learn 1.7.
- Las gráficas ROC/PR se calculan manualmente: scikit-learn 1.9 eliminó el parámetro `color` de `RocCurveDisplay`.

## [0.3.0] — 2026-10-18 · Entrenamiento y registro

### Añadido
- `fuentes/train.py`: pipelines (imputación + escalado), `GridSearchCV` con `StratifiedKFold` (k = 5), métricas
  estandarizadas en CV y prueba, latencia, gráficas y registro completo en MLflow.
- `fuentes/entrena.ipynb`: notebook compatible con Google Colab y ejecución local.

### Corregido
- MLflow 3.x serializa con *skops* y rechazaba tipos internos de scikit-learn; se declaran como confiables
  (los modelos los genera el propio script).
- La latencia del Random Forest se inflaba por el paralelismo al predecir una sola muestra; se mide con `n_jobs=1`.
- Las características enteras generaban avisos en la firma de MLflow; ahora todas son `float`.

## [0.2.0] — 2026-10-18 · Limpieza y características

### Añadido
- `fuentes/datos_prep.py`: validación de archivos, duplicados (MD5), corrección de tamaño de máscara, descarte de máscaras
  vacías, imputación por mediana de entrenamiento y extracción de 30 características.
- `datos/datos_limp/mmotu_caracteristicas.csv` y `reporte_limpieza.json`.

### Resultado de la limpieza
- 1,469 registros iniciales → 1,469 finales: sin archivos faltantes, corruptos, duplicados, máscaras vacías ni nulos.

### Cambiado
- La extracción trabaja sobre un recorte de la lesión: mismos valores, ~4 veces más rápido (0.33 → 0.085 s por imagen).

## [0.1.0] — 2026-10-18 · Preparación del repositorio

### Añadido
- Estructura `datos/{datos_ini, datos_limp}`, `fuentes/`, `README.md`, `CHANGELOG.md`, `requirements.txt` y `.gitignore`.
- Datos originales en `datos/datos_ini/` (MMOTU, UT-EndoMRI, GLENDA, ENID; no versionados, ver su README).
- Selección de MMOTU como dataset de la actividad.
