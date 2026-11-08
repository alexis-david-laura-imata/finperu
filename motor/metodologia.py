"""Metodología CPPC/WACC + EVA del curso Administración Financiera II (UNSAAC).

Reglas en _analisis/metodologia_curso.yaml. Validado contra:
  Laive 2023 (práctica final): Ke 11.0887%, WACC 9.0667%, ROIC 11.2153%, EVA 7,061.95
  Laive 2021 (modelo docente): WACC 9.1122%

Uso:
    datos = recolectar("CI0011", 2023, "Food Processing", kd=tabla_kd)
    res = calcular(datos)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import config
from .datos import bcrp, damodaran, smv, tesoro
from .datos.red import Dato, Fuente
from .eventos import emitir


# ---------------------------------------------------------------- costo de la deuda
@dataclass
class LineaDeuda:
    tipo: str                 # "SOBREGIROS" | "ARRENDAMIENTO FINANCIERO" | "PRESTAMOS BANCARIOS" | otro
    entidad: str
    tasa_min: float           # en decimal (0.0525)
    tasa_max: float | None    # si es rango; None si es una sola tasa
    corriente: float
    no_corriente: float
    moneda: str = "S/"
    nota: str = ""

    @property
    def tasa(self) -> float:
        return self.tasa_min if self.tasa_max is None else (self.tasa_min + self.tasa_max) / 2

    @property
    def total(self) -> float:
        return (self.corriente or 0) + (self.no_corriente or 0)


def kd_desde_tabla(lineas: list[LineaDeuda]) -> dict[str, Any]:
    """Kd del curso: promedio ponderado por saldo dentro de cada tipo y luego entre tipos."""
    grupos: dict[str, list[LineaDeuda]] = {}
    for l in lineas:
        grupos.setdefault(l.tipo.upper(), []).append(l)
    resumen = []
    total_general = sum(l.total for l in lineas)
    for tipo, ls in grupos.items():
        tot = sum(l.total for l in ls)
        if tot == 0:
            continue
        tasa_g = sum(l.tasa * l.total / tot for l in ls)
        resumen.append({"tipo": tipo, "tasa": tasa_g, "total": tot, "peso": tot / total_general})
    kd = sum(g["tasa"] * g["peso"] for g in resumen)
    return {"kd": kd, "resumen": resumen, "total_deuda_nota": total_general}


# ---------------------------------------------------------------- recolección
@dataclass
class Insumos:
    empresa: dict
    anio: int
    industria: str
    parametros: dict
    datos: dict[str, Dato] = field(default_factory=dict)
    kd_tabla: list[LineaDeuda] | None = None
    estados: Any = None          # DataFrame SMV del año
    estados_ant: Any = None      # DataFrame SMV del año anterior (para promedio de capital)
    avisos: list[str] = field(default_factory=list)


def _manual(valor: float, detalle: str) -> Dato:
    return Dato(valor, Fuente(url="(ingresado por el usuario)", archivo="", sha256="-",
                              descargado="", origen="usuario"), detalle=detalle)


def recolectar(rpj: str, anio: int, industria: str, *, kd: float | list[LineaDeuda] | None = None,
               parametros: dict | None = None, sobrescribir: dict[str, float] | None = None,
               locales: dict[str, Path] | None = None, via_smv: str = "auto",
               kd_pdf: dict | None = None) -> Insumos:
    """Junta todos los insumos con su fuente. `sobrescribir` permite fijar valores dados
    por el docente (p.ej. {'inflacion_pe': 0.0341}); quedan marcados como 'usuario'."""
    p = {**config.PARAMETROS_DEFECTO, **(parametros or {})}
    sob = sobrescribir or {}
    loc = locales or {}
    emp = next((e for e in smv.buscar_empresa(rpj) if e["rpj"] == rpj), {"rpj": rpj, "nombre": rpj})
    ins = Insumos(empresa=emp, anio=anio, industria=industria, parametros=p)
    emitir("inicio", f"Recolectando insumos: {emp.get('nombre')} ({rpj}) {anio}, industria {industria}")

    # 1) Estados financieros SMV (año N y N-1 vienen en el mismo archivo como comparativo)
    df, f_smv, tipo_usado = smv.estados(rpj, anio, "A", p["estados_tipo"], via=via_smv)
    ins.estados, p["estados_tipo_usado"] = df, tipo_usado
    if tipo_usado != p["estados_tipo"]:
        ins.avisos.append(f"Se usaron estados {'individuales' if tipo_usado == 'I' else tipo_usado} "
                          f"(no hay consolidados para {anio}).")
    plan = smv.plan_de_cuentas(df)
    p["plan_cuentas"] = plan
    if plan == "F":
        ins.avisos.append("Empresa del sistema financiero (plan de cuentas F de la SMV): la deuda financiera (D) son los "
                          "adeudos y obligaciones financieras; los depósitos del público se tratan como pasivo operativo. "
                          "Para bancos el WACC/EVA es referencial: Damodaran recomienda valorarlos con el costo del "
                          "patrimonio (Ke).")
    elif plan != "D":
        ins.avisos.append(f"La empresa usa el plan de cuentas {plan} de la SMV ({smv.NOMBRE_PLAN.get(plan, 'especial')}); "
                          "las cuentas del modelo se tomaron de su equivalente en ese plan. Revisa la hoja EEFF.")
    if not (smv.cuentas_concepto(df, "otros_pasivos_financieros_cp") or
            smv.cuentas_concepto(df, "otros_pasivos_financieros_lp")):
        ins.avisos.append("No encontré cuentas de deuda financiera en los EEFF de la SMV: se toma D = 0 (empresa sin deuda).")
    for c in ("otros_pasivos_financieros_cp", "otros_pasivos_financieros_lp", "patrimonio_total",
              "utilidad_operativa", "activo_total", "pasivo_total", "ingresos", "utilidad_neta"):
        ins.datos[c] = smv.dato_concepto(df, f_smv, c, rpj, anio)
        ins.datos[c + "_ant"] = smv.dato_concepto(df, f_smv, c, rpj, anio, comparativo=True)

    # 2) Mercado
    ins.datos["rf"] = (_manual(sob["rf"], "Rf ingresado") if "rf" in sob
                       else tesoro.rf_10y(anio, loc.get("tesoro")))
    ins.datos["riesgo_pais"] = (_manual(sob["riesgo_pais"], "Riesgo país ingresado") if "riesgo_pais" in sob
                                else bcrp.riesgo_pais(anio))
    ins.datos["prima"] = (_manual(sob["prima"], "Prima ingresada") if "prima" in sob
                          else damodaran.prima_mercado(anio, p["prima_promedio"], local=loc.get("histretSP")))
    ins.datos["beta_u"] = (_manual(sob["beta_u"], f"Beta desapalancada ingresada ({industria})") if "beta_u" in sob
                           else damodaran.beta_desapalancada(industria, anio, p["region_beta"], p["damodaran_vintage"],
                                                             p["beta_columna"], local=loc.get("betas")))
    if plan == "F":
        # Bancos: la beta se toma APALANCADA de la industria (Damodaran, columna 'Beta'), sin Hamada,
        # porque el D/E de Damodaran para bancos no es comparable con los adeudos del banco.
        ins.datos["beta_l_industria"] = (
            _manual(sob["beta_l_industria"], f"Beta apalancada ingresada ({industria})") if "beta_l_industria" in sob
            else damodaran.beta_desapalancada(industria, anio, p["region_beta"], p["damodaran_vintage"], "Beta",
                                              local=loc.get("betas")))
        ins.datos["utilidad_neta_ant"] = smv.dato_concepto(df, f_smv, "utilidad_neta", rpj, anio, comparativo=True)
        try:
            df_i = df if tipo_usado == "I" else smv.estados(rpj, anio, "A", "I", via=via_smv)[0]
            fi = df_i.attrs.get("fuente_por_estado", {}).get("ER", f_smv)
            v_int = abs(smv.conceptos(df_i)["intereses_deuda"] or 0)
            if v_int:
                ins.datos["intereses_deuda"] = Dato(v_int, fi, detalle=(
                    f"SMV RPJ {rpj}, ejercicio {anio}, cuenta 2F0404 (EEFF individuales): intereses de adeudos y "
                    "obligaciones financieras. Se suman a la utilidad operativa para el ROIC (su costo ya está en el WACC)."))
        except Exception as e:  # noqa: BLE001
            emitir("aviso", f"No pude leer los intereses de adeudos del banco ({e})")
        if "intereses_deuda" not in ins.datos:
            ins.avisos.append("No se encontraron los intereses de adeudos (2F0404): el ROIC del banco usa la utilidad "
                              "operativa tal cual (ya neta de esos intereses), por lo que queda subestimado.")
    ins.datos["inflacion_pe"] = (_manual(sob["inflacion_pe"], "Inflación Perú (dato del docente)")
                                 if "inflacion_pe" in sob else bcrp.inflacion_peru(anio))
    ins.datos["inflacion_us"] = (_manual(sob["inflacion_us"], "Inflación EE.UU. (dato del docente)")
                                 if "inflacion_us" in sob else damodaran.inflacion_eeuu(anio, loc.get("histretSP")))
    ins.datos["tasa_impuesto"] = _manual(p["tasa_impuesto"], "Tasa de impuesto a la renta (parámetro)")

    # 3) Costo de la deuda
    if isinstance(kd, list):
        ins.kd_tabla = kd
        k = kd_desde_tabla(kd)
        ins.datos["kd"] = _manual(k["kd"], "Kd ponderado de la nota 'Otros pasivos financieros' (tabla revisada)")
        if kd_pdf and kd_pdf.get("archivo") and Path(kd_pdf["archivo"]).exists():
            from .datos.red import fuente_local
            f_pdf = fuente_local(Path(kd_pdf["archivo"]), "smv", url=kd_pdf.get("url"),
                                 nota=kd_pdf.get("nota", "EEFF auditados (PDF)"))
            ins.datos["kd"] = Dato(k["kd"], f_pdf, detalle=f"Kd ponderado de la nota de deuda del PDF auditado "
                                   f"(pág. {kd_pdf.get('pagina', '?')}), tabla revisada por el usuario")
        d_modelo = ins.datos["otros_pasivos_financieros_cp"].valor + ins.datos["otros_pasivos_financieros_lp"].valor
        if abs(k["total_deuda_nota"] - d_modelo) > 1:
            ins.avisos.append(f"La tabla de Kd suma {k['total_deuda_nota']:,.0f} pero la deuda del ESF es "
                              f"{d_modelo:,.0f}: revisar la nota.")
    elif kd is not None:
        ins.datos["kd"] = _manual(float(kd), "Kd ingresado")
    else:
        c1, c0 = smv.conceptos(df), smv.conceptos(df, True)
        aprox, que, f_er = None, "", df.attrs.get("fuente_por_estado", {}).get("ER", f_smv)
        if plan == "F":   # bancos: intereses de adeudos (solo en el individual) / adeudos promedio
            try:
                df_i = df if tipo_usado == "I" else smv.estados(rpj, anio, "A", "I", via=via_smv)[0]
                i1, i0 = smv.conceptos(df_i), smv.conceptos(df_i, True)
                deuda = lambda c: (c["otros_pasivos_financieros_cp"] or 0) + (c["otros_pasivos_financieros_lp"] or 0)  # noqa: E731
                intereses = abs(i1.get("intereses_deuda") or 0)
                if intereses and deuda(i1) + deuda(i0):
                    aprox = intereses / ((deuda(i1) + deuda(i0)) / 2)
                    que = ("intereses de adeudos y obligaciones financieras (cuenta 2F0404 de los EEFF individuales) / "
                           "adeudos y obligaciones promedio")
                    f_er = df_i.attrs.get("fuente_por_estado", {}).get("ER", f_er)
            except Exception as e:  # noqa: BLE001
                emitir("aviso", f"No pude leer los EEFF individuales para el Kd del banco ({e})")
        if aprox is None:
            gf = abs(c1["gastos_financieros"] or 0)
            d0, d1 = c0["pasivos_con_costo"] or 0, c1["pasivos_con_costo"] or 0
            aprox = gf / ((d0 + d1) / 2) if d0 + d1 else 0.0
            que = ("gastos por intereses / pasivos con costo promedio (depósitos, interbancarios y adeudos: "
                   "costo de fondeo del banco)" if plan == "F" else "gastos financieros / deuda financiera promedio")
        ins.datos["kd"] = Dato(aprox, f_er, detalle=f"APROXIMACIÓN: {que} (no es el método del curso; "
                                                    "reemplazar con la tabla de la nota)")
        ins.avisos.append(f"Kd aproximado = {que} = {aprox:.2%}. Para el método del curso, "
                          "cargar la tabla de la nota de deuda del PDF auditado.")
        if aprox <= 0:
            ins.avisos.append("La SMV no reporta gastos financieros o deuda para esta empresa: el Kd aproximado es 0. "
                              "Ingresa el Kd (tasa única o tabla) para un WACC válido.")
    emitir("insumos_ok", f"Insumos completos ({len(ins.datos)} datos con fuente)")
    return ins


# ---------------------------------------------------------------- cálculo
class DatosIncompletos(ValueError):
    """Faltan cifras indispensables para el modelo (mensaje pensado para el usuario)."""


REQUERIDOS = {
    "patrimonio_total": "total patrimonio", "patrimonio_total_ant": "total patrimonio del año anterior",
    "utilidad_operativa": "utilidad (resultado) operativa", "activo_total": "total activo",
    "pasivo_total": "total pasivo", "otros_pasivos_financieros_cp": "deuda financiera corriente",
    "otros_pasivos_financieros_lp": "deuda financiera no corriente",
    "otros_pasivos_financieros_cp_ant": "deuda financiera corriente del año anterior",
    "otros_pasivos_financieros_lp_ant": "deuda financiera no corriente del año anterior",
    "rf": "tasa libre de riesgo", "riesgo_pais": "riesgo país", "prima": "prima de mercado",
    "beta_u": "beta desapalancada", "inflacion_pe": "inflación Perú", "inflacion_us": "inflación EE.UU.",
    "tasa_impuesto": "tasa de impuesto", "kd": "costo de la deuda (Kd)",
}


def validar(ins: Insumos) -> None:
    faltan = [f"{nombre} ({k})" for k, nombre in REQUERIDOS.items()
              if ins.datos.get(k) is None or ins.datos[k].valor is None]
    if faltan:
        plan = ins.parametros.get("plan_cuentas", "?")
        raise DatosIncompletos(
            f"No se encontraron estas cifras para {ins.empresa.get('nombre', '')} {ins.anio} "
            f"(plan de cuentas SMV '{plan}'): " + ", ".join(faltan) +
            ". Revisa que la empresa haya presentado estados anuales ese año o ingrésalas manualmente.")
    if ins.parametros.get("plan_cuentas") == "F":
        for k, nombre in (("utilidad_neta", "utilidad neta"), ("beta_l_industria", "beta apalancada de la industria")):
            if ins.datos.get(k) is None or ins.datos[k].valor is None:
                raise DatosIncompletos(f"Falta {nombre} ({k}) para el modelo del banco.")
    v = ins.datos
    if (v["otros_pasivos_financieros_cp"].valor + v["otros_pasivos_financieros_lp"].valor
            + v["patrimonio_total"].valor) <= 0:
        raise DatosIncompletos("Deuda + patrimonio es cero o negativo: no se puede calcular la estructura de capital.")
    if v["patrimonio_total"].valor <= 0:
        raise DatosIncompletos("El patrimonio es negativo o cero: la relación D/E y el WACC no tienen sentido "
                               "económico para esta empresa en ese año.")


def calcular(ins: Insumos, mostrar: bool = False, velocidad: float = 1.0) -> dict[str, Any]:
    validar(ins)
    v = {k: d.valor for k, d in ins.datos.items()}
    t = v["tasa_impuesto"]
    D = v["otros_pasivos_financieros_cp"] + v["otros_pasivos_financieros_lp"]
    E = v["patrimonio_total"]
    D0 = v["otros_pasivos_financieros_cp_ant"] + v["otros_pasivos_financieros_lp_ant"]
    E0 = v["patrimonio_total_ant"]
    r: dict[str, Any] = {}
    r["D"], r["E"], r["D+E"] = D, E, D + E
    r["Wd"], r["We"] = D / (D + E), E / (D + E)
    r["D/E"] = D / E
    banco = ins.parametros.get("plan_cuentas") == "F" and v.get("beta_l_industria") is not None
    r["banco"] = banco
    r["beta_l"] = v["beta_l_industria"] if banco else v["beta_u"] * (1 + r["D/E"] * (1 - t))
    r["ke_usd"] = v["rf"] + r["beta_l"] * v["prima"]
    r["ke_soles"] = (1 + r["ke_usd"]) * (1 + v["inflacion_pe"]) / (1 + v["inflacion_us"]) - 1
    r["ke"] = r["ke_soles"] + v["riesgo_pais"]
    r["kd"] = v["kd"]
    r["kd_despues_impuestos"] = v["kd"] * (1 - t)
    r["wacc"] = v["kd"] * (1 - t) * r["Wd"] + r["ke"] * r["We"]
    r["intereses_deuda"] = v.get("intereses_deuda") or 0.0 if banco else 0.0
    r["nopat"] = (v["utilidad_operativa"] + r["intereses_deuda"]) * (1 - t)
    r["ci"], r["ci_ant"] = D + E, D0 + E0
    r["ci_promedio"] = (r["ci"] + r["ci_ant"]) / 2
    r["roic"] = r["nopat"] / r["ci_promedio"]
    r["eva"] = (r["roic"] - r["wacc"]) * r["ci_promedio"]
    if banco:                                     # enfoque del accionista (Damodaran: bancos se valoran con Ke)
        r["patrimonio_promedio"] = (E + E0) / 2
        r["roe"] = v["utilidad_neta"] / r["patrimonio_promedio"]
        r["eva_accionista"] = (r["roe"] - r["ke"]) * r["patrimonio_promedio"]

    # Controles
    ctrl = []
    def chk(nombre, ok, detalle):
        ctrl.append({"control": nombre, "ok": bool(ok), "detalle": detalle})
    at, pt, pa = v["activo_total"], v["pasivo_total"], E
    chk("Activo = Pasivo + Patrimonio", abs(at - pt - pa) <= 1, f"{at:,.0f} vs {pt + pa:,.0f}")
    chk("Wd + We = 1", abs(r["Wd"] + r["We"] - 1) < 1e-9, f"{r['Wd'] + r['We']:.6f}")
    chk("Beta apalancada ≥ desapalancada", r["beta_l"] >= v["beta_u"], f"{r['beta_l']:.4f} ≥ {v['beta_u']:.4f}")
    chk("Ke > Kd después de impuestos", r["ke"] > r["kd_despues_impuestos"],
        f"{r['ke']:.2%} > {r['kd_despues_impuestos']:.2%}")
    chk("Kd mayor que cero", r["kd"] > 0, f"{r['kd']:.2%}")
    chk("WACC entre Kd(1−t) y Ke", r["kd_despues_impuestos"] <= r["wacc"] <= r["ke"], f"{r['wacc']:.2%}")
    r["controles"] = ctrl
    r["avisos"] = ins.avisos
    if mostrar:
        mostrar_calculos(v, r, velocidad)
    estado = "OK" if all(c["ok"] for c in ctrl) else "REVISAR"
    emitir("resultado", f"WACC {r['wacc']:.2%} | Ke {r['ke']:.2%} | ROIC {r['roic']:.2%} | "
                        f"EVA {r['eva']:,.0f} | controles {estado}")
    return r


def mostrar_calculos(v: dict, r: dict, velocidad: float = 1.0) -> None:
    """Emite cada cálculo con su fórmula y los números reemplazados (modo 'ver cálculos en Python')."""
    import time
    t = v["tasa_impuesto"]
    pasos = [
        ("Deuda financiera D", "Deuda CP + Deuda LP",
         f"{v['otros_pasivos_financieros_cp']:,.0f} + {v['otros_pasivos_financieros_lp']:,.0f}", f"{r['D']:,.0f}"),
        ("Patrimonio E", "Total patrimonio", f"{r['E']:,.0f}", f"{r['E']:,.0f}"),
        ("Peso deuda Wd", "D / (D + E)", f"{r['D']:,.0f} / {r['D+E']:,.0f}", f"{r['Wd']:.4%}"),
        ("Peso patrimonio We", "E / (D + E)", f"{r['E']:,.0f} / {r['D+E']:,.0f}", f"{r['We']:.4%}"),
        (("Beta apalancada (banco)", "β apalancada de la industria (sin Hamada)", f"{r['beta_l']:.4f}",
          f"{r['beta_l']:.4f}") if r.get("banco") else
         ("Beta apalancada", "βU × [1 + D/E × (1 − t)]", f"{v['beta_u']:.4f} × [1 + {r['D/E']:.4f} × (1 − {t:.3f})]",
          f"{r['beta_l']:.4f}")),
        ("Ke en dólares (CAPM)", "Rf + βL × (Rm − Rf)", f"{v['rf']:.4%} + {r['beta_l']:.4f} × {v['prima']:.4%}",
         f"{r['ke_usd']:.4%}"),
        ("Ke en soles (Fisher)", "(1 + Ke$) × (1 + πPE) / (1 + πUS) − 1",
         f"(1 + {r['ke_usd']:.4%}) × (1 + {v['inflacion_pe']:.4%}) / (1 + {v['inflacion_us']:.4%}) − 1", f"{r['ke_soles']:.4%}"),
        ("Ke final", "Ke soles + riesgo país", f"{r['ke_soles']:.4%} + {v['riesgo_pais']:.4%}", f"{r['ke']:.4%}"),
        ("Kd después de impuestos", "Kd × (1 − t)", f"{r['kd']:.4%} × (1 − {t:.3f})", f"{r['kd_despues_impuestos']:.4%}"),
        ("WACC", "Kd(1−t) × Wd + Ke × We",
         f"{r['kd_despues_impuestos']:.4%} × {r['Wd']:.4%} + {r['ke']:.4%} × {r['We']:.4%}", f"{r['wacc']:.4%}"),
        (("NOPAT", "(UO + intereses de adeudos) × (1 − t)",
          f"({v['utilidad_operativa']:,.0f} + {r['intereses_deuda']:,.0f}) × (1 − {t:.3f})", f"{r['nopat']:,.0f}")
         if r.get("banco") else
         ("NOPAT", "UO × (1 − t)", f"{v['utilidad_operativa']:,.0f} × (1 − {t:.3f})", f"{r['nopat']:,.0f}")),
        ("Capital invertido promedio", "(CI actual + CI anterior) / 2", f"({r['ci']:,.0f} + {r['ci_ant']:,.0f}) / 2",
         f"{r['ci_promedio']:,.0f}"),
        ("ROIC", "NOPAT / CI promedio", f"{r['nopat']:,.0f} / {r['ci_promedio']:,.0f}", f"{r['roic']:.4%}"),
        ("EVA", "(ROIC − WACC) × CI promedio", f"({r['roic']:.4%} − {r['wacc']:.4%}) × {r['ci_promedio']:,.0f}",
         f"{r['eva']:,.0f}"),
    ]
    if r.get("banco"):
        pasos += [("ROE", "Utilidad neta / patrimonio promedio",
                   f"{v['utilidad_neta']:,.0f} / {r['patrimonio_promedio']:,.0f}", f"{r['roe']:.4%}"),
                  ("EVA del accionista", "(ROE − Ke) × patrimonio promedio",
                   f"({r['roe']:.4%} − {r['ke']:.4%}) × {r['patrimonio_promedio']:,.0f}", f"{r['eva_accionista']:,.0f}")]
    emitir("calculo_inicio", f"Cálculo en Python ({len(pasos)} pasos)")
    for i, (nombre, formula, sustitucion, resultado) in enumerate(pasos, 1):
        emitir("calculo", f"{i:>2}. {nombre} = {formula} = {sustitucion} = {resultado}",
               nombre=nombre, formula=formula, sustitucion=sustitucion, resultado=resultado)
        if velocidad > 0:
            time.sleep(0.6 * velocidad)
