"""Cultura (Kc), balanço climático mensal e lâminas de projeto para manejo pelo clima."""

from __future__ import annotations

import numpy as np
import streamlit as st

from aspersao import cultura as cult
from aspersao.clima.estatistica import MESES, METODOS_PE
from aspersao.necessidade import VIB_TEXTURA
from aspersao.unidades import horas_para_hhmm

from .. import estado, graficos
from ..estado import P, chk, fmt_br, num, sel


def pagina():
    estado.cabecalho("Cultura e necessidade hídrica",
                     "Dimensionamento agronômico orientado ao manejo pelo clima: a lâmina repõe a ETc acumulada no "
                     "turno de rega; não se usa a capacidade de água do solo.", "🌱")
    cu = P()["cultura"]
    ag = P()["agronomico"]
    nomes = list(cult.CULTURAS.keys()) + ["Personalizada"]
    c1, c2, c3, c4 = st.columns([2, 1, 1, 1.2])
    nome = sel("Cultura", "cultura", "nome", nomes, alvo=c1)
    c = cult.obter_cultura(nome)
    if nome == "Personalizada":
        base = cu.get("personalizada") or c.to_dict()
        with st.expander("Parâmetros da cultura personalizada", expanded=True):
            k = st.columns(5)
            base["kc_ini"] = k[0].number_input("Kc ini", 0.1, 1.5, float(base["kc_ini"]), 0.01, key="tmp_kci")
            base["kc_mid"] = k[1].number_input("Kc mid", 0.1, 1.5, float(base["kc_mid"]), 0.01, key="tmp_kcm")
            base["kc_end"] = k[2].number_input("Kc final", 0.1, 1.5, float(base["kc_end"]), 0.01, key="tmp_kce")
            base["h"] = k[3].number_input("Altura (m)", 0.1, 10.0, float(base["h"]), 0.1, key="tmp_kch")
            base["perene"] = k[4].toggle("Perene", bool(base["perene"]), key="tmp_kcp")
            if not base["perene"]:
                k = st.columns(4)
                for i, (campo, rot) in enumerate((("l_ini", "Inicial (d)"), ("l_dev", "Desenvolvimento (d)"),
                                                  ("l_mid", "Intermediário (d)"), ("l_late", "Final (d)"))):
                    base[campo] = int(k[i].number_input(rot, 1, 400, int(base[campo] or 1), key=f"tmp_{campo}"))
            base["nome"] = "Personalizada"
            cu["personalizada"] = base
            c = cult.Cultura(**base)
    if not c.perene:
        num("Mês de plantio", "cultura", "mes_plantio", 1, 12, 1, alvo=c2, inteiro=True)
        num("Dia de plantio", "cultura", "dia_plantio", 1, 28, 1, alvo=c3, inteiro=True)
    else:
        c2.metric("Ciclo", "Perene")
    chk("Ajuste climático do Kc (FAO-56 Eq. 62)", "cultura", "ajuste_climatico", alvo=c4,
        ajuda="Corrige Kc_mid e Kc_end para o vento e a umidade mínima locais.")
    if c.nota:
        st.caption(f"ℹ️ {c.nota}")

    kc = estado.etapa("kc")
    if kc is None:
        return
    g1, g2 = st.columns([1.3, 1])
    with g1:
        if c.perene or c.ciclo == 0:
            st.plotly_chart(graficos.kc_curva(None, kc["kc_df"]["kc"].values, True, MESES), width="stretch")
        else:
            dias = np.arange(c.ciclo)
            st.plotly_chart(graficos.kc_curva(dias, cult.kc_dia_do_ciclo(c, dias, kc_mid=kc["kc_mid"], kc_end=kc["kc_end"])),
                            width="stretch")
    with g2:
        st.markdown("**Coeficientes**")
        t = {"Kc inicial": c.kc_ini, "Kc intermediário (tabela)": c.kc_mid, "Kc intermediário (ajustado)": kc["kc_mid"],
             "Kc final (tabela)": c.kc_end, "Kc final (ajustado)": kc["kc_end"]}
        st.dataframe({"Parâmetro": list(t), "Valor": [round(v, 3) for v in t.values()]}, hide_index=True, width="stretch")
        if kc["clima_ajuste"]:
            st.caption(f"Ajuste com u2 = {kc['clima_ajuste']['u2']:.2f} m/s e URmín = {kc['clima_ajuste']['urmin']:.0f}% "
                       f"(meses {', '.join(MESES[m - 1] for m in kc['clima_ajuste']['meses'][:6])}…).")
        if c.perene:
            with st.expander("Kc mensal próprio (opcional)"):
                st.caption("Informe 12 valores para usar um Kc calibrado localmente (ex.: cacau sombreado).")
                txtkc = st.text_input("Kc de Jan a Dez separados por ponto e vírgula",
                                      value="; ".join(f"{v:g}" for v in cu.get("kc_mensal") or []), key="tmp_kcmensal")
                try:
                    vals = [float(v.replace(",", ".")) for v in txtkc.split(";") if v.strip()]
                    cu["kc_mensal"] = vals if len(vals) == 12 else []
                except ValueError:
                    st.error("Valores inválidos.")

    st.divider()
    st.subheader("Parâmetros de projeto")
    a1, a2, a3, a4 = st.columns(4)
    sel("ETc de projeto", "agronomico", "metodo_etc",
        {"ciclo": "Maior ETc média mensal do ciclo", "conservador": "Kc máximo × ETo máxima (conservador)",
         "probabilistico": "Análise de frequência (série diária)"}, alvo=a1)
    if ag["metodo_etc"] == "probabilistico":
        num("Probabilidade de não excedência", "agronomico", "prob", 0.5, 0.95, 0.05, alvo=a1)
    num("Turno de rega (dias)", "agronomico", "turno_rega", 1, 15, 1, alvo=a2, inteiro=True,
        ajuda="No manejo pelo clima o turno de rega é uma decisão operacional. Turnos curtos reduzem a lâmina "
              "por evento e o risco de estresse; turnos longos reduzem o número de setores e a vazão.")
    num("Lâmina líquida máxima por evento (mm, 0 = sem limite)", "agronomico", "lamina_max", 0.0, 200.0, 1.0, alvo=a2)
    sel("Precipitação efetiva", "agronomico", "metodo_pe", METODOS_PE, alvo=a3)
    if ag["metodo_pe"] == "fixa":
        num("Fração aproveitada", "agronomico", "frac_pe", 0.1, 1.0, 0.05, alvo=a3)
    chk("Descontar chuva efetiva na ETc de projeto", "agronomico", "considerar_chuva", alvo=a3,
        ajuda="Normalmente desligado: o sistema deve atender o período crítico sem chuva.")
    sel("Eficiência de aplicação", "agronomico", "ea_modo",
        {"calculada": "Calculada (CUC + evaporação/deriva)", "informada": "Informada"}, alvo=a4)
    if ag["ea_modo"] == "informada":
        num("Ea informada", "agronomico", "ea_informada", 0.4, 0.98, 0.01, alvo=a4)
    else:
        num("Área adequadamente irrigada (%)", "agronomico", "adequacao", 50.0, 95.0, 5.0, alvo=a4,
            ajuda="Fração da área que recebe ao menos a lâmina requerida (Keller & Bliesner). 75–80% é usual.")
    b1, b2, b3 = st.columns(3)
    tex = b1.selectbox("Textura do solo (apenas para a intensidade máxima)", list(VIB_TEXTURA),
                       index=list(VIB_TEXTURA).index(ag["textura"]) if ag["textura"] in VIB_TEXTURA else 2,
                       key=estado.chave("agronomico", "textura"))
    if tex != ag["textura"]:
        ag["textura"] = tex
        estado.definir("agronomico", "vib", VIB_TEXTURA[tex])
    num("VIB — velocidade de infiltração básica (mm/h)", "agronomico", "vib", 1.0, 200.0, 0.5, alvo=b2,
        ajuda="A intensidade de aplicação do aspersor deve ser menor que a VIB para evitar escoamento.")
    num("Eficiência de condução", "agronomico", "ef_conducao", 0.8, 1.0, 0.01, alvo=b3)

    agr = estado.etapa("agronomico")
    if agr is None:
        return
    pr = agr["projeto"]
    asp = estado.etapa("aspersor", False)
    st.subheader("Lâminas de projeto")
    k = st.columns(6)
    k[0].metric("ETc de projeto", f"{fmt_br(agr['etc_proj'])} mm/d")
    k[1].metric("Lâmina líquida (LL)", f"{fmt_br(pr['LL'], 1)} mm")
    k[2].metric("Eficiência (Ea)", f"{fmt_br(pr['Ea'] * 100, 1)} %")
    k[3].metric("Lâmina bruta (LB)", f"{fmt_br(pr['LB'], 1)} mm")
    k[4].metric("Intensidade (Ia)", f"{fmt_br(asp['ia'])} mm/h" if asp else "—")
    k[5].metric("Tempo por posição (Ti)", horas_para_hhmm(pr["Ti"]))
    st.caption(f"Critério: {agr['descricao']}. LL = ETc × TR; LB = LL / Ea; Ti = LB / Ia.")
    estado.avisos(pr.get("avisos"))
    if agr.get("prob"):
        st.plotly_chart(graficos.frequencia_etc(agr["prob"]["maximos_anuais"].values, agr["prob"]["valor"],
                                                agr["prob"]["prob"]), width="stretch")
    g1, g2 = st.columns([1.2, 1])
    with g1:
        st.plotly_chart(graficos.balanco_mensal(agr["tabela"]), width="stretch")
    with g2:
        tab = agr["tabela"]
        st.dataframe(tab, hide_index=True, width="stretch", height=360)
        st.caption(f"Totais anuais — ETc: {fmt_br(tab['ETc (mm/mês)'].sum(), 0)} mm · Pe: "
                   f"{fmt_br(tab['Pe (mm/mês)'].sum(), 0)} mm · NIL: {fmt_br(tab['NIL (mm/mês)'].sum(), 0)} mm · "
                   f"NIB: {fmt_br(tab['NIB (mm/mês)'].sum(), 0)} mm · Volume: {fmt_br(tab['Volume (m³)'].sum(), 0)} m³ "
                   f"(área {fmt_br(agr['area_ha'])} ha).")
