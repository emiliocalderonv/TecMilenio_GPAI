"use strict";
const $ = (id) => document.getElementById(id);
let archivoActual = null;
let modeloListo = false;

// ---------------------------------------------------------------- estado del backend
async function revisarSalud() {
  try {
    const r = await fetch("/api/salud");
    const j = await r.json();
    const b = j.backend || {};
    if (r.ok && b.modelo_cargado) {
      modeloListo = true;
      ponerEstado(b.modo_prueba ? "Listo · modo prueba" : "Modelo listo", "ok");
      $("avisoPrueba").hidden = !b.modo_prueba;
      $("avisoError").hidden = true;
      cargarInfo();
      return;
    }
    modeloListo = false;
    ponerEstado(b.estado === "sin_conexion" ? "Esperando backend…" : "Sin modelo", b.estado === "sin_conexion" ? "cargando" : "error");
    if (b.error) mostrarError(b.error);
  } catch {
    ponerEstado("Esperando backend…", "cargando");
  }
  actualizarBoton();
  setTimeout(revisarSalud, 4000);
}

function ponerEstado(texto, tipo) {
  const e = $("estado");
  e.textContent = texto;
  e.className = `pastilla pastilla--${tipo}`;
  actualizarBoton();
}

function mostrarError(msg) {
  $("avisoError").textContent = msg;
  $("avisoError").hidden = false;
}

async function cargarInfo() {
  try {
    const [info, ver] = await Promise.all([fetch("/api/info").then((r) => r.json()), fetch("/api/version").then((r) => r.json())]);
    $("nRedes").textContent = info.n_redes;
    $("umbralFlujo").textContent = info.umbral.toFixed(2);
    $("aviso").textContent = info.aviso || "";
    $("versiones").textContent = `frontend ${ver.frontend} · API ${info.version_api} · modelo ${info.version || "?"}`;
    const m = info.metricas_validacion;
    if (m) {
      const pct = (v) => `${(100 * v).toFixed(0)} %`;
      const tarjetas = [
        ["Detecta (recall)", pct(m.recall), "de los endometriomas"],
        ["Precisión", pct(m.precision), "de las alertas son correctas"],
        ["AUC", m.auc.toFixed(2), "capacidad de distinguir (máx. 1)"],
        ["Evaluado en", `${m.estudios}`, m.fuente || "estudios"],
      ];
      $("metricas").innerHTML = tarjetas.map(([t, v, s]) => `<div><small>${t}</small><b>${v}</b><small>${s}</small></div>`).join("");
    }
  } catch { /* la info es opcional */ }
}

// ---------------------------------------------------------------- selección de imagen
function elegirArchivo(file) {
  if (!file) return;
  if (!file.type.startsWith("image/")) return mostrarError("Selecciona una imagen (JPG o PNG).");
  archivoActual = file;
  const url = URL.createObjectURL(file);
  $("vistaPrevia").src = url;
  $("vistaPrevia").hidden = false;
  $("zonaTexto").hidden = true;
  document.querySelectorAll(".ejemplos button").forEach((b) => b.classList.toggle("activo", b.dataset.archivo === file.name));
  actualizarBoton();
}

function actualizarBoton() {
  $("analizar").disabled = !(archivoActual && modeloListo);
}

$("archivo").addEventListener("change", (e) => elegirArchivo(e.target.files[0]));
const zona = $("zona");
["dragenter", "dragover"].forEach((ev) => zona.addEventListener(ev, (e) => { e.preventDefault(); zona.classList.add("zona--encima"); }));
["dragleave", "drop"].forEach((ev) => zona.addEventListener(ev, (e) => { e.preventDefault(); zona.classList.remove("zona--encima"); }));
zona.addEventListener("drop", (e) => elegirArchivo(e.dataTransfer.files[0]));

async function cargarEjemplos() {
  try {
    const lista = await fetch("/api/ejemplos").then((r) => r.json());
    if (!lista.length) return;
    $("bloqueEjemplos").hidden = false;
    $("ejemplos").innerHTML = lista.map((e) =>
      `<button type="button" data-archivo="${e.archivo}" data-url="${e.url}" title="${e.archivo}">` +
      `<img loading="lazy" src="${e.url}" alt="${e.archivo}"><span>${e.archivo}</span></button>`).join("");
    $("ejemplos").addEventListener("click", async (ev) => {
      const b = ev.target.closest("button");
      if (!b) return;
      const blob = await fetch(b.dataset.url).then((r) => r.blob());
      elegirArchivo(new File([blob], b.dataset.archivo, { type: blob.type || "image/jpeg" }));
    });
  } catch { /* sin ejemplos */ }
}

// ---------------------------------------------------------------- análisis
$("analizar").addEventListener("click", async () => {
  if (!archivoActual) return;
  $("avisoError").hidden = true;
  $("vacio").hidden = true;
  $("resultado").hidden = true;
  $("cargando").hidden = false;
  $("analizar").disabled = true;
  try {
    const form = new FormData();
    form.append("imagen", archivoActual, archivoActual.name);
    const r = await fetch(`/api/analizar?gradcam=${$("gradcam").checked}`, { method: "POST", body: form });
    const j = await r.json();
    if (!r.ok) throw new Error(j.error || `Error ${r.status}`);
    pintarResultado(j);
  } catch (e) {
    mostrarError(e.message);
    $("vacio").hidden = false;
  } finally {
    $("cargando").hidden = true;
    actualizarBoton();
  }
});

function pintarResultado(j) {
  const v = $("veredicto");
  v.className = `veredicto ${j.alerta ? "veredicto--alerta" : "veredicto--ok"}`;
  $("veredictoTitulo").textContent = j.alerta ? "⚠ Alerta: posible endometrioma" : "✓ Sin alerta";
  $("veredictoTexto").textContent = j.mensaje;

  const p = j.probabilidad;
  $("prob").textContent = `${(100 * p).toFixed(1)} %`;
  $("barra").style.width = `${Math.max(1, 100 * p)}%`;
  $("barra").style.background = j.alerta ? "var(--alerta)" : "var(--ok)";
  $("marcaUmbral").style.left = `${100 * j.umbral}%`;
  $("textoUmbral").textContent = `umbral ${j.umbral.toFixed(2)}`;

  $("acuerdo").textContent = `${j.acuerdo.redes_en_alerta} de ${j.acuerdo.redes_total}`;
  $("lesion").textContent = j.lesion.detectada ? `sí · ${j.lesion.area_porcentaje} % de la imagen` : "no (se analizó la imagen completa)";
  $("tiempo").textContent = `${(j.tiempos_ms.total / 1000).toFixed(2)} s`;

  const real = j.etiqueta_real;
  $("filaReal").hidden = !real;
  if (real) {
    const coincide = real.endometrioma === j.alerta;
    $("real").textContent = `${real.endometrioma ? "endometrioma" : real.clase.replaceAll("_", " ")} ${coincide ? "✓ coincide" : "✗ no coincide"}`;
    $("real").style.color = coincide ? "var(--ok)" : "var(--alerta)";
  }

  $("imgContorno").src = j.imagenes.contorno;
  $("imgRecorte").src = j.imagenes.recorte;
  $("figAtencion").hidden = !j.imagenes.atencion;
  if (j.imagenes.atencion) $("imgAtencion").src = j.imagenes.atencion;
  $("resultado").hidden = false;
}

revisarSalud();
cargarEjemplos();
