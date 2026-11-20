"""Dimensionamento operacional: tempo de aplicação, turnos, setores, vazão do
sistema e cronograma de operação (restrição de fechamento N ≤ ns·I do OpenIrri)."""

from __future__ import annotations

import math

import pandas as pd

TIPOS_SISTEMA = {
    "fixo": "Convencional fixo (cobertura total / solid-set)",
    "semifixo": "Convencional semifixo (laterais portáteis, principal enterrada)",
    "portatil": "Convencional portátil (todas as linhas móveis)",
}


def dimensionar_operacao(lb_mm: float, ia_mmh: float, jornada_h: float, turno_rega_d: float, folga_d: int,
                         t_mudanca_h: float, n_aspersores: int, q_asp_m3h: float, q_fonte_m3h: float | None = None,
                         n_setores_forcado: int | None = None, area_ha: float | None = None,
                         ea: float = 0.8) -> dict:
    avisos, recomend = [], []
    ti = lb_mm / ia_mmh if ia_mmh > 0 else float("inf")
    ciclo = ti + t_mudanca_h
    if ti > jornada_h:
        avisos.append(f"Tempo de aplicação ({ti:.1f} h) maior que a jornada diária ({jornada_h:.1f} h).")
        recomend.append("Reduza o turno de rega, aumente a intensidade de aplicação (Ia) ou a jornada.")
    pos_dia = max(1, int(math.floor(jornada_h / ciclo + 1e-9))) if ciclo > 0 else 1
    dias_uteis = max(1, int(round(turno_rega_d - folga_d)))
    n_max = pos_dia * dias_uteis
    n_set = int(n_setores_forcado) if n_setores_forcado and n_setores_forcado > 0 else n_max
    n_set = max(1, min(n_set, max(n_aspersores, 1)))
    if n_set > n_max:
        avisos.append(f"{n_set} setores exigem mais turnos ({n_set}) do que os disponíveis ({n_max}) no turno de rega.")
    asp_setor = math.ceil(n_aspersores / n_set) if n_aspersores else 0
    q_sis = asp_setor * q_asp_m3h
    fonte_ok = True
    if q_fonte_m3h:
        fonte_ok = q_sis <= q_fonte_m3h + 1e-9
        if not fonte_ok:
            n_min = math.ceil(n_aspersores * q_asp_m3h / q_fonte_m3h)
            avisos.append(f"Vazão do sistema ({q_sis:.1f} m³/h) excede a disponibilidade da fonte "
                          f"({q_fonte_m3h:.1f} m³/h).")
            if n_min <= n_max:
                recomend.append(f"Use ao menos {n_min} setores (cabem {n_max} no turno de rega).")
            else:
                recomend.append(f"São necessários {n_min} setores, mas só cabem {n_max}: aumente a jornada, "
                                f"o turno de rega ou a vazão disponível, ou reduza a área.")
    horas_dia = min(pos_dia, math.ceil(n_set / dias_uteis)) * ciclo
    cap_mm_dia = None
    if area_ha:
        # lâmina líquida diária máxima que o sistema consegue repor usando todas as
        # posições disponíveis da jornada em todos os dias úteis do turno de rega
        vol_tr = q_sis * pos_dia * min(ti, jornada_h) * dias_uteis
        cap_mm_dia = vol_tr * ea / (area_ha * 10.0) / max(turno_rega_d, 1.0)
    return {
        "Ti": ti, "ciclo_h": ciclo, "posicoes_dia": pos_dia, "dias_uteis": dias_uteis, "n_setores_max": n_max,
        "n_setores": n_set, "aspersores_setor": asp_setor, "Q_sistema": q_sis, "fonte_ok": fonte_ok,
        "horas_operacao_dia": horas_dia, "capacidade_mm_dia": cap_mm_dia,
        "viavel": ti <= jornada_h and fonte_ok and n_set <= n_max, "avisos": avisos, "recomendacoes": recomend,
        "vazao_especifica_ls_ha": (q_sis / 3.6 / area_ha) if area_ha else None,
    }


def cronograma(n_setores: int, ti_h: float, t_mudanca_h: float, posicoes_dia: int, dias_uteis: int,
               hora_inicio: float = 21.5, vazoes_setor=None) -> pd.DataFrame:
    """Cronograma de operação dos setores ao longo do turno de rega.

    Por padrão inicia às 21h30 (aproveitando a tarifa noturna para irrigantes)."""
    linhas = []
    s = 0
    for dia in range(1, dias_uteis + 1):
        t = hora_inicio
        for _ in range(posicoes_dia):
            if s >= n_setores:
                break
            ini, fim = t, t + ti_h
            linhas.append({
                "Setor": s + 1, "Dia do turno": dia,
                "Início": _hhmm(ini), "Término": _hhmm(fim),
                "Duração": _dur(ti_h),
                "Vazão (m³/h)": round(vazoes_setor[s], 1) if vazoes_setor is not None and s < len(vazoes_setor) else None,
            })
            t = fim + t_mudanca_h
            s += 1
    return pd.DataFrame(linhas)


def _hhmm(h):
    dia_extra = int(h // 24)
    h = h % 24
    hh, mm = int(h), int(round((h - int(h)) * 60))
    if mm == 60:
        hh, mm = hh + 1, 0
    return f"{hh:02d}:{mm:02d}" + (f" (+{dia_extra}d)" if dia_extra else "")


def _dur(h):
    tot = int(round(h * 60))
    return f"{tot // 60}h{tot % 60:02d}"
