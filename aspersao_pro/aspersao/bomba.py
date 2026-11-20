"""Seleção de bomba e motor: altura manométrica, NPSH, potências, curvas,
ponto de operação, leis de afinidade e custo de energia.
"""

from __future__ import annotations

import math

import numpy as np
from scipy.optimize import brentq

from .clima.penman import pressao_atmosferica, pressao_saturacao
from .unidades import G, KPA_POR_MCA, KW_POR_CV, RHO_AGUA

MOTORES_CV = [0.5, 0.75, 1, 1.5, 2, 3, 4, 5, 6, 7.5, 10, 12.5, 15, 20, 25, 30, 40, 50, 60, 75, 100, 125,
              150, 175, 200, 250, 300, 350, 400, 450, 500]

# Rendimentos típicos de motores de indução trifásicos IR3 (alto rendimento), 4 polos
_REND_MOTOR = [(1, 0.80), (2, 0.84), (5, 0.875), (10, 0.895), (20, 0.91), (50, 0.935), (100, 0.945),
               (200, 0.955), (500, 0.96)]


def rendimento_motor(p_cv: float) -> float:
    cv = np.array([p for p, _ in _REND_MOTOR], dtype=float)
    eta = np.array([e for _, e in _REND_MOTOR])
    return float(np.interp(np.log(max(p_cv, 0.5)), np.log(cv), eta))


def folga_motor(p_cv: float) -> float:
    """Margem de segurança usual na seleção do motor (prática brasileira)."""
    if p_cv <= 2:
        return 0.50
    if p_cv <= 5:
        return 0.30
    if p_cv <= 10:
        return 0.20
    if p_cv <= 20:
        return 0.15
    return 0.10


def motor_comercial(p_eixo_cv: float) -> dict:
    folga = folga_motor(p_eixo_cv)
    req = p_eixo_cv * (1.0 + folga)
    escolhido = next((m for m in MOTORES_CV if m >= req), MOTORES_CV[-1])
    return {"potencia_eixo_cv": p_eixo_cv, "folga": folga, "potencia_requerida_cv": req, "motor_cv": escolhido,
            "rendimento": rendimento_motor(escolhido)}


def potencias(q_m3h: float, h_m: float, eta_bomba: float, eta_motor: float | None = None) -> dict:
    """Potência hidráulica, no eixo e elétrica de entrada (Eqs. 7–9 do OpenIrri)."""
    q = q_m3h / 3600.0
    p_h = RHO_AGUA * G * q * h_m / 1000.0
    p_eixo = p_h / eta_bomba
    mot = motor_comercial(p_eixo / KW_POR_CV)
    eta_m = eta_motor or mot["rendimento"]
    p_ent = p_eixo / eta_m
    return {"P_hidraulica_kW": p_h, "P_eixo_kW": p_eixo, "P_eixo_cv": p_eixo / KW_POR_CV,
            "P_eletrica_kW": p_ent, "eta_motor": eta_m, "motor": mot}


def npsh_disponivel(altitude_m: float, temp_agua_c: float, altura_succao_m: float, hf_succao_m: float) -> dict:
    """NPSHd = Patm/γ − Pv/γ − Hs − hf_s  (Hs > 0: bomba acima do nível d'água; < 0: afogada)."""
    patm = float(pressao_atmosferica(altitude_m)) / KPA_POR_MCA
    pv = float(pressao_saturacao(temp_agua_c)) / KPA_POR_MCA
    npshd = patm - pv - altura_succao_m - hf_succao_m
    return {"Patm_mca": patm, "Pv_mca": pv, "NPSHd": npshd}


def rotacao_especifica(n_rpm: float, q_m3s: float, h_m: float) -> float:
    """nq = n·√Q / H^0,75 (rpm, m³/s, m)."""
    return n_rpm * math.sqrt(q_m3s) / h_m ** 0.75


def tipo_rotor(nq: float) -> str:
    if nq < 30:
        return "Radial (centrífuga lenta) — baixa vazão, alta pressão"
    if nq < 60:
        return "Radial normal (centrífuga)"
    if nq < 150:
        return "Fluxo misto (semiaxial)"
    return "Axial — alta vazão, baixa pressão"


def npsh_requerido_estimado(n_rpm: float, q_m3s: float, h_m: float) -> float:
    """Estimativa de NPSHr pelo coeficiente de Thoma (Stepanoff): σ = 0,0012·nq^(4/3)."""
    nq = rotacao_especifica(n_rpm, q_m3s, h_m)
    return 0.0012 * nq ** (4.0 / 3.0) * h_m


class CurvaBomba:
    """Curva H(Q) = a0 + a1·Q + a2·Q² e rendimento η(Q) polinomial (Q em m³/h)."""

    def __init__(self, coef_h, coef_eta, q_max, nome="Curva", n_rpm=3500, coef_npsh=None):
        self.coef_h = np.asarray(coef_h, dtype=float)
        self.coef_eta = np.asarray(coef_eta, dtype=float)
        self.coef_npsh = None if coef_npsh is None else np.asarray(coef_npsh, dtype=float)
        self.q_max = float(q_max)
        self.nome = nome
        self.n_rpm = n_rpm

    def h(self, q):
        return np.polyval(self.coef_h, q)

    def eta(self, q):
        return np.clip(np.polyval(self.coef_eta, q), 0.01, 0.95)

    def npshr(self, q):
        if self.coef_npsh is None:
            return np.full_like(np.asarray(q, dtype=float), np.nan)
        return np.polyval(self.coef_npsh, q)

    @property
    def h_shutoff(self):
        return float(self.h(0.0))

    def afinidade(self, razao_rotacao):
        """Nova curva pelas leis de afinidade (Q ∝ n, H ∝ n²; η mantido)."""
        r = razao_rotacao
        a = self.coef_h  # ordem decrescente: [a2, a1, a0]
        novo_h = np.array([a[0], a[1] * r, a[2] * r ** 2]) if len(a) == 3 else a * r ** 2
        e = self.coef_eta
        novo_eta = np.array([e[0] / r ** 2, e[1] / r, e[2]]) if len(e) == 3 else e
        npsh = None
        if self.coef_npsh is not None and len(self.coef_npsh) == 3:
            c = self.coef_npsh
            npsh = np.array([c[0], c[1] * r, c[2] * r ** 2])
        return CurvaBomba(novo_h, novo_eta, self.q_max * r, f"{self.nome} @ {self.n_rpm * r:.0f} rpm",
                          self.n_rpm * r, npsh)


