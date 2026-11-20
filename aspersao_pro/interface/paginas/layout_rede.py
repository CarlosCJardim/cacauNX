"""Layout automático da rede sobre a área e exportação para Google Earth/CAD/SIG."""

from __future__ import annotations

import streamlit as st
from streamlit_folium import st_folium

from aspersao import exportar

from .. import estado, graficos, mapas
from ..estado import P, fmt_br, num, sel


def pagina():
    estado.cabecalho("Layout da rede",
                     "Topologia em pente: captação → adutora → principal → derivações → laterais. "
                     "Laterais orientadas em nível pelo MDE para minimizar a variação de pressão.", "📐")
    L = P()["layout"]
    c = st.columns(4)
    sel("Orientação das laterais", "layout", "orientacao",
        {"curva_nivel": "Em nível (curvas de nível do MDE)", "maior_lado": "Paralelas ao maior lado", "manual": "Azimute manual"},
        alvo=c[0])
    if L["orientacao"] == "manual":
        num("Azimute das laterais (graus)", "layout", "azimute", 0.0, 179.9, 1.0, alvo=c[0],
            ajuda="Medido a partir do Norte, no sentido horário (0 = Norte–Sul, 90 = Leste–Oeste).")
    sel("Posição das derivações", "layout", "posicao_derivacao",
        {"central": "Central (laterais dos dois lados)", "borda": "Na borda (laterais de um lado)"}, alvo=c[1])
    num("Nº de derivações (0 = automático)", "layout", "n_derivacoes", 0, 50, 1, alvo=c[2], inteiro=True)
    num("Comprimento máximo da lateral (m, 0 = calcular)", "layout", "comp_max_lateral", 0.0, 2000.0, 6.0, alvo=c[3],
        ajuda="Automático: maior comprimento que mantém a variação de pressão ≤ tolerância com o tubo de referência.")

    lo = estado.etapa("layout")
    if lo is None:
        return
    lay = lo["layout"]
    op = estado.etapa("operacao", False)
    k = st.columns(6)
    k[0].metric("Aspersores", fmt_br(lay.n_aspersores, 0))
    k[1].metric("Laterais", len(lay.laterais))
    k[2].metric("Derivações", len(lay.derivacoes))
    k[3].metric("Área irrigada", f"{fmt_br(lay.area_irrigada_ha)} ha", f"de {fmt_br(lay.area_ha)} ha", delta_color="off", delta_arrow="off")
    k[4].metric("Laterais (total)", f"{fmt_br(lay.comprimento_laterais() / 1000, 2)} km")
    k[5].metric("Derivação + principal + adutora",
                f"{fmt_br(lay.comprimento_derivacoes() + lay.comprimento_principal() + lay.comprimento_adutora(), 0)} m")
    info = f"Orientação: {lo['orientacao']} (azimute {lo['azimute']:.1f}°) · comprimento máximo de lateral {lo['comp_max']:.0f} m"
    if lo.get("info_lmax"):
        info += f" (calculado para {lo['info_lmax']['tubo']}, {lo['info_lmax']['n']} aspersores)"
    st.caption(info)
    estado.avisos(lay.avisos)
    if op is None:
        st.info("Complete clima, cultura e aspersor para setorizar o layout.")

    t1, t2 = st.tabs(["🛰️ Sobre imagem do Google Earth", "📐 Planta técnica (UTM)"])
    with t1:
        res = estado.etapa("rede", False) if op else None
        m = mapas.mapa_base(P()["area"]["centro"], P()["area"].get("zoom", 16), False, "Google Satélite (Google Earth)")
        mapas.adicionar_area(m, P()["area"].get("poligono"), P()["area"].get("fonte"), P()["area"].get("rota_adutora"))
        mapas.adicionar_layout(m, lay, res, lay.n_aspersores <= 8000)
        mapas.finalizar(m)
        st_folium(m, height=620, use_container_width=True, key="mapa_layout", returned_objects=[])
    with t2:
        st.plotly_chart(graficos.planta_setores(lay, lay.n_aspersores <= 15000), width="stretch")

    st.subheader("Exportar")
    res = estado.etapa("rede", False) if op else None
    e1, e2, e3 = st.columns(3)
    nome = P()["info"]["nome"]
    e1.download_button("🌍 KMZ para o Google Earth", exportar.kmz_projeto(nome, lay, res, P()["area"].get("poligono")),
                       file_name="projeto_aspersao.kmz", mime="application/vnd.google-earth.kmz", width="stretch",
                       type="primary")
    e2.download_button("📐 DXF (AutoCAD/QGIS)", exportar.dxf_projeto(lay, res), file_name="projeto_aspersao.dxf",
                       mime="application/dxf", width="stretch")
    e3.download_button("🗺️ GeoJSON (SIG)", exportar.geojson_projeto(lay, res), file_name="projeto_aspersao.geojson",
                       mime="application/geo+json", width="stretch")
    st.caption(f"Coordenadas do DXF em {lay.proj.nome}.")
