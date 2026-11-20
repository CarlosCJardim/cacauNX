"""Evapotranspiração de referência — FAO-56 Penman-Monteith e métodos alternativos.

Implementação vetorizada (NumPy) das equações do boletim FAO-56
(Allen, Pereira, Raes & Smith, 1998). Os números das equações citados nas
docstrings referem-se ao boletim.

Unidades: temperatura em °C, radiação em MJ m⁻² d⁻¹, vento em m s⁻¹,
pressões em kPa, altitude em m, ETo em mm d⁻¹.
"""

from __future__ import annotations

import numpy as np

SIGMA = 4.903e-9  # constante de Stefan-Boltzmann (MJ K⁻⁴ m⁻² d⁻¹)
GSC = 0.0820  # constante solar (MJ m⁻² min⁻¹)


# ---------------------------------------------------------------------------
# Parâmetros atmosféricos
# ---------------------------------------------------------------------------
def pressao_atmosferica(z):
    """Pressão atmosférica (kPa) em função da altitude z (m) — Eq. 7."""
    z = np.asarray(z, dtype=float)
    return 101.3 * ((293.0 - 0.0065 * z) / 293.0) ** 5.26


def constante_psicrometrica(p_kpa):
    """Constante psicrométrica γ (kPa °C⁻¹) — Eq. 8."""
    return 0.665e-3 * np.asarray(p_kpa, dtype=float)


def pressao_saturacao(t):
    """Pressão de saturação de vapor e°(T) (kPa) — Eq. 11."""
    t = np.asarray(t, dtype=float)
    return 0.6108 * np.exp(17.27 * t / (t + 237.3))


def declividade_curva_pressao(t):
    """Declividade da curva de pressão de saturação Δ (kPa °C⁻¹) — Eq. 13."""
    t = np.asarray(t, dtype=float)
    return 4098.0 * pressao_saturacao(t) / (t + 237.3) ** 2


def es_media(tmax, tmin):
    """Pressão de saturação média diária es (kPa) — Eq. 12."""
    return (pressao_saturacao(tmax) + pressao_saturacao(tmin)) / 2.0


def ea_tdew(tdew):
    """Pressão real de vapor a partir da temperatura do ponto de orvalho — Eq. 14."""
    return pressao_saturacao(tdew)


def ea_urmax_urmin(tmax, tmin, urmax, urmin):
    """Pressão real de vapor a partir de URmáx e URmín (%) — Eq. 17."""
    urmax = np.clip(np.asarray(urmax, dtype=float), 0, 100)
    urmin = np.clip(np.asarray(urmin, dtype=float), 0, 100)
    return (pressao_saturacao(tmin) * urmax / 100.0 + pressao_saturacao(tmax) * urmin / 100.0) / 2.0


def ea_urmed(tmax, tmin, urmed):
    """Pressão real de vapor a partir da UR média (%) — Eq. 19."""
    urmed = np.clip(np.asarray(urmed, dtype=float), 0, 100)
    return urmed / 100.0 * es_media(tmax, tmin)


def ea_tmin(tmin, ko=0.0):
    """Estimativa de ea quando não há dados de umidade (Tdew ≈ Tmin − Ko) — Eq. 48."""
    return pressao_saturacao(np.asarray(tmin, dtype=float) - ko)


def calcular_ea(tmax, tmin, tdew=None, urmax=None, urmin=None, urmed=None):
    """Escolhe automaticamente o melhor método de ea conforme os dados disponíveis
    (ordem de preferência FAO-56: Tdew > URmáx/URmín > URméd > Tmín).

    Aceita escalares ou vetores; valores ausentes (NaN) caem no próximo método.
    """
    tmax = np.asarray(tmax, dtype=float)
    tmin = np.asarray(tmin, dtype=float)
    ea = np.full(np.broadcast(tmax, tmin).shape, np.nan)
    candidatos = []
    if tdew is not None:
        candidatos.append(ea_tdew(tdew))
    if urmax is not None and urmin is not None:
        candidatos.append(ea_urmax_urmin(tmax, tmin, urmax, urmin))
    if urmed is not None:
        candidatos.append(ea_urmed(tmax, tmin, urmed))
    candidatos.append(ea_tmin(tmin))
    for c in candidatos:
        c = np.broadcast_to(np.asarray(c, dtype=float), ea.shape)
        ea = np.where(np.isnan(ea), c, ea)
    return ea


