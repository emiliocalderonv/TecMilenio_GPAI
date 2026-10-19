# Actividad 5 · OVARA — Regresión logística vs. Random Forest con validación cruzada y MLflow

**Gestión de Proyectos de IA · Maestría en Inteligencia Artificial (Universidad Tecmilenio)** · Emilio Calderón · Octubre 2026

> Herramienta de apoyo a la investigación. **No es un dispositivo de diagnóstico.** El veredicto clínico siempre corresponde al médico.

## Objetivo

Entrenar, ajustar y registrar en **MLflow** dos algoritmos de clasificación (**regresión logística** y **Random Forest**)
que, a partir de una lesión ovárica vista en **ultrasonido** y delimitada por su máscara de segmentación, indiquen si se trata de
un **endometrioma** ("quiste de chocolate") o de otra lesión / ovario normal.

Es la continuación de OVARA (Actividad 4): allí la clasificación directa de cortes de resonancia no fue viable por falta de datos
(13 pacientes positivas). Aquí se cambia a ultrasonido (MMOTU, 336 endometriomas) y a un enfoque **segmentación → características →
clasificación**, alineado con el rol de apoyo al médico: la máscara localiza la lesión y el clasificador sugiere su tipo.

## Estructura del repositorio

```
Actividad5/
├── datos/
│   ├── datos_ini/                     # datos originales (no versionados; ver datos_ini/README.md)
│   └── datos_limp/
│       ├── mmotu_caracteristicas.csv  # tabla limpia: 1,469 lesiones × 30 características + objetivo
│       └── reporte_limpieza.json      # registros, descartes y correcciones de la limpieza
├── fuentes/
│   ├── entrena.ipynb                  # notebook de Colab: entorno → limpieza → EDA → entrenamiento → MLflow → conclusiones
│   ├── datos_prep.py                  # funciones de limpieza y extracción de características
│   ├── eda.py                         # visualizaciones exploratorias (patrones y anomalías)
│   └── train.py                       # GridSearchCV + k-fold, métricas, latencia, comparación estadística y MLflow
├── resultados/
│   ├── eda/                           # gráficas exploratorias
│   ├── Regresion_Logistica/ · Random_Forest/   # matriz de confusión, curvas, importancias, cv_resultados
│   ├── comparacion_*.png/json         # comparación estadística y curvas superpuestas
│   └── mlflow_evidencias/             # capturas de la interfaz de MLflow
├── mlflow.db  ·  mlruns/              # registro de experimentos de MLflow (se generan al entrenar)
├── requirements.txt
├── README.md                          # esta guía
└── CHANGELOG.md                       # historial de cambios y reporte final
```

## Guía de reproducción

### Opción A — Google Colab (recomendada para revisar)

1. Abrir `fuentes/entrena.ipynb` en Colab (*Archivo → Abrir cuaderno → GitHub* → `emiliocalderonv/TecMilenio_GPAI`).
2. Ejecutar todo (*Entorno de ejecución → Ejecutar todas*). El notebook clona el repositorio e instala dependencias.
   - Con `DESCARGAR_MMOTU = False` (por defecto) usa la tabla limpia incluida en `datos/datos_limp/`.
   - Con `DESCARGAR_MMOTU = True` descarga las imágenes originales (173 MB) y repite la limpieza completa.
3. No requiere GPU. Tiempo aproximado: 6–10 minutos (la comparación estadística reentrena ambos modelos 50 veces).

### Opción B — Local (Windows / Linux / macOS)

```bash
python -m pip install -r requirements.txt

# 1) Limpieza y extracción de características (requiere MMOTU en datos/datos_ini/MMOTU/OTU_2d)
python fuentes/datos_prep.py

# 2) Visualizaciones exploratorias
python fuentes/eda.py

# 3) Entrenamiento, validación cruzada, grid search, comparación estadística y registro en MLflow
python fuentes/train.py                  # opciones: --folds 5 --seed 42 --tracking-uri ... --experimento ...

# 4) Ver los experimentos
mlflow ui --backend-store-uri sqlite:///mlflow.db          # abrir http://127.0.0.1:5000
```

Semilla fija (`42`) en particiones, validación cruzada y modelos. `scikit-learn` y `mlflow` están **fijados** en `requirements.txt` porque el Random Forest da resultados distintos entre versiones de scikit-learn (1.7 vs. 1.9). Las versiones exactas de cada corrida quedan en `resultados/entorno.json`.

## Decisiones de diseño

