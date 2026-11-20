import numpy as np
import pandas as pd
import pytest

from aspersao import manejo as mnj
from aspersao import relatorios
from aspersao.clima import fontes
from aspersao.pipeline import executar_tudo
from aspersao.projeto import exemplo_cacau_bahia


def _df(dias=20, eto=5.0, chuva=None):
    idx = pd.date_range("2025-09-01", periods=dias)
    return pd.DataFrame({"eto": eto, "chuva": chuva if chuva is not None else 0.0}, index=idx)


def test_turno_fixo_repoe_etc_acumulada():
    d = _df(12)
    kc = pd.Series(1.0, index=d.index)
    b = mnj.balanco_climatico(d, kc, 0.8, 5.0, "turno_fixo", 3, 15.0)
    irr = b[b["irrig_liq"] > 0]
    assert len(irr) == 4
    assert irr["irrig_liq"].iloc[0] == pytest.approx(15.0)
    assert irr["irrig_bruta"].iloc[0] == pytest.approx(18.75)
    assert irr["tempo_h"].iloc[0] == pytest.approx(3.75)


def test_chuva_abate_irrigacao_e_credito_limitado():
    chuva = np.zeros(12)
    chuva[1] = 60.0  # chuva forte: crédito limitado a uma lâmina de projeto
    d = _df(12, chuva=chuva)
    kc = pd.Series(1.0, index=d.index)
    b = mnj.balanco_climatico(d, kc, 0.8, 5.0, "turno_fixo", 3, 15.0, limiar_pe=5, frac_pe=0.8)
    assert b["saldo"].min() >= -15.0 - 1e-9
    assert b["irrig_liq"].iloc[:4].sum() == 0  # sem irrigação logo após a chuva


def test_lamina_fixa():
    d = _df(20, eto=4.0)
    b = mnj.balanco_climatico(d, pd.Series(1.0, index=d.index), 0.8, 5.0, "lamina_fixa", 3, 20.0)
    assert (b.loc[b["irrig_liq"] > 0, "irrig_liq"] >= 20.0 - 1e-9).all()


def test_leitura_inmet():
    linhas = ["REGIAO:;NE", "UF:;BA", "ESTACAO:;BARREIRAS", "CODIGO (WMO):;A402", "LATITUDE:;-12,12",
              "LONGITUDE:;-45,00", "ALTITUDE:;474", "DATA DE FUNDACAO:;2006-01-01",
              "Data;Hora UTC;PRECIPITAÇÃO TOTAL, HORÁRIO (mm);RADIACAO GLOBAL (Kj/m²);TEMPERATURA DO AR - BULBO SECO, HORARIA (°C);"
              "TEMPERATURA DO PONTO DE ORVALHO (°C);TEMPERATURA MÁXIMA NA HORA ANT. (AUT) (°C);TEMPERATURA MÍNIMA NA HORA ANT. (AUT) (°C);"
              "UMIDADE RELATIVA DO AR, HORARIA (%);VENTO, VELOCIDADE HORARIA (m/s);"]
    for dia in (1, 2):
        for h in range(24):
            t = 22 + 8 * np.sin((h - 9) / 24 * 2 * np.pi)
            rad = max(0, 3000 * np.sin((h - 9) / 12 * np.pi)) if 9 <= h <= 21 else -9999
            linhas.append(f"2024/09/0{dia};{h:02d}00 UTC;0;{rad:.0f};{t:.1f};12,0;{t + 0.5:.1f};{t - 0.5:.1f};50;2,5;".replace(".", ","))
    df, meta = fontes.ler_inmet("\n".join(linhas).encode("latin-1"))
    assert meta["latitude"] == pytest.approx(-12.12)
    assert {"tmax", "tmin", "rs", "u2", "chuva"}.issubset(df.columns)
    assert df["rs"].dropna().between(10, 40).all()


def test_csv_generico():
    df = fontes.ler_csv_generico(fontes.modelo_csv_clima().encode())
    assert {"tmax", "tmin", "ur", "u2", "rs", "chuva", "eca"}.issubset(df.columns)
    assert len(df) == 3


def test_nasa_power_mock(monkeypatch):
    class R:
        status_code = 200
        text = ""

        def json(self):
            return {"geometry": {"coordinates": [-45, -12, 480.0]},
                    "properties": {"parameter": {"T2M_MAX": {"20240101": 31.0}, "T2M_MIN": {"20240101": 19.0},
                                                 "T2M": {"20240101": 25.0}, "RH2M": {"20240101": 70.0},
                                                 "T2MDEW": {"20240101": 18.0}, "WS2M": {"20240101": 2.0},
                                                 "ALLSKY_SFC_SW_DWN": {"20240101": -999.0},
                                                 "PRECTOTCORR": {"20240101": 3.2}}}}
    monkeypatch.setattr(fontes.requests, "get", lambda *a, **k: R())
    df, alt = fontes.nasa_power_diario(-12, -45, pd.Timestamp("2024-01-01"), pd.Timestamp("2024-01-01"))
    assert alt == 480.0 and np.isnan(df["rs"].iloc[0]) and df["tmax"].iloc[0] == 31.0


def test_pdf_e_excel():
    p = exemplo_cacau_bahia()
    r = executar_tudo(p)
    pdf = relatorios.gerar_pdf(p, r)
    xls = relatorios.gerar_excel(p, r)
    assert pdf[:4] == b"%PDF" and len(pdf) > 50_000
    assert xls[:2] == b"PK"
