"""Relatórios: memorial em PDF, planilha Excel, projeto JSON e arquivos geográficos."""

from __future__ import annotations

import streamlit as st

from aspersao import exportar, relatorios
from aspersao.pipeline import executar_tudo
from aspersao.projeto import salvar

from .. import estado
from ..estado import P


def pagina():
    estado.cabecalho("Relatórios e exportação", "Memorial descritivo e de cálculo, planilhas e arquivos para "
                     "Google Earth, CAD e SIG.", "📄")
    nome = P()["info"]["nome"].replace(" ", "_")[:50]
    if st.button("Gerar memorial e planilha", type="primary"):
        with st.spinner("Executando todas as etapas e gerando documentos..."):
            r = executar_tudo(P())
            st.session_state["tmp_pdf"] = relatorios.gerar_pdf(P(), r)
            st.session_state["tmp_xlsx"] = relatorios.gerar_excel(P(), r)
            st.session_state["tmp_erros"] = r["erros"]
            lo, rede = r.get("layout"), r.get("rede")
            if lo:
                st.session_state["tmp_kmz"] = exportar.kmz_projeto(P()["info"]["nome"], lo["layout"], rede,
                                                                   P()["area"].get("poligono"))
                st.session_state["tmp_dxf"] = exportar.dxf_projeto(lo["layout"], rede)
    erros = st.session_state.get("tmp_erros")
    if erros:
        st.warning("Etapas incompletas: " + "; ".join(f"**{k}** — {v}" for k, v in erros.items()))
    c = st.columns(5)
    if st.session_state.get("tmp_pdf"):
        c[0].download_button("📕 Memorial (PDF)", st.session_state["tmp_pdf"], f"memorial_{nome}.pdf",
                             "application/pdf", width="stretch", type="primary")
    if st.session_state.get("tmp_xlsx"):
        c[1].download_button("📗 Planilha (Excel)", st.session_state["tmp_xlsx"], f"calculos_{nome}.xlsx",
                             "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", width="stretch")
    if st.session_state.get("tmp_kmz"):
        c[2].download_button("🌍 Google Earth (KMZ)", st.session_state["tmp_kmz"], f"{nome}.kmz",
                             "application/vnd.google-earth.kmz", width="stretch")
    if st.session_state.get("tmp_dxf"):
        c[3].download_button("📐 CAD (DXF)", st.session_state["tmp_dxf"], f"{nome}.dxf", "application/dxf",
                             width="stretch")
    c[4].download_button("💾 Projeto (JSON)", salvar(P()), f"{nome}.json", "application/json", width="stretch")
    st.markdown("""
**Conteúdo do memorial:** resumo; localização, layout e altimetria; clima e ETo (FAO-56); cultura e necessidade
hídrica com manejo pelo clima; aspersor e uniformidade; operação e setorização; dimensionamento hidráulico
(lateral crítica, trechos, golpe de aríete); conjunto motobomba e energia; orçamento e análise econômica;
roteiro de manejo pelo clima; referências e campo para assinatura do responsável técnico.

O arquivo **JSON** guarda todo o projeto (inclusive a série climática e o MDE) e pode ser reaberto na página
Início — garante rastreabilidade e reprodutibilidade dos cálculos.
""")
