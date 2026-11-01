# Evidencias de integración · OVARA demo

- **Fecha:** 2026-11-01T16:26:10
- **Equipo:** Windows-11-10.0.26200-SP0
- **Docker:** 28.3.0 · **Compose:** 2.38.1-desktop.1 · **Commit:** e3944e8
- **Resultado global:** ✅ TODAS LAS PRUEBAS PASARON (15/15)

## Verificaciones

| # | Verificación | Resultado | Detalle |
|---|---|---|---|
| 1 | Docker disponible | ✅ | Docker 28.3.0 · Compose 2.38.1-desktop.1 |
| 2 | Imágenes ovara-backend y ovara-frontend existen | ✅ | ovara-backend:1.0.0	1.78GB	About an hour ago | ovara-frontend:1.0.0	249MB	About an hour ago |
| 3 | Backend: pytest | ✅ | 7 passed, 1 warning in 3.96s |
| 4 | Frontend: node --test | ✅ | pass 6 fail 0 |
| 5 | docker compose up -d | ✅ |  |
| 6 | Modelo cargado y servicio sano | ✅ | listo en 12 s |
| 7 | Frontend sirve la interfaz (GET /) | ✅ |  |
| 8 | GET /api/version | ✅ | {"frontend": "1.0.0", "backend_url": "http://backend:8000"} |
| 9 | GET /api/info (modelo) | ✅ | 20 redes · umbral 0.28 · versión 1.0.0 |
| 10 | API documentada (backend /docs) | ✅ | http://localhost:8000/docs |
| 11 | POST /api/analizar con 16 imágenes | ✅ | latencia media 1905 ms |
| 12 | Rechaza archivo que no es imagen (415) | ✅ | Solo se aceptan imágenes (JPG o PNG) |
| 13 | Rechaza imagen dañada (422) | ✅ | No se pudo leer la imagen |
| 14 | Rechaza archivo > 10 MB (413) | ✅ | La imagen supera 10 MB |
| 15 | Paridad contenedor vs. modelo validado | ✅ | alertas iguales 100.0 % · Δprob media 0.0006 · 7.5 min |

## Imágenes Docker

```
ovara-backend:1.0.0	1.78GB	About an hour ago
ovara-frontend:1.0.0	249MB	About an hour ago
```

## Casos analizados de punta a punta

| Archivo | HTTP | Probabilidad | Alerta | Redes en alerta | Diagnóstico real | ¿Coincide? | ms |
|---|---|---|---|---|---|---|---|
| 12.JPG | 200 | 0.9921 | sí | 20 | quiste_chocolate | ✅ | 1949 |
| 88.JPG | 200 | 0.6125 | sí | 14 | ovario_normal | ❌ | 1780 |
| 383.JPG | 200 | 0.0076 | no | 0 | tumor_celulas_teca | ✅ | 2059 |
| 494.JPG | 200 | 0.1471 | no | 4 | cistoadenoma_mucinoso | ✅ | 1864 |
| 732.JPG | 200 | 0.888 | sí | 19 | quiste_chocolate | ✅ | 1815 |
| 778.JPG | 200 | 0.3526 | sí | 8 | quiste_chocolate | ✅ | 1903 |
| 825.JPG | 200 | 0.9909 | sí | 20 | quiste_chocolate | ✅ | 2085 |
| 842.JPG | 200 | 0.9379 | sí | 20 | quiste_chocolate | ✅ | 1903 |
| 948.JPG | 200 | 0.0065 | no | 0 | teratoma | ✅ | 1766 |
| 1081.JPG | 200 | 0.0616 | no | 2 | ovario_normal | ✅ | 1795 |
| 1171.JPG | 200 | 0.3446 | sí | 9 | quiste_chocolate | ✅ | 1885 |
| 1234.JPG | 200 | 0.3239 | sí | 7 | quiste_chocolate | ✅ | 2265 |
| 1244.JPG | 200 | 0.0162 | no | 0 | teratoma | ✅ | 1979 |
| 1329.JPG | 200 | 0.8056 | sí | 17 | quiste_chocolate | ✅ | 1962 |
| 1384.JPG | 200 | 0.1296 | no | 4 | ovario_normal | ✅ | 1881 |
| 1413.JPG | 200 | 0.0637 | no | 1 | cistoadenoma_seroso | ✅ | 1594 |

Coincidencia con el diagnóstico real en estos ejemplos: **15/16** (muestra pequeña e ilustrativa; las métricas formales están en `info_modelo.json` y en la paridad).

Latencia de punta a punta (con Grad-CAM, CPU): media 1905 ms · mediana 1894 ms · máxima 2265 ms.

## Paridad con el modelo validado (prueba MMOTU completa)

- Imágenes: 469 · alertas idénticas: **100.0 %** · diferencia de probabilidad media 0.0006 (máx. 0.1189)

| | Recall | Precisión | AUC | TP | FP | FN |
|---|---|---|---|---|---|---|
| Contenedor (CPU) | 0.873 | 0.807 | 0.931 | 96 | 23 | 14 |
| Modelo validado (GPU) | 0.873 | 0.807 | 0.931 | 96 | 23 | 14 |

**Veredicto:** PARIDAD OK

## Archivos de esta carpeta

- `01_build.log`: construcción · `02_imagenes.txt`: imágenes y tamaños
- `03_pytest_backend.log`, `04_test_frontend.log`: pruebas unitarias dentro de los contenedores
- `05_up.log`, `06_compose_ps.txt`: despliegue y estado de los servicios
- `integracion/`: salud, información del modelo y, por cada imagen, la respuesta JSON con sus imágenes (contorno, recorte, atención)
- `07_paridad.log`, `paridad.json`: prueba de paridad (si se corrió)
- `08_logs_contenedores.log`: bitácoras de backend y frontend
