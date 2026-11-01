@echo off
REM OVARA - Detener el demo (los pesos y las imagenes se conservan)
cd /d "%~dp0"
docker compose down
echo Demo detenido. Para volver a encenderlo: iniciar_demo.bat
