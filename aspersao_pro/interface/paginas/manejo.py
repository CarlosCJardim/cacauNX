"""Manejo da irrigação pelo clima: boletim com previsão do tempo, estação ou tanque Classe A,
e simulação da operação com a série histórica."""

from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pandas as pd
import streamlit as st

from aspersao import manejo as mnj
from aspersao.clima import fontes
from aspersao.clima import penman as pm
from aspersao.clima.estatistica import kp_snyder
from aspersao.pipeline import kc_serie_manejo, simular_manejo
from aspersao.unidades import horas_para_hhmm

from .. import estado, graficos
from ..estado import P, fmt_br, num, sel


def _eto_de_df(d, lat, z):
    """ETo própria (PM) quando há variáveis; senão usa a ETo da fonte."""
    tem_vars = {"tmax", "tmin"}.issubset(d.columns) and d[["tmax", "tmin"]].notna().all(axis=1).mean() > 0.8
    if tem_vars:
        dd = pm.et0_diario_df(d, lat, z)
        eto = dd["eto_pm"]
        if "eto_fonte" in d:
            eto = eto.fillna(d["eto_fonte"])
        return eto
    return d.get("eto_fonte", d.get("eto"))


def pagina():
    estado.cabecalho("Manejo da irrigação pelo clima",
                     "Lâmina = ETc acumulada − chuva efetiva desde a última irrigação. Tempo de cada setor = "
                     "lâmina bruta ÷ intensidade de aplicação.", "📅")
    m = P()["manejo"]
    agr = estado.etapa("agronomico")
    asp = estado.etapa("aspersor", False)
    if agr is None or asp is None:
        return
    c = st.columns(4)
    sel("Estratégia", "manejo", "estrategia", mnj.ESTRATEGIAS, alvo=c[0])
    num("Chuva mínima efetiva (mm)", "manejo", "limiar_pe", 0.0, 20.0, 0.5, alvo=c[1],
        ajuda="Chuvas menores são consideradas perdidas por interceptação/evaporação.")
    num("Aproveitamento da chuva", "manejo", "frac_pe", 0.3, 1.0, 0.05, alvo=c[2])
    num("Adiar se a previsão de chuva cobrir (mm)", "manejo", "adiar_chuva_mm", 0.0, 50.0, 1.0, alvo=c[3],
        ajuda="Se a chuva prevista para os próximos 2 dias cobrir o saldo (até este valor), a irrigação é adiada.")
    st.caption(f"Projeto: TR = {agr['projeto']['TR']:.0f} d · LL = {agr['projeto']['LL']:.1f} mm · "
               f"Ea = {asp['ea'] * 100:.1f}% · Ia = {asp['ia']:.2f} mm/h.")

    t1, t2, t3 = st.tabs(["🌤️ Boletim com previsão do tempo", "📈 Simulação com série histórica",
                          "🧪 Estação local ou tanque Classe A"])
    cl = estado.etapa("clima", False)
    lat = P()["clima"].get("lat") or P()["area"]["centro"][0]
    lon = P()["clima"].get("lon") or P()["area"]["centro"][1]
    z = (cl or {}).get("altitude", 500.0)

    with t1:
        c1, c2, c3 = st.columns(3)
        dias_p = c1.number_input("Dias passados", 1, 60, int(m.get("dias_passados", 14)), key="tmp_dp")
        saldo0 = c2.number_input("Saldo no início (mm)", -50.0, 200.0, 0.0, 0.5, key="tmp_saldo0",
                                 help="Déficit já acumulado no primeiro dia baixado (0 = irrigado no dia anterior).")
        if c3.button("Atualizar previsão (Open-Meteo)", type="primary"):
            try:
                with st.spinner("Baixando observações recentes e previsão de 16 dias..."):
                    df, _ = fontes.open_meteo_previsao(lat, lon, int(dias_p), 16)
                st.session_state["tmp_prev"] = df
            except fontes.ErroFonteDados as exc:
                st.error(f"{exc}\n\nSem internet? Use a aba 'Estação local ou tanque Classe A'.")
        df = st.session_state.get("tmp_prev")
        if df is not None:
            d = pd.DataFrame(index=df.index)
            d["eto"] = _eto_de_df(df, lat, z)
            d["chuva"] = df.get("chuva", 0.0)
            if "prob_chuva" in df:
                d["prob_chuva"] = df["prob_chuva"]
            hoje = pd.Timestamp(date.today())
            d["previsao"] = d.index >= hoje
            futura = d["chuva"].where(d["previsao"], 0.0)
            d["chuva_prevista_prox"] = futura.shift(-1).fillna(0) + futura.shift(-2).fillna(0)
            bal = mnj.balanco_climatico(d, kc_serie_manejo(estado.pipe(), d.index),
                                        asp["ea"], asp["ia"], m["estrategia"], int(agr["projeto"]["TR"]),
                                        agr["projeto"]["LL"], m["limiar_pe"], m["frac_pe"], m.get("credito_max"), None,
                                        m.get("adiar_chuva_mm", 0.0), saldo0)
            bal["previsao"] = d["previsao"]
            prox = bal[(bal.index >= hoje) & (bal["irrig_liq"] > 0)]
            if prox.empty:
                st.success("Nenhuma irrigação necessária nos próximos 16 dias segundo a previsão.")
            else:
                ev = prox.iloc[0]
                st.markdown(f"### Próxima irrigação: **{prox.index[0]:%d/%m/%Y}**")
                k = st.columns(4)
                k[0].metric("Lâmina líquida", f"{fmt_br(ev['irrig_liq'], 1)} mm")
                k[1].metric("Lâmina bruta", f"{fmt_br(ev['irrig_bruta'], 1)} mm")
                k[2].metric("Tempo por setor", horas_para_hhmm(ev["tempo_h"]))
                k[3].metric("Eventos previstos (16 d)", len(prox))
                op = estado.etapa("operacao", False)
                if op is not None:
                    bol = mnj.boletim_setores(ev["irrig_bruta"], op["setores"], asp["ia"], asp["ea"],
                                              P()["operacao"].get("hora_inicio", 21.5), P()["operacao"]["t_mudanca_h"],
                                              P()["operacao"]["jornada_h"])
                    st.dataframe(bol, hide_index=True, width="stretch")
                    st.download_button("⬇️ Boletim (CSV)", bol.to_csv(index=False, sep=";", decimal=","),
                                       f"boletim_irrigacao_{prox.index[0]:%Y%m%d}.csv")
            st.plotly_chart(graficos.manejo(bal), width="stretch")
            vis = bal.copy()
            vis.index = vis.index.strftime("%d/%m/%Y")
            st.dataframe(vis.drop(columns=["previsao"]).round(2), width="stretch", height=320)

    with t2:
        if cl is None or cl["diario"] is None:
            st.info("Carregue uma série climática diária na página Clima para simular a operação do sistema "
                    "ao longo dos anos (atendimento da demanda, volume e energia).")
        else:
            d = cl["diario"][["eto", "chuva"]].copy()
            if st.button("Simular operação histórica"):
                with st.spinner("Simulando..."):
                    bal = simular_manejo(estado.pipe(), d)
                st.session_state["tmp_bal_hist"] = bal
            bal = st.session_state.get("tmp_bal_hist")
            if bal is not None:
                try:
                    bm = estado.pipe().get("bomba")
                    op = estado.pipe().get("operacao")
                    resumo = mnj.resumo_simulacao(bal, agr["area_ha"], op["Q_sistema"], bm["potencias"]["P_eletrica_kW"])
                except Exception:  # noqa: BLE001
                    resumo = mnj.resumo_simulacao(bal, agr["area_ha"], 1.0, 0.0)
                k = st.columns(5)
                k[0].metric("ETc média anual", f"{fmt_br(resumo['etc_total_mm_ano'], 0)} mm")
                k[1].metric("Irrigação bruta/ano", f"{fmt_br(resumo['irrig_bruta_mm_ano'], 0)} mm")
                k[2].metric("Volume/ano", f"{fmt_br(resumo['volume_m3_ano'], 0)} m³")
                k[3].metric("Bombeamento/ano", f"{fmt_br(resumo['horas_bombeamento_ano'], 0)} h")
                k[4].metric("Atendimento da demanda", f"{fmt_br(resumo['atendimento_pct'], 1)} %",
                            help="Dias em que o saldo não excedeu uma lâmina de projeto (capacidade suficiente).")
                anos = sorted(set(bal.index.year))
                ano = st.select_slider("Ano exibido", anos, value=anos[-1], key="tmp_ano_bal")
                st.plotly_chart(graficos.manejo(bal[bal.index.year == ano]), width="stretch")
                mensal = bal.groupby([bal.index.year, bal.index.month])["irrig_bruta"].sum().unstack().round(0)
                mensal.columns = ["Jan", "Fev", "Mar", "Abr", "Mai", "Jun", "Jul", "Ago", "Set", "Out", "Nov", "Dez"][:len(mensal.columns)]
                st.markdown("**Irrigação bruta mensal (mm)**")
                st.dataframe(mensal, width="stretch")

    with t3:
        modo = st.radio("Dados", ["Tanque Classe A", "Estação meteorológica (arquivo)"], horizontal=True, key="tmp_modo_loc")
        if modo == "Tanque Classe A":
            c = st.columns(3)
            bord = c[0].number_input("Bordadura de grama (m)", 1.0, 1000.0, float(m.get("kp_bordadura", 10.0)), key="tmp_bord")
            u = c[1].number_input("Vento a 2 m (km/d)", 0.0, 900.0, 170.0, 10.0, key="tmp_ukm")
            ur = c[2].number_input("UR média (%)", 10.0, 100.0, 65.0, 1.0, key="tmp_urkp")
            kp = kp_snyder(bord, u, ur)
            st.caption(f"Kp (Snyder, 1992) = {kp:.3f} → ETo = Kp × ECA")
            hoje = date.today()
            base = pd.DataFrame({"Data": [hoje - timedelta(days=i) for i in range(6, -1, -1)], "ECA (mm)": [6.5] * 7,
                                 "Chuva (mm)": [0.0] * 7})
            ed = st.data_editor(base, num_rows="dynamic", width="stretch", key="tmp_tanque")
            d = pd.DataFrame({"eto": ed["ECA (mm)"].astype(float).values * kp,
                              "chuva": ed["Chuva (mm)"].astype(float).values}, index=pd.to_datetime(ed["Data"]))
        else:
            arq = st.file_uploader("Arquivo INMET ou planilha diária", type=["csv", "txt"], key="tmp_arq_manejo")
            d = None
            if arq is not None:
                try:
                    try:
                        bruto, _ = fontes.ler_inmet(arq.getvalue())
                    except ValueError:
                        bruto = fontes.ler_csv_generico(arq.getvalue())
                    d = pd.DataFrame(index=bruto.index)
                    d["eto"] = _eto_de_df(bruto, lat, z) if "eca" not in bruto else bruto["eca"] * 0.75
                    d["chuva"] = bruto.get("chuva", 0.0)
                    d = d.dropna(subset=["eto"]).tail(60)
                except Exception as exc:  # noqa: BLE001
                    st.error(str(exc))
        if d is not None and len(d):
            d = d.sort_index()
            bal = simular_manejo(estado.pipe(), d)
            st.metric("Saldo atual (déficit a repor)", f"{fmt_br(max(bal['saldo'].iloc[-1], 0), 1)} mm",
                      f"tempo por setor: {horas_para_hhmm(max(bal['saldo'].iloc[-1], 0) / asp['ea'] / asp['ia'])}",
                      delta_color="off", delta_arrow="off")
            vis = bal.copy()
            vis.index = vis.index.strftime("%d/%m/%Y")
            st.dataframe(vis.round(2), width="stretch")
