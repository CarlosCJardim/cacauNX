"""Seleção do aspersor, espaçamento, simulação de uniformidade e otimizador."""

from __future__ import annotations

import numpy as np
import pandas as pd
import streamlit as st

from aspersao import aspersores as am
from aspersao import uniformidade as uni
from aspersao.unidades import horas_para_hhmm

from .. import estado, graficos
from ..estado import P, fmt_br, num, sel


def pagina():
    estado.cabecalho("Aspersor e uniformidade",
                     "Uniformidade simulada por superposição do perfil radial (CUC de Christiansen), como no OpenIrri, "
                     "com distorção pelo vento e perdas por evaporação/deriva (Trimmer).", "💧")
    a = P()["aspersor"]
    cat = am.catalogo_completo(a.get("catalogo_usuario"))
    tipos = sorted({x.tipo for x in cat})
    c1, c2 = st.columns([1, 2])
    filtro = c1.multiselect("Tipos", tipos, default=[], key="tmp_filtro_tipos", placeholder="Todos os tipos")
    lista = [x for x in cat if not filtro or x.tipo in filtro]
    ids = [x.id for x in lista]
    if a["id"] not in ids:
        ids = [a["id"]] + ids if a["id"] in [x.id for x in cat] else ids
    rot = {x.id: f"{x.rotulo} ({x.tipo})" for x in cat}
    asp_id = c2.selectbox("Modelo", ids, index=ids.index(a["id"]) if a["id"] in ids else 0,
                          format_func=lambda i: rot.get(i, i), key=estado.chave("aspersor", "id"))
    a["id"] = asp_id
    asp = am.buscar_aspersor(asp_id, a.get("catalogo_usuario"))
    st.caption(f"ℹ️ {asp.nota}")

    c = st.columns(4)
    p_min, p_max = asp.p_min * 0.8, asp.p_max * 1.2
    if not (p_min <= a["pressao_kpa"] <= p_max):
        estado.definir("aspersor", "pressao_kpa", asp.p_nominal)
    num("Pressão de serviço (kPa)", "aspersor", "pressao_kpa", p_min, p_max, 5.0, alvo=c[0],
        ajuda=f"Faixa do catálogo: {asp.p_min:.0f}–{asp.p_max:.0f} kPa.")
    num("Espaçamento na lateral (m)", "aspersor", "esp_asp", 3.0, 60.0, 0.5, alvo=c[1])
    num("Espaçamento entre laterais (m)", "aspersor", "esp_lat", 3.0, 80.0, 0.5, alvo=c[2])
    sel("Arranjo", "aspersor", "arranjo", {"retangular": "Retangular / quadrado", "triangular": "Triangular"}, alvo=c[3])
    c = st.columns(4)
    num("Vento no período de irrigação (m/s)", "aspersor", "vento_ms", 0.0, 10.0, 0.1, alvo=c[0],
        ajuda="Velocidade média durante a irrigação (à noite costuma ser menor).")
    num("Direção do vento em relação à lateral (graus)", "aspersor", "dir_vento", 0.0, 180.0, 15.0, alvo=c[1])
    sel("Perfil radial", "aspersor", "perfil", uni.PERFIS, alvo=c[2])
    num("Altura da haste (m)", "aspersor", "altura_haste", 0.0, 6.0, 0.1, alvo=c[3])

    r = estado.etapa("aspersor")
    if r is None:
        return
    k = st.columns(7)
    k[0].metric("Vazão", f"{fmt_br(r['q'], 3)} m³/h")
    k[1].metric("Diâm. molhado", f"{fmt_br(r['dm'], 1)} m")
    k[2].metric("Intensidade (Ia)", f"{fmt_br(r['ia'])} mm/h")
    k[3].metric("CUC", f"{fmt_br(r['sim']['CUC'], 1)} %")
    k[4].metric("CUD", f"{fmt_br(r['sim']['CUD'], 1)} %")
    k[5].metric("Perdas evap./deriva", f"{fmt_br(r['perdas_evap'], 1)} %")
    k[6].metric("Ea adotada", f"{fmt_br(r['ea'] * 100, 1)} %")
    esp_l, esp_e = r["esp_rec"]
    st.caption(f"Perfil: {uni.PERFIS.get(r['perfil'], r['perfil'])} · q = {r['k']:.5f}·P^{r['x']:.3f} (P em kPa) · "
               f"Ed({P()['agronomico']['adequacao']:.0f}%) = {r['ed']:.1f}% · Espaçamento máximo recomendado para o vento: "
               f"{esp_l:.1f} m na linha × {esp_e:.1f} m entre linhas · DPV no mês crítico {r['dpv_critico']:.2f} kPa.")
    estado.avisos(r["avisos"])
    g1, g2 = st.columns(2)
    with g1:
        st.plotly_chart(graficos.uniformidade(r["sim"], a["esp_asp"], a["esp_lat"], a["arranjo"]), width="stretch")
    with g2:
        pad = uni.padrao_individual(r["q"], r["dm"], r["perfil"], a["vento_ms"], a["dir_vento"], 81, a.get("radial") or None)
        st.plotly_chart(graficos.padrao_individual(pad), width="stretch")

    st.divider()
    t1, t2, t3 = st.tabs(["🔎 Otimizador de aspersor e espaçamento", "📚 Catálogo", "📈 Curva do aspersor"])
    with t1:
        agr = estado.etapa("agronomico", False)
        lb = agr["projeto"]["LB"] if agr else 25.0
        st.markdown(f"Varre o catálogo × pressões × espaçamentos (múltiplos de 6 m) e ordena as alternativas viáveis "
                    f"para LB = **{lb:.1f} mm**, VIB = **{P()['agronomico']['vib']:.1f} mm/h** e jornada de "
                    f"**{P()['operacao']['jornada_h']:.0f} h**.")
        o1, o2, o3 = st.columns(3)
        cuc_min = o1.number_input("CUC mínimo (%)", 60.0, 95.0, 80.0, 1.0, key="tmp_cucmin")
        tipos_ot = o2.multiselect("Tipos considerados", tipos, default=[asp.tipo], key="tmp_tipos_ot")
        arr = o3.multiselect("Arranjos", ["retangular", "triangular"], default=["retangular"], key="tmp_arr_ot")
        if st.button("Executar otimização", type="primary"):
            with st.spinner("Simulando alternativas..."):
                df = uni.otimizar_espacamentos(cat, lb, P()["operacao"]["jornada_h"], P()["agronomico"]["vib"],
                                               a["vento_ms"], a["dir_vento"], arranjos=tuple(arr or ["retangular"]),
                                               cuc_min=cuc_min, tipos_filtro=tipos_ot or None)
            st.session_state["tmp_otim"] = df
        df = st.session_state.get("tmp_otim")
        if df is not None:
            if df.empty:
                st.warning("Nenhuma combinação atendeu os critérios. Reduza o CUC mínimo ou amplie os tipos.")
            else:
                vis = df.drop(columns=["esp_asp", "esp_lat", "Índice"]).head(30)
                sel_ = st.dataframe(vis, hide_index=True, width="stretch", on_select="rerun", selection_mode="single-row",
                                    key="tmp_tab_otim")
                linhas = sel_.selection.rows if sel_ and hasattr(sel_, "selection") else []
                if linhas:
                    lin = df.iloc[linhas[0]]
                    if st.button(f"Aplicar: {lin['ID']} @ {lin['Pressão (kPa)']} kPa, {lin['Espaçamento (m)']} m, {lin['Arranjo']}"):
                        estado.definir("aspersor", "id", lin["ID"])
                        estado.definir("aspersor", "pressao_kpa", float(lin["Pressão (kPa)"]))
                        estado.definir("aspersor", "esp_asp", float(lin["esp_asp"]))
                        estado.definir("aspersor", "esp_lat", float(lin["esp_lat"]))
                        estado.definir("aspersor", "arranjo", lin["Arranjo"])
                        st.rerun()
                st.caption("Índice de ordenação: CUC ponderado pela potência hidráulica por hectare e pelo número de "
                           "aspersores por hectare (menor energia e menor custo).")
    with t2:
        st.dataframe(am.catalogo_df(cat), hide_index=True, width="stretch", height=380)
        st.markdown("**Importar catálogo do fabricante** — uma linha por ponto pressão × vazão × diâmetro molhado.")
        st.download_button("Modelo CSV", am.MODELO_CSV_ASPERSOR, "modelo_catalogo_aspersores.csv")
        arq = st.file_uploader("Catálogo (.csv)", type=["csv"], key="tmp_cat_asp")
        if arq is not None and st.button("Importar catálogo"):
            try:
                novos = am.importar_csv_aspersores(arq.getvalue())
                existentes = {d["id"]: d for d in a.get("catalogo_usuario") or []}
                existentes.update({d["id"]: d for d in novos})
                a["catalogo_usuario"] = list(existentes.values())
                st.success(f"{len(novos)} aspersor(es) importado(s).")
                st.rerun()
            except Exception as exc:  # noqa: BLE001
                st.error(str(exc))
        with st.expander("Perfil radial medido (ensaio de laboratório)"):
            st.caption("Opcional: lâmina relativa em função da distância ao aspersor. Selecione o perfil "
                       "'Perfil medido (tabela radial)' para usá-lo.")
            base = pd.DataFrame(a.get("radial") or [[0, 0.8], [3, 1.0], [6, 1.0], [9, 0.8], [12, 0.4], [r["dm"] / 2, 0.0]],
                                columns=["Distância (m)", "Lâmina relativa"])
            ed = st.data_editor(base, num_rows="dynamic", key="tmp_radial", width="stretch")
            if st.button("Salvar perfil medido"):
                a["radial"] = ed.dropna().sort_values("Distância (m)").values.tolist()
                st.rerun()
    with t3:
        pr = np.linspace(asp.p_min * 0.8, asp.p_max * 1.2, 40)
        import plotly.graph_objects as go
        fig = go.Figure()
        fig.add_scatter(x=pr, y=asp.vazao(pr), mode="lines", line=dict(width=2, color=graficos.CAT[0]), name="Ajuste q = k·P^x")
        fig.add_scatter(x=asp.pressoes_kpa, y=asp.vazoes_m3h, mode="markers", marker=dict(size=9, color=graficos.CAT[1]),
                        name="Catálogo")
        fig.update_xaxes(title="Pressão (kPa)")
        fig.update_yaxes(title="Vazão (m³/h)")
        st.plotly_chart(graficos._base(fig, "Relação vazão × pressão", 340), width="stretch")
        st.dataframe(pd.DataFrame({"Pressão (kPa)": asp.pressoes_kpa, "Vazão (m³/h)": asp.vazoes_m3h,
                                   "Diâmetro molhado (m)": asp.diametros_m}), hide_index=True)
