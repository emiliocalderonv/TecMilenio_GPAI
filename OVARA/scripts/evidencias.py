"""
Genera las EVIDENCIAS DE INTEGRACIÓN del demo OVARA (solo biblioteca estándar de Python).

Pasos (cada uno queda registrado en evidencias/<fecha>/ y resumido en REPORTE.md):
  1. Entorno: versiones de Docker, Docker Compose, sistema y commit de git.
  2. Construcción de las imágenes (docker compose build) y su tamaño.
  3. Pruebas unitarias DENTRO de los contenedores (pytest en el backend, node:test en el frontend).
  4. Despliegue (docker compose up -d) y espera a que el modelo esté cargado.
  5. Integración de punta a punta: navegador → frontend Node.js → backend FastAPI → modelo.
     Se envían las imágenes de ejemplos/ (o sintéticas si no hay) y se guardan respuestas e imágenes.
  6. Pruebas negativas (archivo que no es imagen, imagen dañada, archivo demasiado grande).
  7. (Opcional) Paridad: el contenedor reproduce las 469 predicciones del modelo validado.
  8. Bitácoras (logs) de los contenedores.

Uso:
  python scripts/evidencias.py                                   # todo menos paridad
  python scripts/evidencias.py --paridad-mmotu C:\\Proyectos\\AI\\OVARA\\datos_ini\\MMOTU\\OTU_2d
  python scripts/evidencias.py --sin-build --bajar
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import platform
import shutil
import statistics
import struct
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid
import zlib
from datetime import datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
TIPOS = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".bmp": "image/bmp", ".webp": "image/webp"}


# ------------------------------------------------------------------------------------------------ utilidades
def correr(cmd: list[str], archivo: Path | None = None, timeout: int = 3600) -> tuple[int, str, float]:
    t0 = time.perf_counter()
    try:
        p = subprocess.run(cmd, cwd=RAIZ, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=timeout)
        salida, codigo = p.stdout.decode("utf-8", "replace"), p.returncode
    except FileNotFoundError:
        salida, codigo = f"No se encontró el comando: {cmd[0]}", 127
    except subprocess.TimeoutExpired as e:
        salida, codigo = (e.stdout or b"").decode("utf-8", "replace") + "\n[TIEMPO AGOTADO]", 124
    dur = time.perf_counter() - t0
    if archivo:
        archivo.write_text(f"$ {' '.join(cmd)}\n# código de salida: {codigo} · {dur:.1f} s\n\n{salida}", encoding="utf-8")
    return codigo, salida, dur


def http(metodo: str, url: str, cuerpo: bytes | None = None, tipo: str | None = None, timeout: int = 180):
    req = urllib.request.Request(url, data=cuerpo, method=metodo, headers={"Content-Type": tipo} if tipo else {})
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            datos, status = r.read(), r.status
    except urllib.error.HTTPError as e:
        datos, status = e.read(), e.code
    except (urllib.error.URLError, ConnectionError, TimeoutError) as e:
        return 0, {"error": str(e)}, (time.perf_counter() - t0) * 1000
    try:
        j = json.loads(datos.decode("utf-8"))
    except ValueError:
        j = {"_texto": datos[:300].decode("utf-8", "replace")}
    return status, j, (time.perf_counter() - t0) * 1000


def multipart(campo: str, nombre: str, datos: bytes, tipo: str) -> tuple[bytes, str]:
    b = uuid.uuid4().hex
    cuerpo = (f"--{b}\r\nContent-Disposition: form-data; name=\"{campo}\"; filename=\"{nombre}\"\r\n"
              f"Content-Type: {tipo}\r\n\r\n").encode() + datos + f"\r\n--{b}--\r\n".encode()
    return cuerpo, f"multipart/form-data; boundary={b}"


def png_sintetico(ancho=480, alto=360, semilla=0) -> bytes:
    """PNG en escala de grises con un 'quiste' oscuro (sin depender de Pillow)."""
    import random
    rnd = random.Random(semilla); filas = []
    for y in range(alto):
        fila = bytearray([0])
        for x in range(ancho):
            dentro = ((x - ancho / 2) / (ancho / 4)) ** 2 + ((y - alto / 2) / (alto / 4)) ** 2 < 1
            fila.append(30 + rnd.randint(0, 20) if dentro else 60 + rnd.randint(0, 90))
        filas.append(bytes(fila))
    def trozo(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)
    return (b"\x89PNG\r\n\x1a\n" + trozo(b"IHDR", struct.pack(">IIBBBBB", ancho, alto, 8, 0, 0, 0, 0))
            + trozo(b"IDAT", zlib.compress(b"".join(filas), 9)) + trozo(b"IEND", b""))


def guardar_data_url(url: str, destino: Path):
    if url and url.startswith("data:image"):
        destino.write_bytes(base64.b64decode(url.split(",", 1)[1]))


def leer_etiquetas() -> dict:
    ruta = RAIZ / "ejemplos" / "etiquetas.csv"
    if not ruta.exists():
        return {}
    lineas = ruta.read_text(encoding="utf-8").strip().splitlines()
    cols = lineas[0].split(",")
    return {d["archivo"]: d for d in (dict(zip(cols, l.split(","))) for l in lineas[1:])}


# ------------------------------------------------------------------------------------------------ principal
def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--puerto", type=int, default=int(os.getenv("PUERTO", "3000")))
    ap.add_argument("--puerto-api", type=int, default=int(os.getenv("PUERTO_API", "8000")))
    ap.add_argument("--sin-build", action="store_true")
    ap.add_argument("--sin-unitarias", action="store_true")
    ap.add_argument("--max-ejemplos", type=int, default=16)
    ap.add_argument("--paridad-mmotu", type=Path, help="carpeta OTU_2d para la prueba de paridad (opcional)")
    ap.add_argument("--espera", type=int, default=300, help="segundos máximos para que cargue el modelo")
    ap.add_argument("--bajar", action="store_true", help="detener los contenedores al terminar")
    ap.add_argument("--solo-integracion", action="store_true", help="no usa Docker: prueba un frontend ya corriendo (desarrollo)")
    args = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    if args.solo_integracion:
        args.sin_build = args.sin_unitarias = True; args.paridad_mmotu = None
    elif shutil.which("docker") is None:
        raise SystemExit("No encontré 'docker'. Instala Docker Desktop y vuelve a intentar.")
    sello = datetime.now().strftime("%Y%m%d_%H%M%S")
    dir_ev = RAIZ / "evidencias" / sello; (dir_ev / "integracion").mkdir(parents=True)
    base, api = f"http://localhost:{args.puerto}", f"http://localhost:{args.puerto_api}"
    checks: list[tuple[str, bool, str]] = []
    def check(nombre, ok, detalle=""):
        checks.append((nombre, bool(ok), detalle)); print(f"  {'✓' if ok else '✗'} {nombre}  {detalle}")

    # 1. entorno
    print("1/8 Entorno")
    entorno = {"fecha": datetime.now().isoformat(timespec="seconds"), "sistema": platform.platform(), "python_host": sys.version.split()[0]}
    for clave, cmd in ({} if args.solo_integracion else {"docker": ["docker", "version", "--format", "{{.Server.Version}}"],
                       "docker_compose": ["docker", "compose", "version", "--short"],
                       "git_commit": ["git", "rev-parse", "--short", "HEAD"]}).items():
        c, s, _ = correr(cmd); entorno[clave] = s.strip() if c == 0 else "n/d"
    for clave in ("docker", "docker_compose", "git_commit"):
        entorno.setdefault(clave, "n/d")
    (dir_ev / "entorno.json").write_text(json.dumps(entorno, indent=2, ensure_ascii=False), encoding="utf-8")
    if not args.solo_integracion:
        check("Docker disponible", entorno["docker"] != "n/d", f"Docker {entorno['docker']} · Compose {entorno['docker_compose']}")

    # 2. construcción
    print("2/8 Construcción de imágenes")
    if not args.sin_build:
        c, _, dur = correr(["docker", "compose", "build"], dir_ev / "01_build.log", timeout=5400)
        check("docker compose build", c == 0, f"{dur:.0f} s")
    s = "" if args.solo_integracion else correr(["docker", "image", "ls", "--format", "{{.Repository}}:{{.Tag}}\t{{.Size}}\t{{.CreatedSince}}"], None)[1]
    imagenes = [l for l in s.splitlines() if l.startswith("ovara-")]
    (dir_ev / "02_imagenes.txt").write_text("\n".join(imagenes) + "\n", encoding="utf-8")
    if not args.solo_integracion:
      check("Imágenes ovara-backend y ovara-frontend existen",
          any(l.startswith("ovara-backend") for l in imagenes) and any(l.startswith("ovara-frontend") for l in imagenes), " | ".join(imagenes))

    # 3. pruebas unitarias dentro de los contenedores
    print("3/8 Pruebas unitarias en contenedores")
    if not args.sin_unitarias:
        c, s, dur = correr(["docker", "compose", "run", "--rm", "--no-deps", "-e", "OVARA_MODO_PRUEBA=1", "-e", "OVARA_MODELOS=/sin_modelos",
                            "backend", "python", "-m", "pytest", "-q", "-p", "no:cacheprovider", "tests"], dir_ev / "03_pytest_backend.log")
        check("Backend: pytest", c == 0, (s.strip().splitlines() or [""])[-1])
        c, s, dur = correr(["docker", "compose", "run", "--rm", "--no-deps", "frontend", "npm", "test", "--silent"], dir_ev / "04_test_frontend.log")
        resumen = " ".join(l.strip("# ") for l in s.splitlines() if l.startswith(("# pass", "# fail")))
        check("Frontend: node --test", c == 0, resumen)

    # 4. despliegue
    print("4/8 Despliegue")
    if not args.solo_integracion:
        c, _, _ = correr(["docker", "compose", "up", "-d"], dir_ev / "05_up.log")
        check("docker compose up -d", c == 0)
    t0, salud = time.time(), {}
    while time.time() - t0 < args.espera:
        st, salud, _ = http("GET", base + "/api/salud", timeout=5)
        if st == 200:
            break
        time.sleep(3)
    t_listo = time.time() - t0
    (dir_ev / "integracion" / "salud.json").write_text(json.dumps(salud, indent=2, ensure_ascii=False), encoding="utf-8")
    backend = salud.get("backend", {}) if isinstance(salud, dict) else {}
    check("Modelo cargado y servicio sano", backend.get("modelo_cargado") is True,
          f"listo en {t_listo:.0f} s" + (" · MODO PRUEBA (pesos aleatorios)" if backend.get("modo_prueba") else ""))
    if not args.solo_integracion:
        correr(["docker", "compose", "ps"], dir_ev / "06_compose_ps.txt")

    # 5. integración de punta a punta
    print("5/8 Integración (frontend → backend → modelo)")
    st, html, _ = http("GET", base + "/")
    check("Frontend sirve la interfaz (GET /)", st == 200)
    st, ver, _ = http("GET", base + "/api/version"); check("GET /api/version", st == 200, json.dumps(ver, ensure_ascii=False))
    st, info, _ = http("GET", base + "/api/info")
    (dir_ev / "integracion" / "info_modelo.json").write_text(json.dumps(info, indent=2, ensure_ascii=False), encoding="utf-8")
    check("GET /api/info (modelo)", st == 200, f"{info.get('n_redes')} redes · umbral {info.get('umbral')} · versión {info.get('version')}")
    st, _, _ = http("GET", api + "/docs"); check("API documentada (backend /docs)", st == 200, api + "/docs")

    etiquetas = leer_etiquetas()
    archivos = sorted([p for p in (RAIZ / "ejemplos").iterdir() if p.suffix.lower() in TIPOS],
                      key=lambda p: (int(p.stem) if p.stem.isdigit() else 0, p.name))[:args.max_ejemplos] if (RAIZ / "ejemplos").exists() else []
    casos = [(p.name, p.read_bytes(), TIPOS[p.suffix.lower()]) for p in archivos] or \
            [(f"sintetica_{i}.png", png_sintetico(semilla=i), "image/png") for i in range(3)]
    filas, tiempos = [], []
    for i, (nombre, datos, tipo) in enumerate(casos):
        cuerpo, ct = multipart("imagen", nombre, datos, tipo)
        st, j, ms = http("POST", base + "/api/analizar?gradcam=true", cuerpo, ct)
        ok = st == 200 and "probabilidad" in j
        if ok:
            tiempos.append(ms)
            carpeta = dir_ev / "integracion" / Path(nombre).stem; carpeta.mkdir(exist_ok=True)
            for k, v in j.get("imagenes", {}).items():
                guardar_data_url(v, carpeta / f"{k}.png")
            (carpeta / "respuesta.json").write_text(json.dumps({k: v for k, v in j.items() if k != "imagenes"}, indent=2, ensure_ascii=False), encoding="utf-8")
        et = etiquetas.get(nombre)
        filas.append({"archivo": nombre, "http": st, "probabilidad": j.get("probabilidad"), "alerta": j.get("alerta"),
                      "redes_en_alerta": (j.get("acuerdo") or {}).get("redes_en_alerta"),
                      "real": (et or {}).get("clase_nombre", "—"),
                      "coincide": (None if not et or not ok else (et["endometrioma"] == "1") == j["alerta"]),
                      "ms": round(ms)})
        print(f"    {nombre}: HTTP {st} · p={j.get('probabilidad')} · alerta={j.get('alerta')} · {ms:.0f} ms")
    check(f"POST /api/analizar con {len(casos)} imágenes", all(f["http"] == 200 for f in filas),
          f"latencia media {statistics.mean(tiempos):.0f} ms" if tiempos else "")

    # 6. pruebas negativas
    print("6/8 Pruebas negativas")
    c1, t1 = multipart("imagen", "nota.txt", b"esto no es una imagen", "text/plain")
    st, j, _ = http("POST", base + "/api/analizar", c1, t1); check("Rechaza archivo que no es imagen (415)", st == 415, j.get("error", ""))
    c2, t2 = multipart("imagen", "danada.jpg", b"\xff\xd8\xff basura", "image/jpeg")
    st, j, _ = http("POST", base + "/api/analizar", c2, t2); check("Rechaza imagen dañada (422)", st == 422, j.get("error", ""))
    c3, t3 = multipart("imagen", "enorme.png", b"\x89PNG" + os.urandom(11 * 1024 * 1024), "image/png")
    st, j, _ = http("POST", base + "/api/analizar", c3, t3); check("Rechaza archivo > 10 MB (413)", st == 413, j.get("error", ""))

    # 7. paridad
    paridad = None
    print("7/8 Paridad con el modelo validado")
    ref = RAIZ / "evidencias" / "referencia" / "predicciones_validadas.csv"
    if args.paridad_mmotu:
        if not ref.exists():
            check("Paridad", False, "falta evidencias/referencia/predicciones_validadas.csv (corre exportar_modelo.py)")
        else:
            c, s, dur = correr(["docker", "compose", "run", "--rm", "--no-deps", "--user", "root",
                                "-v", f"{args.paridad_mmotu.resolve()}:/datos:ro", "-v", f"{ref.parent.resolve()}:/referencia:ro",
                                "-v", f"{dir_ev.resolve()}:/salida", "backend", "python", "paridad.py", "--mmotu", "/datos",
                                "--referencia", "/referencia/predicciones_validadas.csv", "--salida", "/salida/paridad.json"],
                               dir_ev / "07_paridad.log", timeout=7200)
            if (dir_ev / "paridad.json").exists():
                paridad = json.loads((dir_ev / "paridad.json").read_text(encoding="utf-8"))
                check("Paridad contenedor vs. modelo validado", paridad["veredicto"] == "PARIDAD OK",
                      f"alertas iguales {paridad['alertas_coinciden_%']} % · Δprob media {paridad['diferencia_prob_media']:.4f} · {dur / 60:.1f} min")
            else:
                check("Paridad contenedor vs. modelo validado", False, "ver 07_paridad.log")
    else:
        print("  (omitida: usa --paridad-mmotu <carpeta OTU_2d>)")

    # 8. bitácoras
    print("8/8 Bitácoras")
    if not args.solo_integracion:
        correr(["docker", "compose", "logs", "--no-color", "--timestamps"], dir_ev / "08_logs_contenedores.log")
    if args.bajar and not args.solo_integracion:
        correr(["docker", "compose", "down"], dir_ev / "09_down.log")

    # ---- reporte
    ok_total = all(ok for _, ok, _ in checks)
    con_et = [f for f in filas if f["coincide"] is not None]
    lineas = [f"# Evidencias de integración · OVARA demo", "",
              f"- **Fecha:** {entorno['fecha']}",
              f"- **Equipo:** {entorno['sistema']}",
              f"- **Docker:** {entorno['docker']} · **Compose:** {entorno['docker_compose']} · **Commit:** {entorno['git_commit']}",
              f"- **Resultado global:** {'✅ TODAS LAS PRUEBAS PASARON' if ok_total else '❌ HAY PRUEBAS FALLIDAS'}"
              f" ({sum(ok for _, ok, _ in checks)}/{len(checks)})", "",
              "## Verificaciones", "", "| # | Verificación | Resultado | Detalle |", "|---|---|---|---|"]
    lineas += [f"| {i} | {n} | {'✅' if ok else '❌'} | {d} |" for i, (n, ok, d) in enumerate(checks, 1)]
    lineas += ["", "## Imágenes Docker", "", "```", *imagenes, "```", "",
               "## Casos analizados de punta a punta", "",
               "| Archivo | HTTP | Probabilidad | Alerta | Redes en alerta | Diagnóstico real | ¿Coincide? | ms |", "|---|---|---|---|---|---|---|---|"]
    lineas += [f"| {f['archivo']} | {f['http']} | {f['probabilidad']} | {'sí' if f['alerta'] else 'no'} | {f['redes_en_alerta']} | "
               f"{f['real']} | {'—' if f['coincide'] is None else ('✅' if f['coincide'] else '❌')} | {f['ms']} |" for f in filas]
    if con_et:
        lineas += ["", f"Coincidencia con el diagnóstico real en estos ejemplos: **{sum(f['coincide'] for f in con_et)}/{len(con_et)}** "
                       "(muestra pequeña e ilustrativa; las métricas formales están en `info_modelo.json` y en la paridad)."]
    if tiempos:
        lineas += ["", f"Latencia de punta a punta (con Grad-CAM, CPU): media {statistics.mean(tiempos):.0f} ms · "
                       f"mediana {statistics.median(tiempos):.0f} ms · máxima {max(tiempos):.0f} ms."]
    if paridad:
        md, mr = paridad["metricas_docker"], paridad["metricas_referencia"]
        lineas += ["", "## Paridad con el modelo validado (prueba MMOTU completa)", "",
                   f"- Imágenes: {paridad['imagenes']} · alertas idénticas: **{paridad['alertas_coinciden_%']} %** · "
                   f"diferencia de probabilidad media {paridad['diferencia_prob_media']:.4f} (máx. {paridad['diferencia_prob_max']:.4f})", "",
                   "| | Recall | Precisión | AUC | TP | FP | FN |", "|---|---|---|---|---|---|---|",
                   f"| Contenedor (CPU) | {md['recall']:.3f} | {md['precision']:.3f} | {md['auc']:.3f} | {md['TP']} | {md['FP']} | {md['FN']} |",
                   f"| Modelo validado (GPU) | {mr['recall']:.3f} | {mr['precision']:.3f} | {mr['auc']:.3f} | {mr['TP']} | {mr['FP']} | {mr['FN']} |",
                   "", f"**Veredicto:** {paridad['veredicto']}"]
    lineas += ["", "## Archivos de esta carpeta", "",
               "- `01_build.log`: construcción · `02_imagenes.txt`: imágenes y tamaños",
               "- `03_pytest_backend.log`, `04_test_frontend.log`: pruebas unitarias dentro de los contenedores",
               "- `05_up.log`, `06_compose_ps.txt`: despliegue y estado de los servicios",
               "- `integracion/`: salud, información del modelo y, por cada imagen, la respuesta JSON con sus imágenes (contorno, recorte, atención)",
               "- `07_paridad.log`, `paridad.json`: prueba de paridad (si se corrió)",
               "- `08_logs_contenedores.log`: bitácoras de backend y frontend"]
    (dir_ev / "REPORTE.md").write_text("\n".join(lineas) + "\n", encoding="utf-8")
    shutil.copy2(dir_ev / "REPORTE.md", RAIZ / "evidencias" / "ULTIMO_REPORTE.md")
    print(f"\n{'✅' if ok_total else '❌'} Reporte: {dir_ev / 'REPORTE.md'}")
    if not args.bajar:
        print(f"Demo corriendo en {base}  (detener: docker compose down)")
    sys.exit(0 if ok_total else 1)


if __name__ == "__main__":
    main()
