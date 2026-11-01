@echo off
REM Copia el demo OVARA a la carpeta OVARA de tu repo (por ejemplo TecMilenio_GPAI)
REM y coloca el workflow de CI en la raiz del repo (.github\workflows), donde GitHub lo lee.
REM Uso:  publicar_en_repo.bat C:\ruta\a\TecMilenio_GPAI
setlocal
if "%~1"=="" (
  echo Uso: publicar_en_repo.bat C:\ruta\a\TecMilenio_GPAI
  exit /b 1
)
set "REPO=%~f1"
set "ORIGEN=%~dp0"
if not exist "%REPO%\.git" (
  echo No es un repositorio git: %REPO%
  echo Clona primero:  git clone https://github.com/emiliocalderonv/TecMilenio_GPAI.git
  exit /b 1
)
echo Copiando a %REPO%\OVARA ...
robocopy "%ORIGEN%." "%REPO%\OVARA" /E /XD node_modules .git .github _fallidas __pycache__ .pytest_cache .venv /XF *.pt *.zip .env /NFL /NDL /NJH /NJS /NP
if %ERRORLEVEL% GEQ 8 (
  echo Error al copiar ^(robocopy %ERRORLEVEL%^)
  exit /b 1
)
if not exist "%REPO%\.github\workflows" mkdir "%REPO%\.github\workflows"
copy /Y "%ORIGEN%.github\workflows\ovara-ci.yml" "%REPO%\.github\workflows\ovara-ci.yml" >nul
echo.
echo Listo. Revisa con:  cd /d "%REPO%" ^&^& git status
exit /b 0
