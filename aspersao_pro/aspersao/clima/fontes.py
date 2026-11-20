"""Fontes de dados climáticos.

* NASA POWER (série diária desde 1981, sem chave de acesso);
* Open-Meteo Histórico (reanálise ERA5/ERA5-Land, sem chave);
* Open-Meteo Previsão (até 16 dias, inclui ETo FAO e probabilidade de chuva);
* Arquivos de estações automáticas do INMET (CSV horário);
* Planilhas/CSV genéricos (nomes de colunas em português ou inglês).

Todas as funções retornam DataFrames diários com colunas padronizadas:
``tmax, tmin, tmed, ur, urmax, urmin, tdew, u2, rs, chuva, eto_fonte``.
"""

from __future__ import annotations

import io
import re
import unicodedata
from datetime import date

import numpy as np
import pandas as pd
import requests

from .penman import vento_2m

URL_NASA_POWER = "https://power.larc.nasa.gov/api/temporal/daily/point"
URL_OM_HISTORICO = "https://archive-api.open-meteo.com/v1/archive"
URL_OM_PREVISAO = "https://api.open-meteo.com/v1/forecast"

CABECALHO_HTTP = {"User-Agent": "AspersaoPro/1.0 (projeto de irrigacao)"}


class ErroFonteDados(RuntimeError):
    """Falha na obtenção de dados de uma fonte externa."""


def _get_json(url, params, timeout=60):
    try:
        resp = requests.get(url, params=params, timeout=timeout, headers=CABECALHO_HTTP)
    except requests.RequestException as exc:  # sem internet, DNS, proxy...
        raise ErroFonteDados(f"Não foi possível acessar {url.split('/')[2]}: {exc}") from exc
    if resp.status_code != 200:
        detalhe = resp.text[:300]
        raise ErroFonteDados(f"{url.split('/')[2]} respondeu HTTP {resp.status_code}: {detalhe}")
    try:
        return resp.json()
    except ValueError as exc:
        raise ErroFonteDados("Resposta inválida (não é JSON).") from exc


# ---------------------------------------------------------------------------
# NASA POWER
# ---------------------------------------------------------------------------
def nasa_power_diario(lat: float, lon: float, inicio: date, fim: date):
    """Série diária NASA POWER (comunidade AG). Retorna (df, altitude_m)."""
    params = {
        "parameters": "T2M_MAX,T2M_MIN,T2M,RH2M,T2MDEW,WS2M,ALLSKY_SFC_SW_DWN,PRECTOTCORR",
        "community": "AG",
        "longitude": round(lon, 4),
        "latitude": round(lat, 4),
        "start": pd.Timestamp(inicio).strftime("%Y%m%d"),
        "end": pd.Timestamp(fim).strftime("%Y%m%d"),
        "format": "JSON",
    }
    js = _get_json(URL_NASA_POWER, params, timeout=120)
    try:
        par = js["properties"]["parameter"]
    except KeyError as exc:
        raise ErroFonteDados(f"Resposta inesperada da NASA POWER: {str(js)[:300]}") from exc
    df = pd.DataFrame(par)
    df.index = pd.to_datetime(df.index, format="%Y%m%d")
    df = df.replace(-999.0, np.nan).astype(float)
    df = df.rename(columns={
        "T2M_MAX": "tmax", "T2M_MIN": "tmin", "T2M": "tmed", "RH2M": "ur",
        "T2MDEW": "tdew", "WS2M": "u2", "ALLSKY_SFC_SW_DWN": "rs", "PRECTOTCORR": "chuva",
    })
    alt = None
    try:
        coords = js["geometry"]["coordinates"]
        alt = float(coords[2]) if len(coords) > 2 else None
    except (KeyError, TypeError, ValueError):
        pass
    df.attrs["fonte"] = "NASA POWER (MERRA-2/CERES)"
    return df.sort_index(), alt


# ---------------------------------------------------------------------------
# Open-Meteo
# ---------------------------------------------------------------------------
_DIARIO_COMPLETO = [
    "temperature_2m_max", "temperature_2m_min", "temperature_2m_mean",
    "relative_humidity_2m_max", "relative_humidity_2m_min", "relative_humidity_2m_mean",
    "dew_point_2m_mean", "wind_speed_10m_mean", "shortwave_radiation_sum",
    "precipitation_sum", "et0_fao_evapotranspiration",
]
_DIARIO_BASICO = [
    "temperature_2m_max", "temperature_2m_min", "temperature_2m_mean",
    "shortwave_radiation_sum", "precipitation_sum", "et0_fao_evapotranspiration",
    "wind_speed_10m_max",
]
_MAPA_OM = {
    "temperature_2m_max": "tmax", "temperature_2m_min": "tmin", "temperature_2m_mean": "tmed",
    "relative_humidity_2m_max": "urmax", "relative_humidity_2m_min": "urmin",
    "relative_humidity_2m_mean": "ur", "dew_point_2m_mean": "tdew",
    "wind_speed_10m_mean": "u10", "shortwave_radiation_sum": "rs", "precipitation_sum": "chuva",
    "et0_fao_evapotranspiration": "eto_fonte", "precipitation_probability_max": "prob_chuva",
    "wind_speed_10m_max": "u10max",
}


