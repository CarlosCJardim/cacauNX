"""Área do projeto sobre imagens de satélite do Google Earth, importação KML/KMZ."""

from __future__ import annotations

import numpy as np
import streamlit as st
from streamlit_folium import st_folium

from aspersao import geo

from .. import estado, mapas
from ..estado import P, fmt_br, num


def _feicoes_desenhadas(retorno):
    if not retorno:
        return []
    feats = []
    for f in retorno.get("all_drawings") or []:
        g = f.get("geometry") or {}
        t = g.get("type")
        if t == "Polygon":
            feats.append({"tipo": "Polygon", "coords": [list(c[:2]) for c in g["coordinates"][0]]})
        elif t == "LineString":
            feats.append({"tipo": "LineString", "coords": [list(c[:2]) for c in g["coordinates"]]})
        elif t == "Point":
            feats.append({"tipo": "Point", "coords": [list(g["coordinates"][:2])]})
    return feats


def _aplicar_poligono(coords):
    if coords[0] != coords[-1]:
        coords = coords + [coords[0]]
    P()["area"]["poligono"] = coords
    lon = float(np.mean([c[0] for c in coords[:-1]]))
    lat = float(np.mean([c[1] for c in coords[:-1]]))
    P()["area"]["centro"] = [lat, lon]
    P()["area"]["zoom"] = 16
    if P()["clima"].get("lat") is None:
        P()["clima"]["lat"], P()["clima"]["lon"] = lat, lon


