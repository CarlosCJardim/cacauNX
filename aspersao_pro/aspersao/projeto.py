"""Estrutura de dados do projeto (dicionário serializável em JSON), projeto em
branco, projetos-exemplo e funções de salvar/abrir."""

from __future__ import annotations

import copy
import json
from datetime import date

import numpy as np
import pandas as pd

from . import __version__

NORMAIS_VAZIAS = {k: [None] * 12 for k in ("tmax", "tmin", "ur", "u2", "insolacao", "rs", "chuva", "eto")}


def projeto_padrao() -> dict:
    return {
        "versao": __version__,
        "info": {"nome": "Novo projeto", "cliente": "", "propriedade": "", "municipio": "", "uf": "",
                 "responsavel": "", "registro": "", "data": date.today().isoformat(), "observacoes": ""},
        "area": {"poligono": [], "fonte": None, "rota_adutora": [], "centro": [-15.79, -47.88], "zoom": 5,
                 "retangulo": {"comprimento": 400.0, "largura": 250.0, "azimute": 0.0}},
        "altimetria": {"modo": "uniforme", "cota_referencia": 500.0, "declividade_pct": 0.0, "direcao_graus": 0.0,
                       "mde": None, "provedor": "open_meteo", "resolucao": 15, "equidistancia": 1.0,
                       "cota_fonte_manual": None},
        "clima": {"modo": "normais", "lat": None, "lon": None, "altitude": None, "krs": 0.16,
                  "normais": copy.deepcopy(NORMAIS_VAZIAS), "diario": None, "fonte": "",
                  "metodo_eto_diario": "pm", "periodo": [1995, 2024]},
        "cultura": {"nome": "Cacau", "personalizada": None, "mes_plantio": 1, "dia_plantio": 1,
                    "ajuste_climatico": True, "kc_mensal": []},
        "agronomico": {"metodo_etc": "ciclo", "prob": 0.80, "turno_rega": 3, "considerar_chuva": False,
                       "metodo_pe": "usda", "frac_pe": 0.8, "ea_modo": "calculada", "ea_informada": 0.80,
                       "adequacao": 80.0, "ef_conducao": 1.0, "textura": "Franca (média)", "vib": 13.0,
                       "lamina_max": 0.0},
        "aspersor": {"id": "IMP-M-4.4x2.4", "pressao_kpa": 300.0, "esp_asp": 12.0, "esp_lat": 18.0,
                     "arranjo": "retangular", "perfil": "auto", "vento_ms": 2.0, "dir_vento": 90.0,
                     "altura_haste": 1.0, "catalogo_usuario": [], "radial": []},
        "operacao": {"tipo_sistema": "fixo", "jornada_h": 18.0, "folga_d": 0, "t_mudanca_h": 0.0,
                     "q_fonte_m3h": 150.0, "n_setores": 0, "hora_inicio": 21.5},
        "layout": {"orientacao": "curva_nivel", "azimute": 0.0, "posicao_derivacao": "central",
                   "n_derivacoes": 0, "comp_max_lateral": 0.0},
        "hidraulica": {"equacao": "HW", "t_agua": 25.0, "mat_lateral": "Alumínio (engate rápido)",
                       "mat_derivacao": "PVC", "mat_principal": "PVC", "mat_adutora": "PVC",
                       "modo_lateral": "uniforme", "v_max_lateral": 2.0, "v_max_derivacao": 2.0,
                       "v_max_principal": 1.8, "v_max_adutora": 1.5, "tol_lateral": 20.0, "tol_derivacao": 10.0,
                       "perda_local_lateral": 0.0, "perda_local_rede": 10.0, "criterio_principal": "velocidade",
                       "margem_pn": 1.2, "reguladores": "auto", "limite_regulador": 10.0, "catalogo_tubos": None,
                       "dn_ref_lateral": "auto",
                       "tempo_manobra_s": 10.0},
        "bomba": {"altura_succao": 3.0, "comp_succao": 8.0, "dn_succao": "auto", "h_cabecal": 3.0,
                  "eta_bomba": 0.72, "rpm": "auto", "curva": "sintetica", "pontos_curva": [], "temp_agua": 25.0,
                  "energia": "eletrica", "tarifa_kwh": 0.72, "desconto_noturno": 60.0, "horas_desconto": 8.5,
                  "demanda_rs_kw": 0.0, "preco_diesel": 6.3},
        "custos": {"precos": {}, "juros_aa": 8.0, "manutencao_pct": 2.0, "mao_obra_ano": 0.0,
                   "tarifa_agua": 0.0},
        "manejo": {"estrategia": "turno_fixo", "limiar_pe": 5.0, "frac_pe": 0.8, "credito_max": None,
                   "adiar_chuva_mm": 5.0, "fonte": "previsao", "dias_passados": 14, "kp_bordadura": 10.0},
    }