# ---------------------------------------------------------------------------
# Radiação
# ---------------------------------------------------------------------------
def _componentes_solares(lat_graus, dia_juliano):
    phi = np.radians(np.asarray(lat_graus, dtype=float))
    j = np.asarray(dia_juliano, dtype=float)
    dr = 1.0 + 0.033 * np.cos(2.0 * np.pi * j / 365.0)  # Eq. 23
    dec = 0.409 * np.sin(2.0 * np.pi * j / 365.0 - 1.39)  # Eq. 24
    ws = np.arccos(np.clip(-np.tan(phi) * np.tan(dec), -1.0, 1.0))  # Eq. 25
    return phi, dr, dec, ws


def radiacao_extraterrestre(lat_graus, dia_juliano):
    """Radiação extraterrestre Ra (MJ m⁻² d⁻¹) — Eq. 21."""
    phi, dr, dec, ws = _componentes_solares(lat_graus, dia_juliano)
    return (24.0 * 60.0 / np.pi) * GSC * dr * (
        ws * np.sin(phi) * np.sin(dec) + np.cos(phi) * np.cos(dec) * np.sin(ws)
    )


def fotoperiodo(lat_graus, dia_juliano):
    """Duração máxima do brilho solar N (h) — Eq. 34."""
    _, _, _, ws = _componentes_solares(lat_graus, dia_juliano)
    return 24.0 / np.pi * ws


def rs_angstrom(n_horas, lat_graus, dia_juliano, a_s=0.25, b_s=0.50):
    """Radiação solar global pela equação de Angström a partir da insolação n (h) — Eq. 35."""
    ra = radiacao_extraterrestre(lat_graus, dia_juliano)
    n_max = fotoperiodo(lat_graus, dia_juliano)
    razao = np.clip(np.asarray(n_horas, dtype=float) / n_max, 0.0, 1.0)
    return (a_s + b_s * razao) * ra


def rs_hargreaves(tmax, tmin, lat_graus, dia_juliano, krs=0.16):
    """Radiação solar estimada pela amplitude térmica (Hargreaves) — Eq. 50.

    krs = 0,16 para regiões interiores e 0,19 para regiões costeiras.
    """
    ra = radiacao_extraterrestre(lat_graus, dia_juliano)
    amp = np.clip(np.asarray(tmax, dtype=float) - np.asarray(tmin, dtype=float), 0.0, None)
    rs = krs * np.sqrt(amp) * ra
    rso = radiacao_ceu_claro(ra, 0.0)
    return np.minimum(rs, rso)


def radiacao_ceu_claro(ra, z):
    """Radiação de céu claro Rso (MJ m⁻² d⁻¹) — Eq. 37."""
    return (0.75 + 2e-5 * np.asarray(z, dtype=float)) * ra


def saldo_onda_curta(rs, albedo=0.23):
    """Saldo de radiação de ondas curtas Rns — Eq. 38."""
    return (1.0 - albedo) * np.asarray(rs, dtype=float)


def saldo_onda_longa(tmax, tmin, ea, rs, rso):
    """Saldo de radiação de ondas longas Rnl — Eq. 39."""
    tmax_k4 = (np.asarray(tmax, dtype=float) + 273.16) ** 4
    tmin_k4 = (np.asarray(tmin, dtype=float) + 273.16) ** 4
    razao = np.clip(np.asarray(rs, dtype=float) / np.asarray(rso, dtype=float), 0.3, 1.0)
    return SIGMA * (tmax_k4 + tmin_k4) / 2.0 * (0.34 - 0.14 * np.sqrt(np.asarray(ea, dtype=float))) * (
        1.35 * razao - 0.35
    )


def vento_2m(uz, z_medicao):
    """Converte a velocidade do vento medida à altura z para 2 m — Eq. 47."""
    uz = np.asarray(uz, dtype=float)
    if np.isclose(z_medicao, 2.0):
        return uz
    return uz * 4.87 / np.log(67.8 * z_medicao - 5.42)


