"""
Copia imágenes de la PRUEBA de MMOTU (nunca vistas en el entrenamiento) a ejemplos/ con su etiqueta real.

Uso:
    python scripts/copiar_ejemplos.py --mmotu C:\\Proyectos\\AI\\OVARA\\datos_ini\\MMOTU\\OTU_2d          # 16 (8 endometriomas + 8 otras)
    python scripts/copiar_ejemplos.py --mmotu ... --n 30
    python scripts/copiar_ejemplos.py --mmotu ... --todas                                             # las 469
"""
from __future__ import annotations

import argparse
import sys
import random
import shutil
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
CLASES = {0: "quiste_chocolate", 1: "cistoadenoma_seroso", 2: "teratoma", 3: "tumor_celulas_teca",
          4: "quiste_simple", 5: "ovario_normal", 6: "cistoadenoma_mucinoso", 7: "seroso_alto_grado"}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--mmotu", type=Path, required=True, help="carpeta OTU_2d (con images/ y val_cls.txt)")
    ap.add_argument("--n", type=int, default=16)
    ap.add_argument("--todas", action="store_true")
    ap.add_argument("--semilla", type=int, default=7)
    ap.add_argument("--destino", type=Path, default=RAIZ / "ejemplos")
    args = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    filas = [l.split() for l in (args.mmotu / "val_cls.txt").read_text().splitlines() if len(l.split()) == 2]
    filas = [(a, int(c)) for a, c in filas if (args.mmotu / "images" / a).exists()]
    if not args.todas:
        rng = random.Random(args.semilla)
        endo = [f for f in filas if f[1] == 0]; otras = [f for f in filas if f[1] != 0]
        filas = rng.sample(endo, min(len(endo), args.n // 2)) + rng.sample(otras, min(len(otras), args.n - args.n // 2))
    args.destino.mkdir(parents=True, exist_ok=True)
    for a, _ in filas:
        shutil.copy2(args.mmotu / "images" / a, args.destino / a)
    with open(args.destino / "etiquetas.csv", "w", encoding="utf-8") as f:
        f.write("archivo,clase,clase_nombre,endometrioma\n")
        for a, c in sorted(filas, key=lambda x: int(Path(x[0]).stem) if Path(x[0]).stem.isdigit() else 0):
            f.write(f"{a},{c},{CLASES[c]},{int(c == 0)}\n")
    n_endo = sum(c == 0 for _, c in filas)
    print(f"✓ {len(filas)} imágenes de prueba en {args.destino} ({n_endo} endometriomas, {len(filas) - n_endo} otras) + etiquetas.csv")


if __name__ == "__main__":
    main()