| Decisión | Elección | Justificación |
|---|---|---|
| Dataset | **MMOTU OTU_2d** (1,469 ultrasonidos) | Es el único de los cuatro disponibles con clase negativa y suficientes endometriomas (336). UT-EndoMRI tiene muy pocos casos; GLENDA y ENID solo contienen imágenes con lesión. Estos tres se reservan para la fase de segmentación |
| Tarea | Binaria: endometrioma (clase 0 de MMOTU) vs. resto | Es la pregunta clínica de OVARA; el resto de clases incluye ovario normal y otras lesiones con las que se puede confundir |
| Representación | 30 características interpretables por lesión: forma, ecogenicidad (intensidad), contraste con el tejido vecino, textura GLCM y fracción Doppler | Regresión logística y Random Forest requieren datos tabulares; además, el médico puede entender qué mide cada variable |
| Limpieza | Validación de archivos, duplicados por hash MD5, consistencia de tamaño máscara–imagen, máscaras vacías, infinitos/nulos imputados con la mediana de entrenamiento | Evita errores silenciosos y fuga de información de prueba |
| Partición | Partición oficial de MMOTU: *train* 1,000 (ajuste con CV) / *val* 469 (prueba independiente) | Comparable con la literatura y sin tocar la prueba durante el ajuste |
| Validación cruzada | `StratifiedKFold` k = 5 dentro de `GridSearchCV` | Conserva la proporción de endometriomas (~23 %) en cada fold |
| Desbalance | `class_weight="balanced"` en ambos modelos | Sin esto, los modelos tienden a predecir siempre "otra lesión" |
| Métrica de selección | **F1** (`refit`) | Equilibra recall y precisión; el recall se prioriza clínicamente pero optimizarlo solo produce demasiadas falsas alarmas |
| Métricas reportadas | Accuracy, balanced accuracy, precision, recall, F1, ROC-AUC, PR-AUC (CV y prueba) + latencia, throughput, tamaño | Mismo conjunto estandarizado para ambos modelos y en ambas etapas |
| Comparación estadística | Validación cruzada repetida 5 × 10 con prueba t corregida (Nadeau-Bengio) y Wilcoxon; en prueba, McNemar e intervalos bootstrap | Saber si la diferencia entre modelos es real o producto del azar |
| Registro | MLflow con backend SQLite (`mlflow.db`): 1 corrida por modelo, 1 anidada por combinación del grid y 1 de comparación estadística; artefactos (gráficas, tablas, modelo con firma) | Trazabilidad completa del ajuste y modelos listos para reutilizar |
| Versionamiento | Código y datos limpios en Git; datos originales por script/enlace con hash MD5; historial en `CHANGELOG.md` (versionado semántico); experimentos en MLflow | Cualquier resultado puede rastrearse a su versión de código, datos y parámetros |

## Resultados (corrida de referencia, semilla 42, scikit-learn 1.9.1)

| Métrica (prueba, n = 469) | Regresión logística | Random Forest |
|---|---|---|
| F1 en validación cruzada (media ± desv.) | 0.616 ± 0.029 | **0.709 ± 0.045** |
| Accuracy | 0.770 | **0.855** |
| Balanced accuracy | 0.758 | **0.767** |
| Precision | 0.506 | **0.733** |
| Recall (sensibilidad) | **0.736** | 0.600 |
| F1-score | 0.600 | **0.660** |
| ROC-AUC | 0.828 | **0.865** |
| PR-AUC | 0.611 | **0.741** |
| Latencia por muestra* | **~1.5 ms** | ~35 ms |
| Tamaño del modelo | **3 KB** | 7.4 MB |

\* La latencia depende del equipo.

Mejores hiperparámetros: regresión logística `C = 10, L1`; Random Forest `500 árboles, max_depth = None, min_samples_leaf = 1, max_features = sqrt`.

**Comparación estadística:** el Random Forest es significativamente mejor en F1 (+0.086, p = 0.002) y ROC-AUC (+0.035, p = 0.001);
la regresión logística es significativamente mejor en recall con umbral 0.5 (+0.094, p = 0.004). Detalle y conclusiones en [`CHANGELOG.md`](CHANGELOG.md).

## Limitaciones y deuda técnica

- La clasificación usa la **máscara manual** de MMOTU; en uso real la máscara la daría un modelo de segmentación (siguiente fase).
- MMOTU proviene de un solo hospital (China); se requiere validación con población mexicana.
- Licencias de los datos para investigación; no aptas para la versión comercial de OVARA sin datos propios.
- `penalty` de `LogisticRegression` está obsoleto en scikit-learn 1.9 (se usa con aviso silenciado); migrar a `l1_ratio`.
- El umbral de decisión es fijo (0.5); ajustarlo con validación cruzada mejoraría el recall del Random Forest.

## Referencias

- Zhao, Q., Lyu, S., Bai, W., Cai, L., Liu, B., Cheng, G., Wu, M., Sang, X., Yang, M., & Chen, L. (2022). *MMOTU: A multi-modality ovarian tumor ultrasound image dataset for unsupervised cross-domain semantic segmentation* (arXiv:2207.06799). arXiv. https://arxiv.org/abs/2207.06799
- Liang, X., Alpuing Radilla, L. A., Khalaj, K., Mokashi, C., Guan, X., Roberts, K. E., Sheth, S. A., Tammisetti, V. S., & Giancardo, L. (2024). *UTHealth - Endometriosis MRI Dataset (UT-EndoMRI)* (Versión 1) [Conjunto de datos]. Zenodo. https://doi.org/10.5281/zenodo.13749613
- Leibetseder, A., Kletz, S., Schoeffmann, K., Keckstein, S., & Keckstein, J. (2020). GLENDA: Gynecologic laparoscopy endometriosis dataset. En *MultiMedia Modeling (MMM 2020)* (LNCS 11962, pp. 439–450). Springer. https://doi.org/10.1007/978-3-030-37734-2_36
- Leibetseder, A., Schoeffmann, K., Keckstein, J., & Keckstein, S. (2022). Endometriosis detection and localization in laparoscopic gynecology. *Multimedia Tools and Applications, 81*(5), 6191–6215. https://doi.org/10.1007/s11042-021-11730-1
- Pedregosa, F., et al. (2011). Scikit-learn: Machine learning in Python. *Journal of Machine Learning Research, 12*, 2825–2830.
- Zaharia, M., et al. (2018). Accelerating the machine learning lifecycle with MLflow. *IEEE Data Engineering Bulletin, 41*(4), 39–45.
