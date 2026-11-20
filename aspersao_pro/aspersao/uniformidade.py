"""Simulação da distribuição de água por superposição de perfis radiais e
coeficientes de uniformidade (Christiansen, CUD, Hart).

Assim como no OpenIrri, as lâminas individuais não vêm de ensaio de coletores:
são geradas pela superposição do perfil radial do aspersor sobre a malha de
espaçamento, considerando os aspersores vizinhos. Inclui um modelo simplificado
de distorção do padrão pelo vento.
"""

from __future__ import annotations

from functools import lru_cache

import numpy as np

PERFIS = {
    "auto": "Automático (conforme a pressão)",
    "eliptico": "Elíptico (pressão adequada, 2 bocais)",
    "triangular": "Triangular (1 bocal)",
    "trapezoidal": "Trapezoidal",
    "rosca": "Rosca (pressão baixa)",
    "concentrado": "Concentrado (pressão excessiva)",
    "tabela": "Perfil medido (tabela radial)",
}


def perfil_relativo(tipo: str, rho, radial_tab=None):
    """Lâmina relativa f(ρ) em função do raio normalizado ρ = r/R (0 ≤ ρ ≤ 1)."""
    rho = np.asarray(rho, dtype=float)
    dentro = rho <= 1.0
    r = np.clip(rho, 0.0, 1.0)
    if tipo == "triangular":
        f = 1.0 - r
    elif tipo == "trapezoidal":
        f = np.where(r < 0.5, 1.0, 2.0 * (1.0 - r))
    elif tipo == "rosca":
        a_ = np.clip(r / 0.65, 0.0, 1.0)
        b_ = np.clip((r - 0.65) / 0.35, 0.0, 1.0)
        f = np.where(r <= 0.65, 0.45 + 0.55 * a_ ** 1.5, 1.0 - b_ ** 1.5)
    elif tipo == "concentrado":
        f = (1.0 - r) ** 1.6
    elif tipo == "tabela" and radial_tab:
        tab = np.asarray(radial_tab, dtype=float)
        rr = tab[:, 0] / tab[:, 0].max()
        f = np.interp(r, rr, tab[:, 1], right=0.0)
    else:  # elíptico
        f = np.sqrt(np.clip(1.0 - r ** 2, 0.0, 1.0))
    return np.where(dentro, np.clip(f, 0.0, None), 0.0)


def perfil_automatico(p_kpa: float, p_min: float, p_max: float, n_bocais: int = 2) -> str:
    """Seleciona o perfil típico conforme a posição da pressão na faixa recomendada."""
    faixa = max(p_max - p_min, 1e-6)
    pos = (p_kpa - p_min) / faixa
    if pos < -0.05:
        return "rosca"
    if pos > 1.10:
        return "concentrado"
    if n_bocais == 1:
        return "triangular" if pos > 0.4 else "trapezoidal"
    return "eliptico" if pos <= 0.85 else "triangular"


@lru_cache(maxsize=64)
def _integral_cache(tipo, radial_key):
    radial_tab = [list(p) for p in radial_key] if radial_key else None
    rho = np.linspace(0.0, 1.0, 4001)
    return float(np.trapezoid(perfil_relativo(tipo, rho, radial_tab) * rho, rho))


def _integral_perfil(tipo, radial_tab=None):
    chave = tuple(tuple(float(v) for v in p) for p in radial_tab) if radial_tab else None
    return _integral_cache(tipo, chave)


def raios_vento(raio, vento_ms):
    """Semieixos do padrão molhado distorcido pelo vento (a favor, contra, transversal)."""
    u = max(float(vento_ms), 0.0)
    ld = raio * (1.0 + 0.06 * u)
    lu = raio * max(0.35, 1.0 - 0.10 * u)
    lc = raio * max(0.45, 1.0 - 0.07 * u)
    return ld, lu, lc


def taxa_aplicacao_pontual(dx, dy, q_m3h, raio, tipo, vento_ms=0.0, dir_vento_graus=0.0, radial_tab=None):
    """Intensidade de aplicação (mm/h) num ponto à distância (dx, dy) do aspersor."""
    ld, lu, lc = raios_vento(raio, vento_ms)
    a = np.radians(dir_vento_graus)
    xp = dx * np.cos(a) + dy * np.sin(a)  # componente a favor do vento
    yp = -dx * np.sin(a) + dy * np.cos(a)
    lx = np.where(xp >= 0, ld, lu)
    rho = np.sqrt((xp / lx) ** 2 + (yp / lc) ** 2)
    integral = _integral_perfil(tipo, radial_tab)
    escala = 1000.0 * q_m3h / (np.pi * (ld + lu) * lc * integral)
    return escala * perfil_relativo(tipo, rho, radial_tab)


