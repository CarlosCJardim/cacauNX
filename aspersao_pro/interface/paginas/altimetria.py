"""Altimetria: MDE por APIs (Copernicus/SRTM), Google Elevation, Earth Engine,
GeoTIFF ou levantamento topográfico; curvas de nível sobre imagem de satélite."""

from __future__ import annotations

import io

import numpy as np
import pandas as pd
import streamlit as st
from streamlit_folium import st_folium

from aspersao import altimetria as alt
from aspersao.clima.fontes import ErroFonteDados
from aspersao.geo import Projecao

from .. import estado, graficos, mapas
from ..estado import P, fmt_br, num, sel


def _obter_mde(provedor, n):
    a = P()["area"]
    pol = a.get("poligono")
    extras = [a.get("fonte")] if a.get("fonte") else []
    glon, glat = alt.grade_amostragem(pol, n, extras=extras)
    LON, LAT = np.meshgrid(glon, glat)
    seg = st.session_state["segredos"]
    geotiff = st.session_state.get("tmp_geotiff_bytes")
    with st.spinner(f"Consultando {alt.PROVEDORES.get(provedor, provedor)} ({LON.size} pontos)..."):
        z = alt.obter_cotas(provedor, LAT.ravel(), LON.ravel(), seg.get("google_key", ""), seg.get("gee_projeto", ""),
                            st.session_state.get("tmp_gee_produto", "USGS/SRTMGL1_003"), geotiff)
    return alt.montar_mde(glon, glat, z, alt.PROVEDORES.get(provedor, provedor))


