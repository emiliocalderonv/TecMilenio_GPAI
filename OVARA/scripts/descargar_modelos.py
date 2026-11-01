"""
Descarga los pesos del modelo (zip del Release de GitHub) a modelos/ y verifica su integridad (SHA-256).
Solo usa la biblioteca estándar de Python.

Uso:
    python scripts/descargar_modelos.py --url https://github.com/<usuario>/<repo>/releases/download/v1.0.0/ovara_modelos_v1.0.0.zip
    python scripts/descargar_modelos.py --zip ovara_modelos_v1.0.0.zip      # si ya tienes el zip
"""
from __future__ import annotations

import argparse
import hashlib
import os
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
URL_DEFECTO = os.getenv("OVARA_MODELOS_URL", "")


def sha256(ruta: Path) -> str:
    h = hashlib.sha256()
    with open(ruta, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def progreso(n, tam, total):
    if total > 0:
        sys.stdout.write(f"\r  {min(100, n * tam * 100 // total):3d} %  ({n * tam / 1e6:.0f} de {total / 1e6:.0f} MB)"); sys.stdout.flush()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--url", default=URL_DEFECTO)
    ap.add_argument("--zip", type=Path)
    ap.add_argument("--destino", type=Path, default=RAIZ / "modelos")
    args = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    if args.zip:
        z = args.zip
    elif args.url:
        z = Path(tempfile.gettempdir()) / Path(args.url).name
        print(f"Descargando {args.url}")
        urllib.request.urlretrieve(args.url, z, progreso); print()
    else:
        raise SystemExit("Indica --url (Release de GitHub) o --zip (archivo local)")

    args.destino.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(z) as zf:
        zf.extractall(args.destino)
    sumas = args.destino / "SHA256SUMS.txt"
    malos = []
    for linea in sumas.read_text(encoding="utf-8").splitlines():
        h, nombre = linea.split(maxsplit=1)
        if sha256(args.destino / nombre) != h:
            malos.append(nombre)
    if malos:
        raise SystemExit(f"✗ Archivos dañados: {malos}. Vuelve a descargar.")
    print(f"✓ Pesos listos y verificados en {args.destino}")


if __name__ == "__main__":
    main()
