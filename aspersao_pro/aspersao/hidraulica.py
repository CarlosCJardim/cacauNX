"""Hidráulica de tubulações com múltiplas saídas (linhas laterais e de derivação),
perdas de carga e transientes.

* Hazen-Williams (SI): hf = 10,646 L Q^1,852 / (C^1,852 D^4,87)
* Darcy-Weisbach com fator de atrito de Swamee-Jain (1976)
* Fator F de Christiansen (exato e aproximado) com 1ª saída a qualquer distância
* Cálculo passo a passo (trecho a trecho) considerando a cota de cada aspersor
  obtida do modelo digital de elevação e a relação vazão-pressão q = k·P^x
* Golpe de aríete: celeridade (Korteweg/Allievi) e sobrepressão de Joukowsky/Michaud
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
from scipy.optimize import brentq

from .tubos import Tubo
from .unidades import G, KPA_POR_MCA

M_HW = 1.852


# ---------------------------------------------------------------------------
# Perdas de carga
# ---------------------------------------------------------------------------
def hf_hazen_williams(q_m3s, d_m, l_m, c):
    q = np.abs(np.asarray(q_m3s, dtype=float))
    return 10.646 * np.asarray(l_m, dtype=float) * q ** M_HW / (c ** M_HW * np.asarray(d_m, dtype=float) ** 4.87)


def viscosidade_cinematica(t_c=20.0):
    """Viscosidade cinemática da água (m²/s) — ajuste de Vogel."""
    mu = 2.414e-5 * 10 ** (247.8 / (t_c + 273.15 - 140.0))  # Pa·s
    rho = 1000.0 * (1 - (t_c + 288.9414) / (508929.2 * (t_c + 68.12963)) * (t_c - 3.9863) ** 2)
    return mu / rho


def fator_atrito_swamee_jain(re, eps_m, d_m):
    re = np.maximum(np.asarray(re, dtype=float), 1e-9)
    lam = 64.0 / re
    turb = 0.25 / np.log10(eps_m / (3.7 * d_m) + 5.74 / re ** 0.9) ** 2
    return np.where(re < 2000.0, lam, turb)


def hf_darcy_weisbach(q_m3s, d_m, l_m, eps_mm, t_c=20.0):
    q = np.abs(np.asarray(q_m3s, dtype=float))
    d = np.asarray(d_m, dtype=float)
    v = 4.0 * q / (math.pi * d ** 2)
    re = v * d / viscosidade_cinematica(t_c)
    f = fator_atrito_swamee_jain(re, eps_mm / 1000.0, d)
    return f * np.asarray(l_m, dtype=float) / d * v ** 2 / (2.0 * G)


def perda_carga(q_m3s, tubo: Tubo, l_m, equacao="HW", t_c=20.0):
    if equacao == "DW":
        return hf_darcy_weisbach(q_m3s, tubo.d_m, l_m, tubo.rugosidade_mm, t_c)
    return hf_hazen_williams(q_m3s, tubo.d_m, l_m, tubo.c_hw)


def velocidade(q_m3s, d_m):
    return 4.0 * np.abs(np.asarray(q_m3s, dtype=float)) / (math.pi * np.asarray(d_m, dtype=float) ** 2)


# ---------------------------------------------------------------------------
# Fator F de Christiansen
# ---------------------------------------------------------------------------
def fator_f(n: int, m: float = M_HW, a: float = 1.0) -> float:
    """Fator F exato para n saídas de vazão igual, espaçamento S e primeira saída a a·S
    da entrada (a = 1: espaçamento inteiro; a = 0,5: meio espaçamento).

    F = [a·N^m + Σ_{j=1}^{N-1} j^m] / [(N − 1 + a)·N^m]
    """
    n = int(n)
    if n <= 1:
        return 1.0
    j = np.arange(1, n, dtype=float)
    return float((a * n ** m + np.sum(j ** m)) / ((n - 1 + a) * n ** m))


def fator_f_aproximado(n: int, m: float = M_HW) -> float:
    """Fórmula aproximada de Christiansen (1ª saída a um espaçamento):
    F = 1/(m+1) + 1/(2N) + √(m−1)/(6N²)."""
    n = max(int(n), 1)
    return 1.0 / (m + 1.0) + 1.0 / (2.0 * n) + math.sqrt(m - 1.0) / (6.0 * n ** 2)


# ---------------------------------------------------------------------------
# Linha com múltiplas saídas — cálculo passo a passo
# ---------------------------------------------------------------------------
@dataclass
class ResultadoLateral:
    h_bocal: np.ndarray  # pressão no bocal de cada aspersor (mca), da entrada para o final
    q: np.ndarray  # vazão de cada aspersor (m³/h)
    h_linha: np.ndarray  # pressão na tubulação na base de cada haste (mca)
    h_entrada: float  # pressão requerida na entrada da linha (mca)
    q_entrada_m3h: float
    hf_total: float
    dz: float  # cota final − cota da entrada (m)
    var_pressao_pct: float  # (hmax − hmin) / h_media
    var_vazao_pct: float  # (qmax − qmin) / q_media
    idx_critico: int
    distancias: np.ndarray
    cotas: np.ndarray
    velocidade_max: float
    diametros_mm: list = field(default_factory=list)

    @property
    def h_media(self):
        return float(np.mean(self.h_bocal))

    @property
    def cuc_vazao(self):
        q = self.q
        return float(100.0 * (1.0 - np.abs(q - q.mean()).sum() / (q.size * q.mean())))


def _marcha(h_final, n, comp, k, x, cotas, tubos, ha, equacao, perda_local, t_c):
    """Marcha do último aspersor até a entrada. ``cotas`` tem n+1 valores:
    índice 0 = entrada da linha, 1..n = aspersores. ``comp`` tem n comprimentos de trecho
    (comp[0] = entrada → 1º aspersor). Pressões em mca; q = k·(P_kPa)^x (m³/h)."""
    h_bocal = np.empty(n)
    h_linha = np.empty(n)
    q = np.empty(n)
    h_bocal[-1] = h_final
    q[-1] = k * max(h_final * KPA_POR_MCA, 0.0) ** x
    h_linha[-1] = h_final + ha
    q_acum = q[-1]
    vmax = 0.0
    for i in range(n - 2, -1, -1):
        t = tubos[i + 1]  # trecho entre aspersor i e i+1 (índices 0-based)
        hf = float(perda_carga(q_acum / 3600.0, t, comp[i + 1], equacao, t_c)) * (1.0 + perda_local)
        vmax = max(vmax, float(velocidade(q_acum / 3600.0, t.d_m)))
        h_linha[i] = h_linha[i + 1] + hf + (cotas[i + 2] - cotas[i + 1])
        h_bocal[i] = h_linha[i] - ha
        q[i] = k * max(h_bocal[i] * KPA_POR_MCA, 0.0) ** x
        q_acum += q[i]
    t0 = tubos[0]
    hf0 = float(perda_carga(q_acum / 3600.0, t0, comp[0], equacao, t_c)) * (1.0 + perda_local)
    vmax = max(vmax, float(velocidade(q_acum / 3600.0, t0.d_m)))
    h_entrada = h_linha[0] + hf0 + (cotas[1] - cotas[0])
    return h_bocal, h_linha, q, h_entrada, q_acum, vmax


def lateral_passo_a_passo(n: int, esp: float, k: float, x: float, tubos, cotas=None, a: float = 0.5,
                          ha: float = 1.0, h_servico: float | None = None, h_entrada: float | None = None,
                          equacao: str = "HW", perda_local: float = 0.0, t_c: float = 20.0,
                          comprimentos=None) -> ResultadoLateral:
    """Resolve uma linha com ``n`` aspersores espaçados de ``esp`` metros.

    Informe ``h_servico`` (pressão média desejada nos bocais, mca) para obter a
    pressão requerida na entrada, ou ``h_entrada`` para simular a linha com
    pressão de entrada conhecida.

    ``tubos`` pode ser um único :class:`Tubo` ou uma lista com n trechos
    (trecho 0 = entrada → 1º aspersor), permitindo linhas telescópicas.
    ``cotas`` (n+1 valores, m): entrada seguida dos aspersores; padrão = plano.
    ``comprimentos`` (n valores, m): comprimentos reais dos trechos quando o
    espaçamento não é uniforme (ex.: falhas em áreas irregulares).
    """
    n = int(n)
    if n < 1:
        raise ValueError("A linha precisa de ao menos um aspersor.")
    if isinstance(tubos, Tubo):
        tubos = [tubos] * n
    cotas = np.zeros(n + 1) if cotas is None else np.asarray(cotas, dtype=float)
    if comprimentos is None:
        comp = np.concatenate([[a * esp], np.full(n - 1, esp)])
    else:
        comp = np.asarray(comprimentos, dtype=float)
    args = (n, comp, k, x, cotas, tubos, ha, equacao, perda_local, t_c)

    if h_servico is not None:
        alvo = lambda hf_: np.mean(_marcha(hf_, *args)[0]) - h_servico  # noqa: E731
    elif h_entrada is not None:
        alvo = lambda hf_: _marcha(hf_, *args)[3] - h_entrada  # noqa: E731
    else:
        raise ValueError("Informe h_servico ou h_entrada.")
    lo, hi = 0.01, (h_servico or h_entrada) * 1.5 + 5.0
    f_lo = alvo(lo)
    while alvo(hi) < 0 and hi < 2000:
        hi *= 1.6
    if f_lo > 0:
        # nem com pressão mínima no final a condição é atendida (desnível muito favorável)
        h_fim = lo
    else:
        h_fim = brentq(alvo, lo, hi, xtol=1e-6)
    hb, hl, q, he, qe, vmax = _marcha(h_fim, *args)
    hmed = float(np.mean(hb))
    dist = np.cumsum(comp)
    return ResultadoLateral(
        h_bocal=hb, q=q, h_linha=hl, h_entrada=float(he), q_entrada_m3h=float(qe),
        hf_total=float(he - hl[-1] - (cotas[-1] - cotas[0]) - 0.0) if n > 0 else 0.0,
        dz=float(cotas[-1] - cotas[0]),
        var_pressao_pct=float(100.0 * (hb.max() - hb.min()) / hmed) if hmed > 0 else 0.0,
        var_vazao_pct=float(100.0 * (q.max() - q.min()) / q.mean()) if q.mean() > 0 else 0.0,
        idx_critico=int(np.argmin(hb)), distancias=dist, cotas=cotas, velocidade_max=vmax,
        diametros_mm=[t.di_mm for t in tubos],
    )


def lateral_christiansen(n, esp, q_m3h, tubo: Tubo, h_servico, dz=0.0, ha=1.0, a=0.5, equacao="HW", t_c=20.0):
    """Método analítico clássico (Christiansen / Keller):

    hf = F · J · L;  Pin = PS + ¾ hf + ½ ΔZ + Ha   (ΔZ > 0 em aclive)
    """
    l_total = (n - 1 + a) * esp
    q_total = n * q_m3h / 3600.0
    j = float(perda_carga(q_total, tubo, 1.0, equacao, t_c))
    f = fator_f(n, M_HW, a)
    hf = f * j * l_total
    h_in = h_servico + 0.75 * hf + 0.5 * dz + ha
    return {"F": f, "J_m_m": j, "hf": hf, "L": l_total, "Q_m3h": q_total * 3600.0, "h_entrada": h_in,
            "variacao_pct": 100.0 * (hf + dz) / h_servico, "v": float(velocidade(q_total, tubo.d_m))}


def dimensionar_lateral(n, esp, k, x, tubos_candidatos, h_servico, cotas=None, a=0.5, ha=1.0,
                        tolerancia=0.20, v_max=3.0, equacao="HW", perda_local=0.0, t_c=20.0, comprimentos=None):
    """Menor diâmetro que atende a variação de pressão admissível (padrão 20 % de PS)
    e a velocidade máxima. Retorna (tubo, resultado, atende)."""
    ultimo = None
    for t in tubos_candidatos:
        r = lateral_passo_a_passo(n, esp, k, x, t, cotas, a, ha, h_servico=h_servico, equacao=equacao,
                                  perda_local=perda_local, t_c=t_c, comprimentos=comprimentos)
        ultimo = (t, r)
        if r.var_pressao_pct <= tolerancia * 100.0 + 1e-9 and r.velocidade_max <= v_max:
            return t, r, True
    return ultimo[0], ultimo[1], False


def lateral_telescopica(n, esp, k, x, tubos_candidatos, h_servico, cotas=None, a=0.5, ha=1.0,
                        tolerancia=0.20, v_max=3.0, equacao="HW", perda_local=0.0, t_c=20.0, comprimentos=None):
    """Busca a combinação de dois diâmetros consecutivos (maior no início) de menor
    custo que atenda o critério de variação de pressão. Retorna dict ou None."""
    melhor = None
    for i in range(len(tubos_candidatos) - 1):
        t_p, t_g = tubos_candidatos[i], tubos_candidatos[i + 1]
        for n_g in range(1, n):
            trechos = [t_g] * n_g + [t_p] * (n - n_g)
            r = lateral_passo_a_passo(n, esp, k, x, trechos, cotas, a, ha, h_servico=h_servico,
                                      equacao=equacao, perda_local=perda_local, t_c=t_c, comprimentos=comprimentos)
            if r.var_pressao_pct <= tolerancia * 100.0 and r.velocidade_max <= v_max:
                comp = r.distancias
                l_g = float(comp[n_g - 1]) if n_g >= 1 else 0.0
                custo = l_g * t_g.preco_m + (float(comp[-1]) - l_g) * t_p.preco_m
                if melhor is None or custo < melhor["custo"]:
                    melhor = {"custo": custo, "n_maior": n_g, "tubo_maior": t_g, "tubo_menor": t_p, "resultado": r}
                break
    return melhor


def comprimento_maximo_lateral(esp, k, x, tubo: Tubo, h_servico, declividade=0.0, a=0.5, ha=1.0,
                               tolerancia=0.20, n_max=300, equacao="HW", perda_local=0.0):
    """Número máximo de aspersores (e comprimento) que mantém a variação de pressão
    dentro da tolerância, para declividade uniforme (m/m, positiva em aclive)."""
    melhor_n = 1
    for n in range(2, n_max + 1):
        dist = np.concatenate([[0.0], a * esp + esp * np.arange(n)])
        cotas = declividade * dist
        r = lateral_passo_a_passo(n, esp, k, x, tubo, cotas, a, ha, h_servico=h_servico, equacao=equacao,
                                  perda_local=perda_local)
        if r.var_pressao_pct > tolerancia * 100.0:
            break
        melhor_n = n
    return melhor_n, (melhor_n - 1 + a) * esp


# ---------------------------------------------------------------------------
# Curva de entrada de uma linha (para simulação de rede)
# ---------------------------------------------------------------------------
def curva_entrada_lateral(n, esp, k, x, tubos, cotas, a, ha, h_ref, equacao="HW", perda_local=0.0, pontos=7,
                          comprimentos=None):
    """Amostra Q_entrada(h_entrada) em torno da pressão de referência para uso em
    simulação de rede com vazões dependentes da pressão. Retorna (hs, qs, expoente, r_ref)."""
    r_ref = lateral_passo_a_passo(n, esp, k, x, tubos, cotas, a, ha, h_servico=h_ref, equacao=equacao,
                                  perda_local=perda_local, comprimentos=comprimentos)
    hs = np.linspace(0.7, 1.5, pontos) * r_ref.h_entrada
    qs = []
    for h in hs:
        r = lateral_passo_a_passo(n, esp, k, x, tubos, cotas, a, ha, h_entrada=h, equacao=equacao,
                                  perda_local=perda_local, comprimentos=comprimentos)
        qs.append(r.q_entrada_m3h)
    return hs, np.asarray(qs), r_ref


# ---------------------------------------------------------------------------
# Golpe de aríete
# ---------------------------------------------------------------------------
def celeridade(tubo: Tubo, k_agua_gpa: float = 2.07):
    """Celeridade da onda (m/s) — Korteweg: c = √(K/ρ) / √(1 + K·D/(E·e))."""
    k = k_agua_gpa * 1e9
    e_mod = tubo.modulo_elasticidade_gpa * 1e9
    return math.sqrt(k / 1000.0) / math.sqrt(1.0 + k * tubo.di_mm / (e_mod * max(tubo.espessura_mm, 0.1)))


def golpe_ariete(tubo: Tubo, comprimento_m, velocidade_ms, tempo_manobra_s):
    """Sobrepressão máxima (mca): Joukowsky (manobra rápida) ou Michaud (lenta)."""
    c = celeridade(tubo)
    tc = 2.0 * comprimento_m / c
    if tempo_manobra_s <= tc:
        dh = c * velocidade_ms / G
        regime = "Manobra rápida (Joukowsky)"
    else:
        dh = 2.0 * comprimento_m * velocidade_ms / (G * tempo_manobra_s)
        regime = "Manobra lenta (Michaud)"
    return {"celeridade": c, "tempo_critico": tc, "sobrepressao": dh, "regime": regime}


def diametro_bresse(q_m3s, k=1.2):
    """Diâmetro econômico de referência pela fórmula de Bresse: D = K·√Q (m)."""
    return k * math.sqrt(q_m3s)