def pagina():
    estado.cabecalho("Altimetria", "Cotas reais de cada aspersor e nó da rede entram no cálculo hidráulico "
                     "passo a passo e na orientação das laterais em nível.", "⛰️")
    al = P()["altimetria"]
    a = P()["area"]
    tem_area = bool(a.get("poligono")) and len(a["poligono"]) >= 4

    modo = sel("Representação do terreno", "altimetria", "modo",
               {"mde": "Modelo digital de elevação (MDE)", "uniforme": "Terreno plano ou declividade uniforme"},
               radio=True, horizontal=True)

    if modo == "uniforme":
        c1, c2, c3 = st.columns(3)
        num("Cota de referência (m)", "altimetria", "cota_referencia", -100.0, 6000.0, 1.0, alvo=c1)
        num("Declividade média (%)", "altimetria", "declividade_pct", 0.0, 60.0, 0.1, alvo=c2)
        num("Azimute de descida (graus, a partir do Norte)", "altimetria", "direcao_graus", 0.0, 360.0, 5.0, alvo=c3,
            ajuda="Direção para onde o terreno desce, medida do Norte no sentido horário.")
        st.info("Use esta opção para estudos preliminares. Para projeto executivo, obtenha o MDE abaixo.")
    else:
        if not tem_area:
            st.warning("Defina primeiro a área do projeto na página **Área e mapa**.")
        tabs = st.tabs(["🌐 Serviços de MDE", "🛰️ Google (Elevation API / Earth Engine)", "📁 GeoTIFF",
                        "📐 Levantamento topográfico", "🧪 Demonstração"])
        with tabs[0]:
            c1, c2 = st.columns([2, 1])
            prov = c1.selectbox("Fonte", [k for k in alt.PROVEDORES if k not in ("google", "gee")],
                                format_func=lambda k: alt.PROVEDORES[k], key="tmp_prov")
            n = c2.slider("Pontos por lado da grade", 6, 40, int(al.get("resolucao", 15)), key="tmp_res")
            if st.button("Obter altimetria", type="primary", disabled=not tem_area):
                try:
                    P()["altimetria"]["mde"] = _obter_mde(prov, n)
                    P()["altimetria"]["resolucao"] = n
                    st.success("MDE obtido.")
                except ErroFonteDados as exc:
                    st.error(f"{exc}\n\nSem acesso à internet? Use GeoTIFF, levantamento topográfico ou declividade uniforme.")
        with tabs[1]:
            seg = st.session_state["segredos"]
            st.markdown("**Google Maps Elevation API** — precisão superior em muitas regiões; requer chave da Google "
                        "Maps Platform. A chave fica apenas nesta sessão (não é salva no arquivo do projeto).")
            seg["google_key"] = st.text_input("Chave da API Google", value=seg.get("google_key", ""), type="password",
                                              key="tmp_gkey")
            n = st.slider("Pontos por lado", 6, 40, 15, key="tmp_res_g")
            if st.button("Obter pela Google Elevation API", disabled=not tem_area):
                try:
                    P()["altimetria"]["mde"] = _obter_mde("google", n)
                    st.success("MDE obtido pela Google Elevation API.")
                except ErroFonteDados as exc:
                    st.error(str(exc))
            st.divider()
            st.markdown("**Google Earth Engine** — SRTM 30 m, NASADEM ou Copernicus GLO-30. Requer `earthengine-api` "
                        "autenticado (`earthengine authenticate`) e um projeto Google Cloud registrado no Earth Engine.")
            seg["gee_projeto"] = st.text_input("ID do projeto Google Cloud", value=seg.get("gee_projeto", ""),
                                               key="tmp_geeproj")
            st.selectbox("Produto", ["USGS/SRTMGL1_003", "NASA/NASADEM_HGT/001", "COPERNICUS/DEM/GLO30"],
                         key="tmp_gee_produto")
            if st.button("Obter pelo Earth Engine", disabled=not tem_area):
                try:
                    P()["altimetria"]["mde"] = _obter_mde("gee", 25)
                    st.success("MDE obtido pelo Google Earth Engine.")
                except ErroFonteDados as exc:
                    st.error(str(exc))
        with tabs[2]:
            arq = st.file_uploader("MDE em GeoTIFF (qualquer sistema de coordenadas)", type=["tif", "tiff"],
                                   key="tmp_tif")
            if arq is not None:
                st.session_state["tmp_geotiff_bytes"] = arq.getvalue()
                if st.button("Amostrar GeoTIFF na área", disabled=not tem_area):
                    try:
                        P()["altimetria"]["mde"] = _obter_mde("geotiff", 40)
                        st.success("MDE amostrado do GeoTIFF.")
                    except Exception as exc:  # noqa: BLE001
                        st.error(f"Falha ao ler o GeoTIFF: {exc}")
        with tabs[3]:
            st.markdown("CSV com pontos do levantamento planialtimétrico (GNSS RTK / estação total). Colunas aceitas: "
                        "`lon;lat;cota` (graus) **ou** `este;norte;cota` (UTM do fuso da área).")
            arq = st.file_uploader("Pontos do levantamento (.csv)", type=["csv", "txt"], key="tmp_lev")
            if arq is not None:
                try:
                    texto = arq.getvalue().decode("utf-8-sig", errors="ignore")
                    sep = ";" if texto.count(";") > texto.count(",") else ","
                    df = pd.read_csv(io.StringIO(texto), sep=sep, decimal="," if sep == ";" else ".")
                    df.columns = [c.strip().lower() for c in df.columns]
                    st.dataframe(df.head(), hide_index=True)
                    if {"este", "norte"}.issubset(df.columns):
                        proj = Projecao.para_ponto(a["centro"][1], a["centro"][0])
                        lon, lat = proj.geo(df["este"].values, df["norte"].values)
                    else:
                        lon, lat = df["lon"].values, df["lat"].values
                    zc = next(c for c in df.columns if c in ("cota", "z", "elevacao", "altitude"))
                    if st.button("Interpolar MDE (interpolação cúbica)"):
                        P()["altimetria"]["mde"] = alt.mde_de_pontos(lon, lat, df[zc].values, a.get("poligono"), 40)
                        st.success(f"MDE interpolado a partir de {len(df)} pontos.")
                except Exception as exc:  # noqa: BLE001
                    st.error(f"Arquivo inválido: {exc}")
        with tabs[4]:
            st.markdown("Gera um terreno **sintético** (rampa + ondulação) apenas para demonstração e treinamento.")
            c1, c2, c3 = st.columns(3)
            cota = c1.number_input("Cota média (m)", value=float(al.get("cota_referencia", 500.0)), key="tmp_sc")
            dec = c2.number_input("Declividade (%)", 0.0, 30.0, 2.0, 0.1, key="tmp_sd")
            dire = c3.number_input("Direção de descida (graus, a partir do Leste)", 0.0, 360.0, 45.0, key="tmp_sdir")
            if st.button("Gerar terreno de demonstração", disabled=not tem_area):
                P()["altimetria"]["mde"] = alt.mde_sintetico(a["poligono"], cota, dec, dire, 2.0, 25,
                                                             extras=[a.get("fonte")] if a.get("fonte") else [])
                st.rerun()

    st.divider()
    res = estado.etapa("elev", False)
    if res is None:
        return
    elev, info = res
    c = st.columns(5)
    c[0].metric("Fonte", info.get("tipo", ""))
    if "cota_min" in info:
        c[1].metric("Cota mínima", f"{fmt_br(info['cota_min'], 1)} m")
        c[2].metric("Cota máxima", f"{fmt_br(info['cota_max'], 1)} m")
    if "declividade_pct" in info:
        c[3].metric("Declividade média", f"{fmt_br(info['declividade_pct'], 2)} %")
        az_desc = (90.0 - info["direcao_descida_graus"]) % 360.0
        c[4].metric("Descida para (azimute)", f"{az_desc:.0f}°")
    st.caption(f"Fonte dos dados: {info.get('fonte', '')}")
    if modo != "mde" or not al.get("mde"):
        return
    LON, LAT, X, Y, Z = elev.grade_utm(90)
    g = estado.pipe().get("geo")
    num("Equidistância das curvas de nível (m)", "altimetria", "equidistancia", 0.25, 50.0, 0.25)
    t1, t2, t3, t4 = st.tabs(["Curvas sobre imagem de satélite", "Curvas de nível", "Relevo 3D", "Declividade"])
    with t1:
        m = mapas.mapa_base(a["centro"], a.get("zoom", 16), False, "Google Satélite (Google Earth)")
        mapas.adicionar_area(m, a.get("poligono"), a.get("fonte"), a.get("rota_adutora"))
        curvas = alt.curvas_de_nivel(LON, LAT, Z, al["equidistancia"])
        mapas.adicionar_curvas(m, curvas, al["equidistancia"] * 5)
        mapas.adicionar_imagem_mde(m, alt.imagem_mde_png(Z), al["mde"]["lon"], al["mde"]["lat"])
        mapas.finalizar(m)
        st_folium(m, height=560, use_container_width=True, key="mapa_alt", returned_objects=[])
    with t2:
        st.plotly_chart(graficos.terreno_contorno(X, Y, Z, g["pol_utm"], al["equidistancia"]), width="stretch")
    with t3:
        ex = st.slider("Exagero vertical", 1.0, 20.0, 5.0, 1.0, key="tmp_exag")
        st.plotly_chart(graficos.terreno_3d(X, Y, Z, ex), width="stretch")
    with t4:
        S = alt.declividade_grade(X, Y, Z)
        st.plotly_chart(graficos.mapa_declividade(X, Y, S, g["pol_utm"]), width="stretch")