def mesclar_padrao(p: dict) -> dict:
    """Completa um projeto carregado com chaves novas do padrão (compatibilidade de versões)."""
    base = projeto_padrao()

    def rec(b, x):
        for k, v in b.items():
            if k not in x:
                x[k] = copy.deepcopy(v)
            elif isinstance(v, dict) and isinstance(x[k], dict) and k not in ("normais", "precos", "mde"):
                rec(v, x[k])
    rec(base, p)
    return p


# ---------------------------------------------------------------------------
# Serialização de séries diárias
# ---------------------------------------------------------------------------
def df_para_json(df: pd.DataFrame | None):
    if df is None or len(df) == 0:
        return None
    d = df.copy()
    d.index = d.index.strftime("%Y-%m-%d")
    return {"colunas": list(d.columns), "indice": list(d.index),
            "dados": np.where(pd.isna(d.values), None, d.values).tolist(), "fonte": df.attrs.get("fonte", "")}


def json_para_df(js) -> pd.DataFrame | None:
    if not js:
        return None
    df = pd.DataFrame(js["dados"], columns=js["colunas"], index=pd.to_datetime(js["indice"]))
    df = df.apply(pd.to_numeric, errors="coerce")
    df.attrs["fonte"] = js.get("fonte", "")
    return df


def salvar(p: dict) -> str:
    return json.dumps(p, ensure_ascii=False, indent=1, default=_conv)


def abrir(texto: str | bytes) -> dict:
    if isinstance(texto, bytes):
        texto = texto.decode("utf-8")
    return mesclar_padrao(json.loads(texto))


def _conv(o):
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating,)):
        return float(o)
    if isinstance(o, np.ndarray):
        return o.tolist()
    return str(o)


# ---------------------------------------------------------------------------
# Projetos-exemplo
# ---------------------------------------------------------------------------
def exemplo_cacau_bahia() -> dict:
    """Cacau a pleno sol irrigado por aspersão subcopa — Oeste da Bahia.

    Clima: normais ILUSTRATIVAS aproximadas (substitua por NASA POWER/INMET/Open-Meteo).
    Relevo: terreno sintético de demonstração (substitua por altimetria real).
    """
    from .altimetria import mde_sintetico

    p = projeto_padrao()
    p["info"].update({"nome": "Cacau irrigado — Fazenda Exemplo", "cliente": "Produtor exemplo",
                      "propriedade": "Fazenda Exemplo", "municipio": "Barreiras", "uf": "BA",
                      "observacoes": "Projeto demonstrativo. Clima e relevo ilustrativos — substitua por dados reais."})
    pol = [[-44.9562, -12.1210], [-44.9512, -12.1206], [-44.9505, -12.1245], [-44.9530, -12.1262],
           [-44.9566, -12.1250], [-44.9562, -12.1210]]
    p["area"].update({"poligono": pol, "fonte": [-44.9572, -12.1259], "centro": [-12.1234, -44.9535], "zoom": 16})
    p["altimetria"].update({"modo": "mde", "cota_referencia": 720.0, "equidistancia": 1.0})
    p["altimetria"]["mde"] = mde_sintetico(pol, 720.0, 1.6, 300.0, 1.5, 25, extras=[p["area"]["fonte"]])
    p["clima"].update({"modo": "normais", "lat": -12.1234, "lon": -44.9535, "altitude": 720.0, "krs": 0.16,
                       "fonte": "Normais ilustrativas aproximadas (Oeste da Bahia) — substitua por dados reais"})
    p["clima"]["normais"] = {
        "tmax": [30.5, 30.8, 30.8, 31.0, 31.0, 30.6, 30.9, 32.5, 34.0, 33.5, 31.5, 30.5],
        "tmin": [20.0, 20.0, 20.0, 19.5, 17.5, 15.5, 15.0, 16.0, 18.5, 20.0, 20.0, 20.0],
        "ur": [76, 75, 76, 72, 62, 54, 48, 42, 42, 55, 70, 76],
        "u2": [1.5, 1.4, 1.3, 1.4, 1.6, 1.9, 2.2, 2.5, 2.4, 2.0, 1.6, 1.5],
        "insolacao": [6.0, 6.3, 6.5, 7.5, 8.6, 9.0, 9.3, 9.4, 8.5, 7.2, 6.2, 5.8],
        "rs": [None] * 12,
        "chuva": [190, 160, 170, 90, 15, 2, 1, 3, 20, 90, 190, 210],
        "eto": [None] * 12,
    }
    p["cultura"].update({"nome": "Cacau", "ajuste_climatico": True})
    p["agronomico"].update({"metodo_etc": "ciclo", "turno_rega": 3, "ea_modo": "calculada", "adequacao": 80.0,
                            "textura": "Franco-arenosa", "vib": 20.0})
    p["aspersor"].update({"id": "SUBCOPA-4.0", "pressao_kpa": 250.0, "esp_asp": 12.0, "esp_lat": 12.0,
                          "arranjo": "retangular", "vento_ms": 1.0, "dir_vento": 90.0, "altura_haste": 0.6})
    p["operacao"].update({"tipo_sistema": "fixo", "jornada_h": 18.0, "folga_d": 0, "q_fonte_m3h": 220.0})
    p["layout"].update({"orientacao": "curva_nivel", "posicao_derivacao": "central"})
    p["hidraulica"].update({"mat_lateral": "PEAD", "modo_lateral": "uniforme"})
    return p


