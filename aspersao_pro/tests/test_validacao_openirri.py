"""Reprodução do estudo de caso de El-Naggar (2026), SoftwareX 35:102912, Tabela 1,
com o manejo pelo clima (lâmina = ETc × TR)."""
import pytest

from aspersao.pipeline import Pipeline
from aspersao.projeto import exemplo_openirri_trigo


@pytest.fixture(scope="module")
def pipe():
    return Pipeline(exemplo_openirri_trigo())


def test_etc_de_pico(pipe):
    agr = pipe.get("agronomico")
    assert agr["etc_proj"] == pytest.approx(11.65, abs=0.01)  # artigo: 11,65 mm/d


def test_laminas_e_intensidade(pipe):
    agr = pipe.get("agronomico")
    asp = pipe.get("aspersor")
    assert asp["ia"] == pytest.approx(3.28, abs=0.01)  # artigo: 3,28 mm/h
    # pelo clima: LL = 11,65 × 2 = 23,3 mm (artigo, pelo solo: 24 mm); LB = LL/0,75
    assert agr["projeto"]["LL"] == pytest.approx(23.3, abs=0.05)
    assert agr["projeto"]["LB"] == pytest.approx(31.07, abs=0.05)
    assert agr["projeto"]["Ti"] == pytest.approx(9.48, abs=0.05)  # artigo: 9,77 h com LB = 32 mm


def test_layout_e_operacao(pipe):
    lay = pipe.get("layout")["layout"]
    op = pipe.get("operacao")
    assert lay.n_aspersores == 672  # artigo: 672 aspersores
    assert op["posicoes_dia"] == 1 and op["n_setores"] == 2
    assert op["Q_sistema"] <= 200.0  # vazão disponível do artigo
    assert op["Q_sistema"] == pytest.approx(174.7, abs=0.5)  # artigo: 182 m³/h (350 aspersores/turno)


def test_rede_e_bomba(pipe):
    rede = pipe.get("rede")
    assert max(v["res"].var_pressao_pct for v in rede.laterais.values()) <= 20.0  # critério do artigo
    bm = pipe.get("bomba")
    assert bm["npsh"]["NPSHd"] > bm["npshr"]
    assert 30 < bm["Hman"] < 70