def _df_open_meteo(js):
    daily = js.get("daily")
    if not daily:
        raise ErroFonteDados("Open-Meteo não retornou dados diários.")
    df = pd.DataFrame(daily)
    df.index = pd.to_datetime(df.pop("time"))
    df = df.rename(columns=_MAPA_OM).apply(pd.to_numeric, errors="coerce")
    return df


def _horario_para_diario(js):
    hourly = js.get("hourly")
    if not hourly:
        return pd.DataFrame()
    h = pd.DataFrame(hourly)
    h.index = pd.to_datetime(h.pop("time"))
    h = h.apply(pd.to_numeric, errors="coerce")
    agg = pd.DataFrame(index=h.resample("D").mean().index)
    if "relative_humidity_2m" in h:
        agg["urmax"] = h["relative_humidity_2m"].resample("D").max()
        agg["urmin"] = h["relative_humidity_2m"].resample("D").min()
        agg["ur"] = h["relative_humidity_2m"].resample("D").mean()
    if "dew_point_2m" in h:
        agg["tdew"] = h["dew_point_2m"].resample("D").mean()
    if "wind_speed_10m" in h:
        agg["u10"] = h["wind_speed_10m"].resample("D").mean()
    return agg


def _open_meteo(url, params_base, diario_extra=()):
    """Tenta a lista diária completa; se a API recusar alguma variável,
    usa a lista básica e agrega umidade/vento a partir de dados horários."""
    params = dict(params_base)
    params["daily"] = ",".join(_DIARIO_COMPLETO + list(diario_extra))
    try:
        js = _get_json(url, params, timeout=120)
        df = _df_open_meteo(js)
    except ErroFonteDados as exc:
        if "HTTP 400" not in str(exc):
            raise
        params["daily"] = ",".join(_DIARIO_BASICO + list(diario_extra))
        params["hourly"] = "relative_humidity_2m,dew_point_2m,wind_speed_10m"
        js = _get_json(url, params, timeout=180)
        df = _df_open_meteo(js)
        extra = _horario_para_diario(js)
        if not extra.empty:
            df = df.join(extra, how="left")
    if "u10" in df:
        df["u2"] = vento_2m(df["u10"].values, 10.0)
    alt = js.get("elevation")
    return df.sort_index(), (float(alt) if alt is not None else None)


def open_meteo_historico(lat: float, lon: float, inicio: date, fim: date):
    """Reanálise ERA5 (Open-Meteo Historical Weather API). Retorna (df, altitude)."""
    params = {
        "latitude": round(lat, 4), "longitude": round(lon, 4),
        "start_date": pd.Timestamp(inicio).strftime("%Y-%m-%d"),
        "end_date": pd.Timestamp(fim).strftime("%Y-%m-%d"),
        "wind_speed_unit": "ms", "timezone": "auto",
    }
    df, alt = _open_meteo(URL_OM_HISTORICO, params)
    df.attrs["fonte"] = "Open-Meteo (reanálise ERA5)"
    return df, alt


def open_meteo_previsao(lat: float, lon: float, dias_passados: int = 14, dias_previsao: int = 16):
    """Previsão do tempo diária (até 16 dias) + dias passados recentes. Retorna (df, altitude)."""
    params = {
        "latitude": round(lat, 4), "longitude": round(lon, 4),
        "past_days": int(np.clip(dias_passados, 0, 92)),
        "forecast_days": int(np.clip(dias_previsao, 1, 16)),
        "wind_speed_unit": "ms", "timezone": "auto",
    }
    df, alt = _open_meteo(URL_OM_PREVISAO, params, diario_extra=("precipitation_probability_max",))
    df.attrs["fonte"] = "Open-Meteo (previsão numérica)"
    return df, alt


# ---------------------------------------------------------------------------
# Arquivos locais (INMET e CSV genérico)
# ---------------------------------------------------------------------------
def _normalizar(txt: str) -> str:
    txt = unicodedata.normalize("NFKD", str(txt)).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"\s+", " ", txt).strip().upper()


