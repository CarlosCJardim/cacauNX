"""Orçamento (lista de materiais) e análise econômica."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from aspersao import custos as cst
from aspersao import tubos as tub

from .. import estado, graficos
from ..estado import P, fmt_br, num

ROTULOS_PRECOS = {
    "aspersor": "Aspersor (R$/un)", "haste_conjunto": "Conjunto de haste (R$/un)",
    "valvula_setor_por_dn_mm": "Válvula de setor (R$ por mm de DN)", "regulador_pressao": "Regulador de pressão (R$/un)",
    "hidrante": "Hidrante/válvula de engate (R$/un)", "ventosa": "Ventosa (R$/un)",
    "registro_descarga": "Registro de descarga (R$/un)", "conexoes_pct": "Conexões (% dos tubos)",
    "motobomba_r_por_cv": "Motobomba (R$/cv)", "motobomba_fixo": "Motobomba (parcela fixa, R$)",
    "quadro_comando_r_por_cv": "Quadro de comando (R$/cv)", "quadro_comando_fixo": "Quadro de comando (fixo, R$)",
    "cabecal_controle": "Cabeçal de controle (R$)", "casa_bomba": "Casa de bomba (R$)", "escavacao_m": "Valas (R$/m)",
    "mao_obra_pct": "Mão de obra (%)", "frete_pct": "Frete (%)", "projeto_pct": "Projeto e ART (%)",
    "perdas_tubos_pct": "Perdas/sobras de tubos (%)",
}


def pagina():
    estado.cabecalho("Orçamento", "Lista de materiais gerada a partir do layout e do dimensionamento. Preços de "
                     "referência editáveis — atualize com cotações locais.", "💰")
    cu = P()["custos"]
    with st.expander("💲 Preços unitários e parâmetros econômicos"):
        precos = dict(cst.PRECOS_PADRAO)
        precos.update(cu.get("precos") or {})
        df = pd.DataFrame({"Item": [ROTULOS_PRECOS.get(k, k) for k in precos], "chave": list(precos),
                           "Valor": list(precos.values())})
        ed = st.data_editor(df, hide_index=True, disabled=["Item"], column_config={"chave": None}, width="stretch",
                            key="tmp_precos")
        c = st.columns(4)
        num("Taxa de juros (% a.a.)", "custos", "juros_aa", 0.0, 30.0, 0.5, alvo=c[0])
        num("Manutenção anual (% do investimento)", "custos", "manutencao_pct", 0.0, 10.0, 0.25, alvo=c[1])
        num("Mão de obra de operação (R$/ano)", "custos", "mao_obra_ano", 0.0, 1e7, 500.0, alvo=c[2])
        num("Cobrança pelo uso da água (R$/m³)", "custos", "tarifa_agua", 0.0, 5.0, 0.001, fmt="%.3f", alvo=c[3])
        if st.button("Aplicar preços"):
            cu["precos"] = {r["chave"]: float(r["Valor"]) for _, r in ed.iterrows()}
            st.rerun()
        st.markdown("**Catálogo de tubos (preços e dimensões)**")
        cat_df = tub.catalogo_df(estado.pipe()._catalogo_tubos())
        ed_t = st.data_editor(cat_df, hide_index=True, width="stretch", height=300, key="tmp_cat_tubos")
        b1, b2 = st.columns(2)
        if b1.button("Aplicar catálogo de tubos"):
            P()["hidraulica"]["catalogo_tubos"] = [t.to_dict() for t in tub.catalogo_de_df(ed_t)]
            st.rerun()
        if b2.button("Restaurar catálogo padrão"):
            P()["hidraulica"]["catalogo_tubos"] = None
            st.rerun()

    r = estado.etapa("custos")
    if r is None:
        return
    eco = r["economia"]
    k = st.columns(5)
    k[0].metric("Investimento total", f"R$ {fmt_br(eco['investimento'], 0)}")
    k[1].metric("Investimento por hectare", f"R$ {fmt_br(eco['investimento_ha'], 0)}/ha")
    k[2].metric("Custo anual total", f"R$ {fmt_br(eco['custo_anual_total'], 0)}")
    k[3].metric("Custo anual por hectare", f"R$ {fmt_br(eco['custo_anual_ha'], 0)}/ha")
    k[4].metric("Custo da água aplicada", f"R$ {fmt_br(eco['custo_m3'], 3)}/m³")
    g1, g2 = st.columns([1, 1.3])
    with g1:
        st.plotly_chart(graficos.orcamento_grupos(eco["por_grupo"]), width="stretch")
        comp = pd.DataFrame({"Componente": ["Recuperação do capital", "Manutenção", "Energia", "Mão de obra", "Água"],
                             "R$/ano": [eco["custo_capital_anual"], eco["manutencao_anual"], eco["energia_anual"],
                                        eco["mao_obra_anual"], eco["agua_anual"]]}).round(0)
        st.dataframe(comp, hide_index=True, width="stretch")
    with g2:
        st.dataframe(r["orcamento"].drop(columns=["Grupo"]), hide_index=True, width="stretch", height=520,
                     column_config={"Total (R$)": st.column_config.NumberColumn(format="R$ %.2f"),
                                    "Preço unitário (R$)": st.column_config.NumberColumn(format="R$ %.2f")})
