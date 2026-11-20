import pytest

from aspersao import bomba as b


def test_potencias():
    p = b.potencias(180, 50, 0.75)
    assert p["P_hidraulica_kW"] == pytest.approx(24.525, rel=1e-3)
    assert p["P_eixo_kW"] == pytest.approx(32.7, rel=1e-3)
    assert p["motor"]["motor_cv"] >= p["P_eixo_cv"] * 1.1


def test_motor_folgas():
    assert b.motor_comercial(1.5)["motor_cv"] == 3  # 1,5 × 1,5 = 2,25 → 3 cv
    assert b.motor_comercial(8.0)["motor_cv"] == 10  # 8 × 1,2 = 9,6 → 10 cv


def test_npsh_disponivel():
    r = b.npsh_disponivel(0.0, 20.0, 3.0, 0.5)
    assert r["Patm_mca"] == pytest.approx(10.33, abs=0.05)
    assert r["NPSHd"] == pytest.approx(10.33 - 0.24 - 3.5, abs=0.1)


def test_curva_sintetica_passa_pelo_ponto():
    c = b.curva_sintetica(150, 45)
    assert float(c.h(150)) == pytest.approx(45)
    hs = b.curva_sistema(20, 25, 150)
    q, h = b.ponto_operacao(c, hs)
    assert q == pytest.approx(150, rel=1e-3) and h == pytest.approx(45, rel=1e-3)


def test_afinidade():
    c = b.curva_sintetica(150, 45)
    c2 = c.afinidade(0.9)
    assert float(c2.h(0)) == pytest.approx(float(c.h(0)) * 0.81)
    r = b.ajuste_rotacao(c, 140, 38)
    assert 0.8 < r < 1.0


def test_custo_energia_com_desconto():
    cheio = b.custo_energia(30, 1000, 0.8)
    desc = b.custo_energia(30, 1000, 0.8, 60, 8.5, 8.0)
    assert desc["custo_total"] == pytest.approx(cheio["custo_total"] * 0.4)
