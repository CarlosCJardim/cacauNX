"""Operação: turnos, setores, vazão do sistema e cronograma."""

from __future__ import annotations

import streamlit as st

from aspersao.operacao import TIPOS_SISTEMA
from aspersao.unidades import horas_para_hhmm

from .. import estado, graficos
from ..estado import P, fmt_br, num, sel


def pagina():
    estado.cabecalho("Operação e setorização",
                     "Restrição de fechamento: nº de setores ≤ posições por dia × dias úteis do turno de rega.", "⏱️")
    o = P()["operacao"]
    c = st.columns(4)
    sel("Tipo de sistema", "operacao", "tipo_sistema", TIPOS_SISTEMA, alvo=c[0])
    num("Jornada diária de irrigação (h)", "operacao", "jornada_h", 1.0, 24.0, 0.5, alvo=c[1],
        ajuda="Horas disponíveis por dia. Com tarifa noturna, 8h30 com desconto + horas fora de ponta.")
    num("Dias de folga por turno de rega", "operacao", "folga_d", 0, 5, 1, alvo=c[2], inteiro=True)
    num("Tempo de mudança/manobra (h)", "operacao", "t_mudanca_h", 0.0, 3.0, 0.05, alvo=c[3],
        ajuda="Tempo para mudar laterais (portátil/semifixo) ou trocar setores manualmente.")
    c = st.columns(4)
    num("Vazão disponível na fonte (m³/h)", "operacao", "q_fonte_m3h", 0.0, 10000.0, 5.0, alvo=c[0],
        ajuda="Outorga ou vazão de teste do poço/captação. 0 = sem limite.")
    num("Número de setores (0 = automático)", "operacao", "n_setores", 0, 500, 1, alvo=c[1], inteiro=True)
    num("Hora de início da irrigação", "operacao", "hora_inicio", 0.0, 23.5, 0.5, alvo=c[2],
        ajuda="21,5 = 21h30, início típico do período com desconto tarifário para irrigantes.")

    op = estado.etapa("operacao")
    if op is None:
        return
    k = st.columns(6)
    k[0].metric("Tempo de aplicação", horas_para_hhmm(op["Ti"]))
    k[1].metric("Posições por dia", op["posicoes_dia"])
    k[2].metric("Setores", f"{op['n_setores']} / máx. {op['n_setores_max']}")
    k[3].metric("Vazão do sistema", f"{fmt_br(op['Q_sistema'], 1)} m³/h")
    k[4].metric("Operação diária", horas_para_hhmm(op["horas_operacao_dia"]))
    k[5].metric("Capacidade de reposição", f"{fmt_br(op['capacidade_mm_dia'])} mm/d" if op["capacidade_mm_dia"] else "—")
    if op["viavel"] and op["fonte_ok"]:
        st.success(f"✅ Sistema viável: {op['n_setores']} setores irrigados em {op['dias_uteis']} dia(s) úteis, "
                   f"vazão específica de {fmt_br(op['vazao_especifica_ls_ha'])} L/s/ha.")
    estado.avisos(op["avisos"])
    for rcm in op["recomendacoes"]:
        st.info(f"💡 {rcm}")
    g1, g2 = st.columns([1, 1.2])
    with g1:
        st.markdown("**Setores**")
        st.dataframe(op["setores"], hide_index=True, width="stretch", height=380)
    with g2:
        st.plotly_chart(graficos.cronograma_gantt(op["cronograma"]), width="stretch")
    with st.expander("Cronograma detalhado"):
        st.dataframe(op["cronograma"], hide_index=True, width="stretch")