def exemplo_openirri_trigo() -> dict:
    """Reprodução do estudo de caso de El-Naggar (2026), SoftwareX 35:102912 —
    trigo, 408,8 m × 275,4 m, ETo de pico 10,13 mm/d, aspersor 520 L/h @ 276 kPa,
    12,6 × 12,6 m, turno de rega 2 d, jornada 16 h, fonte 200 m³/h.

    ETo mensal: pico de janeiro conforme o artigo; demais meses ilustrativos.
    Localização aproximada (lat. 32,5° S; altitude 1110 m).
    """
    from .geo import retangulo_lonlat

    p = projeto_padrao()
    p["info"].update({"nome": "Validação — estudo de caso OpenIrri (trigo)", "cliente": "El-Naggar (2026)",
                      "propriedade": "Caso SoftwareX 102912", "municipio": "Highveld", "uf": "ZA",
                      "observacoes": "Reproduz os parâmetros da Tabela 1 do artigo com manejo pelo clima."})
    lat, lon = -32.5, 26.0
    pol = retangulo_lonlat(lat, lon, 408.8, 275.4, 0.0)
    fonte = [pol[0][0] - 0.0003, pol[0][1] - 0.0002]
    p["area"].update({"poligono": pol, "fonte": fonte, "centro": [lat, lon], "zoom": 16})
    p["altimetria"].update({"modo": "uniforme", "cota_referencia": 1110.0, "declividade_pct": 0.0})
    p["clima"].update({"modo": "eto_mensal", "lat": lat, "lon": lon, "altitude": 1110.0,
                       "fonte": "ETo mensal (pico de janeiro = 10,13 mm/d, El-Naggar 2026)"})
    p["clima"]["normais"]["eto"] = [10.13, 9.0, 7.2, 5.0, 3.5, 2.8, 3.0, 4.2, 5.8, 7.5, 8.9, 9.8]
    p["clima"]["normais"]["chuva"] = [0.0] * 12
    p["clima"]["normais"]["u2"] = [2.0] * 12
    p["clima"]["normais"]["ur"] = [45.0] * 12
    p["cultura"].update({"nome": "Trigo (primavera)", "mes_plantio": 1, "dia_plantio": 1, "ajuste_climatico": False})
    p["agronomico"].update({"metodo_etc": "conservador", "turno_rega": 2, "ea_modo": "informada",
                            "ea_informada": 0.75, "textura": "Arenosa", "vib": 30.0})
    p["aspersor"].update({"id": "CASO-OPENIRRI", "pressao_kpa": 276.0, "esp_asp": 12.6, "esp_lat": 12.6,
                          "arranjo": "retangular", "vento_ms": 0.0, "altura_haste": 1.0})
    p["operacao"].update({"tipo_sistema": "fixo", "jornada_h": 16.0, "folga_d": 0, "q_fonte_m3h": 200.0})
    p["layout"].update({"orientacao": "manual", "azimute": 0.0, "posicao_derivacao": "central"})
    p["hidraulica"].update({"mat_lateral": "PEAD", "mat_derivacao": "PVC", "mat_principal": "PVC",
                            "mat_adutora": "PVC"})
    return p


EXEMPLOS = {
    "Cacau irrigado — Oeste da Bahia (demonstração)": exemplo_cacau_bahia,
    "Validação — estudo de caso OpenIrri (trigo)": exemplo_openirri_trigo,
}
