# OVARA · Instrucciones de ejecución desde cero

Esta guía explica cómo poner a funcionar el demo de **OVARA** en una computadora nueva, sin nada instalado. Al terminar tendrás una página web en tu navegador donde subes un ultrasonido y el sistema indica si hay hallazgos compatibles con **endometrioma**.

> ⚠️ **Demo académico** (Tecmilenio · Gestión de Proyectos de IA). No es un dispositivo médico ni sustituye el juicio clínico.

**Tiempo estimado:**
- 20 a 40 minutos la primera vez, casi todo en descargas e instalación.
- Menos de 1 minuto las siguientes veces.

---

## 1. Requisitos del equipo

| Requisito | Mínimo |
|---|---|
| Sistema operativo | Windows 10/11 (64 bits), macOS 12 o más reciente, o Linux |
| Memoria RAM | 8 GB (Docker debe tener al menos 4 GB asignados) |
| Espacio libre en disco | 6 GB |
| Internet | Necesario solo para la instalación y la primera descarga |
| Tarjeta gráfica (GPU) | **No es necesaria** |

---

## 2. Instalar las herramientas (solo la primera vez)

Se necesitan tres programas:

- **Docker Desktop:** ejecuta los contenedores.
- **Git:** descarga el proyecto.
- **Python 3.9 o más reciente:** ejecuta los scripts de apoyo.

### Windows

1. Abre **PowerShell como administrador**. Haz clic derecho en Inicio y elige *Terminal (Administrador)*.
2. Activa WSL 2, que Docker necesita en Windows:
   ```powershell
   wsl --install
   ```
   **Reinicia la computadora** si te lo pide.
