"""Orçamento (lista de materiais) e análise econômica do sistema.

Preços unitários de REFERÊNCIA em R$ — devem ser atualizados com cotações locais.
"""

from __future__ import annotations

import math
from collections import defaultdict

import pandas as pd

PRECOS_PADRAO = {
    "aspersor": 95.0,  # R$/unidade
    "haste_conjunto": 38.0,  # tubo de subida + tê/colar + estabilizador
    "valvula_setor_por_dn_mm": 9.5,  # R$ por mm de DN (registro/válvula hidráulica)
    "regulador_pressao": 160.0,
    "hidrante": 120.0,  # válvula de engate / hidrante (semifixo)
    "ventosa": 450.0,
    "registro_descarga": 280.0,
    "conexoes_pct": 15.0,  # % sobre tubos
    "motobomba_r_por_cv": 1150.0,
    "motobomba_fixo": 4500.0,
    "quadro_comando_r_por_cv": 420.0,
    "quadro_comando_fixo": 3500.0,
    "cabecal_controle": 6500.0,  # filtro de tela, manômetros, hidrômetro, válvulas
    "casa_bomba": 9000.0,
    "escavacao_m": 9.0,  # R$/m de vala (principal/derivações enterradas)
    "mao_obra_pct": 12.0,
    "frete_pct": 3.0,
    "projeto_pct": 4.0,
    "perdas_tubos_pct": 5.0,
}

VIDA_UTIL = {"Tubulações": 20, "Aspersores e hastes": 8, "Válvulas e acessórios": 12, "Motobomba e comando": 12,
             "Obras e serviços": 25}


def orcamento(lay, res_rede, asp_rotulo: str, tipo_sistema: str, motor_cv: float, precos: dict | None = None,
              tubos_laterais_fisicos=None) -> pd.DataFrame:
    """Lista de materiais com quantidades e custos."""
    p = dict(PRECOS_PADRAO)
    p.update(precos or {})
    itens = []

    def add(cat, item, un, qtd, preco, grupo):
        itens.append({"Categoria": cat, "Item": item, "Unidade": un, "Quantidade": round(qtd, 2),
                      "Preço unitário (R$)": round(preco, 2), "Total (R$)": round(qtd * preco, 2),
                      "Grupo": grupo})

    perdas = 1 + p["perdas_tubos_pct"] / 100.0
    # Laterais
    comp_lat = defaultdict(float)
    tubos_lat = {}
    if tipo_sistema == "fixo":
        for l in lay.laterais:
            t = res_rede.laterais[l.id]["tubo"]
            comp_lat[t.rotulo] += l.comprimento
            tubos_lat[t.rotulo] = t
        n_asp = lay.n_aspersores
    else:
        # laterais móveis: quantidade = maior setor
        maior = max(lay.setores, key=lambda ids: sum(lay.laterais[i].n for i in ids))
        for i in maior:
            l = lay.laterais[i]
            t = res_rede.laterais[l.id]["tubo"]
            comp_lat[t.rotulo] += l.comprimento
            tubos_lat[t.rotulo] = t
        n_asp = sum(lay.laterais[i].n for i in maior)
    for rot, comp in comp_lat.items():
        t = tubos_lat[rot]
        add("Tubulações", f"Linha lateral — {rot}", "m", comp * perdas, t.preco_m, "Tubulações")
    # Rede
    comp_rede = defaultdict(float)
    tubos_rede = {}
    for tr in res_rede.trechos:
        rot = f"{ {'adutora': 'Adutora', 'principal': 'Linha principal', 'derivacao': 'Derivação'}[tr.tipo]} — {tr.tubo.rotulo}"
        comp_rede[rot] += tr.comprimento
        tubos_rede[rot] = tr.tubo
    total_tubos = 0.0
    for rot, comp in comp_rede.items():
        add("Tubulações", rot, "m", comp * perdas, tubos_rede[rot].preco_m, "Tubulações")
    total_tubos = sum(i["Total (R$)"] for i in itens if i["Categoria"] == "Tubulações")
    add("Tubulações", "Conexões, curvas, tês e reduções (estimativa)", "vb", 1, total_tubos * p["conexoes_pct"] / 100,
        "Tubulações")
    # Aspersores
    add("Aspersores", asp_rotulo, "un", n_asp, p["aspersor"], "Aspersores e hastes")
    add("Aspersores", "Conjunto de haste (tubo de subida, tê/colar, estabilizador)", "un", n_asp,
        p["haste_conjunto"], "Aspersores e hastes")
    # Válvulas
    n_set = len(lay.setores)
    dn_der = max((tr.tubo.di_mm for tr in res_rede.trechos if tr.tipo == "derivacao"), default=75.0)
    if tipo_sistema == "fixo":
        add("Válvulas e acessórios", f"Válvula de setor (≈DN {dn_der:.0f})", "un", n_set,
            p["valvula_setor_por_dn_mm"] * dn_der, "Válvulas e acessórios")
    else:
        n_hid = len({l.no_entrada + l.lado for l in lay.laterais})
        add("Válvulas e acessórios", "Hidrante / válvula de engate nas posições das laterais", "un", n_hid,
            p["hidrante"], "Válvulas e acessórios")
    regs = {n for s in res_rede.setores if s for n in s["reguladores"]}
    if regs:
        n_reg = sum(1 for l in lay.laterais if l.no_entrada in regs)
        if tipo_sistema != "fixo":
            n_reg = len({l.no_entrada + l.lado for l in lay.laterais if l.no_entrada in regs})
        add("Válvulas e acessórios", "Regulador de pressão (entrada de lateral)", "un", n_reg,
            p["regulador_pressao"], "Válvulas e acessórios")
    n_vent = getattr(res_rede, "n_ventosas", 0) or max(1, len(lay.derivacoes))
    add("Válvulas e acessórios", "Ventosa de duplo efeito", "un", n_vent, p["ventosa"], "Válvulas e acessórios")
    add("Válvulas e acessórios", "Registro de descarga (pontos baixos/finais de linha)", "un",
        max(len(lay.derivacoes), getattr(res_rede, "n_descargas", 0)), p["registro_descarga"], "Válvulas e acessórios")
    # Bombeamento
    add("Bombeamento", f"Conjunto motobomba centrífuga ({motor_cv:g} cv)", "un", 1,
        p["motobomba_fixo"] + p["motobomba_r_por_cv"] * motor_cv, "Motobomba e comando")
    add("Bombeamento", "Quadro de comando / partida (soft-starter ou inversor)", "un", 1,
        p["quadro_comando_fixo"] + p["quadro_comando_r_por_cv"] * motor_cv, "Motobomba e comando")
    add("Bombeamento", "Cabeçal de controle (filtro de tela, manômetros, hidrômetro)", "vb", 1, p["cabecal_controle"],
        "Motobomba e comando")
    add("Bombeamento", "Casa de bomba e base", "vb", 1, p["casa_bomba"], "Obras e serviços")
    # Obras
    vala = sum(tr.comprimento for tr in res_rede.trechos)
    add("Serviços", "Abertura e fechamento de valas (adutora, principal, derivações)", "m", vala, p["escavacao_m"],
        "Obras e serviços")
    sub = sum(i["Total (R$)"] for i in itens)
    add("Serviços", "Mão de obra de montagem", "vb", 1, sub * p["mao_obra_pct"] / 100, "Obras e serviços")
    add("Serviços", "Frete", "vb", 1, sub * p["frete_pct"] / 100, "Obras e serviços")
    add("Serviços", "Projeto executivo e ART", "vb", 1, sub * p["projeto_pct"] / 100, "Obras e serviços")
    return pd.DataFrame(itens)