def _decodificar(conteudo: bytes) -> str:
    for enc in ("utf-8-sig", "latin-1", "cp1252"):
        try:
            return conteudo.decode(enc)
        except UnicodeDecodeError:
            continue
    return conteudo.decode("latin-1", errors="ignore")


def _num(valor):
    try:
        return float(str(valor).replace(",", ".").strip())
    except (TypeError, ValueError):
        return None


def ler_inmet(conteudo: bytes, fuso_horas: int = -3):
    """Lê o CSV horário de estação automática do INMET (portal BDMEP / dados históricos)
    e agrega para escala diária no horário local.

    Retorna (df_diario, metadados) — metadados contém nome, latitude, longitude e altitude.
    """
    texto = _decodificar(conteudo)
    linhas = texto.splitlines()
    meta = {}
    idx_cab = None
    for i, linha in enumerate(linhas[:30]):
        n = _normalizar(linha)
        if n.startswith("DATA") and "HORA" in n:
            idx_cab = i
            break
        if ":" in linha:
            chave, _, valor = linha.partition(":")
            meta[_normalizar(chave)] = valor.strip(" ;\t")
    if idx_cab is None:
        raise ValueError("Cabeçalho do INMET não encontrado (linha iniciando com 'Data;Hora').")
    df = pd.read_csv(io.StringIO("\n".join(linhas[idx_cab:])), sep=";", decimal=",",
                     na_values=["-9999", "-9999,0", "-9999.0", ""], dtype=str)
    df = df.loc[:, [c for c in df.columns if not str(c).startswith("Unnamed")]]
    cols = {c: _normalizar(c) for c in df.columns}

    def achar(*chaves, excluir=()):
        for c, n in cols.items():
            if all(k in n for k in chaves) and not any(e in n for e in excluir):
                return c
        return None

    c_data = achar("DATA")
    c_hora = achar("HORA")
    mapa = {
        "chuva": achar("PRECIPITA"),
        "rad": achar("RADIACAO"),
        "temp": achar("BULBO SECO"),
        "tdew": achar("PONTO DE ORVALHO", excluir=("MAX", "MIN")),
        "tmax": achar("TEMPERATURA MAXIMA"),
        "tmin": achar("TEMPERATURA MINIMA"),
        "urmax": achar("UMIDADE REL. MAX") or achar("UMIDADE", "MAX"),
        "urmin": achar("UMIDADE REL. MIN") or achar("UMIDADE", "MIN"),
        "ur": achar("UMIDADE RELATIVA", "HORARIA"),
        "vento": achar("VENTO", "VELOCIDADE"),
    }
    num = pd.DataFrame(index=df.index)
    for nome, c in mapa.items():
        if c is not None:
            num[nome] = pd.to_numeric(df[c].astype(str).str.replace(",", "."), errors="coerce")
    hora = df[c_hora].astype(str).str.extract(r"(\d{1,2})")[0].astype(float).fillna(0)
    datas = pd.to_datetime(df[c_data].astype(str).str.replace("/", "-"), errors="coerce")
    stamp = datas + pd.to_timedelta(hora, unit="h") + pd.to_timedelta(fuso_horas, unit="h")
    num.index = stamp
    num = num[~num.index.isna()]
    g = num.resample("D")
    cont = g.count()
    out = pd.DataFrame(index=g.mean().index)
    if "tmax" in num:
        out["tmax"] = g["tmax"].max()
    elif "temp" in num:
        out["tmax"] = g["temp"].max()
    if "tmin" in num:
        out["tmin"] = g["tmin"].min()
    elif "temp" in num:
        out["tmin"] = g["temp"].min()
    if "temp" in num:
        out["tmed"] = g["temp"].mean()
    if "urmax" in num:
        out["urmax"] = g["urmax"].max()
    if "urmin" in num:
        out["urmin"] = g["urmin"].min()
    if "ur" in num:
        out["ur"] = g["ur"].mean()
    if "tdew" in num:
        out["tdew"] = g["tdew"].mean()
    if "vento" in num:
        out["u2"] = vento_2m(g["vento"].mean().values, 10.0)  # anemômetro do INMET a 10 m
    if "rad" in num:
        rad = num["rad"].clip(lower=0)
        out["rs"] = rad.resample("D").sum() / 1000.0  # kJ/m² → MJ/m²
        out.loc[cont["rad"] < 10, "rs"] = np.nan
    if "chuva" in num:
        out["chuva"] = g["chuva"].sum(min_count=18)
    # Dias com poucas observações de temperatura são descartados
    ref = "tmax" if "tmax" in num else ("temp" if "temp" in num else None)
    if ref is not None:
        out.loc[cont[ref] < 18, ["tmax", "tmin"]] = np.nan
    metadados = {
        "estacao": meta.get("ESTACAO", ""),
        "codigo": meta.get("CODIGO (WMO)", ""),
        "latitude": _num(meta.get("LATITUDE")),
        "longitude": _num(meta.get("LONGITUDE")),
        "altitude": _num(meta.get("ALTITUDE")),
    }
    out.attrs["fonte"] = f"INMET {metadados['estacao']} {metadados['codigo']}".strip()
    return out.sort_index(), metadados


