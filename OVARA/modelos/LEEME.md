# Pesos del modelo

Esta carpeta se monta en el backend (`/modelos`). Debe contener:

- `modelo_ovara.json`: la configuración, el umbral y las métricas de validación.
- `segmentador.pt`: la U-Net.
- `clf_00_*.pt` … `clf_19_*.pt`: las 20 redes del ensamble.
- `SHA256SUMS.txt`: las huellas para verificar que los archivos no estén dañados.

Se obtienen de una de estas dos formas:

- `python scripts/descargar_modelos.py --url <URL del Release>`, que descarga el zip del Release de GitHub.
- `python scripts/exportar_modelo.py --origen <carpeta Experimento_CNN>`, que los exporta desde el experimento original.