3. Instala los tres programas con `winget`:
   ```powershell
   winget install -e --id Docker.DockerDesktop
   winget install -e --id Git.Git
   winget install -e --id Python.Python.3.12
   ```
   Si `winget` no funciona, descárgalos de sus páginas oficiales:
   - [Docker Desktop](https://www.docker.com/products/docker-desktop/)
   - [Git](https://git-scm.com/downloads)
   - [Python](https://www.python.org/downloads/). Durante la instalación marca **"Add Python to PATH"**.
4. **Cierra y vuelve a abrir** PowerShell para que reconozca los nuevos programas.
5. Abre **Docker Desktop** una vez desde el menú Inicio, acepta los términos y espera a que diga **"Engine running"**.
6. En Docker Desktop, entra a *Settings → Resources* y revisa que tenga **al menos 4 GB de memoria**.

### macOS

```bash
# Si no tienes Homebrew: https://brew.sh
brew install --cask docker
brew install git python
open -a Docker      # espera a que diga "Engine running"
```

### Linux (Ubuntu/Debian)

```bash
sudo apt update && sudo apt install -y git python3 curl
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER    # luego cierra sesión y vuelve a entrar
```

### Verificar la instalación

Ejecuta estos comandos en una terminal nueva. Cada uno debe mostrar un número de versión.

```powershell
docker --version
docker compose version
git --version
python --version        # en macOS/Linux: python3 --version
```

---

## 3. Descargar el proyecto

```powershell
cd C:\                 # o la carpeta donde quieras guardarlo
git clone https://github.com/emiliocalderonv/TecMilenio_GPAI.git
cd TecMilenio_GPAI\OVARA
```

Todos los comandos siguientes se ejecutan **desde la carpeta `OVARA`**.

---

## 4. Ejecutar el demo

### Opción A: todo en un paso (recomendada)

**Windows:** ejecuta lo siguiente o haz doble clic en `iniciar_demo.bat`.

```powershell
.\iniciar_demo.bat
```

**macOS / Linux:**

```bash
chmod +x iniciar_demo.sh
./iniciar_demo.sh
```

El script hace todo esto por ti:

1. ✔ Verifica que estén Docker y Python.
2. ✔ Enciende Docker Desktop si está apagado.
3. ✔ Descarga los pesos del modelo (406 MB, solo la primera vez) y comprueba que no estén dañados.
4. ✔ Construye y enciende los contenedores. La primera vez tarda de 5 a 10 minutos.
5. ✔ Espera a que el modelo cargue.
6. ✔ Abre el navegador en **http://localhost:3000**.

### Opción B: paso a paso (manual)

```powershell
# 1. Encender Docker (si no está abierto)
docker desktop start

# 2. Descargar y verificar los pesos del modelo (solo la primera vez)
python scripts\descargar_modelos.py

# 3. Construir y encender los dos contenedores
docker compose up --build -d

# 4. Revisar que estén corriendo
docker compose ps
```

Después abre **http://localhost:3000** en tu navegador.

---

## 5. Usar el demo

1. Elige una de las **16 imágenes de prueba** de la galería, o arrastra un ultrasonido propio (JPG o PNG, máximo 10 MB).
2. Presiona **Analizar imagen**. Tarda unos 2 segundos.
3. Revisa el resultado:
   - **Alerta / Sin alerta** y la probabilidad, comparada con el umbral de 0.28.
   - **Redes en alerta:** cuántas de las 20 redes coinciden.
   - **Lesión localizada:** el contorno amarillo que encontró el sistema.
   - **Dónde miró el modelo:** en rojo, las zonas que más pesaron en la decisión.
   - En las imágenes de prueba, el **diagnóstico real** y si coincide con el del modelo.

Casos sugeridos para una demostración:

| Imagen | Diagnóstico real | Qué muestra |
|---|---|---|
| `12.JPG` | Endometrioma | Acierto claro (probabilidad 0.99, 20 de 20 redes) |
| `948.JPG` | Teratoma | Lesión correctamente descartada (0.01) |
| `88.JPG` | Ovario normal | Falsa alarma (0.61): por qué el médico siempre confirma |

La documentación técnica de la API está en **http://localhost:8000/docs**.

---

## 6. Ejecutar las pruebas (opcional)

```powershell
python scripts\evidencias.py
```

Este comando construye, prueba y genera un reporte en `evidencias\ULTIMO_REPORTE.md`. El reporte incluye:

- Pruebas unitarias dentro de los contenedores.
- Integración de punta a punta con las 16 imágenes.
- Rechazo de archivos inválidos.
- Bitácoras de los contenedores.

Si tienes el dataset MMOTU, puedes agregar la **prueba de paridad** con las 469 imágenes. Tarda unos 7 minutos.

```powershell
python scripts\evidencias.py --paridad-mmotu RUTA\A\MMOTU\OTU_2d
```

---

## 7. Detener y volver a encender

| Acción | Comando |
|---|---|
| Detener el demo | `.\detener_demo.bat` o `docker compose down` |
| Volver a encenderlo | `.\iniciar_demo.bat` o `docker compose up -d` |
| Ver qué está pasando | `docker compose logs -f backend` |
| Apagar Docker por completo | `docker desktop stop` |
| Borrar todo (contenedores e imágenes) | `docker compose down --rmi all` |

Los pesos del modelo se conservan en la carpeta `modelos`, así que no se vuelven a descargar.

---

## 8. Solución de problemas

| Síntoma | Causa probable | Solución |
|---|---|---|
| `error during connect ... dockerDesktopLinuxEngine` | Docker Desktop está apagado | `docker desktop start` y espera a "Engine running" |
| `'docker' no se reconoce como un comando` | Docker no está instalado o la terminal es anterior a la instalación | Instala Docker Desktop y abre una terminal nueva |
| `publicar_en_repo.bat no se reconoce` en PowerShell | PowerShell no ejecuta archivos de la carpeta actual sin `.\` | Escribe `.\nombre.bat` |
| La página dice **"Sin modelo"** | Faltan los pesos en `modelos` | `python scripts\descargar_modelos.py` y luego `docker compose up -d --force-recreate` |
| La página dice **"Esperando backend…"** por más de 1 minuto | El modelo sigue cargando, o falta memoria | `docker compose logs backend`; sube la memoria de Docker a 4 GB o más |
| `port is already allocated` (3000 u 8000) | Otro programa usa el puerto | Copia `.env.example` como `.env` y cambia `PUERTO` o `PUERTO_API` |
| La descarga de pesos da **404** | Problema temporal o URL incorrecta | Repite el comando; si sigue, descarga el zip desde la pestaña *Releases* del repositorio y usa `python scripts\descargar_modelos.py --zip RUTA\ovara_modelos_v1.0.0.zip` |
| La construcción falla al descargar PyTorch | Conexión interrumpida | Vuelve a ejecutar `docker compose up --build -d` |
| El análisis tarda más de 5 segundos | Equipo con pocos núcleos | Desactiva *"Mostrar dónde miró el modelo"* para acelerarlo |

---

## 9. Resumen rápido (para la próxima vez)

```powershell
cd C:\TecMilenio_GPAI\OVARA
.\iniciar_demo.bat          # enciende y abre http://localhost:3000
.\detener_demo.bat          # apaga
```

**Repositorio:** https://github.com/emiliocalderonv/TecMilenio_GPAI (carpeta `OVARA`)
**Pesos del modelo:** Release `ovara-v1.0.0` del mismo repositorio