def curva_sintetica(q_proj_m3h, h_proj_m, eta_max=0.75, n_rpm=3500, folga_h=1.20):
    """Curva genérica de bomba centrífuga que passa pelo ponto de projeto.

    H(Q) = H0 − a·Q², com H0 = folga_h·Hp; η(Q) parabólica com BEP em 1,05·Qp.
    """
    h0 = folga_h * h_proj_m
    a = (h0 - h_proj_m) / q_proj_m3h ** 2
    qb = 1.05 * q_proj_m3h
    coef_eta = np.array([-eta_max / qb ** 2, 2.0 * eta_max / qb, 0.0])
    q_max = math.sqrt(h0 / a)
    npsh_bep = npsh_requerido_estimado(n_rpm, qb / 3600.0, h_proj_m)
    coef_npsh = np.array([npsh_bep * 0.6 / qb ** 2, 0.0, npsh_bep * 0.4])  # cresce com Q²
    return CurvaBomba(np.array([-a, 0.0, h0]), coef_eta, q_max, "Curva sintética (genérica)", n_rpm, coef_npsh)


def curva_de_pontos(q, h, eta=None, npshr=None, nome="Curva do fabricante", n_rpm=3500):
    """Ajusta polinômios de 2º grau aos pontos informados pelo fabricante."""
    q = np.asarray(q, dtype=float)
    h = np.asarray(h, dtype=float)
    coef_h = np.polyfit(q, h, 2)
    if eta is not None and len(eta) == len(q):
        e = np.asarray(eta, dtype=float)
        e = e / 100.0 if e.max() > 1.5 else e
        coef_eta = np.polyfit(q, e, 2)
    else:
        coef_eta = np.array([0.0, 0.0, 0.70])
    coef_npsh = np.polyfit(q, np.asarray(npshr, dtype=float), 2) if npshr is not None and len(npshr) == len(q) else None
    return CurvaBomba(coef_h, coef_eta, q.max() * 1.1, nome, n_rpm, coef_npsh)


def curva_sistema(h_estatica, h_dinamica_proj, q_proj_m3h, m=1.852):
    """H_sis(Q) = Hest + K·Q^m, com K tal que H_sis(Qp) = Hest + Hdin(Qp)."""
    k = h_dinamica_proj / q_proj_m3h ** m
    return lambda q: h_estatica + k * np.asarray(q, dtype=float) ** m


def ponto_operacao(curva: CurvaBomba, h_sis) -> tuple[float, float] | None:
    f = lambda q: curva.h(q) - h_sis(q)  # noqa: E731
    q_hi = curva.q_max
    if f(1e-6) < 0:
        return None
    while f(q_hi) > 0 and q_hi < 1e6:
        q_hi *= 1.5
    q = brentq(f, 1e-6, q_hi)
    return float(q), float(curva.h(q))


def ajuste_rotacao(curva: CurvaBomba, q_alvo, h_alvo, h_sis=None):
    """Razão de rotação que faz a bomba operar no ponto (q_alvo, h_alvo) — inversor de frequência."""
    def f(r):
        return float(curva.afinidade(r).h(q_alvo) - h_alvo)
    try:
        return brentq(f, 0.4, 1.6)
    except ValueError:
        return None


def custo_energia(p_eletrica_kw, horas_ano, tarifa_kwh, desconto_noturno_pct=0.0, horas_noturnas_dia=8.5,
                  horas_operacao_dia=None, demanda_kw_mes_tarifa=0.0, meses_operacao=12):
    """Custo anual de energia elétrica com desconto especial para irrigação noturna
    (Resolução ANEEL nº 1.000/2021: desconto na tarifa no período de 8h30 contínuas).

    A fração das horas de operação diárias que ocorre no período com desconto é
    min(horas noturnas, horas de operação diária) / horas de operação diária.
    """
    energia = p_eletrica_kw * horas_ano
    frac = 1.0
    if horas_operacao_dia and horas_operacao_dia > 0:
        frac = min(horas_noturnas_dia, horas_operacao_dia) / horas_operacao_dia
    custo_cons = energia * tarifa_kwh * (1.0 - frac * desconto_noturno_pct / 100.0)
    custo_dem = demanda_kw_mes_tarifa * p_eletrica_kw * meses_operacao
    return {"energia_kWh": energia, "fracao_desconto": frac if desconto_noturno_pct > 0 else 0.0,
            "custo_consumo": custo_cons, "custo_demanda": custo_dem, "custo_total": custo_cons + custo_dem}


def custo_diesel(p_eixo_kw, horas_ano, preco_litro, consumo_especifico_l_kwh=0.27):
    litros = p_eixo_kw * horas_ano * consumo_especifico_l_kwh
    return {"litros": litros, "custo_total": litros * preco_litro}