_ALIASES = {
    "data": ["DATA", "DATE", "DIA", "TIME"],
    "tmax": ["TMAX", "TMÁX", "T_MAX", "TEMP_MAX", "TEMPMAX", "TEMPERATURA MAXIMA", "T2M_MAX"],
    "tmin": ["TMIN", "T_MIN", "TEMP_MIN", "TEMPMIN", "TEMPERATURA MINIMA", "T2M_MIN"],
    "tmed": ["TMED", "TMEAN", "T_MED", "TEMP_MED", "TEMPERATURA MEDIA", "T2M"],
    "ur": ["UR", "URMED", "UR_MED", "RH", "RHMEAN", "UMIDADE", "UMIDADE RELATIVA", "RH2M"],
    "urmax": ["URMAX", "UR_MAX", "RHMAX"],
    "urmin": ["URMIN", "UR_MIN", "RHMIN"],
    "tdew": ["TDEW", "TORVALHO", "PONTO DE ORVALHO", "T2MDEW", "DEWPOINT"],
    "u2": ["U2", "VENTO", "VENTO2M", "WS2M", "WIND", "VELOCIDADE DO VENTO"],
    "u10": ["U10", "VENTO10M", "WS10M"],
    "rs": ["RS", "RADIACAO", "RADIACAO SOLAR", "RAD", "SRAD", "ALLSKY_SFC_SW_DWN"],
    "insolacao": ["INSOLACAO", "N", "SUNSHINE", "BRILHO SOLAR"],
    "chuva": ["CHUVA", "PRECIPITACAO", "P", "PREC", "RAIN", "PRECTOTCORR", "PRECIPITATION"],
    "eto_fonte": ["ETO", "ET0", "ETO_FAO"],
    "eca": ["ECA", "TANQUE", "EVAPORACAO", "EPAN", "TANQUE CLASSE A"],
}


def ler_csv_generico(conteudo: bytes):
    """Lê CSV/TXT diário com nomes de colunas livres (reconhece português e inglês).

    Retorna DataFrame com índice de datas e colunas padronizadas.
    """
    texto = _decodificar(conteudo)
    amostra = texto[:5000]
    sep = ";" if amostra.count(";") > amostra.count(",") else ","
    decimal = "," if sep == ";" else "."
    df = pd.read_csv(io.StringIO(texto), sep=sep, decimal=decimal)
    if df.shape[1] == 1:
        df = pd.read_csv(io.StringIO(texto), sep=None, engine="python")
    norm = {c: _normalizar(c).replace("(", " ").replace(")", " ").split(" ")[0] for c in df.columns}
    norm_completo = {c: _normalizar(c) for c in df.columns}
    renomear = {}
    for padrao, aliases in _ALIASES.items():
        al = [_normalizar(a) for a in aliases]
        for c in df.columns:
            if c in renomear:
                continue
            if norm[c] in al or norm_completo[c] in al:
                renomear[c] = padrao
                break
    df = df.rename(columns=renomear)
    if "data" not in df:
        raise ValueError("Coluna de data não encontrada (use 'data' ou 'date').")
    df["data"] = pd.to_datetime(df["data"], dayfirst=True, errors="coerce")
    df = df.dropna(subset=["data"]).set_index("data").sort_index()
    manter = [c for c in _ALIASES if c != "data" and c in df.columns]
    df = df[manter].apply(pd.to_numeric, errors="coerce")
    if "u10" in df and "u2" not in df:
        df["u2"] = vento_2m(df["u10"].values, 10.0)
    df.attrs["fonte"] = "Arquivo do usuário"
    return df


def modelo_csv_clima() -> str:
    """Modelo de planilha diária para download."""
    linhas = [
        "data;tmax;tmin;ur;u2;rs;chuva;eca",
        "01/09/2025;33,2;18,4;45;2,6;22,1;0;7,8",
        "02/09/2025;34,0;19,1;42;2,9;22,8;0;8,3",
        "03/09/2025;33,5;19,8;48;2,2;21,4;3,2;7,1",
    ]
    return "\n".join(linhas)
