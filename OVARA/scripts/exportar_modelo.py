"""
Exporta el modelo validado (Experimento_CNN) a la carpeta modelos/ del demo.

- Lee modelo_final/modelo_final.json (ensamble de 20 CNN + U-Net + flujo automático, umbral 0.28).
- Copia los pesos en float16, a la mitad del tamaño (usa --fp32 para conservarlos completos).
- Escribe modelos/modelo_ovara.json con el umbral, la estrategia y las métricas de validación.
- Genera SHA256SUMS.txt y un zip listo para subir como Release de GitHub.
- Copia las predicciones validadas a evidencias/referencia/ para la prueba de paridad.

Uso (desde la raíz del repo, con el Python donde tienes PyTorch):
    python scripts/exportar_modelo.py --origen C:\\Proyectos\\AI\\OVARA\\Experimento_CNN
"""
from __future__ import annotations

import argparse
import sys
import hashlib
import json
import shutil
import zipfile
from datetime import date
from pathlib import Path

import torch

RAIZ = Path(__file__).resolve().parents[1]
VERSION = "1.0.0"


def sha256(ruta: Path) -> str:
    h = hashlib.sha256()
    with open(ruta, "rb") as f:
        for bloque in iter(lambda: f.read(1 << 20), b""):
            h.update(bloque)
    return h.hexdigest()


def guardar(origen: Path, destino: Path, fp32: bool):
    estado = torch.load(origen, map_location="cpu", weights_only=True)
    if not fp32:
        estado = {k: v.half() if v.is_floating_point() else v for k, v in estado.items()}
    torch.save(estado, destino)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--origen", type=Path, required=True, help="carpeta Experimento_CNN")
    ap.add_argument("--destino", type=Path, default=RAIZ / "modelos")
    ap.add_argument("--fp32", action="store_true", help="no convertir a float16")
    ap.add_argument("--sin-zip", action="store_true")
    args = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    cfg = json.loads((args.origen / "modelo_final" / "modelo_final.json").read_text(encoding="utf-8"))
    fa = cfg.get("flujo_automatico")
    if not fa:
        raise SystemExit("modelo_final.json no tiene 'flujo_automatico': corre antes calibrar_flujo.py en el experimento")
    args.destino.mkdir(parents=True, exist_ok=True)
    for viejo in args.destino.glob("*.pt"):
        viejo.unlink()

    print(f"Exportando {len(cfg['modelos'])} clasificadores + segmentador ({'float32' if args.fp32 else 'float16'})...")
    clasificadores = []
    for i, m in enumerate(cfg["modelos"]):
        nombre = f"clf_{i:02d}_{m['arch']}.pt"
        guardar(args.origen / m["ruta"], args.destino / nombre, args.fp32)
        clasificadores.append({"arch": m["arch"], "archivo": nombre, "origen": m["ruta"]})
    guardar(args.origen / cfg["segmentador"], args.destino / "segmentador.pt", args.fp32)

    # métricas de la última validación con el flujo automático (validacion_externa.py)
    metricas, ref = None, None
    corridas = sorted((args.origen / "validacion_externa").glob("*/resumen.json"), key=lambda p: p.stat().st_mtime)
    for r in reversed(corridas):
        j = json.loads(r.read_text(encoding="utf-8"))
        if abs(float(j.get("umbral", -1)) - float(fa["umbral"])) < 1e-9 and "metricas" in j:
            mm = j["metricas"]
            metricas = {"recall": mm["recall"], "precision": mm["precision"], "auc": mm["roc_auc"], "f1": mm["f1"],
                        "estudios": j["imagenes"], "fuente": "prueba MMOTU", "ic95": j.get("ic95"),
                        "corrida": r.parent.name}
            ref = r.parent / "predicciones.csv"
            break
    if metricas is None:
        print("⚠ No encontré una corrida de validacion_externa con el umbral del flujo; el demo no mostrará métricas")

    salida = {
        "version": VERSION, "fecha_exportacion": date.today().isoformat(),
        "descripcion": "OVARA Fase 2: U-Net (localiza la lesión) + ensamble de CNN sobre el recorte (alerta de endometrioma)",
        "umbral": fa["umbral"], "estrategia": fa["estrategia"], "area_min": fa["area_min"],
        "meta_recall_oof": fa.get("meta_recall_oof"), "calibracion": fa.get("calibrado_con"),
        "segmentador": "segmentador.pt", "clasificadores": clasificadores, "precision_pesos": "float32" if args.fp32 else "float16",
        "metricas_validacion": metricas,
        "referencia_random_forest": {"recall": 0.80, "precision": 0.515, "auc": 0.861},
    }
    (args.destino / "modelo_ovara.json").write_text(json.dumps(salida, indent=2, ensure_ascii=False), encoding="utf-8")

    archivos = sorted([p for p in args.destino.iterdir() if p.suffix in (".pt", ".json")])
    (args.destino / "SHA256SUMS.txt").write_text("".join(f"{sha256(p)}  {p.name}\n" for p in archivos), encoding="utf-8")
    total = sum(p.stat().st_size for p in archivos) / 1e6
    print(f"✓ {len(archivos)} archivos en {args.destino} ({total:.0f} MB)")

    if ref and ref.exists():
        (RAIZ / "evidencias" / "referencia").mkdir(parents=True, exist_ok=True)
        shutil.copy2(ref, RAIZ / "evidencias" / "referencia" / "predicciones_validadas.csv")
        print("✓ Predicciones validadas copiadas a evidencias/referencia/ (para la prueba de paridad)")

    if not args.sin_zip:
        z = RAIZ / f"ovara_modelos_v{VERSION}.zip"
        with zipfile.ZipFile(z, "w", compression=zipfile.ZIP_STORED) as zf:
            for p in archivos + [args.destino / "SHA256SUMS.txt"]:
                zf.write(p, p.name)
        print(f"✓ {z.name} ({z.stat().st_size / 1e6:.0f} MB) → súbelo como asset de un Release de GitHub (ver README)")


if __name__ == "__main__":
    main()
