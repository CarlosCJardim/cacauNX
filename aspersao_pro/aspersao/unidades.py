"""Constantes físicas e conversões de unidades usadas em todo o programa.

Convenção interna:
* pressão / carga em metros de coluna d'água (mca);
* vazão hidráulica em m³/s nas equações e m³/h na interface;
* diâmetros internos em milímetros nos catálogos e metros nas equações.
"""

G = 9.81  # aceleração da gravidade (m/s²)
RHO_AGUA = 1000.0  # massa específica da água (kg/m³)
KPA_POR_MCA = 9.80665  # 1 mca = 9,80665 kPa
MCA_POR_BAR = 10.1972
KW_POR_CV = 0.7355  # 1 cv = 735,5 W


def kpa_para_mca(p_kpa):
    return p_kpa / KPA_POR_MCA


def mca_para_kpa(h_mca):
    return h_mca * KPA_POR_MCA


def bar_para_mca(p_bar):
    return p_bar * MCA_POR_BAR


def mca_para_bar(h_mca):
    return h_mca / MCA_POR_BAR


def m3h_para_m3s(q_m3h):
    return q_m3h / 3600.0


def m3s_para_m3h(q_m3s):
    return q_m3s * 3600.0


def ls_para_m3h(q_ls):
    return q_ls * 3.6


def m3h_para_ls(q_m3h):
    return q_m3h / 3.6


def kw_para_cv(p_kw):
    return p_kw / KW_POR_CV


def cv_para_kw(p_cv):
    return p_cv * KW_POR_CV


def horas_para_hhmm(h: float) -> str:
    """Converte horas decimais em texto 'HhMMmin'."""
    if h is None or h != h:  # NaN
        return "—"
    total_min = int(round(h * 60))
    hh, mm = divmod(total_min, 60)
    return f"{hh}h{mm:02d}min"