def pagina():
    estado.cabecalho("Área e mapa", "Desenhe ou importe a área sobre as imagens de satélite do Google Earth. "
                     "Marque a captação (bomba) e, se quiser, a rota da adutora.", "🗺️")
    a = P()["area"]
    col_mapa, col_ctrl = st.columns([2.6, 1])

    with col_mapa:
        camada = st.radio("Imagem de fundo", list(mapas.CAMADAS.keys())[:4], horizontal=True, key="tmp_camada",
                          index=1)
        m = mapas.mapa_base(a.get("centro", [-15.79, -47.88]), a.get("zoom", 5), True, camada)
        mapas.adicionar_area(m, a.get("poligono"), a.get("fonte"), a.get("rota_adutora"))
        if st.session_state.get("tmp_mostrar_layout"):
            res_lay = estado.etapa("layout", False)
            if res_lay:
                res_rede = estado.etapa("rede", False) if st.session_state.get("tmp_mostrar_rede") else None
                mapas.adicionar_layout(m, res_lay["layout"], res_rede, True)
        mapas.finalizar(m)
        retorno = st_folium(m, height=640, width=None, use_container_width=True, key="mapa_area",
                            returned_objects=["all_drawings"])
        st.caption("Ferramentas à esquerda do mapa: polígono/retângulo (área), marcador (captação), linha (rota da "
                   "adutora), régua de medição. Busque endereços/municípios pela lupa à direita.")
    feats = _feicoes_desenhadas(retorno)

    with col_ctrl:
        st.subheader("Feições desenhadas")
        pols = [f for f in feats if f["tipo"] == "Polygon"]
        pts = [f for f in feats if f["tipo"] == "Point"]
        lins = [f for f in feats if f["tipo"] == "LineString"]
        if not feats:
            st.caption("Nenhuma feição nova desenhada.")
        if pols and st.button(f"✅ Usar polígono desenhado como área ({len(pols[-1]['coords']) - 1} vértices)",
                              type="primary", width="stretch"):
            _aplicar_poligono(pols[-1]["coords"])
            st.rerun()
        if pts and st.button("📍 Usar marcador como captação / bomba", width="stretch"):
            P()["area"]["fonte"] = pts[-1]["coords"][0]
            st.rerun()
        if lins and st.button("〰️ Usar linha como rota da adutora", width="stretch"):
            P()["area"]["rota_adutora"] = lins[-1]["coords"]
            st.rerun()

        st.subheader("Importar do Google Earth")
        arq = st.file_uploader("KML, KMZ ou GeoJSON", type=["kml", "kmz", "geojson", "json"], key="tmp_kml")
        if arq is not None:
            try:
                nome = arq.name.lower()
                fe = geo.ler_geojson(arq.getvalue()) if nome.endswith(("json", "geojson")) else \
                    geo.ler_kml(arq.getvalue(), arq.name)
                polys = [f for f in fe if f["tipo"] == "Polygon"]
                pontos = [f for f in fe if f["tipo"] == "Point"]
                linhas = [f for f in fe if f["tipo"] == "LineString"]
                st.caption(f"{len(polys)} polígono(s), {len(pontos)} ponto(s), {len(linhas)} linha(s).")
                if polys:
                    escolha = st.selectbox("Polígono da área", range(len(polys)),
                                           format_func=lambda i: polys[i]["nome"], key="tmp_kml_pol")
                    if st.button("Importar polígono", width="stretch"):
                        _aplicar_poligono(polys[escolha]["coords"])
                        if pontos:
                            P()["area"]["fonte"] = pontos[0]["coords"][0]
                        if linhas:
                            P()["area"]["rota_adutora"] = linhas[0]["coords"]
                        st.rerun()
            except Exception as exc:  # noqa: BLE001
                st.error(f"Não foi possível ler o arquivo: {exc}")

        with st.expander("Área retangular por dimensões"):
            r = a["retangulo"]
            c1, c2 = st.columns(2)
            lat = c1.number_input("Latitude do centro", value=float(a["centro"][0]), format="%.6f", key="tmp_rlat")
            lon = c2.number_input("Longitude do centro", value=float(a["centro"][1]), format="%.6f", key="tmp_rlon")
            r["comprimento"] = st.number_input("Comprimento (m)", 10.0, 20000.0, float(r["comprimento"]), 10.0,
                                               key="tmp_rcomp")
            r["largura"] = st.number_input("Largura (m)", 10.0, 20000.0, float(r["largura"]), 10.0, key="tmp_rlarg")
            r["azimute"] = st.number_input("Rotação do comprimento (graus a partir do Leste)", -90.0, 90.0,
                                           float(r["azimute"]), 1.0, key="tmp_raz")
            if st.button("Criar retângulo", width="stretch"):
                _aplicar_poligono(geo.retangulo_lonlat(lat, lon, r["comprimento"], r["largura"], r["azimute"]))
                st.rerun()

        with st.expander("Coordenadas da captação"):
            f = a.get("fonte") or [a["centro"][1], a["centro"][0]]
            c1, c2 = st.columns(2)
            flat = c1.number_input("Latitude", value=float(f[1]), format="%.6f", key="tmp_flat")
            flon = c2.number_input("Longitude", value=float(f[0]), format="%.6f", key="tmp_flon")
            if st.button("Definir captação", width="stretch"):
                P()["area"]["fonte"] = [flon, flat]
                st.rerun()

        st.subheader("Resumo")
        if a.get("poligono") and len(a["poligono"]) >= 4:
            area, per = geo.area_perimetro(a["poligono"])
            proj = geo.Projecao.para_ponto(a["centro"][1], a["centro"][0])
            c1, c2 = st.columns(2)
            c1.metric("Área", f"{fmt_br(area / 1e4)} ha")
            c2.metric("Perímetro", f"{fmt_br(per, 0)} m")
            st.caption(f"Sistema de projeção: {proj.nome}")
            st.download_button("⬇️ Área em KML (abrir no Google Earth)",
                               geo.kml_poligono_simples(P()["info"]["nome"], a["poligono"]),
                               file_name="area_projeto.kml", mime="application/vnd.google-earth.kml+xml",
                               width="stretch")
        else:
            st.info("Defina a área do projeto para continuar.")
        st.markdown(f"**Captação:** {'definida ✅' if a.get('fonte') else 'não definida'}  \n"
                    f"**Rota da adutora:** {'definida ✅' if a.get('rota_adutora') else 'automática (linha reta)'}")
        if a.get("rota_adutora") and st.button("Remover rota da adutora", width="stretch"):
            P()["area"]["rota_adutora"] = []
            st.rerun()
        st.toggle("Sobrepor o layout gerado no mapa", key="tmp_mostrar_layout")
        if st.session_state.get("tmp_mostrar_layout"):
            st.toggle("Incluir rede dimensionada (diâmetros)", key="tmp_mostrar_rede")
