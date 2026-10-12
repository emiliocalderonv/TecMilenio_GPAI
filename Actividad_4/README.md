# OVARA — Detección asistida de endometriomas en resonancia magnética

**Actividad 4 · Gestión de Proyectos de IA · Maestría en Inteligencia Artificial (Universidad Tecmilenio)**
Autor: Emilio Calderón · Octubre 2026

> Herramienta de apoyo a la investigación. **No es un dispositivo de diagnóstico.** El veredicto clínico siempre corresponde al médico.

## Descripción del proyecto

**OVARA** es una plataforma que acerca a pacientes y ginecólogos para dar seguimiento a padecimientos como la endometriosis leve, la adenomiosis difusa y el síndrome venoso pélvico. Su valor agregado es un módulo de inteligencia artificial que ayuda al médico a revisar los estudios de imagen.

Este repositorio contiene la primera prueba de ese módulo. Es un **análisis comparativo de tres modelos de clasificación** que señalan qué cortes de una resonancia magnética pélvica (secuencia T2) contienen un quiste o endometrioma. Así el médico puede revisar primero las imágenes relevantes.

**Problema:** la endometriosis afecta aproximadamente a 1 de cada 10 mujeres en edad reproductiva y su diagnóstico suele tardar varios años. Interpretar una resonancia exige experiencia especializada y revisar decenas de cortes por estudio.

**Modelos comparados**

| # | Modelo | Tipo | Parámetros |
|---|---|---|---|
| 1 | CNN propia | Red convolucional de 4 bloques, entrenada desde cero (línea base) | 0.39 M |
| 2 | ResNet18 | Preentrenada en ImageNet + ajuste fino | 11.18 M |
| 3 | EfficientNet-B0 | Preentrenada en ImageNet + ajuste fino | 4.01 M |

## Estructura del proyecto

```
OVARA/
├── README.md                         # Este archivo
├── ovara_comparacion_modelos.ipynb   # Notebook principal: datos → entrenamiento → métricas → latencia → conclusiones
├── preparar_dataset.py               # Descarga, verifica (MD5), descomprime e inventaría el dataset
├── requirements.txt                  # Dependencias de Python
├── UT-EndoMRI/                       # Dataset descomprimido (no se versiona)
│   └── UT-EndoMRI/
│       ├── D1_MHS/                   # 51 pacientes, máscaras de 3 evaluadores
│       └── D2_TCPW/                  # Pacientes usadas en esta actividad
└── resultados_ovara/                 # Salidas generadas
    ├── cache_T2_224_roi1_v2.npz      # Cortes preprocesados (caché)
    ├── cnn_propia_v3.pt              # Pesos de cada modelo
    ├── resnet18_v3.pt
    ├── efficientnet_b0_v3.pt
    ├── resumen_modelos.csv           # Tabla comparativa final
    └── detalle_pacientes_prueba.csv  # Predicción por paciente de prueba
```

## Dataset

**UT-EndoMRI** (UTHealth Endometriosis MRI Dataset): resonancias magnéticas pélvicas en formato NIfTI (`.nii.gz`) de dos hospitales de Texas, con segmentaciones manuales.

- **Secuencias:** `T1`, `T1FS`, `T2` y `T2FS` (FS = supresión de grasa).
- **Máscaras (D2):** `ut` (útero), `ov` (ovarios), `cy` (quiste), `em` (endometrioma) y `pat`.
- **Nombres de archivo:** `D[subconjunto]-[paciente]_[secuencia o estructura].nii.gz`; en D1 se agrega `_r[evaluador]`.
- **Usado en esta actividad:** subconjunto D2, secuencia T2. Quedaron 45 pacientes válidas (13 con quiste y 32 sin quiste), con 445 cortes de la región pélvica.
- **Licencia:** uso **exclusivo en investigación científica no comercial**.

## Instalación y reproducción

Requisitos: Python 3.10–3.12 y, de preferencia, una GPU NVIDIA (también funciona en CPU, pero mucho más lento).

```powershell
# 1. PyTorch con CUDA (ajustar cu128 según el selector de pytorch.org; sin GPU NVIDIA, omitir --index-url)
python -m pip install torch torchvision --index-url https://download.pytorch.org/whl/cu128 --timeout 300 --retries 10

# 2. Resto de dependencias
python -m pip install -r requirements.txt

# 3. Obtener y preparar el dataset (~8 GB)
python preparar_dataset.py               # o: python preparar_dataset.py --solo-inventario

# 4. Abrir ovara_comparacion_modelos.ipynb en VS Code/Jupyter y ejecutar "Run All"
```

