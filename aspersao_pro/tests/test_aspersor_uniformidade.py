import numpy as np
import pytest

from aspersao import aspersores as am
from aspersao import uniformidade as uni


def test_catalogo_e_ajuste_vazao_pressao():
    cat = am.catalogo_referencia()
    assert len(cat) > 20
    for a in cat:
        k, x = a.coef_k_x()
        assert x == pytest.approx(0.5, abs=0.01)  # bocal de orifício
        assert a.vazao(a.p_nominal) > 0


def test_aspersor_estudo_de_caso():
    a = am.aspersor_estudo_caso_openirri()
    assert float(a.vazao(276)) == pytest.approx(0.520, abs=0.002)
    assert a.diametro(276) == pytest.approx(28.0, abs=0.3)


@pytest.mark.parametrize("perfil", ["eliptico", "triangular", "trapezoidal", "rosca", "concentrado"])
def test_balanco_de_massa_da_superposicao(perfil):
    r = uni.simular_malha(1.4, 26.0, 12, 18, "retangular", perfil, 2.5, 30, 24)
    assert abs(r["erro_balanco_pct"]) < 1.0  # média simulada = q / (Sa·Sl)
    assert 0 < r["CUC"] <= 100


def test_triangular_balanco():
    r = uni.simular_malha(1.4, 26.0, 12, 18, "triangular", "eliptico", 0.0, 0, 24)
    assert abs(r["erro_balanco_pct"]) < 1.0


def test_coeficientes_uniforme():
    c = uni.coeficientes(np.full(100, 5.0))
    assert c["CUC"] == pytest.approx(100) and c["CUD"] == pytest.approx(100)


def test_espacamento_maior_reduz_cuc():
    a = uni.simular_malha(1.4, 26.0, 12, 12, "retangular", "eliptico")["CUC"]
    b = uni.simular_malha(1.4, 26.0, 18, 24, "retangular", "eliptico")["CUC"]
    assert a > b


def test_eficiencia_distribuicao_keller():
    assert uni.eficiencia_distribuicao(80, 50) == pytest.approx(100, abs=0.5)
    assert uni.eficiencia_distribuicao(80, 75) == pytest.approx(83.4, abs=0.5)
    assert uni.eficiencia_distribuicao(90, 75) > uni.eficiencia_distribuicao(80, 75)


def test_perdas_trimmer_faixa():
    p = uni.perdas_evaporacao_deriva(4.0, 1.5, 300, 2.0)
    assert 5 < p < 20
    assert uni.perdas_evaporacao_deriva(4.0, 3.0, 400, 5.0) > p


def test_otimizador_retorna_alternativas_viaveis():
    cat = [x for x in am.catalogo_referencia() if x.tipo.startswith("Impacto médio")][:3]
    df = uni.otimizar_espacamentos(cat, 25.0, 20, 15.0, 2.0, cuc_min=75)
    assert not df.empty
    assert (df["Ia (mm/h)"] <= 15.0).all() and (df["CUC (%)"] >= 75).all()
