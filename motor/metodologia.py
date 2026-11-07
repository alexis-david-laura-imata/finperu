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
        gf = abs(smv.conceptos(df)["gastos_financieros"] or 0)
        d0 = sum(smv.conceptos(df, True)[c] or 0 for c in ("otros_pasivos_financieros_cp", "otros_pasivos_financieros_lp"))
        d1 = sum(smv.conceptos(df)[c] or 0 for c in ("otros_pasivos_financieros_cp", "otros_pasivos_financieros_lp"))
        aprox = gf / ((d0 + d1) / 2) if d0 + d1 else 0
        ins.datos["kd"] = Dato(aprox, f_smv, detalle="APROXIMACIÓN: gastos financieros / deuda financiera promedio "
                                                     "(no es el método del curso; reemplazar con la tabla de la nota)")
        ins.avisos.append("Kd aproximado con gastos financieros / deuda promedio. Para el método del curso, "
                          "cargar la tabla de la nota 'Otros pasivos financieros'.")
    emitir("insumos_ok", f"Insumos completos ({len(ins.datos)} datos con fuente)")
    return ins


# ---------------------------------------------------------------- cálculo
def calcular(ins: Insumos, mostrar: bool = False, velocidad: float = 1.0) -> dict[str, Any]:
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
    r["beta_l"] = v["beta_u"] * (1 + r["D/E"] * (1 - t))
    r["ke_usd"] = v["rf"] + r["beta_l"] * v["prima"]
    r["ke_soles"] = (1 + r["ke_usd"]) * (1 + v["inflacion_pe"]) / (1 + v["inflacion_us"]) - 1
    r["ke"] = r["ke_soles"] + v["riesgo_pais"]
    r["kd"] = v["kd"]
    r["kd_despues_impuestos"] = v["kd"] * (1 - t)
    r["wacc"] = v["kd"] * (1 - t) * r["Wd"] + r["ke"] * r["We"]
    r["nopat"] = v["utilidad_operativa"] * (1 - t)
    r["ci"], r["ci_ant"] = D + E, D0 + E0
    r["ci_promedio"] = (r["ci"] + r["ci_ant"]) / 2
    r["roic"] = r["nopat"] / r["ci_promedio"]
    r["eva"] = (r["roic"] - r["wacc"]) * r["ci_promedio"]

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
        ("Beta apalancada", "βU × [1 + D/E × (1 − t)]", f"{v['beta_u']:.4f} × [1 + {r['D/E']:.4f} × (1 − {t:.3f})]",
         f"{r['beta_l']:.4f}"),
        ("Ke en dólares (CAPM)", "Rf + βL × (Rm − Rf)", f"{v['rf']:.4%} + {r['beta_l']:.4f} × {v['prima']:.4%}",
         f"{r['ke_usd']:.4%}"),
        ("Ke en soles (Fisher)", "(1 + Ke$) × (1 + πPE) / (1 + πUS) − 1",
         f"(1 + {r['ke_usd']:.4%}) × (1 + {v['inflacion_pe']:.4%}) / (1 + {v['inflacion_us']:.4%}) − 1", f"{r['ke_soles']:.4%}"),
        ("Ke final", "Ke soles + riesgo país", f"{r['ke_soles']:.4%} + {v['riesgo_pais']:.4%}", f"{r['ke']:.4%}"),
        ("Kd después de impuestos", "Kd × (1 − t)", f"{r['kd']:.4%} × (1 − {t:.3f})", f"{r['kd_despues_impuestos']:.4%}"),
        ("WACC", "Kd(1−t) × Wd + Ke × We",
         f"{r['kd_despues_impuestos']:.4%} × {r['Wd']:.4%} + {r['ke']:.4%} × {r['We']:.4%}", f"{r['wacc']:.4%}"),
        ("NOPAT", "UO × (1 − t)", f"{v['utilidad_operativa']:,.0f} × (1 − {t:.3f})", f"{r['nopat']:,.0f}"),
        ("Capital invertido promedio", "(CI actual + CI anterior) / 2", f"({r['ci']:,.0f} + {r['ci_ant']:,.0f}) / 2",
         f"{r['ci_promedio']:,.0f}"),
        ("ROIC", "NOPAT / CI promedio", f"{r['nopat']:,.0f} / {r['ci_promedio']:,.0f}", f"{r['roic']:.4%}"),
        ("EVA", "(ROIC − WACC) × CI promedio", f"({r['roic']:.4%} − {r['wacc']:.4%}) × {r['ci_promedio']:,.0f}",
         f"{r['eva']:,.0f}"),
    ]
    emitir("calculo_inicio", f"Cálculo en Python ({len(pasos)} pasos)")
    for i, (nombre, formula, sustitucion, resultado) in enumerate(pasos, 1):
        emitir("calculo", f"{i:>2}. {nombre} = {formula} = {sustitucion} = {resultado}",
               nombre=nombre, formula=formula, sustitucion=sustitucion, resultado=resultado)
        if velocidad > 0:
            time.sleep(0.6 * velocidad)
