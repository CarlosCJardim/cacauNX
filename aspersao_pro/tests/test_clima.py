"""Validação das rotinas FAO-56 contra os exemplos resolvidos do boletim."""
import numpy as np
import pandas as pd
import pytest

from aspersao.clima import penman as pm
from aspersao.clima.estatistica import (etc_projeto_probabilistico, kp_snyder, normais_de_serie,
                                        precipitacao_efetiva_diaria, precipitacao_efetiva_mensal)


def test_pressao_saturacao_e_declividade():
    assert pm.pressao_saturacao(25.0) == pytest.approx(3.168, abs=0.002)
    assert pm.declividade_curva_pressao(25.0) == pytest.approx(0.189, abs=0.001)


def test_pressao_atmosferica_exemplo2():
    # FAO-56 Exemplo 2: z = 1800 m → P = 81,8 kPa, γ = 0,054
    p = pm.pressao_atmosferica(1800)
    assert p == pytest.approx(81.8, abs=0.1)
    assert pm.constante_psicrometrica(p) == pytest.approx(0.054, abs=0.001)


def test_radiacao_extraterrestre_exemplo8():
    # 20° S, 3 de setembro (J = 246) → Ra = 32,2 MJ m-2 d-1
    assert pm.radiacao_extraterrestre(-20.0, 246) == pytest.approx(32.2, abs=0.1)


def test_vento_2m_exemplo14():
    assert pm.vento_2m(3.2, 10.0) == pytest.approx(2.4, abs=0.05)


def test_eto_diaria_exemplo18_bruxelas():
    lat, j, z = 50.0 + 48 / 60, 187, 100
    tmax, tmin = 21.5, 12.3
    ea = pm.ea_urmax_urmin(tmax, tmin, 84, 63)
    u2 = pm.vento_2m(10 / 3.6, 10.0)
    rs = pm.rs_angstrom(9.25, lat, j)
    eto = pm.et0_penman_monteith(tmax, tmin, rs, u2, ea, lat, j, z)
    assert float(eto) == pytest.approx(3.9, abs=0.1)


def test_eto_mensal_exemplo17_bangkok():
    lat, j, z = 13.0 + 44 / 60, 105, 2
    rs = pm.rs_angstrom(8.5, lat, j)
    eto = pm.et0_penman_monteith(34.8, 25.6, rs, 2.0, 2.85, lat, j, z, g=0.14)
    assert float(eto) == pytest.approx(5.72, abs=0.1)


def test_hargreaves_plausivel():
    eto = pm.et0_hargreaves(32.0, 18.0, -12.0, 250)
    assert 4.0 < float(eto) < 7.5


def test_eto_diario_df_com_dados_faltantes():
    idx = pd.date_range("2024-01-01", periods=10)
    df = pd.DataFrame({"tmax": 32.0, "tmin": 20.0, "ur": 60.0, "u2": 2.0, "rs": 22.0}, index=idx)
    df.loc[idx[3], "rs"] = np.nan
    df.loc[idx[5], "u2"] = np.nan
    out = pm.et0_diario_df(df, -12.0, 500)
    assert out["eto_pm"].notna().all()
    assert (out["eto_pm"] > 2).all() and (out["eto_pm"] < 9).all()
    assert out["metodo_eto"].iloc[3] == "PM (dados estimados)"


def test_normais_e_etc_probabilistica():
    idx = pd.date_range("2000-01-01", "2009-12-31")
    rng = np.random.default_rng(1)
    eto = 4 + 2 * np.sin(2 * np.pi * (idx.dayofyear - 260) / 365) + rng.normal(0, 0.5, len(idx))
    df = pd.DataFrame({"eto": eto, "chuva": rng.gamma(0.3, 10, len(idx))}, index=idx)
    n = normais_de_serie(df)
    assert len(n) == 12 and n["eto"].between(1, 8).all()
    r = etc_projeto_probabilistico(df["eto"], 3, 0.8)
    assert r["valor"] > df["eto"].rolling(3).mean().median()
    assert len(r["maximos_anuais"]) == 10


def test_precipitacao_efetiva():
    assert precipitacao_efetiva_mensal([100.0], "usda")[0] == pytest.approx(84.0)
    assert precipitacao_efetiva_mensal([300.0], "usda")[0] == pytest.approx(155.0)
    assert precipitacao_efetiva_mensal([50.0], "fao")[0] == pytest.approx(20.0)
    assert list(precipitacao_efetiva_diaria([3.0, 10.0], 5.0, 0.8)) == [0.0, 8.0]


def test_kp_snyder():
    assert 0.6 < kp_snyder(10, 170, 70) < 0.85
