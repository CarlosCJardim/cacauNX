import numpy as np
import pytest

from aspersao import geo
from aspersao import layout as lay_mod
from aspersao import rede as rede_mod
from aspersao.altimetria import ElevacaoUniforme
from aspersao.pipeline import Pipeline
from aspersao.projeto import exemplo_cacau_bahia


def _layout_retangulo(decl=0.0, pos="central", nd=0):
    pol = geo.retangulo_lonlat(-15.0, -47.0, 360.0, 240.0, 0.0)
    proj = geo.Projecao.para_ponto(-47.0, -15.0)
    pu = geo.poligono_utm(pol, proj)
    c = pu.centroid
    elev = ElevacaoUniforme(500.0, c.x, c.y, decl, 0.0)
    fonte = (pu.bounds[0] - 30, pu.bounds[1] - 30)
    return lay_mod.gerar_layout(pu, proj, 12.0, 18.0, 0.0 + 90.0, fonte, "retangular", pos, 0.0, nd, elev)


def test_contagem_de_aspersores_retangulo():
    lay = _layout_retangulo()
    # 360 m / 12 m = 30 colunas; 240 m / 18 m = 13 linhas
    assert lay.n_aspersores == 30 * 13
    assert lay.area_irrigada_ha == pytest.approx(30 * 13 * 216 / 1e4)


def test_derivacoes_borda_e_central():
    assert len(_layout_retangulo(nd=2).derivacoes) == 2
    lay = _layout_retangulo(pos="borda", nd=1)
    assert all(l.lado == "D" for l in lay.laterais)


def test_setorizacao_equilibrada():
    lay = _layout_retangulo(nd=2)
    lay_mod.setorizar(lay, 6)
    n = [sum(lay.laterais[i].n for i in s) for s in lay.setores]
    assert len(n) == 6 and sum(n) == lay.n_aspersores
    assert max(n) - min(n) <= 2 * max(l.n for l in lay.laterais)
    # cada setor em uma única derivação
    for s in lay.setores:
        assert len({lay.laterais[i].derivacao for i in s}) == 1


def test_dimensionamento_rede_completo():
    p = Pipeline(exemplo_cacau_bahia())
    res = p.get("rede")
    lay = p.get("layout")["layout"]
    a = p.get("aspersor")
    assert res.p_fonte_max > a["h_servico"]
    # diâmetros não crescentes ao longo de cada derivação
    for d in lay.derivacoes:
        dis = [res.rede.trecho_por_id(f"D{d['id']}_{k}").tubo.di_mm for k in range(len(d["nos"]) - 1)]
        assert all(x >= y - 1e-9 for x, y in zip(dis, dis[1:]))
    # velocidades dentro dos limites
    for t in res.trechos:
        assert t.v_proj <= 2.0 + 1e-6
    # simulação do setor crítico próxima ao dimensionamento
    sim = rede_mod.simular_setor(lay, res, res.setor_critico, a["k"], a["x"], a["h_servico"], p.config_hidraulica())
    q_proj = res.setores[res.setor_critico]["Q_m3h"]
    assert sim["Q_total"] == pytest.approx(q_proj, rel=0.08)
    assert sim["p_min"] >= a["h_servico"] * 0.85


def test_orientacao_em_nivel_pelo_mde():
    p = Pipeline(exemplo_cacau_bahia())
    lo = p.get("layout")
    _, info = p.get("elev")
    assert lo["orientacao"].startswith("Laterais em nível")
    ang = lay_mod.azimute_para_angulo(lo["azimute"])
    # laterais perpendiculares à direção de máxima declividade
    dif = abs((ang - info["direcao_descida_graus"]) % 180 - 90)
    assert dif < 1.0