El notebook usa la semilla 42. Puede haber pequeñas variaciones entre equipos por el no determinismo de la GPU.

## Metodología (resumen)

1. Se lee cada volumen T2 y se remuestrean las máscaras a su malla.
2. Se normaliza la intensidad (percentiles 1–99) y se extraen los cortes 2D de la región pélvica, a 224×224.
3. **Etiqueta:** un corte es positivo si la máscara `cy` tiene al menos 10 píxeles en él.
4. **División por paciente** (70/15/15), para evitar fuga de información entre conjuntos.
5. **Entrenamiento:** AdamW + *cosine annealing*, precisión mixta (AMP), muestreo balanceado y *early stopping* por AUC de validación.
6. **Umbral:** se calibra en validación y se aplica en prueba. A nivel paciente, el estudio es sospechoso si al menos 2 cortes superan el umbral.
7. **Evaluación:** accuracy, precision, recall, F1 y AUC, más la latencia (por corte, *throughput* y por paciente de punta a punta).

## Resultados (conjunto de prueba: 7 pacientes, 60 cortes)

| Modelo | Accuracy | Precision | Recall | F1 | AUC | ms/corte | s/paciente |
|---|---|---|---|---|---|---|---|
| CNN propia | 0.633 | 0.174 | **0.571** | **0.267** | 0.601 | **1.1** | 0.24 |
| ResNet18 | 0.617 | 0.136 | 0.429 | 0.207 | 0.617 | 3.1 | 0.24 |
| EfficientNet-B0 | 0.800 | 0.143 | 0.143 | 0.143 | 0.491 | 10.2 | 0.25 |

GPU usada: NVIDIA GeForce RTX 3070 Ti Laptop (8 GB).

## Veredicto

Ningún modelo alcanza el criterio mínimo de **recall ≥ 0.80**, por lo que **ninguno se integra todavía a la plataforma**. La **CNN propia** queda como candidato provisional: tiene el mejor recall y F1 y es la más ligera y rápida. La latencia no es un problema: el estudio completo de una paciente se procesa en unos 0.25 s. La causa principal del bajo desempeño es la escasez de datos (solo 13 pacientes con quiste).

## Limitaciones

- La etiqueta proviene de la máscara `cy` (quiste). Las máscaras `em` (endometrioma) no se usaron, y 8 pacientes con `em` pero sin `cy` quedaron como negativas.
- Se asumió que una paciente sin archivo `cy` no tiene quiste.
- El dataset es pequeño y de una sola población (EE. UU.); con 7 pacientes de prueba, las métricas tienen alta varianza.
- Las máscaras de D2 están en la geometría de T2FS, por lo que se remuestrearon a T2.
- La licencia no comercial impide usar estos modelos en la versión de pago de OVARA.

## Siguiente fase

- [ ] Usar como etiqueta `cy ∪ em` (quiste o endometrioma).
- [ ] Evaluar T2FS como secuencia principal: hay 70 pacientes y coincide con la geometría de las máscaras.
- [ ] Incorporar el subconjunto D1 (51 pacientes con máscaras `em`).
- [ ] Validación cruzada por paciente y ajuste de la regla a nivel paciente.
- [ ] Conseguir datos de población mexicana con licencia comercial.
- [ ] Migrar de clasificación a segmentación (nnU-Net) para entregar la ubicación y el volumen de la lesión.

## Referencias

- Liang, X., Alpuing Radilla, L. A., Khalaj, K., Mokashi, C., Guan, X., Roberts, K. E., Sheth, S. A., Tammisetti, V. S., & Giancardo, L. (2024). *UTHealth - Endometriosis MRI Dataset (UT-EndoMRI)* (Versión 1) [Conjunto de datos]. Zenodo. https://doi.org/10.5281/zenodo.13749613
- He, K., Zhang, X., Ren, S., & Sun, J. (2016). Deep residual learning for image recognition. *Proceedings of the IEEE Conference on Computer Vision and Pattern Recognition*, 770–778.
- Tan, M., & Le, Q. (2019). EfficientNet: Rethinking model scaling for convolutional neural networks. *Proceedings of the 36th International Conference on Machine Learning*, 6105–6114.
