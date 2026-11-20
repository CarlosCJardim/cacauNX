"""AspersãoPro — projeto profissional de irrigação por aspersão com manejo pelo clima.

Execute com:  streamlit run app.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).parent))

from aspersao import NOME_PROGRAMA, __version__  # noqa: E402
from aspersao.projeto import salvar  # noqa: E402
from interface import estado  # noqa: E402
from interface.paginas import (agronomia, altimetria, area_mapa, aspersor, bomba, clima, hidraulica, inicio,  # noqa: E402
                               layout_rede, manejo, operacao, orcamento, relatorios)

st.set_page_config(page_title=f"{NOME_PROGRAMA} — Projeto de Irrigação por Aspersão", page_icon="💧", layout="wide",
                   initial_sidebar_state="expanded")
estado.iniciar()

st.markdown("""
<style>
[data-testid="stMetricValue"] { font-size: 1.45rem; }
[data-testid="stSidebarNav"] span { font-size: 0.93rem; }
.bloco-nota { border-left: 3px solid #2a78d6; padding: 0.4rem 0.8rem; background: rgba(42,120,214,0.06);
              border-radius: 0 6px 6px 0; margin: 0.4rem 0 0.8rem 0; font-size: 0.92rem; }
</style>
""", unsafe_allow_html=True)

paginas = {
    "Projeto": [st.Page(inicio.pagina, title="Início", icon="🏠", url_path="inicio", default=True)],
    "1 · Dados de campo": [
        st.Page(area_mapa.pagina, title="Área e mapa (Google Earth)", icon="🗺️", url_path="area"),
        st.Page(altimetria.pagina, title="Altimetria", icon="⛰️", url_path="altimetria"),
    ],
    "2 · Agronomia — manejo pelo clima": [
        st.Page(clima.pagina, title="Clima e ETo", icon="🌦️", url_path="clima"),
        st.Page(agronomia.pagina, title="Cultura e necessidade hídrica", icon="🌱", url_path="cultura"),
    ],
    "3 · Equipamento e operação": [
        st.Page(aspersor.pagina, title="Aspersor e uniformidade", icon="💧", url_path="aspersor"),
        st.Page(operacao.pagina, title="Operação e setorização", icon="⏱️", url_path="operacao"),
    ],
    "4 · Rede e bombeamento": [
        st.Page(layout_rede.pagina, title="Layout da rede", icon="📐", url_path="layout"),
        st.Page(hidraulica.pagina, title="Hidráulica", icon="🔧", url_path="hidraulica"),
        st.Page(bomba.pagina, title="Bomba e energia", icon="⚙️", url_path="bomba"),
    ],
    "5 · Resultados": [
        st.Page(orcamento.pagina, title="Orçamento", icon="💰", url_path="orcamento"),
        st.Page(manejo.pagina, title="Manejo pelo clima", icon="📅", url_path="manejo"),
        st.Page(relatorios.pagina, title="Relatórios e exportação", icon="📄", url_path="relatorios"),
    ],
}

with st.sidebar:
    st.markdown(f"### 💧 {NOME_PROGRAMA}")
    st.caption(f"Projeto de irrigação por aspersão · v{__version__}")
    st.markdown(f"**Projeto:** {estado.P()['info']['nome']}")

nav = st.navigation(paginas, position="sidebar", expanded=True)
nav.run()

with st.sidebar:
    st.divider()
    st.download_button("💾 Salvar projeto (.json)", data=salvar(estado.P()),
                       file_name=f"{estado.P()['info']['nome'][:40].replace(' ', '_')}.json", mime="application/json",
                       width="stretch")
    st.caption("Motor de cálculo: FAO-56 · Christiansen · Keller & Bliesner · Hazen-Williams/Darcy-Weisbach.")
