"""Dimensionamento hidráulico: laterais, derivações, principal e adutora; simulação por setor."""

from __future__ import annotations

import numpy as np
import pandas as pd
import streamlit as st

from aspersao import hidraulica as hid
from aspersao import rede as rede_mod
from aspersao import tubos as tub
from aspersao.unidades import mca_para_kpa

from .. import estado, graficos
from ..estado import P, fmt_br, num, sel


def pagina():
    estado.cabecalho("Hidráulica", "Cálculo passo a passo com a cota real de cada aspersor (MDE), fator F de "
                     "Christiansen como verificação, tolerância de 20 % na lateral e simulação por setor.", "🔧")
    h = P()["hidraulica"]
    mats = tub.MATERIAIS
    with st.expander("⚙️ Critérios e materiais", expanded=False):
        c = st.columns(4)
        sel("Equação de perda de carga", "hidraulica", "equacao",
            {"HW": "Hazen-Williams", "DW": "Darcy-Weisbach (Swamee-Jain)"}, alvo=c[0])
        num("Temperatura da água (°C)", "hidraulica", "t_agua", 5.0, 40.0, 1.0, alvo=c[0])
        sel("Material das laterais", "hidraulica", "mat_lateral", mats, alvo=c[1])
        sel("Material das derivações", "hidraulica", "mat_derivacao", mats, alvo=c[1])
        sel("Material da principal", "hidraulica", "mat_principal", mats, alvo=c[2])
        sel("Material da adutora", "hidraulica", "mat_adutora", mats, alvo=c[2])
        sel("Diâmetro das laterais", "hidraulica", "modo_lateral",
            {"uniforme": "Único para todas (padroniza compra)", "individual": "Individual por lateral"}, alvo=c[3])
        cand = tub.tubos_por_material(h["mat_lateral"])
        sel("Tubo de referência (comprimento máx.)", "hidraulica", "dn_ref_lateral",
            ["auto"] + [t.dn for t in cand], formato=lambda d: "Automático" if d == "auto" else f"DN {d}", alvo=c[3])
        c = st.columns(4)
        num("Variação de pressão máx. na lateral (%)", "hidraulica", "tol_lateral", 5.0, 40.0, 1.0, alvo=c[0],
            ajuda="Critério de Christiansen: 20 % da PS (≈ 10 % de variação de vazão).")
        num("Variação máx. entre laterais do setor (%)", "hidraulica", "tol_derivacao", 2.0, 30.0, 1.0, alvo=c[0])
        num("Velocidade máx. — laterais (m/s)", "hidraulica", "v_max_lateral", 0.5, 4.0, 0.1, alvo=c[1])
        num("Velocidade máx. — derivações (m/s)", "hidraulica", "v_max_derivacao", 0.5, 3.0, 0.1, alvo=c[1])
        num("Velocidade máx. — principal (m/s)", "hidraulica", "v_max_principal", 0.5, 3.0, 0.1, alvo=c[2])
        num("Velocidade máx. — adutora (m/s)", "hidraulica", "v_max_adutora", 0.5, 3.0, 0.1, alvo=c[2])
        num("Perdas localizadas na rede (% do atrito)", "hidraulica", "perda_local_rede", 0.0, 50.0, 1.0, alvo=c[3])
        num("Perdas localizadas nas laterais (%)", "hidraulica", "perda_local_lateral", 0.0, 50.0, 1.0, alvo=c[3],
            ajuda="Engates de alumínio já estão considerados no C = 130.")
        c = st.columns(4)
        sel("Critério da principal/adutora", "hidraulica", "criterio_principal",
            {"velocidade": "Velocidade máxima", "economico": "Diâmetro econômico (custo anual mínimo)"}, alvo=c[0])
        sel("Reguladores de pressão", "hidraulica", "reguladores",
            {"auto": "Automático (quando necessário)", "sempre": "Em todas as laterais", "nunca": "Não usar"}, alvo=c[1])
        num("Excesso que exige regulador (% da PS)", "hidraulica", "limite_regulador", 2.0, 40.0, 1.0, alvo=c[1])
        num("Fator de segurança da classe de pressão", "hidraulica", "margem_pn", 1.0, 2.0, 0.05, alvo=c[2])
        num("Tempo de fechamento das válvulas (s)", "hidraulica", "tempo_manobra_s", 0.5, 120.0, 0.5, alvo=c[3])

    res = estado.etapa("rede")
    if res is None:
        return
    pp = estado.pipe()
    lay = pp.get("layout")["layout"]
    a = pp.get("aspersor")
    crit = res.setores[res.setor_critico]
    k = st.columns(6)
    k[0].metric("Pressão na saída da bomba", f"{fmt_br(res.p_fonte_max, 1)} mca",
                f"{fmt_br(mca_para_kpa(res.p_fonte_max), 0)} kPa", delta_color="off", delta_arrow="off")
    k[1].metric("Setor crítico", res.setor_critico + 1)
    k[2].metric("Vazão máxima", f"{fmt_br(res.q_max, 1)} m³/h")
    var_lat = [v["res"].var_pressao_pct for v in res.laterais.values()]
    k[3].metric("Variação máx. nas laterais", f"{fmt_br(max(var_lat), 1)} %")
    k[4].metric("Laterais fora do critério", sum(1 for v in res.laterais.values() if not v["atende"]))
    regs = {n for s in res.setores if s for n in s["reguladores"]}
    k[5].metric("Pontos com regulador", len(regs))
    estado.avisos(res.avisos)

    t1, t2, t3, t4, t5 = st.tabs(["🧵 Laterais", "🔀 Rede e diâmetros", "📊 Setores", "🧪 Simulação do setor",
                                  "🌊 Adutora e golpe de aríete"])
    with t1:
        ids = sorted(res.laterais, key=lambda i: -res.laterais[i]["res"].h_entrada)
        escolha = st.selectbox("Lateral", ids, format_func=lambda i: (
            f"Lateral {i + 1} — setor {lay.laterais[i].setor + 1} — {lay.laterais[i].n} aspersores — "
            f"Pin {res.laterais[i]['res'].h_entrada:.1f} mca — ΔP {res.laterais[i]['res'].var_pressao_pct:.1f}%"),
            key="tmp_lat_sel")
        rl = res.laterais[escolha]
        l = lay.laterais[escolha]
        r = rl["res"]
        c = st.columns(5)
        c[0].metric("Tubo", f"{rl['tubo'].material} DN {rl['tubo'].dn}")
        c[1].metric("Pressão na entrada", f"{fmt_br(r.h_entrada, 2)} mca")
        c[2].metric("Vazão na entrada", f"{fmt_br(r.q_entrada_m3h, 2)} m³/h")
        c[3].metric("Variação de pressão", f"{fmt_br(r.var_pressao_pct, 1)} %")
        c[4].metric("Desnível (fim − início)", f"{fmt_br(r.dz, 2)} m")
        st.plotly_chart(graficos.perfil_lateral(r, a["h_servico"], P()["hidraulica"]["tol_lateral"] / 100), width="stretch")
        ch = hid.lateral_christiansen(l.n, lay.esp_asp, a["q"], rl["tubo"], a["h_servico"], r.dz,
                                      P()["aspersor"]["altura_haste"], 0.5, P()["hidraulica"]["equacao"])
        st.caption(f"Verificação analítica (Christiansen): F = {ch['F']:.4f}, hf = {ch['hf']:.2f} m, "
                   f"Pin = PS + ¾hf + ½ΔZ + Ha = {ch['h_entrada']:.2f} mca (passo a passo: {r.h_entrada:.2f} mca). "
                   f"CUC de vazão na lateral: {r.cuc_vazao:.1f}%.")
        resumo = pd.DataFrame([{"Lateral": i + 1, "Setor": lay.laterais[i].setor + 1, "Aspersores": lay.laterais[i].n,
                                "Comprimento (m)": round(lay.laterais[i].comprimento, 1),
                                "Tubo": v["tubo"].rotulo, "Pin (mca)": round(v["res"].h_entrada, 2),
                                "Q (m³/h)": round(v["res"].q_entrada_m3h, 2), "ΔP (%)": round(v["res"].var_pressao_pct, 1),
                                "Δq (%)": round(v["res"].var_vazao_pct, 1), "ΔZ (m)": round(v["res"].dz, 2),
                                "Atende": "✅" if v["atende"] else "❌"} for i, v in res.laterais.items()])
        with st.expander("Todas as laterais"):
            st.dataframe(resumo, hide_index=True, width="stretch", height=360)
    with t2:
        st.plotly_chart(graficos.planta_diametros(lay, res), width="stretch")
        tab = pd.DataFrame([{"Trecho": t.id, "Tipo": rede_mod.NOMES_TIPO[t.tipo], "Material": t.tubo.material, "DN": t.tubo.dn,
                             "PN (mca)": t.tubo.pn_mca, "DI (mm)": t.tubo.di_mm, "L (m)": round(t.comprimento, 1),
                             "Q proj. (m³/h)": round(t.q_proj, 1), "v (m/s)": round(t.v_proj, 2),
                             "hf máx. (m)": round(t.hf_proj, 3), "P máx. (mca)": round(t.p_max, 1)} for t in res.trechos])
        st.markdown("**Linhas da rede (trechos consecutivos com o mesmo tubo agrupados)**")
        st.dataframe(rede_mod.trechos_agrupados(res), hide_index=True, width="stretch")
        with st.expander("Todos os trechos (nó a nó)"):
            st.dataframe(tab, hide_index=True, width="stretch", height=360)
        resumo_tubos = tab.groupby(["Tipo", "Material", "DN", "PN (mca)"], as_index=False)["L (m)"].sum()
        st.markdown("**Quantitativo de tubos da rede**")
        st.dataframe(resumo_tubos, hide_index=True)
    with t3:
        linhas = []
        for s in res.setores:
            if not s:
                continue
            linhas.append({"Setor": s["setor"] + 1, "Q (m³/h)": round(s["Q_m3h"], 1),
                           "Pressão na bomba (mca)": round(s["p_fonte"], 2), "Nó crítico": s["no_critico"],
                           "Excesso máx. (mca)": round(s["excesso_max"], 2),
                           "Excesso máx. (% PS)": round(s["variacao_pct"], 1), "Reguladores": len(s["reguladores"])})
        st.dataframe(pd.DataFrame(linhas), hide_index=True, width="stretch")
        st.caption("Excesso = pressão disponível na entrada da lateral menos a pressão requerida por ela. Setores com "
                   "pressão de bomba muito diferente se beneficiam de inversor de frequência.")
    with t4:
        s_ids = [s["setor"] for s in res.setores if s]
        s = st.selectbox("Setor", s_ids, index=s_ids.index(res.setor_critico), format_func=lambda i: f"Setor {i + 1}",
                         key="tmp_sim_setor")
        c1, c2 = st.columns(2)
        p_bomba = c1.number_input("Pressão na saída da bomba (mca)", 1.0, 300.0, float(res.setores[s]["p_fonte"]), 0.5,
                                  key="tmp_sim_p")
        com_reg = c2.toggle("Considerar reguladores de pressão", True, key="tmp_sim_reg")
        if st.button("Simular setor", type="primary"):
            with st.spinner("Resolvendo a rede com vazões dependentes da pressão..."):
                sim = rede_mod.simular_setor(lay, res, s, a["k"], a["x"], a["h_servico"], pp.config_hidraulica(),
                                             p_bomba, com_reg)
            st.session_state["tmp_sim_res"] = (s, sim)
        guard = st.session_state.get("tmp_sim_res")
        if guard and guard[0] == s and guard[1]:
            sim = guard[1]
            c = st.columns(5)
            c[0].metric("Vazão do setor", f"{fmt_br(sim['Q_total'], 1)} m³/h")
            c[1].metric("Pressão média", f"{fmt_br(sim['p_media'], 1)} mca")
            c[2].metric("Faixa de pressão", f"{fmt_br(sim['p_min'], 1)}–{fmt_br(sim['p_max'], 1)} mca")
            c[3].metric("CUC de vazão", f"{fmt_br(sim['cuc_vazao'], 1)} %")
            c[4].metric("CUD de vazão", f"{fmt_br(sim['cud_vazao'], 1)} %")
            st.plotly_chart(graficos.pressoes_setor(sim, a["h_servico"]), width="stretch")
    with t5:
        perfil = res.perfil_adutora
        hf_adut = crit["hf"][res.trechos[0].id]
        h_ini = res.rede.z["F"] + crit["p_fonte"]
        st.plotly_chart(graficos.perfil_adutora(perfil, h_ini, h_ini - hf_adut, res.rede.z["F"]), width="stretch")
        st.caption(f"{len(perfil['altos'])} ponto(s) alto(s) — ventosas; {len(perfil['baixos'])} ponto(s) baixo(s) — "
                   "registros de descarga. Instale também ventosas no início de cada derivação e no ponto mais alto da rede.")
        g = res.golpe
        tr = res.trechos[0]
        c = st.columns(4)
        c[0].metric("Celeridade da onda", f"{fmt_br(g['celeridade'], 0)} m/s")
        c[1].metric("Tempo crítico 2L/c", f"{fmt_br(g['tempo_critico'], 1)} s")
        c[2].metric("Sobrepressão", f"{fmt_br(g['sobrepressao'], 1)} mca")
        p_tot = crit["p_fonte"] + g["sobrepressao"]
        c[3].metric("Pressão máx. transitória", f"{fmt_br(p_tot, 1)} mca", f"PN do tubo: {tr.tubo.pn_mca:.0f} mca",
                    delta_color="off", delta_arrow="off")
        st.caption(f"{g['regime']}. " + ("✅ A classe de pressão suporta o transitório." if p_tot <= tr.tubo.pn_mca else
                                         "❌ Transitório excede a classe do tubo: aumente o tempo de fechamento, instale "
                                         "válvula antigolpe/alívio ou use classe superior."))
