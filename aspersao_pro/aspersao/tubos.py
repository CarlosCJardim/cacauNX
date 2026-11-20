"""Catálogo de tubulações (PVC, PEAD, alumínio engate rápido e aço galvanizado).

Diâmetros internos calculados a partir do diâmetro externo e da classe de
pressão pela fórmula de Barlow (e = DE·P / (2σ + P)), com espessura mínima
construtiva. Preços de referência (R$/m) proporcionais à massa de material.
Todos os valores são editáveis na interface — confirme com o fabricante.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass

import pandas as pd


@dataclass
class Tubo:
    material: str
    dn: str  # rótulo nominal
    de_mm: float
    di_mm: float
    pn_mca: float
    c_hw: float
    rugosidade_mm: float
    preco_m: float
    modulo_elasticidade_gpa: float
    espessura_mm: float

    @property
    def rotulo(self):
        return f"{self.material} DN {self.dn} PN{self.pn_mca:.0f} (DI {self.di_mm:.1f} mm)"

    @property
    def d_m(self):
        return self.di_mm / 1000.0

    def to_dict(self):
        return asdict(self)


# material: (σ_projeto MPa, densidade kg/m³, R$/kg, C Hazen-Williams, ε mm, E GPa, e_min mm)
PROPRIEDADES = {
    "PVC": (10.0, 1400.0, 26.0, 150.0, 0.0015, 3.0, 1.2),
    "PEAD": (6.3, 950.0, 24.0, 145.0, 0.007, 0.9, 2.0),
    "Alumínio (engate rápido)": (None, 2700.0, 62.0, 130.0, 0.0015, 70.0, None),
    "Aço galvanizado": (None, 7850.0, 19.0, 120.0, 0.15, 207.0, None),
}

_PVC_DE = {"50": 50.5, "75": 75.5, "100": 101.6, "125": 125.0, "150": 150.0, "200": 200.0,
           "250": 250.0, "300": 300.0}
_PVC_PN = (40.0, 60.0, 80.0, 125.0)
_PEAD_DE = {"32": 32.0, "40": 40.0, "50": 50.0, "63": 63.0, "75": 75.0, "90": 90.0, "110": 110.0,
            "125": 125.0, "160": 160.0}
_PEAD_PN = (40.0, 60.0, 80.0, 100.0)
_ALUMINIO = {'2"': (50.8, 1.27), '3"': (76.2, 1.27), '4"': (101.6, 1.27), '5"': (127.0, 1.47), '6"': (152.4, 1.65),
             '8"': (203.2, 2.03)}
_ACO = {'1"': (33.4, 3.38), '1.1/2"': (48.3, 3.68), '2"': (60.3, 3.91), '2.1/2"': (73.0, 5.16), '3"': (88.9, 5.49),
        '4"': (114.3, 6.02), '5"': (141.3, 6.55), '6"': (168.3, 7.11), '8"': (219.1, 8.18)}


def _preco(material, de, e):
    _, dens, preco_kg, *_ = PROPRIEDADES[material]
    massa = math.pi * (de - e) * e * 1e-6 * dens  # kg/m
    return round(massa * preco_kg + 2.0, 2)


def _tubo_termoplastico(material, dn, de, pn):
    sigma, _, _, c, eps, e_gpa, e_min = PROPRIEDADES[material]
    p_mpa = pn / 101.97
    e = max(de * p_mpa / (2.0 * sigma + p_mpa), e_min)
    return Tubo(material, dn, de, round(de - 2 * e, 1), pn, c, eps, _preco(material, de, e), e_gpa, round(e, 2))


def catalogo_tubos() -> list[Tubo]:
    cat = []
    for dn, de in _PVC_DE.items():
        for pn in _PVC_PN:
            cat.append(_tubo_termoplastico("PVC", dn, de, pn))
    for dn, de in _PEAD_DE.items():
        for pn in _PEAD_PN:
            cat.append(_tubo_termoplastico("PEAD", dn, de, pn))
    for dn, (de, e) in _ALUMINIO.items():
        m = "Alumínio (engate rápido)"
        p = PROPRIEDADES[m]
        cat.append(Tubo(m, dn, de, round(de - 2 * e, 2), 100.0, p[3], p[4], _preco(m, de, e) + 8.0, p[5], e))
    for dn, (de, e) in _ACO.items():
        m = "Aço galvanizado"
        p = PROPRIEDADES[m]
        cat.append(Tubo(m, dn, de, round(de - 2 * e, 2), 250.0, p[3], p[4], _preco(m, de, e), p[5], e))
    return cat


MATERIAIS = list(PROPRIEDADES.keys())


def tubos_por_material(material: str, catalogo: list[Tubo] | None = None, pn_min: float = 0.0) -> list[Tubo]:
    """Tubos de um material, um por DN (a menor classe PN ≥ pn_min), em ordem crescente de DI."""
    cat = catalogo or catalogo_tubos()
    por_dn = {}
    for t in cat:
        if t.material != material or t.pn_mca < pn_min:
            continue
        atual = por_dn.get(t.dn)
        if atual is None or t.pn_mca < atual.pn_mca:
            por_dn[t.dn] = t
    return sorted(por_dn.values(), key=lambda t: t.di_mm)


def classe_para_pressao(material: str, dn: str, pressao_mca: float, catalogo: list[Tubo] | None = None):
    """Menor classe PN de um DN que suporte a pressão (mca). Retorna None se nenhuma."""
    cat = catalogo or catalogo_tubos()
    opcoes = sorted([t for t in cat if t.material == material and t.dn == dn], key=lambda t: t.pn_mca)
    for t in opcoes:
        if t.pn_mca >= pressao_mca:
            return t
    return None


def catalogo_df(cat: list[Tubo] | None = None) -> pd.DataFrame:
    cat = cat or catalogo_tubos()
    return pd.DataFrame([{
        "Material": t.material, "DN": t.dn, "DE (mm)": t.de_mm, "e (mm)": t.espessura_mm,
        "DI (mm)": t.di_mm, "PN (mca)": t.pn_mca, "C (H-W)": t.c_hw, "ε (mm)": t.rugosidade_mm,
        "Preço (R$/m)": t.preco_m,
    } for t in cat])


def catalogo_de_df(df: pd.DataFrame) -> list[Tubo]:
    """Reconstrói o catálogo a partir da tabela editada pelo usuário."""
    out = []
    for _, r in df.iterrows():
        m = str(r["Material"])
        e_gpa = PROPRIEDADES.get(m, (None, 0, 0, 0, 0, 3.0, None))[5]
        out.append(Tubo(m, str(r["DN"]), float(r["DE (mm)"]), float(r["DI (mm)"]), float(r["PN (mca)"]),
                        float(r["C (H-W)"]), float(r["ε (mm)"]), float(r["Preço (R$/m)"]), e_gpa, float(r["e (mm)"])))
    return out