def coeficientes(laminas):
    """CUC (Christiansen), CUD (quartil inferior) e CUH (Hart) em %."""
    x = np.asarray(laminas, dtype=float).ravel()
    media = x.mean()
    if media <= 0:
        return {"CUC": 0.0, "CUD": 0.0, "CUH": 0.0, "media": 0.0}
    cuc = 100.0 * (1.0 - np.abs(x - media).sum() / (x.size * media))
    n25 = max(1, int(round(0.25 * x.size)))
    cud = 100.0 * np.sort(x)[:n25].mean() / media
    cuh = 100.0 * (1.0 - np.sqrt(2.0 / np.pi) * x.std() / media)
    return {"CUC": float(cuc), "CUD": float(cud), "CUH": float(cuh), "media": float(media),
            "min": float(x.min()), "max": float(x.max())}


def simular_malha(q_m3h, diametro_m, esp_asp, esp_lat, arranjo="retangular", tipo="eliptico",
                  vento_ms=0.0, dir_vento_graus=0.0, pontos=24, radial_tab=None):
    """Simula a distribuição numa célula interna (esp_asp × esp_lat) de uma área
    totalmente sobreposta.

    Retorna dict com malha X, Y (m), lâmina L (mm/h), coeficientes e intensidade média.
    """
    raio = diametro_m / 2.0
    ld, lu, lc = raios_vento(raio, vento_ms)
    alcance = max(ld, lu, lc)
    nx = pontos
    ny = max(8, int(round(pontos * esp_lat / max(esp_asp, 1e-6))))
    xs = (np.arange(nx) + 0.5) * esp_asp / nx
    ys = (np.arange(ny) + 0.5) * esp_lat / ny
    X, Y = np.meshgrid(xs, ys)
    ni = int(np.ceil(alcance / esp_asp)) + 2
    nj = int(np.ceil(alcance / esp_lat)) + 2
    jj, ii = np.meshgrid(np.arange(-nj, nj + 1), np.arange(-ni, ni + 1), indexing="ij")
    desloc = (esp_asp / 2.0) * (jj % 2) if arranjo == "triangular" else 0.0
    sx = (ii * esp_asp + desloc).ravel()[:, None, None]
    sy = (jj * esp_lat).ravel()[:, None, None]
    L = taxa_aplicacao_pontual(X[None] - sx, Y[None] - sy, q_m3h, raio, tipo, vento_ms,
                               dir_vento_graus, radial_tab).sum(axis=0)
    coef = coeficientes(L)
    ia = 1000.0 * q_m3h / (esp_asp * esp_lat)
    return {"X": X, "Y": Y, "L": L, **coef, "Ia": ia, "erro_balanco_pct": 100.0 * (coef["media"] - ia) / ia}


def padrao_individual(q_m3h, diametro_m, tipo="eliptico", vento_ms=0.0, dir_vento_graus=0.0, n=81, radial_tab=None):
    """Padrão de um único aspersor (para visualização)."""
    raio = diametro_m / 2.0
    ld, _, _ = raios_vento(raio, vento_ms)
    ext = 1.05 * ld
    xs = np.linspace(-ext, ext, n)
    X, Y = np.meshgrid(xs, xs)
    L = taxa_aplicacao_pontual(X, Y, q_m3h, raio, tipo, vento_ms, dir_vento_graus, radial_tab)
    return {"x": xs, "y": xs, "L": L}


def eficiencia_distribuicao(cuc: float, adequacao_pct: float) -> float:
    """Eficiência de distribuição para a fração adequadamente irrigada a (%), assumindo
    distribuição normal das lâminas (Keller & Bliesner):

    Ed_a = 100 + (606 − 24,9 a + 0,349 a² − 0,00186 a³)(1 − CUC/100)
    """
    a = float(np.clip(adequacao_pct, 50.0, 99.0))
    termo = 606.0 - 24.9 * a + 0.349 * a ** 2 - 0.00186 * a ** 3
    return float(np.clip(100.0 + termo * (1.0 - cuc / 100.0), 10.0, 100.0))


