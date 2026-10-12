"""
OVARA - Script reproducible de obtención y preparación del dataset UT-EndoMRI.

Fuente: Liang, X. et al. (2024). UTHealth - Endometriosis MRI Dataset (UT-EndoMRI) (v1)
        [Conjunto de datos]. Zenodo. https://doi.org/10.5281/zenodo.13749613
Licencia: uso exclusivo en investigación científica no comercial.

Pasos:
  1. Descarga UT-EndoMRI.zip (~8 GB) desde Zenodo (se omite si ya existe).
  2. Verifica la integridad con MD5.
  3. Descomprime en ./UT-EndoMRI (se omite si ya está descomprimido).
  4. Genera un inventario por paciente (inventario_dataset.csv) con secuencias, máscaras,
     dimensiones y tamaño de vóxel.

Uso (desde la carpeta OVARA):
    python preparar_dataset.py               # todo el proceso
    python preparar_dataset.py --solo-inventario
Después: abrir ovara_comparacion_modelos.ipynb y ejecutar "Run All".
"""
import argparse, csv, hashlib, sys, urllib.request, zipfile
from pathlib import Path

URL = "https://zenodo.org/records/13749613/files/UT-EndoMRI.zip?download=1"
MD5 = "7ace6e1b08efa10d0a1967073b0ba41c"
BASE = Path(__file__).resolve().parent
ZIP = BASE / "UT-EndoMRI.zip"
OUT = BASE / "UT-EndoMRI"
SEQS = ["T1", "T1FS", "T2", "T2FS"]
MASKS = ["ut", "ov", "cy", "em", "pat", "cds"]


def descargar():
    if ZIP.exists():
        print(f"[1/4] Ya existe {ZIP.name}, se omite la descarga.")
        return
    print(f"[1/4] Descargando {URL} ...")
    def progreso(b, bs, total):
        if total > 0 and b % 200 == 0:
            print(f"      {min(b * bs / total, 1):.1%}", end="\r")
    urllib.request.urlretrieve(URL, ZIP, progreso)
    print()


def verificar():
    print("[2/4] Verificando MD5 (puede tardar unos minutos)...")
    h = hashlib.md5()
    with open(ZIP, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 24), b""):
            h.update(chunk)
    if h.hexdigest() != MD5:
        sys.exit(f"MD5 incorrecto ({h.hexdigest()}). Borra {ZIP.name} y vuelve a descargar.")
    print("      MD5 correcto.")


def descomprimir():
    if (OUT / "UT-EndoMRI" / "D2_TCPW").exists():
        print("[3/4] Dataset ya descomprimido, se omite.")
        return
    print(f"[3/4] Descomprimiendo en {OUT} ...")
    with zipfile.ZipFile(ZIP) as z:
        z.extractall(OUT, members=[m for m in z.namelist() if not m.startswith("__MACOSX")])


def inventario():
    import nibabel as nib
    print("[4/4] Generando inventario_dataset.csv ...")
    filas = []
    for ds in sorted((OUT / "UT-EndoMRI").glob("D*_*")):
        for pac in sorted(p for p in ds.iterdir() if p.is_dir()):
            archivos = {f.name.replace(pac.name + "_", "").replace(".nii.gz", ""): f
                        for f in pac.glob("*.nii.gz")}
            fila = {"subconjunto": ds.name, "paciente": pac.name}
            for s in SEQS:
                fila[s] = int(s in archivos)
            for m in MASKS:
                fila[m] = sum(1 for k in archivos if k == m or k.startswith(m + "_r"))
            if "T2" in archivos:
                img = nib.load(str(archivos["T2"]))
                fila["T2_dim"] = "x".join(map(str, img.shape[:3]))
                fila["T2_voxel_mm"] = "x".join(f"{z:.2f}" for z in img.header.get_zooms()[:3])
            filas.append(fila)
    campos = list(dict.fromkeys(k for f in filas for k in f))
    with open(BASE / "inventario_dataset.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=campos); w.writeheader(); w.writerows(filas)
    print(f"      {len(filas)} pacientes inventariados.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--solo-inventario", action="store_true")
    a = ap.parse_args()
    if not a.solo_inventario:
        descargar(); verificar(); descomprimir()
    inventario()