# ---------------------------------------------------------------------------
# ETo
# ---------------------------------------------------------------------------
def et0_penman_monteith(tmax, tmin, rs, u2, ea, lat_graus, dia_juliano, z, g=0.0, tmed=None):
    """ETo FAO-56 Penman-Monteith (mm d⁻¹) — Eq. 6.

    Parâmetros
    ----------
    tmax, tmin : temperaturas máxima e mínima do ar (°C)
    rs : radiação solar global (MJ m⁻² d⁻¹)
    u2 : velocidade do vento a 2 m (m s⁻¹)
    ea : pressão real de vapor (kPa)
    lat_graus : latitude (graus decimais; negativa no hemisfério sul)
    dia_juliano : dia do ano (1–366)
    z : altitude (m)
    g : fluxo de calor no solo (MJ m⁻² d⁻¹), 0 para escala diária
    tmed : temperatura média; se omitida, usa (Tmax+Tmin)/2 (recomendação FAO-56)
    """
    tmax = np.asarray(tmax, dtype=float)
    tmin = np.asarray(tmin, dtype=float)
    t = (tmax + tmin) / 2.0 if tmed is None else np.asarray(tmed, dtype=float)
    es = es_media(tmax, tmin)
    delta = declividade_curva_pressao(t)
    gama = constante_psicrometrica(pressao_atmosferica(z))
    ra = radiacao_extraterrestre(lat_graus, dia_juliano)
    rso = radiacao_ceu_claro(ra, z)
    rn = saldo_onda_curta(rs) - saldo_onda_longa(tmax, tmin, ea, rs, rso)
    u2 = np.asarray(u2, dtype=float)
    num = 0.408 * delta * (rn - g) + gama * (900.0 / (t + 273.0)) * u2 * (es - np.asarray(ea, dtype=float))
    den = delta + gama * (1.0 + 0.34 * u2)
    return np.maximum(num / den, 0.0)


def et0_hargreaves(tmax, tmin, lat_graus, dia_juliano, tmed=None):
    """ETo por Hargreaves-Samani (1985) — Eq. 52 (mm d⁻¹)."""
    tmax = np.asarray(tmax, dtype=float)
    tmin = np.asarray(tmin, dtype=float)
    t = (tmax + tmin) / 2.0 if tmed is None else np.asarray(tmed, dtype=float)
    ra = radiacao_extraterrestre(lat_graus, dia_juliano)
    return np.maximum(0.0023 * (t + 17.8) * np.sqrt(np.clip(tmax - tmin, 0, None)) * 0.408 * ra, 0.0)


def dia_juliano_meio_mes(mes):
    """Dia juliano do meio do mês (aproximação FAO-56: J = int(30,4 M − 15))."""
    mes = np.asarray(mes, dtype=float)
    return np.floor(30.4 * mes - 15.0).astype(int)


def g_mensal(t_mes_anterior, t_mes_posterior):
    """Fluxo de calor no solo mensal — Eq. 43 (meses anterior e posterior)."""
    return 0.07 * (np.asarray(t_mes_posterior) - np.asarray(t_mes_anterior))


def et0_mensal_normais(tmax, tmin, lat, z, u2=None, urmed=None, urmax=None, urmin=None, tdew=None,
                       insolacao=None, rs=None, krs=0.16):
    """ETo média diária de cada mês (mm d⁻¹) a partir de 12 normais climatológicas.

    Usa Penman-Monteith quando há umidade e vento; caso contrário assume
    u2 = 2 m s⁻¹ e ea ≈ e°(Tmin) (procedimento FAO-56 para dados ausentes).
    A radiação é obtida, nesta ordem: rs informado → insolação (Angström) →
    Hargreaves (amplitude térmica).
    Retorna (eto, metodo_rs_usado, g) onde g é o fluxo de calor mensal estimado.
    """
    tmax = np.asarray(tmax, dtype=float)
    tmin = np.asarray(tmin, dtype=float)
    meses = np.arange(1, 13)
    j = dia_juliano_meio_mes(meses)
    if rs is not None and not np.all(np.isnan(np.asarray(rs, dtype=float))):
        rs_v = np.asarray(rs, dtype=float)
        metodo = "Radiação informada"
    elif insolacao is not None and not np.all(np.isnan(np.asarray(insolacao, dtype=float))):
        rs_v = rs_angstrom(insolacao, lat, j)
        metodo = "Angström (insolação)"
    else:
        rs_v = rs_hargreaves(tmax, tmin, lat, j, krs)
        metodo = f"Hargreaves (kRs={krs:.2f})"
    u2_v = np.full(12, 2.0) if u2 is None else np.asarray(u2, dtype=float)
    ea = calcular_ea(tmax, tmin, tdew=tdew, urmax=urmax, urmin=urmin, urmed=urmed)
    t = (tmax + tmin) / 2.0
    g = g_mensal(np.roll(t, 1), np.roll(t, -1))
    eto = et0_penman_monteith(tmax, tmin, rs_v, u2_v, ea, lat, j, z, g=g)
    return eto, metodo, g


