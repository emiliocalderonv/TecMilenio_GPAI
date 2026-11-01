"""
Descarga los pesos del modelo (zip del Release de GitHub) a modelos/ y verifica su integridad (SHA-256).
Funciona con repos PÚBLICOS y PRIVADOS (para privados usa tu sesión de GitHub CLI o un token).
Solo usa la biblioteca estándar de Python.

Uso:
    python scripts/descargar_modelos.py                          # usa el Release por defecto (ver abajo)
    python scripts/descargar_modelos.py --url https://github.com/<usuario>/<repo>/releases/download/<tag>/<archivo>.zip
    python scripts/descargar_modelos.py --zip ovara_modelos_v1.0.0.zip      # si ya descargaste el zip

Repo privado: el script toma el token, en este orden, de
    1) la variable de entorno GITHUB_TOKEN (o GH_TOKEN), o
    2) GitHub CLI ya autenticado (`gh auth login`), con `gh auth token`.
El token solo necesita permiso de lectura de contenido del repo.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
URL_DEFECTO = os.getenv("OVARA_MODELOS_URL",
                        "https://github.com/emiliocalderonv/TecMilenio_GPAI/releases/download/ovara-v1.0.0/ovara_modelos_v1.0.0.zip")
PATRON = re.compile(r"https://github\.com/([^/]+)/([^/]+)/releases/download/([^/]+)/(.+)$")


def sha256(ruta: Path) -> str:
    h = hashlib.sha256()
    with open(ruta, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def obtener_token() -> str | None:
    for var in ("GITHUB_TOKEN", "GH_TOKEN"):
        if os.getenv(var):
            return os.getenv(var).strip()
    if shutil.which("gh"):
        try:
            r = subprocess.run(["gh", "auth", "token"], capture_output=True, text=True, timeout=15)
            if r.returncode == 0 and r.stdout.strip():
                return r.stdout.strip()
        except (OSError, subprocess.TimeoutExpired):
            pass
    return None


class SinAuthAlRedirigir(urllib.request.HTTPRedirectHandler):
    """GitHub redirige el archivo a otro dominio (almacenamiento): ahí NO se debe reenviar el token."""
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        nuevo = super().redirect_request(req, fp, code, msg, headers, newurl)
        if nuevo is not None and urllib.parse.urlparse(newurl).netloc != urllib.parse.urlparse(req.full_url).netloc:
            for h in ("Authorization", "authorization"):
                nuevo.headers.pop(h, None); nuevo.unredirected_hdrs.pop(h, None)
        return nuevo


def descargar(url: str, destino: Path, cabeceras: dict | None = None):
    opener = urllib.request.build_opener(SinAuthAlRedirigir())
    req = urllib.request.Request(url, headers={"User-Agent": "ovara-descarga", **(cabeceras or {})})
    with opener.open(req, timeout=60) as r, open(destino, "wb") as f:
        total, n = int(r.headers.get("Content-Length") or 0), 0
        for bloque in iter(lambda: r.read(1 << 20), b""):
            f.write(bloque); n += len(bloque)
            if total:
                sys.stdout.write(f"\r  {100 * n // total:3d} %  ({n / 1e6:.0f} de {total / 1e6:.0f} MB)"); sys.stdout.flush()
    print()


def descargar_privado(url: str, destino: Path, token: str):
    """Repo privado: se busca el archivo del Release con la API de GitHub y se descarga autenticado."""
    m = PATRON.match(url)
    if not m:
        raise SystemExit("La URL no tiene el formato de un Release de GitHub")
    dueno, repo, tag, nombre = m.groups()
    api = f"https://api.github.com/repos/{dueno}/{repo}/releases/tags/{urllib.parse.quote(tag)}"
    auth = {"Authorization": f"Bearer {token}", "X-GitHub-Api-Version": "2022-11-28"}
    try:
        req = urllib.request.Request(api, headers={"User-Agent": "ovara-descarga", "Accept": "application/vnd.github+json", **auth})
        with urllib.request.urlopen(req, timeout=30) as r:
            rel = json.load(r)
    except urllib.error.HTTPError as e:
        raise SystemExit(f"✗ No se encontró el Release '{tag}' en {dueno}/{repo} (HTTP {e.code}). "
                         "Revisa el tag y que tu cuenta/token tenga acceso al repo.")
    asset = next((a for a in rel.get("assets", []) if a["name"] == urllib.parse.unquote(nombre)), None)
    if asset is None:
        raise SystemExit(f"✗ El Release '{tag}' no tiene el archivo {nombre}. Tiene: {[a['name'] for a in rel.get('assets', [])]}")
    print(f"Repo privado: descargando con tu sesión de GitHub ({asset['size'] / 1e6:.0f} MB)")
    descargar(asset["url"], destino, {**auth, "Accept": "application/octet-stream"})


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--url", default=URL_DEFECTO)
    ap.add_argument("--zip", type=Path)
    ap.add_argument("--destino", type=Path, default=RAIZ / "modelos")
    args = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    if args.zip:
        z = args.zip
    else:
        z = Path(tempfile.gettempdir()) / Path(urllib.parse.urlparse(args.url).path).name
        print(f"Descargando {args.url}")
        try:
            descargar(args.url, z)
        except urllib.error.HTTPError as e:
            if e.code not in (401, 403, 404):
                raise
            token = obtener_token()
            if not token:
                raise SystemExit(
                    f"✗ HTTP {e.code}: el repo parece privado y no encontré credenciales.\n"
                    "  Opción 1: instala GitHub CLI y ejecuta  gh auth login  (luego repite este comando)\n"
                    "  Opción 2: define un token:  $env:GITHUB_TOKEN = \"ghp_...\"   (PowerShell)\n"
                    "  Opción 3: descarga el zip desde el navegador y usa  --zip <ruta al zip>")
            descargar_privado(args.url, z, token)

    args.destino.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(z) as zf:
        zf.extractall(args.destino)
    malos = []
    for linea in (args.destino / "SHA256SUMS.txt").read_text(encoding="utf-8").splitlines():
        h, nombre = linea.split(maxsplit=1)
        if sha256(args.destino / nombre) != h:
            malos.append(nombre)
    if malos:
        raise SystemExit(f"✗ Archivos dañados: {malos}. Vuelve a descargar.")
    print(f"✓ Pesos listos y verificados en {args.destino}")


if __name__ == "__main__":
    main()
