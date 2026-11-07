/* FinPerú — lógica del panel.
   Solo usa las rutas documentadas en web/README.md. Sin librerías ni compilación.
   Organización: utilidades → estado → secciones (empresa, ejercicio, Kd, construir, resultados, historial, registro). */
"use strict";

// ------------------------------------------------------------------ utilidades
const $ = (sel, raiz = document) => raiz.querySelector(sel);
const $$ = (sel, raiz = document) => [...raiz.querySelectorAll(sel)];
const pct = (x, d = 2) => (x == null ? "—" : (x * 100).toFixed(d) + " %");
const miles = (x) => (x == null ? "—" : Math.round(x).toLocaleString("es-PE"));
const esc = (t) => String(t ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

async function api(ruta, opciones = {}) {
  const r = await fetch(ruta, { headers: { "Content-Type": "application/json" }, ...opciones });
  const cuerpo = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(cuerpo.detail || `Error ${r.status}`);
  return cuerpo;
}

// ------------------------------------------------------------------ estado
const estado = { empresa: null, vista: null, trabajo: null, carpeta: null, totalPasos: 10, kdPdf: null };

// ------------------------------------------------------------------ sistema
async function cargarEstado() {
  try {
    const e = await api("/api/estado");
    $("#estado-sistema").textContent = e.excel_vivo ? `v${e.version} · Excel en vivo disponible` : `v${e.version} · Solo modo rápido`;
    if (!e.excel_vivo) {
      $("#ver-excel").checked = false; $("#ver-excel").disabled = true;
    }
  } catch { $("#estado-sistema").textContent = "Sin conexión con el motor"; }
}

// ------------------------------------------------------------------ 1. empresa (combobox accesible)
const entrada = $("#buscar-empresa"), lista = $("#lista-empresas");
let resultados = [], activo = -1, temporizador;

entrada.addEventListener("input", () => {
  clearTimeout(temporizador);
  temporizador = setTimeout(buscar, 250);
});
entrada.addEventListener("keydown", (ev) => {
  if (lista.hidden) return;
  if (ev.key === "ArrowDown") { ev.preventDefault(); marcar(Math.min(activo + 1, resultados.length - 1)); }
  else if (ev.key === "ArrowUp") { ev.preventDefault(); marcar(Math.max(activo - 1, 0)); }
  else if (ev.key === "Enter" && activo >= 0) { ev.preventDefault(); elegir(resultados[activo]); }
  else if (ev.key === "Escape") cerrarLista();
});
document.addEventListener("click", (ev) => { if (!ev.target.closest(".combo")) cerrarLista(); });

async function buscar() {
  const q = entrada.value.trim();
  if (q.length < 2) return cerrarLista();
  try { resultados = await api(`/api/empresas?q=${encodeURIComponent(q)}`); }
  catch (e) { resultados = []; }
  lista.innerHTML = resultados.map((e, i) =>
    `<li id="op-${i}" role="option" aria-selected="false" data-i="${i}">${esc(e.nombre)}
       <small>RPJ ${esc(e.rpj)} · RUC ${esc(e.ruc)} · ${esc(e.sector || e.tipo_empresa)} · datos ${esc(e.primer_periodo)}–${esc(e.ultimo_periodo)}</small></li>`).join("")
    || `<li role="option" aria-disabled="true">Sin resultados</li>`;
  lista.hidden = false; entrada.setAttribute("aria-expanded", "true"); activo = -1;
  $$("li[data-i]", lista).forEach((li) => li.addEventListener("click", () => elegir(resultados[+li.dataset.i])));
}
function marcar(i) {
  activo = i;
  $$("li", lista).forEach((li, k) => li.setAttribute("aria-selected", String(k === i)));
  entrada.setAttribute("aria-activedescendant", `op-${i}`);
  $(`#op-${i}`)?.scrollIntoView({ block: "nearest" });
}
function cerrarLista() { lista.hidden = true; entrada.setAttribute("aria-expanded", "false"); entrada.removeAttribute("aria-activedescendant"); }

function elegir(e) {
  estado.empresa = e; cerrarLista(); entrada.value = e.nombre;
  const caja = $("#empresa-elegida");
  caja.hidden = false;
  caja.innerHTML = `<strong>${esc(e.nombre)}</strong><br><span class="ayuda">RPJ ${esc(e.rpj)} · RUC ${esc(e.ruc)} ·
    CIIU ${esc(e.ciiu || "—")} · ${esc(e.tipo_empresa)}</span>`;
  // años disponibles (anuales) según el último periodo publicado
  const ultimo = parseInt((e.ultimo_periodo || "").slice(0, 4), 10) || new Date().getFullYear() - 1;
  const conAnual = (e.ultimo_periodo || "").endsWith("-A") || (e.ultimo_periodo || "").includes("T4") ? ultimo : ultimo - 1;
  const primero = Math.max(parseInt((e.primer_periodo || "2010").slice(0, 4), 10), 2005);
  $("#anio").innerHTML = Array.from({ length: conAnual - primero + 1 }, (_, k) => conAnual - k)
    .map((a) => `<option>${a}</option>`).join("");
  if (e.industria_sugerida) $("#industria").value = e.industria_sugerida;
  $("#vista-previa").innerHTML = "";
}

// ------------------------------------------------------------------ 2. industrias y vista previa
async function cargarIndustrias() {
  try {
    const ind = await api("/api/industrias");
    $("#lista-industrias").innerHTML = ind.map((i) => `<option value="${esc(i)}">`).join("");
  } catch { /* la lista es solo de ayuda */ }
}

$("#btn-vista-previa").addEventListener("click", async () => {
  if (!estado.empresa) return mostrarError("Primero elige una empresa.");
  const caja = $("#vista-previa");
  caja.textContent = "Consultando la SMV…";
  try {
    const v = await api(`/api/vista_previa?rpj=${estado.empresa.rpj}&anio=${$("#anio").value}`);
    estado.vista = v;
    const c = v.conceptos, c0 = v.conceptos_anterior, a = +$("#anio").value;
    const filas = [["Activo total", "activo_total"], ["Pasivo total", "pasivo_total"], ["Patrimonio", "patrimonio_total"],
      ["Otros pasivos financieros CP", "otros_pasivos_financieros_cp"], ["Otros pasivos financieros LP", "otros_pasivos_financieros_lp"],
      ["Ingresos", "ingresos"], ["Utilidad operativa", "utilidad_operativa"], ["Utilidad neta", "utilidad_neta"]];
    caja.innerHTML = `
      <p class="insignia ${v.cuadra ? "ok" : "mal"}">${v.cuadra ? "✔ El balance cuadra" : "✖ El balance NO cuadra"} ·
        Estados ${v.tipo_estados === "C" ? "consolidados" : "individuales"} · miles de S/</p>
      <div class="tabla-desplazable"><table class="tabla"><caption class="sr-only">Cifras clave</caption>
      <thead><tr><th scope="col">Concepto</th><th scope="col" class="num">${a}</th><th scope="col" class="num">${a - 1}</th></tr></thead>
      <tbody>${filas.map(([t, k]) => `<tr><th scope="row">${t}</th><td class="num">${miles(c[k])}</td><td class="num">${miles(c0[k])}</td></tr>`).join("")}
      <tr><th scope="row">Deuda financiera (D)</th><td class="num"><strong>${miles(v.deuda_financiera)}</strong></td><td class="num">${miles(v.deuda_financiera_anterior)}</td></tr>
      </tbody></table></div>`;
    actualizarCuadreKd();
  } catch (e) { caja.innerHTML = `<p class="mal aviso">${esc(e.message)}</p>`; }
});

// ------------------------------------------------------------------ 3. Kd
$$('input[name="kd-modo"]').forEach((r) => r.addEventListener("change", () => {
  const m = $('input[name="kd-modo"]:checked').value;
  $("#kd-tabla").hidden = m !== "tabla"; $("#kd-unico").hidden = m !== "unico";  // "pdf" y "aprox" no requieren datos
  if (m === "tabla" && !$("#kd-filas").children.length) agregarFilaKd();
}));
$("#btn-kd-agregar").addEventListener("click", () => agregarFilaKd(true));
$("#kd-filas").addEventListener("input", actualizarCuadreKd);
$("#kd-filas").addEventListener("click", (ev) => {
  if (ev.target.matches("[data-quitar]")) { ev.target.closest("tr").remove(); actualizarCuadreKd(); }
});
function agregarFilaKd(enfocar = false) {
  const fila = $("#tpl-fila-kd").content.firstElementChild.cloneNode(true);
  $("#kd-filas").appendChild(fila);
  if (enfocar) $("input", fila).focus();
}
function leerKd() {
  return $$("#kd-filas tr").map((tr) => {
    const g = (k) => $(`[data-k="${k}"]`, tr).value;
    return { tipo: g("tipo"), entidad: g("entidad"), moneda: g("moneda") || "S/",
      tasa_min: parseFloat(g("tasa_min")) / 100, tasa_max: g("tasa_max") === "" ? null : parseFloat(g("tasa_max")) / 100,
      corriente: parseFloat(g("corriente")) || 0, no_corriente: parseFloat(g("no_corriente")) || 0,
      nota: tr.dataset.nota || "" };
  }).filter((l) => !Number.isNaN(l.tasa_min));
}
function actualizarCuadreKd() {
  const total = leerKd().reduce((s, l) => s + l.corriente + l.no_corriente, 0);
  const d = estado.vista?.deuda_financiera;
  $("#kd-cuadre").textContent = d == null ? `Total de la tabla: ${miles(total)}`
    : `Total de la tabla: ${miles(total)} · Deuda en el ESF: ${miles(d)} · ${Math.abs(total - d) <= 1 ? "✔ cuadra" : "✖ no cuadra"}`;
}

// Kd desde el PDF auditado (SMV o subido)
function llenarTablaKd(lineas) {
  $("#kd-filas").innerHTML = "";
  lineas.forEach((l) => {
    agregarFilaKd();
    const tr = $("#kd-filas").lastElementChild;
    const p = (x) => (x == null ? "" : +(x * 100).toFixed(4));
    $('[data-k="tipo"]', tr).value = [...$('[data-k="tipo"]', tr).options].some((o) => o.text === l.tipo) ? l.tipo : "OTROS";
    $('[data-k="entidad"]', tr).value = l.entidad; $('[data-k="tasa_min"]', tr).value = p(l.tasa_min);
    $('[data-k="tasa_max"]', tr).value = p(l.tasa_max); $('[data-k="moneda"]', tr).value = l.moneda || "S/";
    $('[data-k="corriente"]', tr).value = l.corriente; $('[data-k="no_corriente"]', tr).value = l.no_corriente;
    tr.dataset.nota = l.nota || "";
    if (/NO REVELADA/.test(l.nota || "")) { tr.classList.add("fila-revisar"); tr.title = l.nota; }
  });
  actualizarCuadreKd();
}
function mostrarResultadoPdf(r) {
  estado.kdPdf = r.kd_pdf;
  if (r.deuda_esf != null) estado.vista = { ...(estado.vista || {}), deuda_financiera: r.deuda_esf };
  llenarTablaKd(r.lineas || []);
  const kd = r.kd_estimado != null ? ` · Kd estimado ${pct(r.kd_estimado)}` : "";
  $("#kd-pdf-resultado").innerHTML = (r.encontrada
    ? `<p class="insignia ${r.cuadra ? "ok" : "mal"}">${r.cuadra ? "✔" : "✖"} Nota leída (pág. ${r.pagina}): ${r.lineas.length} líneas,
       total ${miles(r.total_extraido)} vs deuda del balance ${miles(r.deuda_esf)}${kd}</p>`
    : `<p class="insignia mal">✖ No encontré la nota de deuda en el PDF.</p>`)
    + (r.avisos || []).map((a) => `<p class="aviso">⚠ ${esc(a)}</p>`).join("")
    + `<p class="ayuda">Revisa la tabla: las filas en naranja tienen datos que no vienen del PDF.</p>`;
}
$("#btn-kd-pdf").addEventListener("click", async () => {
  if (!estado.empresa) return mostrarError("Primero elige una empresa (paso 1).");
  const b = $("#btn-kd-pdf"); b.disabled = true; b.textContent = "Buscando en la SMV…";
  $("#kd-pdf-resultado").textContent = "Abriendo el portal de la SMV y leyendo el PDF…";
  try {
    mostrarResultadoPdf(await api("/api/kd_pdf", { method: "POST",
      body: JSON.stringify({ rpj: estado.empresa.rpj, anio: +$("#anio").value, visible: $("#kd-pdf-visible").checked }) }));
  } catch (e) { $("#kd-pdf-resultado").innerHTML = `<p class="insignia mal">${esc(e.message)}</p>`; }
  finally { b.disabled = false; b.textContent = "Leer la nota desde la SMV"; }
});
$("#kd-pdf-archivo").addEventListener("change", async (ev) => {
  const f = ev.target.files[0];
  if (!f || !estado.empresa) return mostrarError("Elige primero la empresa y el año.");
  const fd = new FormData(); fd.append("rpj", estado.empresa.rpj); fd.append("anio", $("#anio").value); fd.append("archivo", f);
  $("#kd-pdf-resultado").textContent = "Leyendo el PDF…";
  try {
    const r = await fetch("/api/kd_pdf_subir", { method: "POST", body: fd });
    const cuerpo = await r.json();
    if (!r.ok) throw new Error(cuerpo.detail || "Error");
    mostrarResultadoPdf(cuerpo);
  } catch (e) { $("#kd-pdf-resultado").innerHTML = `<p class="insignia mal">${esc(e.message)}</p>`; }
});

// ------------------------------------------------------------------ 4/5. construir
const PRESETS = { todo: [1, 1, 1], excel: [0, 1, 0], descargas: [1, 0, 0], calculos: [0, 0, 1], nada: [0, 0, 0] };
$$("[data-preset]").forEach((b) => b.addEventListener("click", () => {
  const [n, x, c] = PRESETS[b.dataset.preset];
  $("#ver-navegador").checked = !!n; if (!$("#ver-excel").disabled) $("#ver-excel").checked = !!x; $("#ver-calculos").checked = !!c;
  if (b.dataset.preset === "nada") { $("#velocidad").value = 0; $("#velocidad-valor").textContent = "0×"; }
}));
$("#velocidad").addEventListener("input", (e) => { $("#velocidad-valor").textContent = e.target.value + "×"; });

function mostrarError(m) { $("#error-form").textContent = m; }

$("#form-modelo").addEventListener("submit", async (ev) => {
  ev.preventDefault(); mostrarError("");
  if (!estado.empresa) return mostrarError("Elige una empresa (paso 1).");
  const industria = $("#industria").value.trim();
  if (!industria) return mostrarError("Indica la industria comparable (paso 2).");
  const kdModo = $('input[name="kd-modo"]:checked').value;
  const pedido = {
    rpj: estado.empresa.rpj, anio: +$("#anio").value, industria,
    modo: $("#ver-excel").checked ? "vivo" : "archivo", velocidad: +$("#velocidad").value,
    ver_navegador: $("#ver-navegador").checked, ver_calculos: $("#ver-calculos").checked, kd_modo: kdModo,
    parametros: { tasa_impuesto: +$("#p-tasa").value / 100, damodaran_vintage: $("#p-vintage").value,
      beta_columna: $("#p-columna").value, prima_promedio: $("#p-prima").value, region_beta: $("#p-region").value },
  };
  if (kdModo === "tabla") {
    pedido.kd_tabla = leerKd();
    if (!pedido.kd_tabla.length) return mostrarError("La tabla de Kd está vacía.");
    if (estado.kdPdf) pedido.kd_pdf = estado.kdPdf;
  } else if (kdModo === "unico") {
    const v = parseFloat($("#kd-valor").value);
    if (Number.isNaN(v)) return mostrarError("Escribe el Kd en %.");
    pedido.kd = v / 100;
  }
  const sob = {};
  $$("[data-sob]").forEach((i) => { if (i.value !== "") sob[i.dataset.sob] = i.dataset.pct === "no" ? +i.value : +i.value / 100; });
  if (Object.keys(sob).length) pedido.sobrescribir = sob;

  $("#btn-generar").disabled = true; $("#btn-generar").textContent = "Construyendo…";
  $("#registro").innerHTML = ""; progreso(0, "Iniciando…");
  try {
    const { id } = await api("/api/generar", { method: "POST", body: JSON.stringify(pedido) });
    estado.trabajo = id; esperar(id);
  } catch (e) { mostrarError(e.message); restaurarBoton(); }
});

function restaurarBoton() { $("#btn-generar").disabled = false; $("#btn-generar").textContent = "Generar modelo"; }

async function esperar(id) {
  const t = await api(`/api/trabajos/${id}`);
  if (t.estado === "trabajando") return setTimeout(() => esperar(id), 1000);
  restaurarBoton();
  if (t.estado === "error") { mostrarError("No se pudo generar: " + t.error); progreso(0, "Error"); return; }
  progreso(estado.totalPasos, "Listo");
  mostrarResultados(t.resultado);
  cargarHistorial();
}

// ------------------------------------------------------------------ resultados
function mostrarResultados(r) {
  estado.carpeta = r.carpeta.split(/[\\/]/).pop();
  const x = r.resultados;
  const kpis = [["WACC", pct(x.wacc)], ["Ke", pct(x.ke)], ["Kd", pct(x.kd)], ["ROIC", pct(x.roic)],
    ["EVA (miles S/)", miles(x.eva)], ["Beta apalancada", x.beta_l.toFixed(4)]];
  $("#kpis").innerHTML = kpis.map(([a, b]) => `<div class="kpi"><p class="kpi__etiqueta">${a}</p><p class="kpi__valor">${b}</p></div>`).join("");
  $("#controles").innerHTML = r.controles.map((c) =>
    `<li class="${c.ok ? "ok" : "mal"}">${c.ok ? "✔" : "✖"} ${esc(c.control)} <span class="ayuda">(${esc(c.detalle)})</span></li>`).join("");
  $("#avisos").innerHTML = (r.avisos || []).map((a) => `<p class="aviso">⚠ ${esc(a)}</p>`).join("");
  $("#btn-descargar").href = `/api/modelos/${encodeURIComponent(estado.carpeta)}/excel`;
  const sec = $("#resultados"); sec.hidden = false; sec.focus(); sec.scrollIntoView({ behavior: "smooth" });
}
$("#btn-abrir-excel").addEventListener("click", () => abrir("excel"));
$("#btn-abrir-carpeta").addEventListener("click", () => abrir("carpeta"));
async function abrir(que, carpeta = estado.carpeta) {
  try { await api(`/api/modelos/${encodeURIComponent(carpeta)}/abrir?que=${que}`, { method: "POST" }); }
  catch (e) { mostrarError(e.message); }
}

// ------------------------------------------------------------------ historial
async function cargarHistorial() {
  try {
    const h = await api("/api/historial");
    $("#historial").innerHTML = h.map((m) => `<tr><td>${esc(m.empresa)}</td><td>${m.anio}</td><td class="num">${pct(m.wacc)}</td>
      <td class="num">${miles(m.eva)}</td><td>${m.controles_ok ? '<span class="ok">✔ OK</span>' : '<span class="mal">✖ Revisar</span>'}</td>
      <td>${esc((m.generado || "").replace("T", " ").slice(0, 16))}</td>
      <td><button type="button" class="boton boton--icono" data-abrir="${esc(m.carpeta)}" aria-label="Abrir Excel de ${esc(m.empresa)} ${m.anio}">Abrir</button></td></tr>`).join("")
      || `<tr><td colspan="7">Aún no hay modelos.</td></tr>`;
    $$("[data-abrir]").forEach((b) => b.addEventListener("click", () => abrir("excel", b.dataset.abrir)));
  } catch { /* opcional */ }
}

// ------------------------------------------------------------------ registro en vivo (SSE)
function progreso(n, texto) {
  $("#paso-actual").textContent = texto;
  $(".barra").setAttribute("aria-valuenow", n);
  $("#barra-relleno").style.width = `${(n / estado.totalPasos) * 100}%`;
}
function conectarEventos() {
  const fuente = new EventSource("/api/eventos");
  fuente.onmessage = (m) => {
    const ev = JSON.parse(m.data);
    const li = document.createElement("li");
    li.className = `ev-${ev.tipo}`;
    li.innerHTML = `<time>${esc(ev.t.slice(11, 19))}</time>${esc(ev.msg)}`;
    const ol = $("#registro"); ol.appendChild(li);
    while (ol.children.length > 400) ol.firstChild.remove();
    ol.scrollTop = ol.scrollHeight;
    const p = /Paso (\d+)\/(\d+)/.exec(ev.msg);
    if (p) { estado.totalPasos = +p[2]; progreso(+p[1], ev.msg); }
  };
  fuente.onerror = () => { /* el navegador reintenta solo */ };
}

// ------------------------------------------------------------------ actualizaciones
async function revisarActualizacion() {
  try {
    const a = await api("/api/actualizacion");
    if (!a.hay_actualizacion) return;
    $("#texto-actualizacion").textContent = `Hay una versión nueva de FinPerú: ${a.ultima} (tienes ${a.actual}).`;
    $("#aviso-actualizacion").hidden = false;
  } catch { /* sin internet: se ignora */ }
}
$("#btn-actualizar").addEventListener("click", async () => {
  const b = $("#btn-actualizar"); b.disabled = true; b.textContent = "Actualizando…";
  try {
    const r = await api("/api/actualizar", { method: "POST" });
    $("#texto-actualizacion").textContent = r.mensaje + " Cierra esta ventana y vuelve a abrir FinPerú.";
    b.hidden = true;
  } catch (e) { $("#texto-actualizacion").textContent = e.message; b.disabled = false; b.textContent = "Reintentar"; }
});

// ------------------------------------------------------------------ inicio
cargarEstado(); cargarIndustrias(); cargarHistorial(); conectarEventos(); revisarActualizacion();
