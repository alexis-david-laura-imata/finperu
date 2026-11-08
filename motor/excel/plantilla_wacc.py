"""Plantilla P1 — Costo de capital (CPPC/WACC) + ROIC + EVA. Formato estándar FinPerú.

Hojas (siempre las mismas, en este orden):
  Portada · Parametros · EEFF · Kd · Mercado · CPPC · EVA · Controles · Fuentes · Registro

Reglas de auditoría que cumple:
- Todo dato de entrada está en una celda de entrada (azul) con comentario de procedencia y enlace a su fuente.
- Todo cálculo es una fórmula de Excel que usa nombres definidos (=Tasa_Rf+Beta_L*Prima_Mercado).
- Ningún número escrito dentro de una fórmula (salvo constantes de unidad: 1, 10000, 100).
- Hoja Controles compara el cálculo de Excel con el cálculo independiente en Python.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from .. import __version__
from ..datos.red import Dato
from ..eventos import desuscribir, emitir, suscribir
from ..metodologia import Insumos, kd_desde_tabla
from .lienzo import AZUL_OSCURO, Lienzo

COLOR = {"portada": AZUL_OSCURO, "datos": (0, 112, 192), "calculo": (112, 48, 160),
         "control": (0, 176, 80), "aux": (128, 128, 128)}


class Fuentes:
    """Numera las fuentes y arma la hoja Fuentes."""
    def __init__(self):
        self.filas: list[dict] = []
        self._por_clave: dict[tuple, int] = {}

    def id(self, nombre: str, d: Dato) -> str:
        clave = (nombre, d.fuente.url) if nombre == "Estados financieros SMV" else (nombre, d.fuente.url, d.detalle)
        if clave not in self._por_clave:
            self.filas.append({"dato": nombre, "valor": d.valor, "detalle": d.detalle, "origen": d.fuente.origen,
                               "url": d.fuente.url, "fecha": d.fuente.descargado, "sha": d.fuente.sha256,
                               "archivo": d.fuente.archivo, "nota": d.fuente.nota})
            self._por_clave[clave] = len(self.filas)
        return f"F{self._por_clave[clave]}"


def _url_corta(u: str) -> str:
    u = u.replace("https://", "").replace("http://", "")
    return (u[:60] + "…") if len(u) > 61 else u


def construir(L: Lienzo, ins: Insumos, r: dict[str, Any]) -> dict:
    """Escribe el modelo completo en el lienzo. Devuelve el mapa de nombres -> celdas."""
    registro: list[dict] = []
    oyente = registro.append
    suscribir(oyente)
    F = Fuentes()
    d = ins.datos
    emp, N = ins.empresa, ins.anio
    nombre_emp = emp.get("nombre", emp.get("rpj"))

    def dato(hoja, fila, etiqueta, clave, nombre, formato, nota="", estilo=None, valor=None):
        """Fila estándar Parámetro | Valor | Fuente | Nota."""
        dd: Dato = d[clave] if clave else None
        fid = F.id(etiqueta, dd) if dd else ""
        est = estilo or ("usuario" if dd and dd.fuente.origen == "usuario" else "dato")
        L.escribir(hoja, f"B{fila}", etiqueta, "etiqueta")
        L.escribir(hoja, f"C{fila}", dd.valor if valor is None else valor, est, formato, nombre,
                   comentario=f"[{fid}] {dd.comentario()}" if dd else None)
        if dd and dd.fuente.url.startswith("http"):
            L.enlace(hoja, f"D{fila}", dd.fuente.url, f"[{fid}] {dd.fuente.origen.upper()} · {_url_corta(dd.fuente.url)}")
        elif dd:
            L.escribir(hoja, f"D{fila}", f"[{fid}] {dd.fuente.origen} · {dd.detalle[:70]}", "nota")
        if nota:
            L.escribir(hoja, f"E{fila}", nota, "nota")

    def formula(hoja, fila, etiqueta, f, nombre, formato, nota="", estilo=None):
        L.escribir(hoja, f"B{fila}", etiqueta, "etiqueta")
        L.escribir(hoja, f"C{fila}", f, estilo, formato, nombre)
        L.escribir(hoja, f"D{fila}", f[1:] if f.startswith("=") else "", "nota")
        if nota:
            L.escribir(hoja, f"E{fila}", nota, "nota")

    def encabezado(hoja, titulo, subtitulo, color):
        L.nueva_hoja(hoja, color)
        for col, w in (("A", 3), ("B", 56), ("C", 18), ("D", 58), ("E", 60)):
            L.ancho(hoja, col, w)
        L.escribir(hoja, "B2", titulo, "titulo", pausa=0.3)
        L.escribir(hoja, "B3", subtitulo, "nota")

    def cabecera(hoja, fila, cols=("Parámetro", "Valor", "Fuente / fórmula", "Nota")):
        for col, t in zip("BCDE", cols):
            L.escribir(hoja, f"{col}{fila}", t, "cabecera", pausa=0.03)

    # ------------------------------------------------------------ 1. PORTADA (encabezado)
    L.paso("Paso 1/10 · Portada")
    encabezado("Portada", f"Costo de capital (WACC) y EVA — {nombre_emp}",
               f"Ejercicio {N} · Miles de S/ · Metodología Administración Financiera II (UNSAAC)", COLOR["portada"])

    # ------------------------------------------------------------ 2. PARAMETROS
    L.paso("Paso 2/10 · Parámetros y supuestos")
    h = "Parametros"
    encabezado(h, "Parámetros del modelo", "Decisiones metodológicas. Cambiarlas cambia el resultado: quedan registradas.",
               COLOR["datos"])
    cabecera(h, 5, ("Parámetro", "Valor", "Opciones", "Explicación"))
    p = ins.parametros
    filas_par = [
        ("Tasa de impuesto a la renta", p["tasa_impuesto"], "pct", "Tasa_IR", "29.5% / 30%",
         "Perú: 29.5%. Algunas prácticas usan 30% por indicación del docente."),
        ("Tipo de estados financieros", "Consolidado" if p.get("estados_tipo_usado") == "C" else "Individual (separado)",
         None, None, "Consolidado / Individual", "Se prefiere consolidado; si la empresa no lo presenta, se usa individual."),
        ("Año del archivo de betas Damodaran", p["damodaran_vintage"], None, None,
         "cierre_siguiente / disponible_al_cierre",
         "cierre_siguiente: se usan las betas CON DATOS DEL AÑO EVALUADO (archivo betaemergAA, que Damodaran publica en enero del año siguiente)."),
        ("Columna de beta", p["beta_columna"], None, None, "Unlevered beta / ...corrected for cash",
         "Los modelos del curso usan 'Unlevered beta'."),
        ("Promedio de la prima de mercado", p["prima_promedio"], None, None, "aritmetico / geometrico",
         "Los Excel del curso usan aritmético (el PPT 9 menciona geométrico)."),
        ("Región de betas", p["region_beta"], None, None, "emerg / us / global", "Mercados emergentes, como en el curso."),
        ("Industria Damodaran", ins.industria, None, "Industria", "Lista de Damodaran", "Sector comparable de la empresa."),
    ]
    for i, (et, v, fmt, nom, opc, expl) in enumerate(filas_par, start=6):
        L.escribir(h, f"B{i}", et, "etiqueta")
        L.escribir(h, f"C{i}", v, "usuario", fmt, nom, comentario="Parámetro metodológico elegido para este modelo.")
        L.escribir(h, f"D{i}", opc, "nota")
        L.escribir(h, f"E{i}", expl, "nota")

    # ------------------------------------------------------------ 3. EEFF
    L.paso("Paso 3/10 · Estados financieros (SMV)")
    h = "EEFF"
    L.nueva_hoja(h, COLOR["datos"])
    for col, w in (("A", 3), ("B", 10), ("C", 62), ("D", 16), ("E", 16)):
        L.ancho(h, col, w)
    L.escribir(h, "B2", f"Estados financieros — {nombre_emp}", "titulo")
    smv_dato: Dato = d["patrimonio_total"]
    fid_smv = F.id("Estados financieros SMV", smv_dato)
    L.escribir(h, "B3", f"[{fid_smv}] Fuente: SMV, servicio de datos abiertos (RPJ {emp.get('rpj')}). "
                        f"Miles de S/. Copia tal cual de lo presentado por la empresa.", "nota")
    for col, t in zip("BCDE", ("Cuenta SMV", "Descripción", str(N), str(N - 1))):
        L.escribir(h, f"{col}5", t, "cabecera", pausa=0.03)
    df = ins.estados
    fila = 6
    celdas_cuenta: dict[str, int] = {}
    for estado, titulo in (("BG", "ESTADO DE SITUACIÓN FINANCIERA"), ("ER", "ESTADO DE RESULTADOS")):
        L.escribir(h, f"B{fila}", titulo, "subtitulo")
        fila += 1
        ini = fila
        totales = []
        sub = df[df["estado"] == estado]
        for row in sub.itertuples():
            m, mc = row.monto, row.monto_comparativo
            vacio = lambda x: x is None or x != x or x == 0  # noqa: E731
            if vacio(m) and vacio(mc):
                continue
            L.fila(h, f"B{fila}", [str(row.cuenta), str(row.descripcion),
                                   None if m != m else float(m), None if mc != mc else float(mc)], pausa=0.03)
            if str(row.cuenta).endswith(("ST", "0T")):
                totales.append(fila)
            celdas_cuenta[str(row.cuenta)] = fila
            fila += 1
        if fila > ini:
            L.estilo_rango(h, f"B{ini}:B{fila - 1}", "nota")
            L.estilo_rango(h, f"C{ini}:C{fila - 1}", "etiqueta")
            L.estilo_rango(h, f"D{ini}:E{fila - 1}", "dato", "num")
            for t in totales:
                L.estilo_rango(h, f"C{t}", "etiqueta_b")
        fila += 1

    from ..datos.smv import cuentas_concepto
    ctas = {c: cuentas_concepto(df, c) for c in ("otros_pasivos_financieros_cp", "otros_pasivos_financieros_lp",
                                                  "patrimonio_total", "activo_total", "pasivo_total",
                                                  "utilidad_operativa")}

    def nombrar(concepto, nombre, col="D"):
        """Nombre de rango = suma de las celdas de las cuentas del concepto (0 si la empresa no tiene esa cuenta)."""
        celdas = [f"'EEFF'!${col}${celdas_cuenta[c]}" for c in ctas[concepto] if c in celdas_cuenta]
        if not celdas and concepto not in ("otros_pasivos_financieros_cp", "otros_pasivos_financieros_lp"):
            raise LookupError(f"No encontré en los EEFF de la SMV la cuenta de {concepto} ({nombre})")
        ref = "=" + ("+".join(celdas) if celdas else "0")
        L._nombre(nombre, ref)
        L.nombres[nombre] = ref

    for conc, nom in (("otros_pasivos_financieros_cp", "Deuda_CP"), ("otros_pasivos_financieros_lp", "Deuda_LP"),
                      ("patrimonio_total", "Patrimonio"), ("activo_total", "Activo_Total"),
                      ("pasivo_total", "Pasivo_Total"), ("utilidad_operativa", "Utilidad_Operativa")):
        nombrar(conc, nom)
    for conc, nom in (("otros_pasivos_financieros_cp", "Deuda_CP_Ant"), ("otros_pasivos_financieros_lp", "Deuda_LP_Ant"),
                      ("patrimonio_total", "Patrimonio_Ant")):
        nombrar(conc, nom, "E")
    montos = df.drop_duplicates("cuenta").set_index("cuenta")["monto"]
    for clave in ("otros_pasivos_financieros_cp", "otros_pasivos_financieros_lp", "patrimonio_total",
                  "utilidad_operativa"):
        dd = d[clave]
        fid = F.id("Estados financieros SMV", dd) if dd.fuente is not smv_dato.fuente else fid_smv
        for cta in ctas[clave]:
            if cta in celdas_cuenta:
                L.escribir(h, f"D{celdas_cuenta[cta]}", float(montos[cta]), "dato", "num",
                           comentario=f"[{fid}] Cuenta usada en el modelo. {dd.comentario()}", pausa=0.3)

    # ------------------------------------------------------------ 4. Kd
    L.paso("Paso 4/10 · Costo de la deuda (Kd)")
    h = "Kd"
    L.nueva_hoja(h, COLOR["datos"])
    for col, w in zip("ABCDEFGHIJKL", (3, 40, 34, 11, 11, 12, 12, 13, 13, 13, 12, 13)):
        L.ancho(h, col, w)
    L.escribir(h, "B2", "Costo de la deuda (Kd)", "titulo")
    if ins.kd_tabla:
        L.escribir(h, "B3", "Nota 'Otros pasivos financieros' de los EEFF auditados (PDF). Tasa = promedio si es rango; "
                            "peso = saldo / total del tipo; Kd = promedio ponderado entre tipos.", "nota")
        cols = ("Tipo", "Entidad", "Tasa mín.", "Tasa máx.", "Tasa usada", "Moneda", "Corriente", "No corriente",
                "Total", "Peso en tipo", "Ponderada")
        for col, t in zip("BCDEFGHIJKL", cols):
            L.escribir(h, f"{col}5", t, "cabecera", pausa=0.03)
        i0 = 6
        n = len(ins.kd_tabla)
        i1 = i0 + n - 1
        for k, l in enumerate(ins.kd_tabla):
            i = i0 + k
            com = f"Dato de la nota de deuda, revisado por el usuario. {l.nota}".strip()
            L.escribir(h, f"B{i}", l.tipo.upper(), "etiqueta")
            L.escribir(h, f"C{i}", l.entidad, "etiqueta")
            L.escribir(h, f"D{i}", l.tasa_min, "usuario", "pct", comentario=com)
            L.escribir(h, f"E{i}", l.tasa_max, "usuario", "pct")
            L.escribir(h, f"F{i}", f'=IF(E{i}="",D{i},(D{i}+E{i})/2)', None, "pct")
            L.escribir(h, f"G{i}", l.moneda, "etiqueta")
            L.escribir(h, f"H{i}", l.corriente, "usuario", "num")
            L.escribir(h, f"I{i}", l.no_corriente, "usuario", "num")
            L.escribir(h, f"J{i}", f"=H{i}+I{i}", None, "num")
            L.escribir(h, f"K{i}", f"=IF(SUMIF($B${i0}:$B${i1},B{i},$J${i0}:$J${i1})=0,0,"
                                   f"J{i}/SUMIF($B${i0}:$B${i1},B{i},$J${i0}:$J${i1}))", None, "pct")
            L.escribir(h, f"L{i}", f"=F{i}*K{i}", None, "pct4")
        res = kd_desde_tabla(ins.kd_tabla)["resumen"]
        f0 = i1 + 3
        L.escribir(h, f"B{f0 - 1}", "RESUMEN POR TIPO", "subtitulo")
        for col, t in zip("BCDE", ("Tipo", "Tasa del tipo", "Total", "Peso")):
            L.escribir(h, f"{col}{f0}", t, "cabecera", pausa=0.03)
        g0 = f0 + 1
        g1 = g0 + len(res) - 1
        for k, g in enumerate(res):
            i = g0 + k
            L.escribir(h, f"B{i}", g["tipo"], "etiqueta")
            L.escribir(h, f"C{i}", f"=SUMIF($B${i0}:$B${i1},B{i},$L${i0}:$L${i1})", None, "pct")
            L.escribir(h, f"D{i}", f"=SUMIF($B${i0}:$B${i1},B{i},$J${i0}:$J${i1})", None, "num")
            L.escribir(h, f"E{i}", f"=D{i}/SUM($D${g0}:$D${g1})", None, "pct")
        L.escribir(h, f"B{g1 + 2}", "Kd (costo de la deuda antes de impuestos)", "etiqueta_b")
        L.escribir(h, f"C{g1 + 2}", f"=SUMPRODUCT(C{g0}:C{g1},E{g0}:E{g1})", "resultado", "pct", "Kd_Prom",
                   pausa=0.5)
        L.escribir(h, f"B{g1 + 3}", "Total deuda según la nota", "etiqueta")
        L.escribir(h, f"C{g1 + 3}", f"=SUM(D{g0}:D{g1})", None, "num", "Deuda_Nota")
    else:
        dato(h, 5, "Kd (costo de la deuda antes de impuestos)", "kd", "Kd_Prom", "pct",
             nota=d["kd"].detalle)
        L.escribir(h, "B7", "Total deuda según la nota", "etiqueta")
        L.escribir(h, "C7", "=Deuda_CP+Deuda_LP", None, "num", "Deuda_Nota")
        L.escribir(h, "D7", "Sin tabla de la nota: se toma la deuda del ESF.", "nota")

    # ------------------------------------------------------------ 5. MERCADO
    L.paso("Paso 5/10 · Datos de mercado (Tesoro, Damodaran, BCRP)")
    h = "Mercado"
    encabezado(h, "Datos de mercado", "Cada dato con su fuente. Pasa el mouse sobre el valor para ver el detalle.",
               COLOR["datos"])
    cabecera(h, 5)
    dato(h, 6, "Tasa libre de riesgo (Rf) — Bono Tesoro EE.UU. 10 años", "rf", "Tasa_Rf", "pct",
         "Último día hábil del año del ejercicio.")
    prima = d["prima"]
    if "rm" in prima.extra:
        L.escribir(h, "B7", "Rendimiento promedio S&P 500 (Rm)", "etiqueta")
        L.escribir(h, "C7", prima.extra["rm"], "dato", "pct4", "Rm_Hist",
                   comentario=f"[{F.id('Prima de mercado', prima)}] {prima.comentario()}")
        L.enlace(h, "D7", prima.fuente.url, f"[{F.id('Prima de mercado', prima)}] DAMODARAN · histretSP")
        L.escribir(h, "E7", f"Promedio {ins.parametros['prima_promedio']} 1928–{N}", "nota")
        L.escribir(h, "B8", "Rendimiento promedio T-Bond 10 años (Rf histórica)", "etiqueta")
        L.escribir(h, "C8", prima.extra["rf_hist"], "dato", "pct4", "Rf_Hist")
        L.escribir(h, "D8", "Misma fuente", "nota")
        formula(h, 9, "Prima de riesgo de mercado (Rm − Rf)", "=Rm_Hist-Rf_Hist", "Prima_Mercado", "pct4")
    else:
        dato(h, 9, "Prima de riesgo de mercado (Rm − Rf)", "prima", "Prima_Mercado", "pct4")
    rp = d["riesgo_pais"]
    if "pbs" in rp.extra:
        L.escribir(h, "B10", "Riesgo país Perú — EMBIG (puntos básicos)", "etiqueta")
        L.escribir(h, "C10", rp.extra["pbs"], "dato", "num2", "RP_Pbs",
                   comentario=f"[{F.id('Riesgo país', rp)}] {rp.comentario()}")
        L.enlace(h, "D10", rp.fuente.url, f"[{F.id('Riesgo país', rp)}] BCRP · PN01129XM")
        L.escribir(h, "E10", "Valor de diciembre del año del ejercicio (promedio mensual).", "nota")
        formula(h, 11, "Riesgo país (%)", "=RP_Pbs/10000", "Riesgo_Pais", "pct")
    else:
        dato(h, 11, "Riesgo país (%)", "riesgo_pais", "Riesgo_Pais", "pct")
    dato(h, 12, f"Beta desapalancada — {ins.industria}", "beta_u", "Beta_U", "dec4",
         d["beta_u"].extra.get("fecha_archivo", "") and f"Archivo del {d['beta_u'].extra.get('fecha_archivo')}")
    dato(h, 13, "Inflación Perú (dic/dic)", "inflacion_pe", "Infl_Peru", "pct")
    dato(h, 14, "Inflación EE.UU.", "inflacion_us", "Infl_EEUU", "pct")
    formula(h, 15, "Tasa de impuesto a la renta", "=Tasa_IR", None, "pct", "Viene de la hoja Parametros")
    banco = bool(r.get("banco"))
    if banco:
        dato(h, 16, f"Beta APALANCADA de la industria — {ins.industria}", "beta_l_industria", "Beta_Ind", "dec4",
             "Bancos: se usa la beta apalancada de la industria (Damodaran, columna 'Beta') sin desapalancar ni "
             "re-apalancar: el D/E de Damodaran para bancos no es comparable con los adeudos del banco.")

    # ------------------------------------------------------------ 6. CPPC
    L.paso("Paso 6/10 · Estructura de capital, beta, Ke y WACC")
    h = "CPPC"
    encabezado(h, "Costo promedio ponderado de capital (CPPC / WACC)",
               "Todas son fórmulas. La columna D muestra la fórmula en texto para leerla sin hacer clic.", COLOR["calculo"])
    cabecera(h, 5, ("Concepto", "Valor", "Fórmula", "Nota"))
    nota_d = ("Adeudos y obligaciones financieras (cuentas " + " + ".join(ctas["otros_pasivos_financieros_cp"] +
              ctas["otros_pasivos_financieros_lp"]) + "). Los depósitos del público son pasivo operativo del banco."
              if banco else "Cuentas " + " + ".join(ctas["otros_pasivos_financieros_cp"] + ctas["otros_pasivos_financieros_lp"])
              + " del ESF (incluye arrendamientos financieros si la empresa los presenta en ese rubro).")
    filas = [
        ("Deuda financiera (D) = otros pasivos financieros CP + LP", "=Deuda_CP+Deuda_LP", "Deuda_Fin", "num", nota_d),
        ("Patrimonio (E)", "=Patrimonio", None, "num", "Total patrimonio (valor contable)."),
        ("Total financiamiento (D + E)", "=Deuda_Fin+Patrimonio", "Total_DE", "num", ""),
        ("Peso de la deuda (Wd)", "=Deuda_Fin/Total_DE", "Peso_Deuda", "pct", ""),
        ("Peso del patrimonio (We)", "=Patrimonio/Total_DE", "Peso_Patrim", "pct", ""),
        ("Relación deuda / patrimonio (D/E)", "=Deuda_Fin/Patrimonio", "Ratio_DE", "dec4", ""),
        (("Beta apalancada (βL) — industria bancaria", "=Beta_Ind", "Beta_L", "dec4",
          "Bancos: beta apalancada de la industria, sin Hamada (ver hoja Mercado).") if banco else
         ("Beta apalancada (βL) — Hamada", "=Beta_U*(1+Ratio_DE*(1-Tasa_IR))", "Beta_L", "dec4",
          "βL = βU × [1 + D/E × (1 − t)]")),
        ("Ke en dólares (CAPM)", "=Tasa_Rf+Beta_L*Prima_Mercado", "Ke_USD", "pct", "Ke = Rf + βL × (Rm − Rf)"),
        ("Ke en soles (Fisher)", "=(1+Ke_USD)*(1+Infl_Peru)/(1+Infl_EEUU)-1", "Ke_Soles", "pct",
         "(1 + Ke$) × (1 + πPE) / (1 + πUS) − 1"),
        ("Costo del patrimonio (Ke) = Ke soles + riesgo país", "=Ke_Soles+Riesgo_Pais", "Ke_Final", "pct",
         "El riesgo país se suma después de Fisher."),
        ("Costo de la deuda (Kd)", "=Kd_Prom", None, "pct", "Viene de la hoja Kd"),
        ("Kd después de impuestos", "=Kd_Prom*(1-Tasa_IR)", "Kd_Neto", "pct", "Escudo fiscal"),
    ]
    for k, (et, f, nom, fmt, nota) in enumerate(filas, start=6):
        formula(h, k, et, f, nom, fmt, nota, estilo="vinculo" if f in ("=Patrimonio", "=Kd_Prom") else None)
    fw = 6 + len(filas) + 1
    L.escribir(h, f"B{fw}", "WACC", "subtitulo")
    L.escribir(h, f"C{fw}", "=Kd_Neto*Peso_Deuda+Ke_Final*Peso_Patrim", "resultado", "pct", "WACC", pausa=0.8)
    L.escribir(h, f"D{fw}", "Kd × (1 − t) × Wd + Ke × We", "nota")

    # ------------------------------------------------------------ 7. EVA
    L.paso("Paso 7/10 · ROIC y EVA")
    h = "EVA"
    encabezado(h, "ROIC y valor económico agregado (EVA)", "¿La empresa rinde más de lo que le cuesta su capital?",
               COLOR["calculo"])
    cabecera(h, 5, ("Concepto", "Valor", "Fórmula", "Nota"))
    if banco:
        di = d.get("intereses_deuda")
        L.escribir(h, "G6", "Intereses de adeudos (2F0404)", "etiqueta")
        L.escribir(h, "H6", di.valor if di else 0, "dato", "num", "Int_Deuda",
                   comentario=di.comentario() if di else "No disponible: el ROIC queda subestimado.")
        L.ancho(h, "G", 34)
        L.ancho(h, "H", 16)
        fila_uo = [("Utilidad operativa", "=Utilidad_Operativa", None, "num",
                    "EEFF, cuenta " + "+".join(ctas["utilidad_operativa"]) + " (ya neta de intereses de adeudos)"),
                   ("NOPAT = (UO + intereses de adeudos) × (1 − t)", "=(Utilidad_Operativa+Int_Deuda)*(1-Tasa_IR)",
                    "NOPAT", "num", "Se suman los intereses de la deuda D porque su costo ya está en el WACC.")]
    else:
        fila_uo = [("Utilidad operativa", "=Utilidad_Operativa", None, "num",
                    "EEFF, cuenta " + "+".join(ctas["utilidad_operativa"])),
                   ("NOPAT = UO × (1 − t)", "=Utilidad_Operativa*(1-Tasa_IR)", "NOPAT", "num", "")]
    filas = [
        *fila_uo,
        (f"Capital invertido {N} (D + E)", "=Deuda_Fin+Patrimonio", "CI_Actual", "num", ""),
        (f"Capital invertido {N - 1} (D + E)", "=Deuda_CP_Ant+Deuda_LP_Ant+Patrimonio_Ant", "CI_Anterior", "num",
         "Columna del año anterior en EEFF"),
        ("Capital invertido promedio", "=(CI_Actual+CI_Anterior)/2", "CI_Prom", "num", ""),
        ("ROIC = NOPAT / CI promedio", "=NOPAT/CI_Prom", "ROIC", "pct", ""),
        ("WACC", "=WACC", None, "pct", "Viene de la hoja CPPC"),
        ("Diferencial (ROIC − WACC)", "=ROIC-WACC", "Spread", "pct", "Positivo = crea valor"),
    ]
    for k, (et, f, nom, fmt, nota) in enumerate(filas, start=6):
        formula(h, k, et, f, nom, fmt, nota, estilo="vinculo" if f in ("=Utilidad_Operativa", "=WACC") else None)
    fe = 6 + len(filas) + 1
    L.escribir(h, f"B{fe}", "EVA (miles de S/)", "subtitulo")
    L.escribir(h, f"C{fe}", "=(ROIC-WACC)*CI_Prom", "resultado", "num", "Valor_EVA", pausa=0.8)
    L.escribir(h, f"D{fe}", "(ROIC − WACC) × capital invertido promedio", "nota")
    L.escribir(h, f"B{fe + 1}", "Conclusión", "etiqueta_b")
    L.escribir(h, f"C{fe + 1}", '=IF(Valor_EVA>0,"CREA VALOR","DESTRUYE VALOR")', "formula_b")
    if banco:
        fb = fe + 3
        L.escribir(h, f"B{fb}", "Enfoque del accionista (recomendado para bancos)", "subtitulo")
        un, un0 = d["utilidad_neta"], d.get("utilidad_neta_ant")
        L.escribir(h, f"B{fb + 1}", "Utilidad neta del ejercicio", "etiqueta")
        L.escribir(h, f"C{fb + 1}", un.valor, "dato", "num", "Utilidad_Neta", comentario=un.comentario())
        filas_b = [
            ("Patrimonio promedio", "=(Patrimonio+Patrimonio_Ant)/2", "Patrim_Prom", "num", ""),
            ("ROE = utilidad neta / patrimonio promedio", "=Utilidad_Neta/Patrim_Prom", "ROE", "pct", ""),
            ("Costo del patrimonio (Ke)", "=Ke_Final", None, "pct", "Viene de la hoja CPPC"),
            ("EVA del accionista = (ROE − Ke) × patrimonio promedio", "=(ROE-Ke_Final)*Patrim_Prom",
             "EVA_Accionista", "num", "Damodaran: a los bancos se les mide contra el costo del patrimonio."),
        ]
        for k, (et, f, nom, fmt, nota) in enumerate(filas_b, start=fb + 2):
            formula(h, k, et, f, nom, fmt, nota)

    # ------------------------------------------------------------ 8. CONTROLES
    L.paso("Paso 8/10 · Controles de auditoría")
    h = "Controles"
    encabezado(h, "Controles de auditoría", "Excel calcula; Python calcula por separado; ambos deben coincidir.",
               COLOR["control"])
    for col, w in (("C", 16), ("D", 16), ("E", 12), ("F", 12), ("G", 48)):
        L.ancho(h, col, w)
    for col, t in zip("BCDEFG", ("Control", "Valor Excel", "Referencia", "Diferencia", "Estado", "Explicación")):
        L.escribir(h, f"{col}5", t, "cabecera", pausa=0.03)
    controles = [
        ("Activo = Pasivo + Patrimonio", "=Activo_Total", "=Pasivo_Total+Patrimonio", 1, "num",
         "El balance de la SMV cuadra."),
        ("Peso deuda + peso patrimonio = 100%", "=Peso_Deuda+Peso_Patrim", 1, 1e-9, "pct", ""),
        ("Deuda de la nota (Kd) = deuda del ESF", "=Deuda_Nota", "=Deuda_Fin", 1, "num",
         "La tabla de bancos suma lo mismo que 'otros pasivos financieros'."),
        ("WACC Excel = WACC Python", "=WACC", r["wacc"], 1e-9, "pct4", "Doble cálculo independiente."),
        ("Ke Excel = Ke Python", "=Ke_Final", r["ke"], 1e-9, "pct4", ""),
        ("ROIC Excel = ROIC Python", "=ROIC", r["roic"], 1e-9, "pct4", ""),
        ("EVA Excel = EVA Python", "=Valor_EVA", r["eva"], 0.01, "num2", ""),
        ("Beta apalancada ≥ desapalancada", "=Beta_L", "=Beta_U", None, "dec4", "Con deuda, el riesgo sube."),
        *([("ROE Excel = ROE Python", "=ROE", r["roe"], 1e-9, "pct4", "Enfoque del accionista (bancos).")]
          if "roe" in r else []),
        ("Ke > Kd después de impuestos", "=Ke_Final", "=Kd_Neto", None, "pct", "El accionista exige más que el banco."),
    ]
    c0 = 6
    for k, (et, a, b, tol, fmt, expl) in enumerate(controles):
        i = c0 + k
        L.escribir(h, f"B{i}", et, "etiqueta")
        L.escribir(h, f"C{i}", a, None, fmt)
        es_python = isinstance(b, float) and not isinstance(b, bool) and "Python" in et
        L.escribir(h, f"D{i}", b, "dato" if es_python else None, fmt,
                   comentario="Calculado por el motor en Python, de forma independiente a Excel." if es_python else None)
        if "Deuda de la nota" in et and not ins.kd_tabla:
            L.escribir(h, f"E{i}", "", None)
            L.escribir(h, f"F{i}", "N/A", "formula_b")
            L.escribir(h, f"G{i}", "No aplica: el Kd no viene de la tabla de la nota (ver avisos).", "nota")
            continue
        if tol is None:
            L.escribir(h, f"E{i}", f"=C{i}-D{i}", None, fmt)
            L.escribir(h, f"F{i}", f'=IF(C{i}>=D{i},"OK","REVISAR")', "formula_b")
        else:
            L.escribir(h, f"E{i}", f"=C{i}-D{i}", None, fmt)
            L.escribir(h, f"F{i}", f'=IF(ABS(E{i})<={tol},"OK","REVISAR")', "formula_b")
        L.escribir(h, f"G{i}", expl, "nota")
    c1 = c0 + len(controles) - 1
    L.formato_condicional_ok(h, f"F{c0}:F{c1}")
    L.escribir(h, f"B{c1 + 2}", "ESTADO GENERAL", "subtitulo")
    L.escribir(h, f"C{c1 + 2}", f'=IF(COUNTIF(F{c0}:F{c1},"REVISAR")=0,"OK","REVISAR")', "resultado", None,
               "Estado_Controles", pausa=0.8)
    L.formato_condicional_ok(h, f"C{c1 + 2}")
    if ins.avisos:
        L.escribir(h, f"B{c1 + 4}", "Avisos del motor", "subtitulo")
        for k, a in enumerate(ins.avisos):
            L.escribir(h, f"B{c1 + 5 + k}", f"• {a}", "nota")

    # ------------------------------------------------------------ 9. FUENTES
    L.paso("Paso 9/10 · Registro de fuentes")
    h = "Fuentes"
    L.nueva_hoja(h, COLOR["aux"])
    for col, w in zip("ABCDEFGHI", (3, 6, 34, 14, 12, 50, 20, 20, 60)):
        L.ancho(h, col, w)
    L.escribir(h, "B2", "Fuentes de datos", "titulo")
    L.escribir(h, "B3", "Cada dato de entrada del modelo apunta a una fila de esta tabla. El SHA-256 identifica el "
                        "archivo exacto descargado; está guardado en la carpeta 'evidencias'.", "nota")
    for col, t in zip("BCDEFGHI", ("ID", "Dato", "Valor", "Origen", "URL", "Descargado", "SHA-256", "Detalle")):
        L.escribir(h, f"{col}5", t, "cabecera", pausa=0.02)
    n_f = len(F.filas)
    for k, fr in enumerate(F.filas):
        i = 6 + k
        v = fr["valor"] if isinstance(fr["valor"], (int, float)) else str(fr["valor"])
        L.fila(h, f"B{i}", [f"F{k + 1}", fr["dato"], v, fr["origen"], "", fr["fecha"][:16].replace("T", " "),
                            fr["sha"][:16], fr["detalle"]], pausa=0.1)
        if str(fr["url"]).startswith("http"):
            L.enlace(h, f"F{i}", fr["url"], _url_corta(fr["url"]))
        else:
            L.fila(h, f"F{i}", [fr["url"]], pausa=0)
    if n_f:
        L.estilo_rango(h, f"B6:B{5 + n_f}", "etiqueta_b")
        L.estilo_rango(h, f"D6:D{5 + n_f}", "dato", "#,##0.0000")
        L.estilo_rango(h, f"H6:I{5 + n_f}", "nota")

    # ------------------------------------------------------------ 10. PORTADA (completar) + REGISTRO
    L.paso("Paso 10/10 · Resumen en la portada")
    h = "Portada"
    L.activar(h)
    info = [("Empresa", nombre_emp), ("RPJ (SMV) / RUC", f"{emp.get('rpj')} / {emp.get('ruc', '')}"),
            ("Ejercicio", str(N)),
            ("Estados financieros", "Consolidados" if ins.parametros.get("estados_tipo_usado") == "C"
             else "Individuales (separados)"),
            ("Industria comparable (Damodaran)", ins.industria),
            ("Generado", datetime.now().strftime("%d/%m/%Y %H:%M")), ("Herramienta", f"FinPerú MCP v{__version__}")]
    for k, (a, b) in enumerate(info, start=5):
        L.escribir(h, f"B{k}", a, "etiqueta_b")
        L.escribir(h, f"C{k}", b, "texto")
    L.escribir(h, "B13", "RESULTADOS", "subtitulo")
    res = [("Costo del patrimonio (Ke)", "=Ke_Final", "pct"), ("Costo de la deuda después de impuestos", "=Kd_Neto", "pct"),
           ("WACC", "=WACC", "pct"), ("ROIC", "=ROIC", "pct"), ("EVA (miles de S/)", "=Valor_EVA", "num"),
           ("Estado de los controles", "=Estado_Controles", None)]
    for k, (a, f, fmt) in enumerate(res, start=14):
        L.escribir(h, f"B{k}", a, "etiqueta")
        L.escribir(h, f"C{k}", f, "resultado", fmt, pausa=0.4)
    L.formato_condicional_ok(h, "C19")
    L.escribir(h, "B21", "CÓMO AUDITAR ESTE MODELO", "subtitulo")
    pasos = ["1. Celdas azules = datos de entrada. Pasa el mouse: el comentario dice de dónde salen.",
             "2. Celdas naranjas = supuestos o datos confirmados por el usuario (parámetros, tabla de Kd).",
             "3. Celdas negras/verdes = fórmulas. Usan nombres (Formulas > Administrador de nombres).",
             "4. Hoja Fuentes: URL, fecha y SHA-256 de cada archivo; los originales están en /evidencias.",
             "5. Hoja Controles: todo en verde = el modelo cuadra y Excel coincide con el cálculo en Python.",
             "6. receta.json (junto a este archivo) permite regenerar el modelo idéntico."]
    for k, t in enumerate(pasos, start=22):
        L.escribir(h, f"B{k}", t, "texto", pausa=0.1)

    # Registro (eventos de esta construcción)
    h = "Registro"
    L.nueva_hoja(h, COLOR["aux"])
    for col, w in zip("BCD", (22, 14, 110)):
        L.ancho(h, col, w)
    L.escribir(h, "B2", "Registro de la construcción", "titulo", pausa=0)
    for col, t in zip("BCD", ("Hora", "Tipo", "Mensaje")):
        L.escribir(h, f"{col}4", t, "cabecera", pausa=0)
    evs = registro[-300:]
    for k, ev in enumerate(evs, start=5):
        L.fila(h, f"B{k}", [ev["t"][:19].replace("T", " "), ev["tipo"], ev["msg"]], pausa=0)
    if evs:
        L.estilo_rango(h, f"B5:D{4 + len(evs)}", "nota")
    desuscribir(oyente)
    L.activar("Portada")
    emitir("excel_ok", "Modelo construido")
    return {"nombres": dict(L.nombres), "fuentes": F.filas}
