"""Necessidade hídrica e dimensionamento agronômico orientado ao MANEJO PELO CLIMA.

No manejo pelo clima a lâmina de irrigação é a reposição da evapotranspiração da
cultura acumulada (ETc − Pe) desde a última irrigação, e o turno de rega (TR) é
uma decisão operacional — não é derivado da capacidade de água disponível do
solo. Assim, o projeto é dimensionado para repor a ETc de projeto em cada TR:

    LL = ETc_proj × TR       LB = LL / Ea       Ti = LB / Ia
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .clima.estatistica import DIAS_MES, MESES, precipitacao_efetiva_mensal


def tabela_mensal(eto_mmd, chuva_mm_mes, kc_df: pd.DataFrame, ea: float, area_ha: float,
                  metodo_pe: str = "usda", frac_pe: float = 0.8) -> pd.DataFrame:
    """Balanço climático mensal: ETo, Kc, ETc, P, Pe, necessidade líquida e bruta, volume."""
    eto = np.asarray(eto_mmd, dtype=float)
    p = np.asarray(chuva_mm_mes, dtype=float) if chuva_mm_mes is not None else np.zeros(12)
    kc = kc_df["kc"].values
    frac = kc_df["fracao"].values
    etc_d = eto * kc
    etc_m = etc_d * DIAS_MES * frac
    pe = precipitacao_efetiva_mensal(p, metodo_pe, frac_pe) * frac
    pe = np.minimum(pe, etc_m)
    nil = np.maximum(etc_m - pe, 0.0)
    nib = nil / ea if ea > 0 else nil
    vol = nib * area_ha * 10.0  # mm·ha → m³
    df = pd.DataFrame({
        "Mês": MESES, "ETo (mm/d)": eto.round(2), "Kc": kc.round(3), "ETc (mm/d)": etc_d.round(2),
        "ETc (mm/mês)": etc_m.round(1), "P (mm/mês)": p.round(1), "Pe (mm/mês)": pe.round(1),
        "NIL (mm/mês)": nil.round(1), "NIB (mm/mês)": nib.round(1), "Volume (m³)": vol.round(0),
    }, index=range(1, 13))
    return df


def etc_projeto(metodo: str, eto_mensal, kc_df: pd.DataFrame, chuva_ef_mensal=None,
                prob_resultado: dict | None = None, considerar_chuva=False):
    """ETc de projeto (mm/d).

    * 'conservador'  — Kc máximo × ETo máxima mensal (como no OpenIrri);
    * 'ciclo'        — maior ETc média mensal ao longo do ciclo (Kc do mês × ETo do mês);
    * 'probabilistico' — análise de frequência da série diária (ver estatística).
    Retorna (valor, mes_critico (1–12 ou None), descricao).
    """
    eto = np.asarray(eto_mensal, dtype=float)
    kc = kc_df["kc"].values
    if metodo == "probabilistico" and prob_resultado is not None:
        return float(prob_resultado["valor"]), None, (
            f"Quantil {prob_resultado['prob'] * 100:.0f}% dos máximos anuais da média móvel de "
            f"{prob_resultado['janela']} dias da ETc diária")
    if metodo == "ciclo":
        etc = eto * kc
        if considerar_chuva and chuva_ef_mensal is not None:
            etc = np.maximum(etc - np.asarray(chuva_ef_mensal) / DIAS_MES, 0.0)
        m = int(np.nanargmax(etc))
        return float(etc[m]), m + 1, f"Maior ETc média mensal do ciclo ({MESES[m]})"
    kc_max = float(np.nanmax(kc[kc > 0])) if np.any(kc > 0) else 1.0
    m = int(np.nanargmax(eto))
    return kc_max * float(eto[m]), m + 1, f"Kc máximo ({kc_max:.2f}) × ETo máxima ({MESES[m]})"


def projeto_agronomico(etc_proj_mmd: float, turno_rega_d: float, ea: float, pe_proj_mmd: float = 0.0,
                       lamina_max_mm: float | None = None) -> dict:
    """Lâminas de projeto para manejo pelo clima."""
    tr = max(float(turno_rega_d), 1.0)
    demanda = max(etc_proj_mmd - pe_proj_mmd, 0.0)
    ll = demanda * tr
    avisos = []
    if lamina_max_mm and ll > lamina_max_mm:
        avisos.append(f"Lâmina líquida de {ll:.1f} mm excede o limite informado de {lamina_max_mm:.1f} mm por "
                      f"evento — reduza o turno de rega.")
    lb = ll / ea if ea > 0 else ll
    return {"etc_proj": etc_proj_mmd, "demanda_liquida": demanda, "TR": tr, "LL": ll, "LB": lb, "Ea": ea,
            "LB_diaria": lb / tr, "avisos": avisos}


# Velocidade de infiltração básica típica (mm/h) — referência para a intensidade máxima
VIB_TEXTURA = {
    "Arenosa": 30.0,
    "Franco-arenosa": 20.0,
    "Franca (média)": 13.0,
    "Franco-argilosa": 8.0,
    "Argilosa": 5.0,
    "Muito argilosa / compactada": 3.0,
}
