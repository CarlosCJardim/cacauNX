"""Coeficientes de cultura (Kc) — FAO-56, Tabelas 11 e 12, com ajuste climático (Eq. 62).

Inclui culturas de interesse no Brasil. Os valores de Kc tabelados referem-se a
clima sub-úmido (URmín ≈ 45 %, u2 ≈ 2 m s⁻¹) e são ajustados automaticamente para
o clima local do projeto.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date, timedelta

import numpy as np
import pandas as pd


@dataclass
class Cultura:
    nome: str
    kc_ini: float
    kc_mid: float
    kc_end: float
    l_ini: int = 0
    l_dev: int = 0
    l_mid: int = 0
    l_late: int = 0
    h: float = 1.0  # altura máxima da cultura (m)
    perene: bool = False
    nota: str = ""
    kc_mensal: list = field(default_factory=list)  # opcional (12 valores) para perenes

    @property
    def ciclo(self) -> int:
        return int(self.l_ini + self.l_dev + self.l_mid + self.l_late)

    def to_dict(self):
        return asdict(self)


# nome: (kc_ini, kc_mid, kc_end, l_ini, l_dev, l_mid, l_late, h, perene, nota)
_TABELA = {
    "Cacau": (1.00, 1.05, 1.05, 0, 0, 0, 0, 3.0, True, "FAO-56 Tab. 12 (cacau). Para cacau sombreado ou a pleno sol, calibre com dados locais."),
    "Café (solo descoberto)": (0.90, 0.95, 0.95, 0, 0, 0, 0, 2.5, True, "FAO-56 Tab. 12 — cafezal sem cobertura vegetal nas entrelinhas."),
    "Café (com cobertura nas entrelinhas)": (1.05, 1.10, 1.10, 0, 0, 0, 0, 2.5, True, "FAO-56 Tab. 12 — com plantas daninhas/cobertura."),
    "Citros (70% de cobertura)": (0.70, 0.65, 0.70, 0, 0, 0, 0, 4.0, True, "FAO-56 Tab. 12 — sem cobertura do solo."),
    "Citros (50% de cobertura)": (0.65, 0.60, 0.65, 0, 0, 0, 0, 3.0, True, "FAO-56 Tab. 12 — sem cobertura do solo."),
    "Seringueira": (0.95, 1.00, 1.00, 0, 0, 0, 0, 10.0, True, "FAO-56 Tab. 12."),
    "Abacate": (0.60, 0.85, 0.75, 0, 0, 0, 0, 3.0, True, "FAO-56 Tab. 12 — sem cobertura do solo."),
    "Pastagem (pastejo rotacionado)": (0.40, 0.95, 0.85, 0, 0, 0, 0, 0.3, True, "FAO-56 Tab. 12 — média do pastejo rotacionado."),
    "Alfafa (média entre cortes)": (0.40, 0.95, 0.90, 0, 0, 0, 0, 0.7, True, "FAO-56 Tab. 12 — valor médio."),
    "Gramado (estação quente)": (0.80, 0.85, 0.85, 0, 0, 0, 0, 0.1, True, "FAO-56 Tab. 12 — gramas C4."),
    "Banana (1º ano)": (0.50, 1.10, 1.00, 120, 90, 120, 60, 3.0, False, "FAO-56 Tab. 11/12."),
    "Banana (2º ano)": (1.00, 1.20, 1.10, 120, 60, 180, 5, 4.0, False, "FAO-56 Tab. 11/12."),
    "Cana-de-açúcar (cana-planta)": (0.40, 1.25, 0.75, 35, 60, 190, 120, 3.0, False, "FAO-56 Tab. 11/12 (trópicos)."),
    "Cana-de-açúcar (soca)": (0.40, 1.25, 0.75, 25, 70, 135, 50, 3.0, False, "FAO-56 Tab. 11/12 (trópicos)."),
    "Milho (grão)": (0.30, 1.20, 0.35, 25, 40, 45, 30, 2.0, False, "FAO-56 Tab. 11/12."),
    "Milho verde / doce": (0.30, 1.15, 1.05, 20, 25, 25, 10, 1.5, False, "FAO-56 Tab. 11/12."),
    "Soja": (0.40, 1.15, 0.50, 20, 30, 60, 25, 0.8, False, "FAO-56 Tab. 11/12."),
    "Feijão (grão)": (0.40, 1.15, 0.35, 20, 30, 40, 20, 0.4, False, "FAO-56 Tab. 11/12."),
    "Trigo (primavera)": (0.30, 1.15, 0.40, 15, 30, 65, 40, 1.0, False, "FAO-56 Tab. 11/12 — usado no estudo de caso do OpenIrri."),
    "Algodão": (0.35, 1.18, 0.60, 30, 50, 60, 55, 1.3, False, "FAO-56 Tab. 11/12."),
    "Sorgo (grão)": (0.30, 1.05, 0.55, 20, 35, 40, 30, 1.5, False, "FAO-56 Tab. 11/12."),
    "Girassol": (0.35, 1.08, 0.35, 25, 35, 45, 25, 2.0, False, "FAO-56 Tab. 11/12."),
    "Amendoim": (0.40, 1.15, 0.60, 25, 35, 45, 25, 0.4, False, "FAO-56 Tab. 11/12."),
    "Tomate": (0.60, 1.15, 0.80, 30, 40, 40, 25, 0.6, False, "FAO-56 Tab. 11/12."),
    "Batata": (0.50, 1.15, 0.75, 25, 30, 45, 30, 0.6, False, "FAO-56 Tab. 11/12."),
    "Cebola (bulbo)": (0.70, 1.05, 0.75, 15, 25, 70, 40, 0.4, False, "FAO-56 Tab. 11/12."),
    "Cenoura": (0.70, 1.05, 0.95, 20, 30, 50, 20, 0.3, False, "FAO-56 Tab. 11/12."),
    "Alface": (0.70, 1.00, 0.95, 20, 30, 15, 10, 0.3, False, "FAO-56 Tab. 11/12."),
    "Melancia": (0.40, 1.00, 0.75, 20, 30, 30, 30, 0.4, False, "FAO-56 Tab. 11/12."),
    "Melão": (0.50, 1.05, 0.75, 25, 35, 40, 20, 0.3, False, "FAO-56 Tab. 11/12."),
    "Uva de mesa": (0.30, 0.85, 0.45, 20, 40, 120, 60, 2.0, False, "FAO-56 Tab. 11/12."),
}

CULTURAS = {
    nome: Cultura(nome, *v[:3], l_ini=v[3], l_dev=v[4], l_mid=v[5], l_late=v[6], h=v[7], perene=v[8], nota=v[9])
    for nome, v in _TABELA.items()
}


def obter_cultura(nome: str) -> Cultura:
    c = CULTURAS.get(nome)
    if c is None:
        return Cultura("Personalizada", 0.5, 1.0, 0.8, 20, 30, 40, 20, 1.0, False, "Definida pelo usuário.")
    return Cultura(**c.to_dict())


def ajuste_climatico_kc(kc_tab, u2, urmin, h):
    """Ajuste de Kc_mid / Kc_end para clima diferente do sub-úmido — FAO-56 Eq. 62.

    Kc = Kc_tab + [0,04 (u2 − 2) − 0,004 (URmín − 45)] (h/3)^0,3
    Limites de validade: 1 ≤ u2 ≤ 6 m/s, 20 ≤ URmín ≤ 80 %, 0,1 ≤ h ≤ 10 m.
    """
    u2c = np.clip(np.asarray(u2, dtype=float), 1.0, 6.0)
    urc = np.clip(np.asarray(urmin, dtype=float), 20.0, 80.0)
    hc = float(np.clip(h, 0.1, 10.0))
    return np.asarray(kc_tab, dtype=float) + (0.04 * (u2c - 2.0) - 0.004 * (urc - 45.0)) * (hc / 3.0) ** 0.3


def kc_dia_do_ciclo(c: Cultura, dia, kc_ini=None, kc_mid=None, kc_end=None):
    """Kc no dia ``dia`` (0 = semeadura) pela curva de 4 estágios (FAO-56 Fig. 25 / Eq. 66)."""
    kc_ini = c.kc_ini if kc_ini is None else kc_ini
    kc_mid = c.kc_mid if kc_mid is None else kc_mid
    kc_end = c.kc_end if kc_end is None else kc_end
    d = np.asarray(dia, dtype=float)
    e1 = c.l_ini
    e2 = e1 + c.l_dev
    e3 = e2 + c.l_mid
    e4 = e3 + c.l_late
    kc = np.where(
        d < e1, kc_ini,
        np.where(
            d < e2, kc_ini + (d - e1) / max(c.l_dev, 1) * (kc_mid - kc_ini),
            np.where(d < e3, kc_mid,
                     np.where(d < e4, kc_mid + (d - e3) / max(c.l_late, 1) * (kc_end - kc_mid), np.nan)),
        ),
    )
    return kc


def kc_ajustados(c: Cultura, u2_mensal, urmin_mensal, mes_plantio=1, dia_plantio=1, ajustar=True):
    """Retorna (kc_mid_aj, kc_end_aj, clima_usado) com o ajuste climático aplicado
    ao clima médio dos meses do estágio intermediário (ou do mês mais exigente
    para culturas perenes, calculado mês a mês em :func:`kc_mensal`)."""
    if not ajustar:
        return c.kc_mid, c.kc_end, None
    u2_m = np.asarray(u2_mensal, dtype=float)
    ur_m = np.asarray(urmin_mensal, dtype=float)
    if c.perene or c.ciclo == 0:
        u2c, urc = float(np.nanmean(u2_m)), float(np.nanmean(ur_m))
        meses_mid = list(range(1, 13))
    else:
        inicio = date(2001, mes_plantio, min(dia_plantio, 28))
        meio_ini = inicio + timedelta(days=c.l_ini + c.l_dev)
        meses_mid = sorted({(meio_ini + timedelta(days=k)).month for k in range(max(c.l_mid, 1))})
        idx = [m - 1 for m in meses_mid]
        u2c, urc = float(np.nanmean(u2_m[idx])), float(np.nanmean(ur_m[idx]))
    kc_mid = float(ajuste_climatico_kc(c.kc_mid, u2c, urc, c.h))
    kc_end = float(ajuste_climatico_kc(c.kc_end, u2c, urc, c.h)) if c.kc_end >= 0.45 else c.kc_end
    return kc_mid, kc_end, {"u2": u2c, "urmin": urc, "meses": meses_mid}


def kc_mensal(c: Cultura, u2_mensal=None, urmin_mensal=None, mes_plantio=1, dia_plantio=1, ajustar=True):
    """Kc médio de cada mês do ano e fração do mês com a cultura no campo.

    Retorna DataFrame (12 linhas) com colunas ``kc`` e ``fracao``.
    """
    meses = np.arange(1, 13)
    if c.perene or c.ciclo == 0:
        if c.kc_mensal and len(c.kc_mensal) == 12:
            kc = np.asarray(c.kc_mensal, dtype=float)
        elif ajustar and u2_mensal is not None and urmin_mensal is not None:
            kc = ajuste_climatico_kc(c.kc_mid, u2_mensal, urmin_mensal, c.h)
        else:
            kc = np.full(12, c.kc_mid)
        return pd.DataFrame({"kc": np.round(kc, 3), "fracao": np.ones(12)}, index=meses)
    if ajustar and u2_mensal is not None and urmin_mensal is not None:
        kc_mid, kc_end, _ = kc_ajustados(c, u2_mensal, urmin_mensal, mes_plantio, dia_plantio, True)
    else:
        kc_mid, kc_end = c.kc_mid, c.kc_end
    inicio = pd.Timestamp(2001, mes_plantio, min(dia_plantio, 28))
    dias = pd.date_range(inicio, periods=c.ciclo, freq="D")
    kc_d = kc_dia_do_ciclo(c, np.arange(c.ciclo), kc_mid=kc_mid, kc_end=kc_end)
    s = pd.Series(kc_d, index=dias.month)
    soma = s.groupby(level=0).sum()
    cont = s.groupby(level=0).count()
    kc_m = (soma / cont).reindex(meses)
    dias_mes = pd.Series([31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31], index=meses)
    frac = (cont.reindex(meses).fillna(0) / dias_mes).clip(upper=1.0)
    return pd.DataFrame({"kc": kc_m.fillna(0).round(3), "fracao": frac.round(3)}, index=meses)


def kc_por_data(c: Cultura, datas, mes_plantio=1, dia_plantio=1, kc_mid=None, kc_end=None, ano_plantio=None):
    """Série diária de Kc para uma lista de datas (usada no manejo).

    Para culturas anuais, a semeadura ocorre em (dia_plantio/mes_plantio) do ano
    ``ano_plantio`` (ou, se omitido, no ano mais recente anterior à primeira data).
    Fora do ciclo o Kc é NaN (sem irrigação).
    """
    idx = pd.DatetimeIndex(datas)
    if c.perene or c.ciclo == 0:
        if c.kc_mensal and len(c.kc_mensal) == 12:
            vals = np.asarray(c.kc_mensal)[idx.month - 1]
        else:
            vals = np.full(len(idx), kc_mid if kc_mid is not None else c.kc_mid)
        return pd.Series(vals, index=idx, name="kc")
    if ano_plantio is None:
        primeira = idx.min()
        ano_plantio = primeira.year
        if pd.Timestamp(ano_plantio, mes_plantio, min(dia_plantio, 28)) > primeira:
            ano_plantio -= 1
    plantio = pd.Timestamp(int(ano_plantio), mes_plantio, min(dia_plantio, 28))
    dias = (idx - plantio).days.values
    kc = kc_dia_do_ciclo(c, dias, kc_mid=kc_mid, kc_end=kc_end)
    kc = np.where(dias < 0, np.nan, kc)
    return pd.Series(kc, index=idx, name="kc")
