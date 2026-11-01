#!/usr/bin/env bash
# OVARA - Demo local en un solo paso (Linux / macOS)
# Uso: ./iniciar_demo.sh [evidencias | paridad RUTA_OTU_2d]
set -euo pipefail
cd "$(dirname "$0")"
PUERTO=${PUERTO:-3000}
PY=$(command -v python3 || command -v python) || { echo "[X] Falta Python 3"; exit 1; }
command -v docker >/dev/null || { echo "[X] Falta Docker"; exit 1; }
if ! docker info >/dev/null 2>&1; then
  echo "[..] Iniciando Docker..."; (docker desktop start || open -a Docker || true) >/dev/null 2>&1
  for i in $(seq 60); do docker info >/dev/null 2>&1 && break; sleep 3; done
  docker info >/dev/null 2>&1 || { echo "[X] Docker no respondió"; exit 1; }
fi
echo "[OK] Docker encendido"
[ -f modelos/modelo_ovara.json ] || "$PY" scripts/descargar_modelos.py
docker compose up --build -d --force-recreate
echo "[..] Esperando a que el modelo cargue..."
for i in $(seq 60); do curl -sf -o /dev/null "http://localhost:$PUERTO/api/salud" && break; sleep 3; done
curl -sf -o /dev/null "http://localhost:$PUERTO/api/salud" || { echo "[X] El modelo no cargó. Revisa: docker compose logs backend"; exit 1; }
echo "[OK] Demo listo en http://localhost:$PUERTO"
(xdg-open "http://localhost:$PUERTO" || open "http://localhost:$PUERTO") >/dev/null 2>&1 || true
case "${1:-}" in
  evidencias) "$PY" scripts/evidencias.py --sin-build ;;
  paridad) "$PY" scripts/evidencias.py --sin-build --paridad-mmotu "$2" ;;
esac
echo "Para detener: docker compose down"