def et0_diario_df(df, lat, z, krs=0.16, altura_vento=2.0):
    """Calcula ETo Penman-Monteith dia a dia para um DataFrame diário.

    Colunas reconhecidas: tmax, tmin, tmed, tdew, ur, urmax, urmin, u2 (ou u10 / vento),
    rs, insolacao. Índice deve ser DatetimeIndex. Quando faltam variáveis num dia,
    aplica os procedimentos de dados ausentes da FAO-56 e, em último caso,
    Hargreaves-Samani. Retorna uma cópia com as colunas 'eto_pm' e 'metodo_eto'.
    """
    import pandas as pd

    d = df.copy()
    n = len(d)
    j = d.index.dayofyear.values
    col = lambda nome: d[nome].values.astype(float) if nome in d else np.full(n, np.nan)  # noqa: E731
    tmax, tmin = col("tmax"), col("tmin")
    # Vento a 2 m
    if "u2" in d:
        u2 = col("u2")
    elif "u10" in d:
        u2 = vento_2m(col("u10"), 10.0)
    elif "vento" in d:
        u2 = vento_2m(col("vento"), altura_vento)
    else:
        u2 = np.full(n, np.nan)
    sem_vento = np.isnan(u2)
    u2 = np.where(sem_vento, 2.0, u2)
    # Radiação
    rs = col("rs")
    rs_ang = rs_angstrom(col("insolacao"), lat, j) if "insolacao" in d else np.full(n, np.nan)
    rs_har = rs_hargreaves(tmax, tmin, lat, j, krs)
    sem_rs = np.isnan(rs) & np.isnan(rs_ang)
    rs = np.where(np.isnan(rs), rs_ang, rs)
    rs = np.where(np.isnan(rs), rs_har, rs)
    # Umidade
    ea = calcular_ea(
        tmax, tmin,
        tdew=col("tdew") if "tdew" in d else None,
        urmax=col("urmax") if "urmax" in d else None,
        urmin=col("urmin") if "urmin" in d else None,
        urmed=col("ur") if "ur" in d else None,
    )
    eto = et0_penman_monteith(tmax, tmin, rs, u2, ea, lat, j, z)
    eto_hs = et0_hargreaves(tmax, tmin, lat, j)
    metodo = np.where(sem_rs | sem_vento, "PM (dados estimados)", "Penman-Monteith")
    falta_t = np.isnan(tmax) | np.isnan(tmin)
    eto = np.where(np.isnan(eto), eto_hs, eto)
    metodo = np.where(falta_t, "ausente", metodo)
    d["eto_pm"] = np.round(eto, 3)
    d["metodo_eto"] = pd.Series(metodo, index=d.index)
    return d


def deficit_pressao_vapor(tmax, tmin, ea):
    """Déficit de pressão de vapor médio (kPa)."""
    return np.maximum(es_media(tmax, tmin) - np.asarray(ea, dtype=float), 0.0)


def urmin_estimada(tmax, ea):
    """UR mínima estimada (%) a partir de Tmax e ea — usada no ajuste climático do Kc."""
    return np.clip(100.0 * np.asarray(ea, dtype=float) / pressao_saturacao(tmax), 0, 100)
