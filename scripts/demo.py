"""Demo: construye el modelo WACC + EVA en vivo en Excel.

Ejemplos (PowerShell, con el entorno activado):
    python scripts\\demo.py                       # Laive 2023, datos en vivo, Excel visible
    python scripts\\demo.py --caso curso          # reproduce la práctica calificada al decimal
    python scripts\\demo.py --velocidad 2         # más lento (para presentar)
    python scripts\\demo.py --modo archivo        # sin abrir Excel (rápido)
    python scripts\\demo.py --ver todo            # navegador + Excel + cálculos en Python
    python scripts\\demo.py --empresa "Leche Gloria" --anio 2025 --ver descargas
    python scripts\\demo.py --empresa "Alicorp" --anio 2024 --industria "Food Processing"
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from motor import config  # noqa: E402
from motor.datos import smv  # noqa: E402
from motor.generar import generar_wacc, kd_desde_pdf  # noqa: E402

# Nota 12 de los EEFF auditados de Laive 2023 (tasas tal como figuran en el PDF)
KD_LAIVE_2023 = [
    dict(tipo="SOBREGIROS", entidad="Banco de Crédito del Perú", tasa_min=0.0815, tasa_max=0.0875,
         corriente=25935, no_corriente=0, moneda="S/ y US$",
         nota="Nota 12 del PDF auditado: 'Entre 8.15 y 8.75'. (La práctica calificada tipeó 8.76.)"),
    dict(tipo="SOBREGIROS", entidad="Scotiabank Perú S.A.A.", tasa_min=0.0785, corriente=51706),
    dict(tipo="PRESTAMOS BANCARIOS", entidad="Banco de Crédito del Perú", tasa_min=0.0355, tasa_max=0.0555,
         corriente=11027, no_corriente=15805),
    dict(tipo="PRESTAMOS BANCARIOS", entidad="BBVA Banco Continental", tasa_min=0.0525,
         corriente=3700, no_corriente=5505),
]
DOCENTE_LAIVE_2023 = {"inflacion_pe": 0.0341, "inflacion_us": 0.034, "riesgo_pais": 0.0162,
                      "beta_u": 0.61}

ap = argparse.ArgumentParser(description="Demo FinPerú: WACC + EVA en Excel")
ap.add_argument("--empresa", default="Laive")
ap.add_argument("--anio", type=int, default=2023)
ap.add_argument("--industria", default="Food Processing")
ap.add_argument("--caso", choices=["vivo", "curso"], default="vivo",
                help="vivo: datos frescos de las fuentes; curso: mismos datos que la práctica calificada")
ap.add_argument("--modo", choices=["vivo", "archivo", "auto"], default="auto")
ap.add_argument("--velocidad", type=float, default=1.0)
ap.add_argument("--kd-pdf", action="store_true",
                help="lee la tabla de Kd de la nota de deuda del PDF auditado (navegador visible)")
ap.add_argument("--ver", choices=["todo", "excel", "descargas", "calculos", "nada"], default="excel",
                help="qué mostrar: todo | excel | descargas (navegador) | calculos (Python) | nada")
ap.add_argument("--industria-auto", action="store_true", help="usa la industria sugerida por el CIIU")
a = ap.parse_args()

cands = smv.buscar_empresa(a.empresa)
if not cands:
    sys.exit(f"No encontré '{a.empresa}' en el catálogo SMV")
emp = cands[0]
print(f"Empresa: {emp['nombre']} (RPJ {emp['rpj']}, RUC {emp['ruc']})")

VER = {"todo": (1, 1, 1), "excel": (0, 1, 0), "descargas": (1, 0, 0), "calculos": (0, 0, 1), "nada": (0, 0, 0)}
ver_nav, ver_xl, ver_calc = map(bool, VER[a.ver])
modo = a.modo if a.modo != "auto" else ("vivo" if ver_xl else "archivo")
if a.industria_auto:
    from motor.industrias import sugerir
    a.industria = sugerir(emp.get("ciiu")) or a.industria
    print(f"Industria sugerida: {a.industria}")

es_laive = emp["rpj"] == "CI0011" and a.anio == 2023
kd = KD_LAIVE_2023 if es_laive else "pdf"   # otras empresas: Kd automático desde el PDF auditado
sob = DOCENTE_LAIVE_2023 if (a.caso == "curso" and es_laive) else None
if a.caso == "curso" and es_laive:
    sob = dict(sob, prima=0.06799170755600067)

kd_pdf = None
if a.kd_pdf:
    r = kd_desde_pdf(emp["rpj"], a.anio, visible=True)
    print(f"Nota de deuda: pág. {r['pagina']}, {len(r['lineas'])} líneas, cuadra={r['cuadra']}, avisos={r['avisos']}")
    for l in r["lineas"]:
        print(f"   {l['tipo']:<24} {l['entidad'][:40]:<40} {l['tasa_min']} {l['tasa_max']} "
              f"{l['corriente']:>12,.0f} {l['no_corriente']:>12,.0f}")
    if r["lineas"] and all(l["tasa_min"] is not None for l in r["lineas"]):
        kd, kd_pdf = r["lineas"], r["kd_pdf"]

s = generar_wacc(emp["rpj"], a.anio, a.industria, kd=kd, sobrescribir=sob, modo=modo, velocidad=a.velocidad,
                 kd_pdf=kd_pdf, ver_navegador=ver_nav, ver_calculos=ver_calc)
print()
print(json.dumps({"excel": s["excel"], "modo": s["modo"], "segundos": s["segundos"],
                  "WACC": f"{s['resultados']['wacc']:.4%}", "Ke": f"{s['resultados']['ke']:.4%}",
                  "ROIC": f"{s['resultados']['roic']:.4%}", "EVA": round(s['resultados']['eva'], 2),
                  "verificacion_excel": s["verificacion_excel"], "avisos": s["avisos"]},
                 ensure_ascii=False, indent=2, default=str))
