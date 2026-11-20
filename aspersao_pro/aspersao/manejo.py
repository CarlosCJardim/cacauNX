"""Manejo da irrigação pelo CLIMA (sem balanço de água no solo).

A necessidade de irrigação é contabilizada como saldo climático acumulado:

    S_t = clip(S_{t−1} + ETc_t − Pe_t − I_liq,t ,  −Cmax, +∞)

onde Cmax é o crédito máximo de chuva (quanto da chuva excedente pode abater
irrigações futuras — tipicamente uma lâmina líquida de projeto). Estratégias:

* 'turno_fixo'  — irriga a cada TR dias repondo o saldo acumulado;
* 'lamina_fixa' — irriga quando o saldo atinge a lâmina líquida de projeto;
* 'diaria'      — repõe diariamente o saldo (sistemas com jornada folgada).

O módulo também gera o BOLETIM DE IRRIGAÇÃO com o tempo de funcionamento de
cada setor, ajustado pela previsão de chuva.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .clima.estatistica import precipitacao_efetiva_diaria

ESTRATEGIAS = {
    "turno_fixo": "Turno de rega fixo (repõe o acumulado ETc − Pe)",
    "lamina_fixa": "Lâmina fixa (irriga ao atingir a lâmina de projeto)",
    "diaria": "Reposição diária",
}


def balanco_climatico(df: pd.DataFrame, kc: pd.Series, ea: float, ia_mmh: float, estrategia: str = "turno_fixo",
                      turno_rega: int = 3, lamina_projeto: float = 20.0, limiar_pe: float = 5.0, frac_pe: float = 0.8,
                      credito_max: float | None = None, capacidade_liq_mm_dia: float | None = None,
                      adiar_chuva_mm: float = 0.0, saldo_inicial: float = 0.0) -> pd.DataFrame:
    """Simulação diária. ``df`` precisa das colunas 'eto' e 'chuva' (mm/d) e,
    opcionalmente, 'chuva_prevista_prox' (chuva prevista nos próximos dias, mm).

    Retorna DataFrame com ETc, Pe, saldo, irrigação líquida/bruta e tempo de aplicação (h).
    """
    d = df.copy()
    d["kc"] = kc.reindex(d.index).values
    d["etc"] = (d["eto"] * d["kc"]).fillna(0.0)
    d["pe"] = precipitacao_efetiva_diaria(d.get("chuva", pd.Series(0.0, index=d.index)).values, limiar_pe, frac_pe)
    cmax = lamina_projeto if credito_max is None else credito_max
    saldo = saldo_inicial
    dias_desde = 0
    reg = []
    for dt, linha in d.iterrows():
        ativo = not np.isnan(linha["kc"]) if "kc" in linha else True
        saldo = saldo + linha["etc"] - linha["pe"]
        saldo = max(saldo, -cmax)
        dias_desde += 1
        irrigar = False
        if ativo and saldo > 0.5:
            if estrategia == "diaria":
                irrigar = True
            elif estrategia == "lamina_fixa":
                irrigar = saldo >= lamina_projeto
            else:
                irrigar = dias_desde >= turno_rega
        motivo = ""
        if irrigar and adiar_chuva_mm > 0 and "chuva_prevista_prox" in d:
            prev = linha.get("chuva_prevista_prox", 0.0) or 0.0
            if prev * frac_pe >= min(saldo, adiar_chuva_mm):
                irrigar = False
                motivo = f"Adiada: previsão de {prev:.0f} mm"
        il = 0.0
        if irrigar:
            il = saldo
            if capacidade_liq_mm_dia:
                il = min(il, capacidade_liq_mm_dia * max(dias_desde, 1))
            saldo -= il
            dias_desde = 0
            motivo = "Irrigar"
        ib = il / ea if ea > 0 else il
        reg.append({"data": dt, "saldo": saldo, "irrig_liq": il, "irrig_bruta": ib,
                    "tempo_h": ib / ia_mmh if ia_mmh > 0 else np.nan, "acao": motivo})
    r = pd.DataFrame(reg).set_index("data")
    out = d[["eto", "kc", "etc", "pe"] + [c for c in ("chuva", "prob_chuva") if c in d]].join(r)
    # saldo além de uma lâmina de projeto indica capacidade insuficiente do sistema
    out["deficit_nao_atendido"] = (out["saldo"] - lamina_projeto).clip(lower=0.0)
    return out


def boletim_setores(lamina_bruta_mm: float, setores: pd.DataFrame, ia_mmh: float, ea: float,
                    hora_inicio: float = 21.5, t_mudanca_h: float = 0.0, jornada_h: float = 24.0):
    """Tabela de operação por setor para uma irrigação com lâmina bruta definida."""
    from .operacao import _hhmm

    ti = lamina_bruta_mm / ia_mmh if ia_mmh > 0 else 0.0
    linhas = []
    t = hora_inicio
    dia = 1
    for _, s in setores.iterrows():
        if t + ti > hora_inicio + jornada_h + 1e-6:
            dia += 1
            t = hora_inicio
        vol = s["Vazão (m³/h)"] * ti
        linhas.append({"Dia": dia, "Setor": int(s["Setor"]), "Início": _hhmm(t), "Término": _hhmm(t + ti),
                       "Tempo": f"{int(ti)}h{int(round((ti - int(ti)) * 60)):02d}",
                       "Lâmina bruta (mm)": round(lamina_bruta_mm, 1),
                       "Lâmina líquida (mm)": round(lamina_bruta_mm * ea, 1), "Volume (m³)": round(vol, 0)})
        t += ti + t_mudanca_h
    return pd.DataFrame(linhas)


def resumo_simulacao(bal: pd.DataFrame, area_ha: float, q_sis_m3h: float, p_kw: float) -> dict:
    """Indicadores anuais/médios da operação simulada."""
    anos = max(len(bal) / 365.25, 1e-9)
    vol = bal["irrig_bruta"].sum() * area_ha * 10.0
    horas = vol / q_sis_m3h if q_sis_m3h > 0 else 0.0
    eventos = int((bal["irrig_liq"] > 0).sum())
    return {
        "etc_total_mm_ano": bal["etc"].sum() / anos,
        "pe_total_mm_ano": bal["pe"].sum() / anos,
        "irrig_liq_mm_ano": bal["irrig_liq"].sum() / anos,
        "irrig_bruta_mm_ano": bal["irrig_bruta"].sum() / anos,
        "volume_m3_ano": vol / anos,
        "horas_bombeamento_ano": horas / anos,
        "energia_kwh_ano": horas * p_kw / anos,
        "eventos_ano": eventos / anos,
        "dias_com_deficit": int((bal["deficit_nao_atendido"] > 1.0).sum()),
        "atendimento_pct": 100.0 * (1 - bal["deficit_nao_atendido"].gt(1.0).mean()),
    }
