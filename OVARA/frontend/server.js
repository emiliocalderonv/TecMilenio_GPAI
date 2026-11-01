/**
 * OVARA · frontend (Node.js + Express)
 *  - Sirve la interfaz web (public/).
 *  - Recibe la imagen del usuario y la reenvía al backend de inferencia (FastAPI).
 *  - Lista las imágenes de ejemplo (carpeta ./ejemplos montada en el contenedor).
 */
"use strict";

const express = require("express");
const multer = require("multer");
const fs = require("node:fs");
const path = require("node:path");

const PUERTO = Number(process.env.PORT || 3000);
const BACKEND_URL = (process.env.BACKEND_URL || "http://localhost:8000").replace(/\/$/, "");
const EJEMPLOS_DIR = process.env.EJEMPLOS_DIR || path.join(__dirname, "..", "ejemplos");
const MAX_MB = Number(process.env.OVARA_MAX_MB || 10);
const TIMEOUT_MS = Number(process.env.TIMEOUT_MS || 120000);
const EXTENSIONES = new Set([".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".webp"]);
const VERSION = require("./package.json").version;

const subir = multer({
  storage: multer.memoryStorage(),
  limits: { fileSize: MAX_MB * 1024 * 1024, files: 1 },
  fileFilter: (_req, file, cb) =>
    file.mimetype.startsWith("image/") ? cb(null, true) : cb(new ErrorUsuario(415, "Solo se aceptan imágenes (JPG o PNG)")),
});

class ErrorUsuario extends Error {
  constructor(status, mensaje) { super(mensaje); this.status = status; }
}

async function llamarBackend(ruta, opciones = {}) {
  const ctrl = new AbortController();
  const t = setTimeout(() => ctrl.abort(), opciones.timeout || TIMEOUT_MS);
  try {
    const r = await fetch(BACKEND_URL + ruta, { ...opciones, signal: ctrl.signal });
    const cuerpo = await r.json().catch(() => ({}));
    return { status: r.status, cuerpo };
  } finally {
    clearTimeout(t);
  }
}

/** Etiquetas opcionales de los ejemplos (ejemplos/etiquetas.csv: archivo,clase_nombre,endometrioma). */
function leerEtiquetas() {
  const ruta = path.join(EJEMPLOS_DIR, "etiquetas.csv");
  if (!fs.existsSync(ruta)) return {};
  const [encabezado, ...filas] = fs.readFileSync(ruta, "utf8").trim().split(/\r?\n/);
  const cols = encabezado.split(",");
  const etiquetas = {};
  for (const fila of filas) {
    const v = fila.split(","); const reg = Object.fromEntries(cols.map((c, i) => [c, v[i]]));
    etiquetas[reg.archivo] = { clase: reg.clase_nombre, endometrioma: reg.endometrioma === "1" };
  }
  return etiquetas;
}

function crearApp() {
  const app = express();
  app.disable("x-powered-by");
  app.use(express.static(path.join(__dirname, "public")));
  app.use("/ejemplos", express.static(EJEMPLOS_DIR, { fallthrough: false }));

  app.get("/api/version", (_req, res) => res.json({ frontend: VERSION, backend_url: BACKEND_URL }));

  app.get("/api/salud", async (_req, res) => {
    try {
      const { status, cuerpo } = await llamarBackend("/health", { timeout: 4000 });
      res.status(status === 200 ? 200 : 503).json({ frontend: "ok", backend: cuerpo });
    } catch (e) {
      res.status(503).json({ frontend: "ok", backend: { estado: "sin_conexion", error: `No se pudo contactar ${BACKEND_URL}` } });
    }
  });

  app.get("/api/info", async (_req, res, next) => {
    try { const { status, cuerpo } = await llamarBackend("/info", { timeout: 4000 }); res.status(status).json(cuerpo); }
    catch (e) { next(new ErrorUsuario(503, "Backend no disponible")); }
  });

  app.get("/api/ejemplos", (_req, res) => {
    const etiquetas = leerEtiquetas();
    let archivos = [];
    try {
      archivos = fs.readdirSync(EJEMPLOS_DIR).filter((f) => EXTENSIONES.has(path.extname(f).toLowerCase()));
    } catch { /* carpeta vacía o no montada */ }
    archivos.sort((a, b) => a.localeCompare(b, "es", { numeric: true }));
    res.json(archivos.map((a) => ({ archivo: a, url: `/ejemplos/${encodeURIComponent(a)}`, etiqueta: etiquetas[a] || null })));
  });

  app.post("/api/analizar", subir.single("imagen"), async (req, res, next) => {
    try {
      if (!req.file) throw new ErrorUsuario(400, "Adjunta una imagen en el campo 'imagen'");
      const form = new FormData();
      form.append("imagen", new Blob([req.file.buffer], { type: req.file.mimetype }), req.file.originalname);
      const gradcam = req.query.gradcam === "false" ? "false" : "true";
      const t0 = Date.now();
      const { status, cuerpo } = await llamarBackend(`/predict?gradcam=${gradcam}`, { method: "POST", body: form });
      if (status !== 200) throw new ErrorUsuario(status, cuerpo.detail || "Error en el backend");
      const etiqueta = leerEtiquetas()[req.file.originalname] || null;
      res.json({ ...cuerpo, etiqueta_real: etiqueta, tiempo_ida_vuelta_ms: Date.now() - t0 });
    } catch (e) {
      next(e.name === "AbortError" ? new ErrorUsuario(504, "El análisis tardó demasiado") :
           e instanceof TypeError ? new ErrorUsuario(503, "Backend no disponible") : e);
    }
  });

  // errores → JSON legible
  // eslint-disable-next-line no-unused-vars
  app.use((err, _req, res, _next) => {
    if (err instanceof multer.MulterError) {
      const msg = err.code === "LIMIT_FILE_SIZE" ? `La imagen supera ${MAX_MB} MB` : err.message;
      return res.status(413).json({ error: msg });
    }
    const status = err.status || err.statusCode || 500;
    if (status >= 500 && !(err instanceof ErrorUsuario)) console.error(err);
    res.status(status).json({ error: err.message || "Error interno" });
  });
  return app;
}

if (require.main === module) {
  crearApp().listen(PUERTO, () => console.log(`OVARA frontend en http://localhost:${PUERTO}  →  backend ${BACKEND_URL}`));
}

module.exports = { crearApp };