def perdas_evaporacao_deriva(d_bocal_mm, dpv_kpa, p_kpa, vento_ms):
    """Perdas por evaporação e deriva (%) — Trimmer (1987), ajuste do nomograma de
    Frost & Schwalen (1955):

    Pe = [1,98 D^-0,72 + 0,22 (es−ea)^0,63 + 3,6·10⁻⁴ h^1,16 + 0,14 W^0,7]^4,2
    D: bocal (mm); es−ea: déficit de pressão de vapor (kPa); h: pressão (kPa); W: vento (km/h).
    """
    d = max(float(d_bocal_mm), 1.0)
    w = max(float(vento_ms), 0.0) * 3.6
    termo = 1.98 * d ** -0.72 + 0.22 * max(dpv_kpa, 0.0) ** 0.63 + 3.6e-4 * max(p_kpa, 0.0) ** 1.16 + 0.14 * w ** 0.7
    return float(np.clip(termo ** 4.2, 0.0, 45.0))


def eficiencia_aplicacao(cuc, adequacao_pct, perdas_evap_pct, ef_conducao=1.0):
    """Ea = Ed_a × (1 − perdas por evaporação/deriva) × eficiência de condução."""
    ed = eficiencia_distribuicao(cuc, adequacao_pct) / 100.0
    return float(ed * (1.0 - perdas_evap_pct / 100.0) * ef_conducao)


def otimizar_espacamentos(catalogo, lamina_bruta_mm, jornada_h, vib_mmh, vento_ms, dir_vento=0.0,
                          espacamentos=(6, 12, 18, 24, 30, 36), arranjos=("retangular", "triangular"),
                          cuc_min=80.0, ti_max_h=None, pontos=14, tipos_filtro=None):
    """Varre aspersores × pressões × espaçamentos e ordena as alternativas viáveis.

    Critérios: CUC ≥ cuc_min; Ia ≤ VIB; tempo de aplicação ≤ jornada (ou ti_max);
    ordenação por CUC (desc.) e potência hidráulica específica (asc.).
    """
    import pandas as pd

    linhas = []
    ti_lim = ti_max_h or jornada_h
    for asp in catalogo:
        if tipos_filtro and asp.tipo not in tipos_filtro:
            continue
        n_bocais = len(asp.bocal.split("x"))
        for p in sorted(set([asp.p_min, asp.p_nominal, asp.p_max])):
            q = float(asp.vazao(p))
            dm = asp.diametro(p)
            for ea_ in espacamentos:
                for el in espacamentos:
                    if ea_ > el or ea_ > 0.75 * dm or el > 0.85 * dm:
                        continue
                    for arr in arranjos:
                        ia = 1000.0 * q / (ea_ * el)
                        if ia > vib_mmh:
                            continue
                        ti = lamina_bruta_mm / ia
                        if ti > ti_lim:
                            continue
                        tipo = perfil_automatico(p, asp.p_min, asp.p_max, n_bocais)
                        r = simular_malha(q, dm, ea_, el, arr, tipo, vento_ms, dir_vento, pontos)
                        if r["CUC"] < cuc_min:
                            continue
                        # potência hidráulica por hectare (kW/ha) — indicador energético
                        pot = 9.81 * (q / 3600.0) * (p / 9.80665) * (10000.0 / (ea_ * el))
                        linhas.append({
                            "ID": asp.id, "Aspersor": asp.rotulo, "Pressão (kPa)": round(p),
                            "Vazão (m³/h)": round(q, 3), "Dm (m)": round(dm, 1),
                            "Espaçamento (m)": f"{ea_} x {el}", "esp_asp": ea_, "esp_lat": el,
                            "Arranjo": arr, "Ia (mm/h)": round(ia, 2), "Ti (h)": round(ti, 2),
                            "CUC (%)": round(r["CUC"], 1), "CUD (%)": round(r["CUD"], 1),
                            "Aspersores/ha": round(10000.0 / (ea_ * el), 1),
                            "Potência hidráulica (kW/ha)": round(pot, 2),
                        })
    df = pd.DataFrame(linhas)
    if df.empty:
        return df
    df["Índice"] = (df["CUC (%)"] / 100.0) / (df["Potência hidráulica (kW/ha)"] ** 0.35) / (df["Aspersores/ha"] ** 0.25)
    return df.sort_values(["Índice", "CUC (%)"], ascending=False).reset_index(drop=True)
