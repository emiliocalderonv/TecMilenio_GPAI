@echo off
REM ============================================================================
REM  OVARA - Demo local en un solo paso (Windows)
REM  Uso:   iniciar_demo.bat              -> enciende el demo y abre el navegador
REM         iniciar_demo.bat evidencias   -> ademas corre todas las pruebas
REM         iniciar_demo.bat paridad RUTA_OTU_2d -> pruebas + paridad (469 imagenes)
REM ============================================================================
setlocal EnableDelayedExpansion
cd /d "%~dp0"
set "PUERTO=3000"
if exist .env for /f "usebackq tokens=1,2 delims== " %%a in (".env") do if /i "%%a"=="PUERTO" set "PUERTO=%%b"

echo.
echo === OVARA demo ===
echo.

REM ---- 1. Herramientas
where docker >nul 2>&1 || (echo [X] No encontre Docker. Instala Docker Desktop: https://www.docker.com/products/docker-desktop/ & goto :error)
set "PY=python"
where python >nul 2>&1 || (where py >nul 2>&1 && set "PY=py" || (echo [X] No encontre Python 3. Instalalo desde https://www.python.org/ & goto :error))

REM ---- 2. Motor de Docker
docker info >nul 2>&1
if not errorlevel 1 goto :docker_listo
echo [..] Docker no esta encendido. Iniciando Docker Desktop...
docker desktop start >nul 2>&1
if errorlevel 1 if exist "%ProgramFiles%\Docker\Docker\Docker Desktop.exe" start "" "%ProgramFiles%\Docker\Docker\Docker Desktop.exe"
set /a intentos=0
:esperar_docker
timeout /t 3 /nobreak >nul
docker info >nul 2>&1
if not errorlevel 1 goto :docker_listo
set /a intentos+=1
if !intentos! lss 60 goto :esperar_docker
echo [X] Docker no respondio en 3 minutos. Abre Docker Desktop manualmente y vuelve a intentar.
goto :error
:docker_listo
echo [OK] Docker encendido

REM ---- 3. Pesos del modelo
if not exist "modelos\modelo_ovara.json" (
  echo [..] Descargando los pesos del modelo ^(406 MB, solo la primera vez^)...
  %PY% scripts\descargar_modelos.py || goto :error
) else (
  echo [OK] Pesos del modelo presentes
)

REM ---- 4. Construir y encender (recrea los contenedores para que lean los pesos actuales)
echo [..] Construyendo y encendiendo los contenedores ^(la primera vez tarda 5-10 min^)...
docker compose up --build -d --force-recreate || goto :error

REM ---- 5. Esperar a que el modelo cargue
echo [..] Esperando a que el modelo cargue...
set /a intentos=0
:esperar_modelo
timeout /t 3 /nobreak >nul
curl -s -f -o nul http://localhost:%PUERTO%/api/salud && goto :listo
set /a intentos+=1
if !intentos! lss 60 goto :esperar_modelo
echo [X] El modelo no cargo en 3 minutos. Revisa:  docker compose logs backend
goto :error

:listo
echo [OK] Demo listo en http://localhost:%PUERTO%
start "" http://localhost:%PUERTO%

REM ---- 6. Pruebas opcionales
if /i "%~1"=="evidencias" %PY% scripts\evidencias.py --sin-build
if /i "%~1"=="paridad" %PY% scripts\evidencias.py --sin-build --paridad-mmotu "%~2"

echo.
echo Para detener el demo:  detener_demo.bat   (o docker compose down)
endlocal
exit /b 0

:error
echo.
echo *** No se pudo iniciar el demo. Revisa el mensaje anterior. ***
endlocal
exit /b 1
