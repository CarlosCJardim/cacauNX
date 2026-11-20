"""Estatística climática para projeto: normais mensais, ETc de projeto
probabilística, precipitação efetiva e tanque Classe A."""

from __future__ import annotations

import numpy as np
import pandas as pd

MESES = ["Jan", "Fev", "Mar", "Abr", "Mai", "Jun", "Jul", "Ago", "Set", "Out", "Nov", "Dez"]
DIAS_MES = np.array([31, 28.25, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31])


def normais_de_serie(df: pd.DataFrame, col_eto: str = "eto") -> pd.DataFrame:
    """Médias mensais (normais) a partir de uma série diária.

    Retorna 12 linhas com: eto (mm/d média), eto_p80 (mm/d, percentil 80 das médias
    mensais de cada ano), chuva (mm/mês, média dos totais anuais do mês),
    tmax, tmin, ur, urmin, u2, rs (médias), n_anos.
    """
    d = df.copy()
    d["ano"] = d.index.year
    d["mes"] = d.index.month
    out = pd.DataFrame(index=range(1, 13))
    out.index.name = "mes"
    if col_eto in d:
        mensal_ano = d.groupby(["ano", "mes"])[col_eto].mean().unstack()
        out["eto"] = mensal_ano.mean()
        out["eto_p80"] = mensal_ano.quantile(0.8)
    if "chuva" in d:
        tot = d.groupby(["ano", "mes"])["chuva"].sum(min_count=20).unstack()
        out["chuva"] = tot.mean()
        out["chuva_p75"] = tot.quantile(0.25)  # chuva provável a 75% (excedida em 75% dos anos)
    for c in ("tmax", "tmin", "ur", "urmin", "u2", "rs", "tdew"):
        if c in d:
            out[c] = d.groupby("mes")[c].mean()
    out["n_anos"] = d.groupby("mes")["ano"].nunique()
    out.insert(0, "Mês", MESES)
    return out


def etc_projeto_probabilistico(etc_diaria: pd.Series, janela_dias: int, prob: float = 0.80):
    """ETc de projeto pela análise de frequência dos máximos anuais da média móvel.

    Para cada ano calcula-se o máximo da média móvel de ``janela_dias`` (= turno de
    rega) da ETc diária; o valor de projeto é o quantil ``prob`` (probabilidade de
    não excedência) desses máximos (Doorenbos & Pruitt, 1977; Allen et al., 1998).

    Retorna dict(valor, maximos_anuais (Series), janela, prob).
    """
    s = etc_diaria.dropna()
    if s.empty:
        raise ValueError("Série de ETc vazia.")
    janela = max(1, int(janela_dias))
    movel = s.rolling(janela, min_periods=janela).mean()
    maximos = movel.groupby(movel.index.year).max().dropna()
    # Descarta anos incompletos (menos de 300 dias)
    contagem = s.groupby(s.index.year).count()
    maximos = maximos[contagem.reindex(maximos.index).fillna(0) >= 300] if len(maximos) > 2 else maximos
    if maximos.empty:
        maximos = movel.groupby(movel.index.year).max().dropna()
    valor = float(np.quantile(maximos.values, prob)) if len(maximos) > 1 else float(maximos.iloc[0])
    return {"valor": valor, "maximos_anuais": maximos, "janela": janela, "prob": prob}


# ---------------------------------------------------------------------------
# Precipitação efetiva
# ---------------------------------------------------------------------------
METODOS_PE = {
    "usda": "USDA-SCS (CROPWAT)",
    "fao": "FAO/AGLW (chuva confiável)",
    "fixa": "Percentual fixo",
    "nenhuma": "Desconsiderar a chuva",
}


def precipitacao_efetiva_mensal(p_mm, metodo: str = "usda", fracao: float = 0.8):
    """Precipitação efetiva mensal (mm/mês)."""
    p = np.asarray(p_mm, dtype=float)
    if metodo == "usda":
        return np.where(p <= 250.0, p * (125.0 - 0.2 * p) / 125.0, 125.0 + 0.1 * p)
    if metodo == "fao":
        return np.maximum(np.where(p <= 70.0, 0.6 * p - 10.0, 0.8 * p - 24.0), 0.0)
    if metodo == "fixa":
        return p * fracao
    return np.zeros_like(p)


def precipitacao_efetiva_diaria(p_mm, limiar_mm: float = 5.0, fracao: float = 0.8):
    """Precipitação efetiva diária para manejo pelo clima.

    Chuvas abaixo do limiar são consideradas interceptadas/evaporadas (Pe = 0);
    acima dele, aplica-se a fração de aproveitamento.
    """
    p = np.nan_to_num(np.asarray(p_mm, dtype=float))
    return np.where(p < limiar_mm, 0.0, p * fracao)


# ---------------------------------------------------------------------------
# Tanque Classe A
# ---------------------------------------------------------------------------
def kp_snyder(bordadura_m: float, vento_km_dia: float, ur_media: float) -> float:
    """Coeficiente do tanque Classe A (Snyder, 1992), tanque circundado por grama.

    Kp = 0,482 + 0,024 ln(B) − 0,000376 U + 0,0045 UR
    B: bordadura (m), U: vento a 2 m (km/d), UR: umidade relativa média (%).
    """
    b = max(float(bordadura_m), 1.0)
    return float(np.clip(0.482 + 0.024 * np.log(b) - 0.000376 * vento_km_dia + 0.0045 * ur_media, 0.35, 1.1))


def kp_fao(bordadura_m: float, vento_ms: float, ur_media: float) -> float:
    """Kp aproximado da Tabela 5 da FAO-56 (caso A, bordadura verde) por interpolação.

    Usa a forma analítica de Allen & Pruitt (1991):
    Kp = 0,108 − 0,0286u + 0,0422 ln(B) + 0,1434 ln(UR) − 0,000631 [ln(B)]² ln(UR)
    """
    u = float(vento_ms)
    b = max(float(bordadura_m), 1.0)
    ur = float(np.clip(ur_media, 10.0, 100.0))
    kp = 0.108 - 0.0286 * u + 0.0422 * np.log(b) + 0.1434 * np.log(ur) - 0.000631 * np.log(b) ** 2 * np.log(ur)
    return float(np.clip(kp, 0.35, 0.85))