def frc(i, n):
    """Fator de recuperação de capital."""
    return i * (1 + i) ** n / ((1 + i) ** n - 1) if i > 0 else 1.0 / n


def analise_economica(df_orc: pd.DataFrame, area_ha: float, custo_energia_ano: float, volume_m3_ano: float,
                      juros_aa: float = 0.08, manutencao_pct: float = 2.0, mao_obra_ano: float = 0.0,
                      tarifa_agua_m3: float = 0.0, lamina_mm_ano: float | None = None) -> dict:
    invest = float(df_orc["Total (R$)"].sum())
    por_grupo = df_orc.groupby("Grupo")["Total (R$)"].sum()
    anual_capital = sum(v * frc(juros_aa, VIDA_UTIL.get(g, 15)) for g, v in por_grupo.items())
    manut = invest * manutencao_pct / 100
    agua = volume_m3_ano * tarifa_agua_m3
    total_anual = anual_capital + manut + custo_energia_ano + mao_obra_ano + agua
    out = {
        "investimento": invest, "investimento_ha": invest / area_ha if area_ha else math.nan,
        "custo_capital_anual": anual_capital, "manutencao_anual": manut, "energia_anual": custo_energia_ano,
        "mao_obra_anual": mao_obra_ano, "agua_anual": agua, "custo_anual_total": total_anual,
        "custo_anual_ha": total_anual / area_ha if area_ha else math.nan,
        "custo_m3": total_anual / volume_m3_ano if volume_m3_ano else math.nan,
        "por_grupo": por_grupo.to_dict(),
    }
    if lamina_mm_ano:
        out["custo_mm_ha"] = total_anual / (lamina_mm_ano * area_ha) if area_ha else math.nan
    return out
