"""Sugerencia de industria Damodaran a partir del CIIU (Rev. 3) que reporta la SMV.

Es solo una SUGERENCIA: el usuario siempre puede elegir otra industria de la lista.
Se busca primero el código de 4 dígitos, luego 3 y luego 2.
"""
from __future__ import annotations

CIIU_A_DAMODARAN = {
    # Alimentos y bebidas
    "1511": "Food Processing", "1512": "Farming/Agriculture", "1513": "Food Processing", "1514": "Food Processing",
    "1520": "Food Processing", "153": "Food Processing", "154": "Food Processing", "1541": "Food Processing",
    "1542": "Food Processing", "1551": "Beverage (Alcoholic)", "1552": "Beverage (Alcoholic)",
    "1553": "Beverage (Alcoholic)", "1554": "Beverage (Soft)", "16": "Tobacco", "15": "Food Processing",
    # Agro, pesca, minería, petróleo
    "01": "Farming/Agriculture", "02": "Paper/Forest Products", "05": "Farming/Agriculture",
    "10": "Coal & Related Energy", "11": "Oil/Gas (Production and Exploration)", "13": "Metals & Mining",
    "1320": "Metals & Mining", "14": "Metals & Mining", "23": "Oil/Gas Distribution",
    # Manufactura
    "17": "Apparel", "18": "Apparel", "19": "Shoe", "20": "Paper/Forest Products", "21": "Paper/Forest Products",
    "22": "Publishing & Newspapers", "24": "Chemical (Basic)", "2423": "Drugs (Pharmaceutical)",
    "25": "Rubber& Tires", "26": "Building Materials", "2694": "Building Materials", "27": "Steel",
    "2720": "Metals & Mining", "28": "Machinery", "29": "Machinery", "31": "Electrical Equipment",
    "34": "Auto & Truck", "36": "Furn/Home Furnishings",
    # Servicios
    "40": "Power", "401": "Power", "41": "Utility (Water)", "45": "Engineering/Construction",
    "50": "Retail (Automotive)", "51": "Retail (Distributors)", "5150": "Retail (Distributors)",
    "52": "Retail (General)", "55": "Hotel/Gaming", "60": "Transportation", "61": "Shipbuilding & Marine",
    "62": "Air Transport", "63": "Transportation", "64": "Telecom. Services", "65": "Bank (Money Center)",
    "66": "Insurance (General)", "67": "Financial Svcs. (Non-bank & Insurance)", "70": "Real Estate (Development)",
    "72": "Computer Services", "74": "Business & Consumer Services", "80": "Education",
    "85": "Hospitals/Healthcare Facilities",
}


def sugerir(ciiu: str | None) -> str | None:
    c = (ciiu or "").strip()
    for n in (4, 3, 2):
        if len(c) >= n and c[:n] in CIIU_A_DAMODARAN:
            return CIIU_A_DAMODARAN[c[:n]]
    return None
