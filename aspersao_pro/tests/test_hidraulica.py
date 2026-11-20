import numpy as np
import pytest

from aspersao import hidraulica as hid
from aspersao.tubos import catalogo_tubos, tubos_por_material


def test_hazen_williams_valor_conhecido():
    # Q = 50 L/s, D = 200 mm, L = 1000 m, C = 150 → hf ≈ 9,8 m
    assert float(hid.hf_hazen_williams(0.05, 0.2, 1000, 150)) == pytest.approx(9.81, abs=0.05)


def test_darcy_proximo_de_hazen_para_pvc():
    hw = float(hid.hf_hazen_williams(0.05, 0.2, 1000, 150))
    dw = float(hid.hf_darcy_weisbach(0.05, 0.2, 1000, 0.0015))
    assert dw == pytest.approx(hw, rel=0.10)


def test_fator_f():
    assert hid.fator_f(1) == 1.0
    assert hid.fator_f(10) == pytest.approx(hid.fator_f_aproximado(10), abs=1e-4)
    assert hid.fator_f(10, a=0.5) < hid.fator_f(10)
    assert hid.fator_f(200) == pytest.approx(1 / 2.852, abs=0.01)


def test_passo_a_passo_concorda_com_christiansen():
    t = tubos_por_material("Alumínio (engate rápido)")[0]
    k = 0.52 / 276 ** 0.5
    r = hid.lateral_passo_a_passo(15, 12.6, k, 0.5, t, h_servico=276 / 9.80665, a=0.5, ha=1.0)
    c = hid.lateral_christiansen(15, 12.6, 0.52, t, 276 / 9.80665, 0.0, 1.0, 0.5)
    assert r.h_entrada == pytest.approx(c["h_entrada"], rel=0.01)
    assert np.mean(r.h_bocal) == pytest.approx(276 / 9.80665, abs=1e-3)
    assert r.q_entrada_m3h == pytest.approx(15 * 0.52, rel=0.01)


def test_declive_reduz_pressao_requerida():
    t = tubos_por_material("PEAD")[3]
    k = 0.52 / 276 ** 0.5
    plano = hid.lateral_passo_a_passo(20, 12, k, 0.5, t, h_servico=28.0)
    dist = np.concatenate([[0.0], 6 + 12 * np.arange(20)])
    declive = hid.lateral_passo_a_passo(20, 12, k, 0.5, t, cotas=-0.02 * dist, h_servico=28.0)
    aclive = hid.lateral_passo_a_passo(20, 12, k, 0.5, t, cotas=0.02 * dist, h_servico=28.0)
    assert declive.h_entrada < plano.h_entrada < aclive.h_entrada


def test_dimensionar_lateral_respeita_20pct():
    cands = tubos_por_material("PEAD")
    k = 1.4 / 300 ** 0.5
    t, r, ok = hid.dimensionar_lateral(20, 12, k, 0.5, cands, 300 / 9.80665)
    assert ok and r.var_pressao_pct <= 20.0


def test_telescopica_mais_barata_que_uniforme():
    cands = tubos_por_material("Alumínio (engate rápido)")[:3]
    k = 0.52 / 276 ** 0.5
    tel = hid.lateral_telescopica(25, 12.6, k, 0.5, cands, 28.14)
    t_u, r_u, ok = hid.dimensionar_lateral(25, 12.6, k, 0.5, cands, 28.14)
    assert tel is not None
    assert tel["custo"] <= r_u.distancias[-1] * t_u.preco_m


def test_golpe_de_ariete():
    pvc = tubos_por_material("PVC")[3]
    g = hid.golpe_ariete(pvc, 500, 1.5, 1.0)
    assert 200 < g["celeridade"] < 600
    assert g["regime"].startswith("Manobra rápida")
    lento = hid.golpe_ariete(pvc, 500, 1.5, 60.0)
    assert lento["sobrepressao"] < g["sobrepressao"]


def test_catalogo_tubos_consistente():
    for t in catalogo_tubos():
        assert 0 < t.di_mm < t.de_mm
        assert t.preco_m > 0
