// Pruebas del frontend con un backend simulado (node:test, sin dependencias extra).
"use strict";
const { test, before, after } = require("node:test");
const assert = require("node:assert/strict");
const http = require("node:http");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");

// PNG 1×1 válido
const PNG = Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==", "base64");
let backend, servidor, base, recibido;

before(async () => {
  backend = http.createServer((req, res) => {
    let cuerpo = [];
    req.on("data", (c) => cuerpo.push(c));
    req.on("end", () => {
      res.setHeader("content-type", "application/json");
      if (req.url === "/health") return res.end(JSON.stringify({ estado: "ok", modelo_cargado: true, modo_prueba: true }));
      if (req.url === "/info") return res.end(JSON.stringify({ umbral: 0.28, n_redes: 20, version_api: "1.0.0" }));
      if (req.url.startsWith("/predict")) {
        recibido = { url: req.url, bytes: Buffer.concat(cuerpo).length, tipo: req.headers["content-type"] };
        return res.end(JSON.stringify({ probabilidad: 0.9, umbral: 0.28, alerta: true, imagenes: {} }));
      }
      res.statusCode = 404; res.end("{}");
    });
  }).listen(0);
  const dirEj = fs.mkdtempSync(path.join(os.tmpdir(), "ej-"));
  fs.writeFileSync(path.join(dirEj, "12.JPG"), PNG);
  fs.writeFileSync(path.join(dirEj, "etiquetas.csv"), "archivo,clase,clase_nombre,endometrioma\n12.JPG,0,quiste_chocolate,1\n");
  process.env.BACKEND_URL = `http://localhost:${backend.address().port}`;
  process.env.EJEMPLOS_DIR = dirEj;
  const { crearApp } = require("../server.js");
  servidor = crearApp().listen(0);
  base = `http://localhost:${servidor.address().port}`;
});

after(() => { servidor.close(); backend.close(); });

test("sirve la interfaz", async () => {
  const r = await fetch(base + "/");
  assert.equal(r.status, 200);
  assert.match(await r.text(), /OVARA/);
});

test("reporta la salud del backend", async () => {
  const j = await (await fetch(base + "/api/salud")).json();
  assert.equal(j.frontend, "ok");
  assert.equal(j.backend.modelo_cargado, true);
});

test("lista ejemplos con su etiqueta", async () => {
  const j = await (await fetch(base + "/api/ejemplos")).json();
  assert.equal(j.length, 1);
  assert.equal(j[0].etiqueta.endometrioma, true);
});

test("reenvía la imagen al backend y agrega la etiqueta real", async () => {
  const form = new FormData();
  form.append("imagen", new Blob([PNG], { type: "image/png" }), "12.JPG");
  const r = await fetch(base + "/api/analizar?gradcam=false", { method: "POST", body: form });
  assert.equal(r.status, 200);
  const j = await r.json();
  assert.equal(j.alerta, true);
  assert.equal(j.etiqueta_real.clase, "quiste_chocolate");
  assert.match(recibido.url, /gradcam=false/);
  assert.match(recibido.tipo, /multipart\/form-data/);
  assert.ok(recibido.bytes > PNG.length);
});

test("rechaza archivos que no son imagen", async () => {
  const form = new FormData();
  form.append("imagen", new Blob(["hola"], { type: "text/plain" }), "x.txt");
  const r = await fetch(base + "/api/analizar", { method: "POST", body: form });
  assert.equal(r.status, 415);
});

test("pide la imagen si no viene", async () => {
  const r = await fetch(base + "/api/analizar", { method: "POST", body: new FormData() });
  assert.equal(r.status, 400);
});
