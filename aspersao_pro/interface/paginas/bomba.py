"""Bomba, motor, NPSH, curvas e custo de energia."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from aspersao.unidades import horas_para_hhmm

from .. import estado, graficos
from ..estado import P, fmt_br, num, sel


def pagina():
    estado.cabecalho("Bomba e energia", "Altura manométrica, NPSH, potência, motor comercial, ponto de operação e "
                     "custo anual de energia com desconto da tarifa noturna para irrigantes.", "⚙️")
    b = P()["bomba"]
    c = st.columns(4)
    num("Altura de sucção (m)", "bomba", "altura_succao", -10.0, 8.0, 0.1, alvo=c[0],
        ajuda="Desnível entre o eixo da bomba e o nível d'água mínimo. Negativo = bomba afogada.")
    num("Comprimento da sucção (m)", "bomba", "comp_succao", 1.0, 100.0, 0.5, alvo=c[0])
    num("Perda no cabeçal de controle (m)", "bomba", "h_cabecal", 0.0, 20.0, 0.5, alvo=c[1],
        ajuda="Filtro de tela, hidrômetro, válvulas de retenção e gaveta.")
    num("Temperatura da água (°C)", "bomba", "temp_agua", 5.0, 40.0, 1.0, alvo=c[1])
    num("Rendimento da bomba no ponto", "bomba", "eta_bomba", 0.30, 0.90, 0.01, alvo=c[2])
    sel("Rotação", "bomba", "rpm", ["auto", 3500, 1750, 1150], formato=lambda v: "Automática" if v == "auto" else f"{v} rpm",
        alvo=c[2])
    sel("Curva da bomba", "bomba", "curva", {"sintetica": "Genérica (passa pelo ponto de projeto)",
                                             "usuario": "Do fabricante (pontos)"}, alvo=c[3])
    if b["curva"] == "usuario":
        base = pd.DataFrame(b.get("pontos_curva") or [{"Q (m³/h)": 0.0, "H (m)": 60.0, "η (%)": 0.0, "NPSHr (m)": 2.0},
                                                       {"Q (m³/h)": 100.0, "H (m)": 55.0, "η (%)": 70.0, "NPSHr (m)": 3.0},
                                                       {"Q (m³/h)": 200.0, "H (m)": 42.0, "η (%)": 76.0, "NPSHr (m)": 5.0}])
        ed = st.data_editor(base, num_rows="dynamic", width="stretch", key="tmp_curva_bomba")
        if st.button("Usar estes pontos"):
            b["pontos_curva"] = ed.dropna().to_dict("records")
            st.rerun()
    st.markdown("**Energia**")
    c = st.columns(4)
    sel("Fonte de energia", "bomba", "energia", {"eletrica": "Elétrica", "diesel": "Diesel"}, alvo=c[0])
    if b["energia"] == "eletrica":
        num("Tarifa de energia (R$/kWh)", "bomba", "tarifa_kwh", 0.05, 3.0, 0.01, alvo=c[1])
        num("Desconto irrigação noturna (%)", "bomba", "desconto_noturno", 0.0, 90.0, 5.0, alvo=c[2],
            ajuda="Resolução ANEEL 1.000/2021 — desconto para irrigação em 8h30 contínuas no período noturno.")
        num("Horas diárias com desconto", "bomba", "horas_desconto", 0.0, 12.0, 0.5, alvo=c[3])
    else:
        num("Preço do diesel (R$/L)", "bomba", "preco_diesel", 1.0, 15.0, 0.05, alvo=c[1])

    bm = estado.etapa("bomba")
    if bm is None:
        return
    pot = bm["potencias"]
    k = st.columns(6)
    k[0].metric("Vazão", f"{fmt_br(bm['Q'], 1)} m³/h")
    k[1].metric("Altura manométrica", f"{fmt_br(bm['Hman'], 1)} m")
    k[2].metric("Potência no eixo", f"{fmt_br(pot['P_eixo_cv'], 1)} cv")
    k[3].metric("Motor comercial", f"{pot['motor']['motor_cv']:g} cv",
                f"folga {pot['motor']['folga'] * 100:.0f}%", delta_color="off", delta_arrow="off")
    k[4].metric("NPSH disp. / req.", f"{fmt_br(bm['npsh']['NPSHd'], 1)} / {fmt_br(bm['npshr'], 1)} m")
    k[5].metric("Rotação específica nq", f"{fmt_br(bm['nq'], 0)}", f"{bm['rpm']:.0f} rpm", delta_color="off", delta_arrow="off")
    st.caption(f"Tipo de rotor indicado: {bm['tipo_rotor']} · Sucção: {bm['tubo_succao'].rotulo} "
               f"(v = {bm['v_succao']:.2f} m/s) · Potência hidráulica {pot['P_hidraulica_kW']:.1f} kW · "
               f"potência elétrica {pot['P_eletrica_kW']:.1f} kW (η motor {pot['eta_motor'] * 100:.1f}%).")
    estado.avisos(bm["avisos"])
    if bm["npsh"]["NPSHd"] >= bm["npshr"] + 0.6:
        st.success("✅ Sem risco de cavitação: NPSH disponível ≥ NPSH requerido + 0,6 m.")
    g1, g2 = st.columns([1.2, 1])
    with g1:
        st.plotly_chart(graficos.curvas_bomba(bm["curva"], bm["h_sis"], bm["ponto"], bm["pontos_setores"], bm["Q"],
                                              bm["npsh"]["NPSHd"]), width="stretch")
    with g2:
        st.plotly_chart(graficos.cascata_hman(bm["decomposicao"], bm["Hman"]), width="stretch")
        if bm["ponto"]:
            st.markdown(f"**Ponto de operação (setor crítico):** {bm['ponto'][0]:.1f} m³/h × {bm['ponto'][1]:.1f} m")
        if bm["rotacao_ideal"] and P()["bomba"]["curva"] == "usuario" and abs(bm["rotacao_ideal"] - 1) > 0.01:
            st.caption(f"Rotação que atende exatamente o ponto de projeto: {bm['rotacao_ideal'] * bm['rpm']:.0f} rpm "
                       f"({bm['rotacao_ideal'] * 100:.0f}% da nominal — ajuste por inversor de frequência).")
        st.dataframe(pd.DataFrame(bm["pontos_setores"]), hide_index=True, width="stretch", height=240)
    st.subheader("Custo anual de energia")
    e = bm["energia"]
    k = st.columns(4)
    k[0].metric("Volume anual de projeto", f"{fmt_br(bm['volume_ano'], 0)} m³")
    k[1].metric("Horas de bombeamento/ano", fmt_br(bm["horas_ano"], 0))
    k[2].metric("Energia anual", f"{fmt_br(e['energia_kWh'], 0)} kWh")
    k[3].metric("Custo anual", f"R$ {fmt_br(e['custo_total'], 0)}")
    if P()["bomba"]["energia"] == "eletrica" and e.get("fracao_desconto"):
        st.caption(f"{e['fracao_desconto'] * 100:.0f}% das horas diárias de operação ocorrem no período com desconto.")
