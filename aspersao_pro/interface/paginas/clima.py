"""Clima e ETo: normais, ETo mensal ou série diária (NASA POWER, Open-Meteo ERA5, INMET, CSV)."""

from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd
import streamlit as st

from aspersao.clima import fontes
from aspersao.clima.estatistica import MESES
from aspersao.projeto import df_para_json

from .. import estado, graficos
from ..estado import P, fmt_br, num, sel


def _coord_padrao():
    c = P()["clima"]
    a = P()["area"]
    lat = c.get("lat") if c.get("lat") is not None else a["centro"][0]
    lon = c.get("lon") if c.get("lon") is not None else a["centro"][1]
    return float(lat), float(lon)


def _salvar_diario(df, alt, fonte):
    c = P()["clima"]
    df = df.copy()
    df.attrs["fonte"] = fonte
    c["diario"] = df_para_json(df)
    c["fonte"] = fonte
    c["modo"] = "diario"
    if alt is not None and c.get("altitude") is None:
        c["altitude"] = alt
    estado.renovar("clima", "modo")


def pagina():
    estado.cabecalho("Clima e evapotranspiração de referência",
                     "Base do manejo pelo clima: ETo FAO-56 Penman-Monteith calculada pelo próprio programa.", "🌦️")
    c = P()["clima"]
    lat0, lon0 = _coord_padrao()
    c1, c2, c3, c4 = st.columns(4)
    c["lat"] = c1.number_input("Latitude (°)", -60.0, 60.0, lat0, format="%.5f", key=estado.chave("clima", "lat"))
    c["lon"] = c2.number_input("Longitude (°)", -180.0, 180.0, lon0, format="%.5f", key=estado.chave("clima", "lon"))
    alt0 = c.get("altitude") if c.get("altitude") is not None else P()["altimetria"]["cota_referencia"]
    c["altitude"] = c3.number_input("Altitude (m)", -100.0, 6000.0, float(alt0), 1.0,
                                    key=estado.chave("clima", "altitude"))
    num("kRs (Hargreaves)", "clima", "krs", 0.10, 0.25, 0.01, alvo=c4,
        ajuda="0,16 para regiões interiores; 0,19 para regiões costeiras. Usado quando falta radiação.")

    modo = sel("Tipo de dado climático", "clima", "modo",
               {"diario": "Série diária (recomendado)", "normais": "Normais mensais de variáveis",
                "eto_mensal": "ETo e chuva mensais já calculadas"}, radio=True, horizontal=True)

    if modo == "diario":
        t1, t2, t3 = st.tabs(["🛰️ NASA POWER / Open-Meteo", "📁 Estação INMET ou planilha", "⚙️ Opções"])
        with t1:
            a1, a2, a3 = st.columns([1, 1, 2])
            ano_fim = date.today().year - 1
            ini = a1.number_input("Ano inicial", 1981, ano_fim, int(c["periodo"][0]), key="tmp_ano_ini")
            fim = a2.number_input("Ano final", 1981, ano_fim, min(int(c["periodo"][1]), ano_fim), key="tmp_ano_fim")
            fonte = a3.selectbox("Fonte", ["NASA POWER (1981–, sem chave)", "Open-Meteo — reanálise ERA5 (1940–, sem chave)"],
                                 key="tmp_fonte_clima")
            if st.button("Baixar série diária", type="primary"):
                c["periodo"] = [int(ini), int(fim)]
                try:
                    with st.spinner("Baixando dados climáticos..."):
                        if fonte.startswith("NASA"):
                            df, alt = fontes.nasa_power_diario(c["lat"], c["lon"], date(int(ini), 1, 1), date(int(fim), 12, 31))
                            nome = f"NASA POWER {ini}–{fim}"
                        else:
                            df, alt = fontes.open_meteo_historico(c["lat"], c["lon"], date(int(ini), 1, 1), date(int(fim), 12, 31))
                            nome = f"Open-Meteo ERA5 {ini}–{fim}"
                    _salvar_diario(df, alt, nome)
                    st.success(f"{len(df)} dias baixados ({nome}).")
                    st.rerun()
                except fontes.ErroFonteDados as exc:
                    st.error(f"{exc}\n\nSem internet? Importe um arquivo da estação ou use normais mensais.")
        with t2:
            tipo = st.radio("Formato", ["INMET — estação automática (CSV horário)", "Planilha diária (CSV)"],
                            horizontal=True, key="tmp_tipo_arq")
            arq = st.file_uploader("Arquivo", type=["csv", "txt", "CSV"], key="tmp_arq_clima")
            st.download_button("Modelo de planilha diária", fontes.modelo_csv_clima(), "modelo_clima_diario.csv")
            if arq is not None and st.button("Importar arquivo"):
                try:
                    if tipo.startswith("INMET"):
                        df, meta = fontes.ler_inmet(arq.getvalue())
                        if meta.get("latitude"):
                            c["lat"], c["lon"] = meta["latitude"], meta["longitude"]
                            c["altitude"] = meta.get("altitude") or c["altitude"]
                            for k in ("lat", "lon", "altitude"):
                                estado.renovar("clima", k)
                        nome = df.attrs.get("fonte", "INMET")
                    else:
                        df = fontes.ler_csv_generico(arq.getvalue())
                        nome = f"Arquivo {arq.name}"
                    _salvar_diario(df, None, nome)
                    st.success(f"{len(df)} dias importados.")
                    st.rerun()
                except Exception as exc:  # noqa: BLE001
                    st.error(f"Falha ao ler o arquivo: {exc}")
        with t3:
            sel("ETo utilizada", "clima", "metodo_eto_diario",
                {"pm": "Calculada pelo AspersãoPro (FAO-56 PM)", "fonte": "Fornecida pela fonte (se houver)"})

    elif modo == "normais":
        n = c["normais"]
        df = pd.DataFrame({"Mês": MESES, "Tmáx (°C)": n["tmax"], "Tmín (°C)": n["tmin"], "UR média (%)": n["ur"],
                           "Vento u2 (m/s)": n["u2"], "Insolação (h/d)": n["insolacao"],
                           "Radiação Rs (MJ/m²/d)": n["rs"], "Chuva (mm/mês)": n["chuva"]})
        st.caption("Preencha as médias mensais. Vento a 2 m de altura. Informe insolação OU radiação; sem ambas, a "
                   "radiação é estimada pela amplitude térmica (Hargreaves).")
        ed = st.data_editor(df, hide_index=True, num_rows="fixed", width="stretch", key="tmp_ed_normais",
                            disabled=["Mês"])
        mapa = {"Tmáx (°C)": "tmax", "Tmín (°C)": "tmin", "UR média (%)": "ur", "Vento u2 (m/s)": "u2",
                "Insolação (h/d)": "insolacao", "Radiação Rs (MJ/m²/d)": "rs", "Chuva (mm/mês)": "chuva"}
        for col, k in mapa.items():
            n[k] = [None if pd.isna(v) else float(v) for v in ed[col]]
    else:
        n = c["normais"]
        df = pd.DataFrame({"Mês": MESES, "ETo (mm/d)": n["eto"], "Chuva (mm/mês)": n["chuva"],
                           "Vento u2 (m/s)": n["u2"], "UR média (%)": n["ur"]})
        ed = st.data_editor(df, hide_index=True, num_rows="fixed", width="stretch", key="tmp_ed_eto", disabled=["Mês"])
        for col, k in {"ETo (mm/d)": "eto", "Chuva (mm/mês)": "chuva", "Vento u2 (m/s)": "u2", "UR média (%)": "ur"}.items():
            n[k] = [None if pd.isna(v) else float(v) for v in ed[col]]

    st.divider()
    cl = estado.etapa("clima")
    if cl is None:
        return
    st.subheader("Resultado")
    k = st.columns(4)
    k[0].metric("ETo média anual", f"{fmt_br(np.nanmean(cl['eto']))} mm/d")
    m = int(np.nanargmax(cl["eto"]))
    k[1].metric("ETo máxima mensal", f"{fmt_br(cl['eto'][m])} mm/d", MESES[m], delta_color="off", delta_arrow="off")
    k[2].metric("ETo anual", f"{fmt_br(np.nansum(cl['eto'] * np.array([31, 28.25, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31])), 0)} mm")
    k[3].metric("Chuva anual", f"{fmt_br(np.nansum(cl['chuva']), 0)} mm")
    st.caption(f"Método: {cl['metodo']} · Fonte: {cl.get('fonte') or '—'}")
    g1, g2 = st.columns([1.4, 1])
    with g1:
        st.plotly_chart(graficos.clima_mensal(cl["tabela"]), width="stretch")
    with g2:
        st.dataframe(cl["tabela"], hide_index=True, width="stretch", height=460)
    if cl["diario"] is not None:
        d = cl["diario"]
        with st.expander(f"Série diária — {len(d)} dias ({d.index.min():%d/%m/%Y} a {d.index.max():%d/%m/%Y})"):
            st.plotly_chart(graficos.serie_diaria(d), width="stretch")
            if "eto_fonte" in d and d["eto_fonte"].notna().sum() > 30:
                ok = d[["eto_pm", "eto_fonte"]].dropna()
                r = np.corrcoef(ok["eto_pm"], ok["eto_fonte"])[0, 1]
                vies = (ok["eto_pm"] - ok["eto_fonte"]).mean()
                st.caption(f"Comparação ETo AspersãoPro × fonte: r = {r:.3f}; viés médio = {vies:+.2f} mm/d.")
            st.dataframe(d.round(2), width="stretch", height=280)
