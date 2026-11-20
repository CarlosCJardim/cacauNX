"""Gráficos Plotly do AspersãoPro.

Regras visuais: paleta categórica validada em ordem fixa, rampas sequenciais de
um só matiz, divergente azul↔vermelho com cinza no centro, um único eixo y por
gráfico (medidas de unidades diferentes ficam em painéis empilhados), linhas de
2 px e grade discreta.
"""

from __future__ import annotations

import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots

CAT = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"]
SEQ = ["#cde2fb", "#b7d3f6", "#9ec5f4", "#86b6ef", "#6da7ec", "#5598e7", "#3987e5", "#2a78d6", "#256abf",
       "#1c5cab", "#184f95", "#104281", "#0d366b"]
SEQ_ESCALA = [[i / (len(SEQ) - 1), c] for i, c in enumerate(SEQ)]
DIV_ESCALA = [[0.0, "#104281"], [0.25, "#5598e7"], [0.5, "#f0efec"], [0.75, "#e66767"], [1.0, "#a31f1f"]]
TERRENO = "#8a7f6a"
CINZA = "#8c8b86"
STATUS = {"bom": "#0ca30c", "alerta": "#fab219", "serio": "#ec835a", "critico": "#d03b3b"}


def _base(fig, titulo=None, altura=380, legenda=True):
    fig.update_layout(
        title=dict(text=titulo, x=0.0, xanchor="left", font=dict(size=15)) if titulo else None,
        height=altura, margin=dict(l=10, r=10, t=50 if titulo else 20, b=10),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0) if legenda else None,
        showlegend=legenda, hovermode="closest", separators=",.",
    )
    fig.update_xaxes(showgrid=False, zeroline=False, ticks="outside", ticklen=4)
    fig.update_yaxes(gridcolor="rgba(140,139,134,0.18)", zeroline=False)
    return fig


def ordinal(n, i):
    """Cor ordinal (rampa azul a partir do passo 250) para o item i de n."""
    if n <= 1:
        return SEQ[7]
    passos = SEQ[3:]
    return passos[int(round(i / (n - 1) * (len(passos) - 1)))]


# ---------------------------------------------------------------------------
# Clima e necessidade
# ---------------------------------------------------------------------------
def clima_mensal(tab):
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.08,
                        subplot_titles=("ETo média (mm/d)", "Chuva (mm/mês)"))
    fig.add_bar(x=tab["Mês"], y=tab["ETo (mm/d)"], name="ETo", marker_color=CAT[0],
                marker=dict(cornerradius=4), hovertemplate="%{x}: %{y:.2f} mm/d<extra></extra>", row=1, col=1)
    fig.add_bar(x=tab["Mês"], y=tab["Chuva (mm)"], name="Chuva", marker_color=CAT[2],
                marker=dict(cornerradius=4), hovertemplate="%{x}: %{y:.0f} mm<extra></extra>", row=2, col=1)
    fig.update_layout(bargap=0.35)
    return _base(fig, None, 460, legenda=False)


def serie_diaria(d, col_eto="eto"):
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.07,
                        subplot_titles=("ETo diária (mm/d)", "Chuva diária (mm)"))
    fig.add_scatter(x=d.index, y=d[col_eto], mode="lines", line=dict(width=1, color=CAT[0]), name="ETo (Penman-Monteith)",
                    row=1, col=1)
    if "eto_fonte" in d and d["eto_fonte"].notna().any():
        fig.add_scatter(x=d.index, y=d["eto_fonte"], mode="lines", line=dict(width=1, color=CAT[1]),
                        name="ETo da fonte", opacity=0.8, row=1, col=1)
    if "chuva" in d:
        fig.add_bar(x=d.index, y=d["chuva"], marker_color=CAT[2], name="Chuva", row=2, col=1)
    return _base(fig, None, 460)


def kc_curva(dias, kc, perene=False, meses=None):
    fig = go.Figure()
    if perene:
        fig.add_bar(x=meses, y=kc, marker_color=CAT[5], marker=dict(cornerradius=4), name="Kc",
                    hovertemplate="%{x}: Kc %{y:.3f}<extra></extra>")
    else:
        fig.add_scatter(x=dias, y=kc, mode="lines", line=dict(width=2, color=CAT[5]), fill="tozeroy",
                        fillcolor="rgba(0,131,0,0.10)", name="Kc", hovertemplate="Dia %{x}: Kc %{y:.3f}<extra></extra>")
        fig.update_xaxes(title="Dias após a semeadura/plantio")
    fig.update_yaxes(title="Kc", rangemode="tozero")
    return _base(fig, "Curva do coeficiente de cultura (Kc)", 320, legenda=False)


def balanco_mensal(tab):
    fig = go.Figure()
    fig.add_bar(x=tab["Mês"], y=tab["ETc (mm/mês)"], name="ETc", marker_color=CAT[0], marker=dict(cornerradius=4))
    fig.add_bar(x=tab["Mês"], y=tab["Pe (mm/mês)"], name="Chuva efetiva", marker_color=CAT[2], marker=dict(cornerradius=4))
    fig.add_bar(x=tab["Mês"], y=tab["NIL (mm/mês)"], name="Necessidade de irrigação líquida", marker_color=CAT[1],
                marker=dict(cornerradius=4))
    fig.update_layout(barmode="group", bargap=0.25, bargroupgap=0.08)
    fig.update_yaxes(title="mm/mês")
    return _base(fig, "Balanço climático mensal", 360)


def frequencia_etc(maximos, valor, prob):
    s = np.sort(np.asarray(maximos, dtype=float))
    p = (np.arange(1, len(s) + 1)) / (len(s) + 1)
    fig = go.Figure()
    fig.add_scatter(x=p * 100, y=s, mode="markers+lines", marker=dict(size=8, color=CAT[0]),
                    line=dict(width=2, color=CAT[0]), name="Máximos anuais",
                    hovertemplate="P(não exc.) %{x:.0f}%: %{y:.2f} mm/d<extra></extra>")
    fig.add_hline(y=valor, line=dict(color=CAT[1], width=2, dash="dash"),
                  annotation_text=f"Projeto ({prob * 100:.0f}%): {valor:.2f} mm/d", annotation_position="top left")
    fig.update_xaxes(title="Probabilidade de não excedência (%)")
    fig.update_yaxes(title="ETc média no turno de rega (mm/d)")
    return _base(fig, "Análise de frequência da ETc de projeto", 340, legenda=False)


# ---------------------------------------------------------------------------
# Aspersor
# ---------------------------------------------------------------------------
def uniformidade(sim, esp_asp, esp_lat, arranjo):
    fig = go.Figure(go.Heatmap(x=sim["X"][0], y=sim["Y"][:, 0], z=sim["L"], colorscale=SEQ_ESCALA,
                               colorbar=dict(title="mm/h", thickness=12),
                               hovertemplate="x=%{x:.1f} m, y=%{y:.1f} m<br>%{z:.2f} mm/h<extra></extra>"))
    pts = [(0, 0), (esp_asp, 0), (0, esp_lat), (esp_asp, esp_lat)]
    if arranjo == "triangular":
        pts = [(0, 0), (esp_asp, 0), (esp_asp / 2, esp_lat)]
    fig.add_scatter(x=[p[0] for p in pts], y=[p[1] for p in pts], mode="markers",
                    marker=dict(size=11, color="#0b0b0b", symbol="circle", line=dict(color="#fcfcfb", width=2)),
                    name="Aspersores", hoverinfo="skip")
    fig.update_xaxes(title="Ao longo da lateral (m)", range=[-0.5, esp_asp + 0.5], constrain="domain")
    fig.update_yaxes(title="Entre laterais (m)", scaleanchor="x", range=[-0.5, esp_lat + 0.5], showgrid=False)
    return _base(fig, f"Lâmina aplicada na célula {esp_asp:g} × {esp_lat:g} m", 400, legenda=False)


def padrao_individual(pad):
    fig = go.Figure(go.Heatmap(x=pad["x"], y=pad["y"], z=np.where(pad["L"] > 0, pad["L"], np.nan),
                               colorscale=SEQ_ESCALA, colorbar=dict(title="mm/h", thickness=12),
                               hovertemplate="%{z:.2f} mm/h<extra></extra>"))
    fig.update_yaxes(scaleanchor="x", showgrid=False, title="m")
    fig.update_xaxes(title="m")
    return _base(fig, "Padrão de um aspersor isolado", 400, legenda=False)


def perfil_radial(rho, f, titulo):
    fig = go.Figure(go.Scatter(x=rho, y=f, mode="lines", line=dict(width=2, color=CAT[0]), fill="tozeroy",
                               fillcolor="rgba(42,120,214,0.10)"))
    fig.update_xaxes(title="Raio relativo r/R")
    fig.update_yaxes(title="Lâmina relativa", rangemode="tozero")
    return _base(fig, titulo, 260, legenda=False)


# ---------------------------------------------------------------------------
# Layout e rede (planta em UTM)
# ---------------------------------------------------------------------------
def _contorno_poligono(fig, pol, nome="Área"):
    x, y = pol.exterior.xy
    fig.add_scatter(x=list(x), y=list(y), mode="lines", line=dict(color="#d4a000", width=2), name=nome,
                    hoverinfo="skip")


def planta_setores(lay, mostrar_aspersores=True):
    fig = go.Figure()
    _contorno_poligono(fig, lay.poligono)
    n = max(len(lay.setores), 1)
    for s, ids in enumerate(lay.setores):
        cor = ordinal(n, s)
        xs, ys = [], []
        for i in ids:
            l = lay.laterais[i]
            pts = np.vstack([np.asarray(l.entrada_xy)[None, :], l.aspersores_xy])
            xs += list(pts[:, 0]) + [None]
            ys += list(pts[:, 1]) + [None]
        fig.add_scatter(x=xs, y=ys, mode="lines", line=dict(color=cor, width=2), name=f"Setor {s + 1}",
                        legendgroup=f"s{s}", hovertemplate=f"Setor {s + 1}<extra></extra>", showlegend=n <= 12)
        if ids:
            todos = np.vstack([lay.laterais[i].aspersores_xy for i in ids])
            c = todos.mean(axis=0)
            fig.add_annotation(x=c[0], y=c[1], text=f"<b>{s + 1}</b>", showarrow=False,
                               font=dict(size=13, color="#0b0b0b"), bgcolor="rgba(252,252,251,0.85)", borderpad=2)
    if mostrar_aspersores:
        a = lay.todos_aspersores()
        fig.add_scatter(x=a[:, 0], y=a[:, 1], mode="markers", marker=dict(size=3, color="#0b0b0b"),
                        name="Aspersores", hoverinfo="skip")
    _rede_basica(fig, lay)
    fig.update_yaxes(scaleanchor="x", showgrid=False, title="N (m)", tickformat=",.0f")
    fig.update_xaxes(title="E (m)", tickformat=",.0f")
    return _base(fig, f"Planta — {len(lay.setores)} setores (cor = ordem de operação)", 620)


def _rede_basica(fig, lay):
    for k, d in enumerate(lay.derivacoes):
        c = np.asarray(d["coords"])
        fig.add_scatter(x=c[:, 0], y=c[:, 1], mode="lines", line=dict(color=CAT[1], width=4), name="Derivação",
                        legendgroup="der", showlegend=k == 0, hoverinfo="skip")
    if len(lay.principal) > 1:
        c = np.asarray(lay.principal)
        fig.add_scatter(x=c[:, 0], y=c[:, 1], mode="lines", line=dict(color=CAT[7], width=5), name="Linha principal",
                        hoverinfo="skip")
    c = np.asarray(lay.adutora)
    fig.add_scatter(x=c[:, 0], y=c[:, 1], mode="lines", line=dict(color=CAT[6], width=5, dash="dot"), name="Adutora",
                    hoverinfo="skip")
    fig.add_scatter(x=[lay.fonte_xy[0]], y=[lay.fonte_xy[1]], mode="markers+text", text=["Captação"],
                    textposition="bottom center", marker=dict(size=14, color=CAT[0], symbol="square",
                                                              line=dict(color="#fcfcfb", width=2)),
                    name="Captação / bomba", hoverinfo="skip")


def planta_diametros(lay, res):
    fig = go.Figure()
    _contorno_poligono(fig, lay.poligono)
    for l in lay.laterais:
        pts = np.vstack([np.asarray(l.entrada_xy)[None, :], l.aspersores_xy])
        fig.add_scatter(x=pts[:, 0], y=pts[:, 1], mode="lines", line=dict(color="rgba(140,139,134,0.45)", width=1),
                        showlegend=False, hoverinfo="skip")
    dns = sorted({(t.tubo.di_mm, t.tubo.material, t.tubo.dn) for t in res.trechos})
    for i, (di, mat, dn) in enumerate(dns):
        trs = [t for t in res.trechos if t.tubo.di_mm == di and t.tubo.material == mat]
        xs, ys, txt = [], [], []
        for t in trs:
            c = np.asarray(t.coords)
            xs += list(c[:, 0]) + [None]
            ys += list(c[:, 1]) + [None]
            txt += [f"{t.id}: {t.tubo.rotulo}<br>Q={t.q_proj:.1f} m³/h · v={t.v_proj:.2f} m/s · hf={t.hf_proj:.2f} m"] * len(c) + [None]
        fig.add_scatter(x=xs, y=ys, mode="lines", line=dict(color=ordinal(len(dns), i), width=2 + 4 * i / max(len(dns) - 1, 1)),
                        name=f"{mat} DN {dn}", text=txt, hovertemplate="%{text}<extra></extra>")
    fig.add_scatter(x=[lay.fonte_xy[0]], y=[lay.fonte_xy[1]], mode="markers", marker=dict(size=14, color=CAT[0],
                    symbol="square"), name="Captação", hoverinfo="skip")
    fig.update_yaxes(scaleanchor="x", showgrid=False, title="N (m)", tickformat=",.0f")
    fig.update_xaxes(title="E (m)", tickformat=",.0f")
    return _base(fig, "Rede dimensionada — diâmetros", 600)


def pressoes_setor(sim, h_servico):
    xy = sim["xy"]
    desvio = 100 * (sim["pressoes"] - h_servico) / h_servico
    lim = max(abs(desvio).max(), 5)
    fig = go.Figure(go.Scatter(x=xy[:, 0], y=xy[:, 1], mode="markers",
                               marker=dict(size=8, color=desvio, colorscale=DIV_ESCALA, cmin=-lim, cmax=lim,
                                           colorbar=dict(title="Desvio da PS (%)", thickness=12),
                                           line=dict(color="#fcfcfb", width=1)),
                               text=[f"P = {p:.1f} mca · q = {q * 1000:.0f} L/h" for p, q in zip(sim["pressoes"], sim["vazoes"])],
                               hovertemplate="%{text}<extra></extra>"))
    fig.update_yaxes(scaleanchor="x", showgrid=False, title="N (m)", tickformat=",.0f")
    fig.update_xaxes(title="E (m)", tickformat=",.0f")
    return _base(fig, "Pressão nos aspersores do setor simulado", 480, legenda=False)


# ---------------------------------------------------------------------------
# Perfis hidráulicos
# ---------------------------------------------------------------------------
def perfil_lateral(r, h_servico, tol):
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.08, row_heights=[0.65, 0.35],
                        subplot_titles=("Pressão no bocal (mca)", "Cota do terreno (m)"))
    fig.add_scatter(x=r.distancias, y=r.h_bocal, mode="lines+markers", marker=dict(size=8, color=CAT[0]),
                    line=dict(width=2, color=CAT[0]), name="Pressão", row=1, col=1,
                    hovertemplate="%{x:.0f} m: %{y:.2f} mca<extra></extra>")
    fig.add_hline(y=h_servico, line=dict(color=CINZA, width=1, dash="dash"), row=1, col=1,
                  annotation_text="PS", annotation_position="right")
    fig.add_hrect(y0=h_servico * (1 - tol / 2), y1=h_servico * (1 + tol / 2), fillcolor="rgba(12,163,12,0.07)",
                  line_width=0, row=1, col=1)
    fig.add_scatter(x=np.concatenate([[0], r.distancias]), y=r.cotas, mode="lines", line=dict(width=2, color=TERRENO),
                    fill="tozeroy", fillcolor="rgba(138,127,106,0.12)", name="Terreno", row=2, col=1,
                    hovertemplate="%{x:.0f} m: %{y:.2f} m<extra></extra>")
    zmin, zmax = float(np.min(r.cotas)), float(np.max(r.cotas))
    fig.update_yaxes(range=[zmin - 1, zmax + 1], row=2, col=1)
    fig.update_xaxes(title="Distância da entrada (m)", row=2, col=1)
    return _base(fig, None, 460, legenda=False)


def perfil_adutora(perfil, h_piezo_ini, h_piezo_fim, cota_bomba):
    d, z = perfil["dist"], perfil["cotas"]
    fig = go.Figure()
    fig.add_scatter(x=d, y=z, mode="lines", line=dict(width=2, color=TERRENO), fill="tozeroy",
                    fillcolor="rgba(138,127,106,0.12)", name="Terreno", hovertemplate="%{x:.0f} m: %{y:.2f} m<extra></extra>")
    fig.add_scatter(x=[d[0], d[-1]], y=[h_piezo_ini, h_piezo_fim], mode="lines", line=dict(width=2, color=CAT[0]),
                    name="Linha piezométrica", hovertemplate="%{x:.0f} m: %{y:.2f} m<extra></extra>")
    for i in perfil["altos"]:
        fig.add_scatter(x=[d[i]], y=[z[i]], mode="markers+text", text=["Ventosa"], textposition="top center",
                        marker=dict(size=10, color=CAT[1], symbol="triangle-up"), showlegend=False)
    for i in perfil["baixos"]:
        fig.add_scatter(x=[d[i]], y=[z[i]], mode="markers+text", text=["Descarga"], textposition="bottom center",
                        marker=dict(size=10, color=CAT[6], symbol="triangle-down"), showlegend=False)
    zmin = float(np.min(z))
    fig.update_yaxes(range=[zmin - 2, max(h_piezo_ini, float(np.max(z))) + 3], title="Cota (m)")
    fig.update_xaxes(title="Distância desde a bomba (m)")
    return _base(fig, "Perfil da adutora e linha piezométrica (setor crítico)", 360)


# ---------------------------------------------------------------------------
# Bomba
# ---------------------------------------------------------------------------
def curvas_bomba(curva, h_sis, ponto, pontos_setores, q_proj, npshd):
    qmax = max(curva.q_max, q_proj * 1.4)
    q = np.linspace(0, qmax, 120)
    tem_npsh = curva.coef_npsh is not None
    linhas = 3 if tem_npsh else 2
    titulos = ("Altura manométrica (m)", "Rendimento da bomba (%)", "NPSH (m)")[:linhas]
    fig = make_subplots(rows=linhas, cols=1, shared_xaxes=True, vertical_spacing=0.07, subplot_titles=titulos,
                        row_heights=[0.5, 0.25, 0.25][:linhas])
    h = curva.h(q)
    m = h > 0
    fig.add_scatter(x=q[m], y=h[m], mode="lines", line=dict(width=2, color=CAT[0]), name="Curva da bomba", row=1, col=1)
    fig.add_scatter(x=q, y=h_sis(q), mode="lines", line=dict(width=2, color=CAT[1], dash="dash"),
                    name="Curva do sistema (setor crítico)", row=1, col=1)
    if pontos_setores:
        fig.add_scatter(x=[p["Q (m³/h)"] for p in pontos_setores], y=[p["Hman requerida (m)"] for p in pontos_setores],
                        mode="markers", marker=dict(size=9, color=CAT[2], line=dict(color="#fcfcfb", width=2)),
                        name="Requisito de cada setor", text=[f"Setor {p['Setor']}" for p in pontos_setores],
                        hovertemplate="%{text}: %{x:.1f} m³/h · %{y:.1f} m<extra></extra>", row=1, col=1)
    if ponto:
        fig.add_scatter(x=[ponto[0]], y=[ponto[1]], mode="markers+text", text=["Ponto de operação"],
                        textposition="top right", marker=dict(size=13, color="#0b0b0b", symbol="diamond",
                                                               line=dict(color="#fcfcfb", width=2)),
                        name="Ponto de operação", row=1, col=1)
    fig.add_scatter(x=q, y=100 * curva.eta(q), mode="lines", line=dict(width=2, color=CAT[5]), name="Rendimento",
                    row=2, col=1, showlegend=False)
    if tem_npsh:
        fig.add_scatter(x=q, y=curva.npshr(q), mode="lines", line=dict(width=2, color=CAT[7]), name="NPSH requerido",
                        row=3, col=1)
        fig.add_hline(y=npshd, line=dict(color=CAT[2], width=2, dash="dot"), row=3, col=1,
                      annotation_text=f"NPSH disponível {npshd:.1f} m", annotation_position="top left")
    fig.update_xaxes(title="Vazão (m³/h)", row=linhas, col=1)
    fig.update_yaxes(rangemode="tozero", row=1, col=1)
    return _base(fig, None, 620)


def cascata_hman(decomp: dict, total):
    nomes = list(decomp.keys()) + ["Altura manométrica total"]
    valores = [float(v) for v in decomp.values()] + [float(total)]
    fig = go.Figure(go.Waterfall(orientation="v", x=nomes, y=valores, measure=["relative"] * len(decomp) + ["total"],
                                 connector=dict(line=dict(color=CINZA, width=1)),
                                 increasing=dict(marker=dict(color=CAT[0])), decreasing=dict(marker=dict(color=CAT[2])),
                                 totals=dict(marker=dict(color=CAT[6])),
                                 texttemplate="%{y:.1f}", textposition="outside",
                                 hovertemplate="%{x}: %{y:.2f} m<extra></extra>"))
    fig.update_yaxes(title="m")
    return _base(fig, "Composição da altura manométrica (setor crítico)", 420, legenda=False)


# ---------------------------------------------------------------------------
# Terreno
# ---------------------------------------------------------------------------
def terreno_contorno(X, Y, Z, pol=None, equid=1.0, titulo="Modelo digital de elevação"):
    fig = go.Figure(go.Contour(x=X[0], y=Y[:, 0], z=Z, colorscale="Earth", reversescale=False,
                               contours=dict(start=float(np.floor(Z.min())), end=float(np.ceil(Z.max())), size=equid,
                                             showlabels=True, labelfont=dict(size=10, color="#0b0b0b")),
                               line=dict(width=0.6), colorbar=dict(title="m", thickness=12),
                               hovertemplate="E %{x:.0f} · N %{y:.0f}<br>%{z:.2f} m<extra></extra>"))
    if pol is not None:
        x, y = pol.exterior.xy
        fig.add_scatter(x=list(x), y=list(y), mode="lines", line=dict(color="#0b0b0b", width=2), name="Área",
                        hoverinfo="skip")
    fig.update_yaxes(scaleanchor="x", showgrid=False, title="N (m)", tickformat=",.0f")
    fig.update_xaxes(title="E (m)", tickformat=",.0f")
    return _base(fig, titulo, 520, legenda=False)


def terreno_3d(X, Y, Z, exagero=3.0):
    fig = go.Figure(go.Surface(x=X - X.min(), y=Y - Y.min(), z=Z, colorscale="Earth", showscale=False,
                               contours=dict(z=dict(show=True, usecolormap=False, color="rgba(0,0,0,0.25)", width=1))))
    amp = max(float(np.ptp(X)), float(np.ptp(Y)), 1.0)
    fig.update_layout(scene=dict(aspectmode="manual",
                                 aspectratio=dict(x=float(np.ptp(X)) / amp, y=float(np.ptp(Y)) / amp,
                                                  z=max(0.08, exagero * float(np.ptp(Z)) / amp)),
                                 xaxis_title="E (m)", yaxis_title="N (m)", zaxis_title="Cota (m)"))
    return _base(fig, f"Relevo 3D (exagero vertical {exagero:g}×)", 520, legenda=False)


def mapa_declividade(X, Y, S, pol=None):
    fig = go.Figure(go.Heatmap(x=X[0], y=Y[:, 0], z=S, colorscale=[[0, "#f0efec"], [0.5, "#ec835a"], [1, "#a31f1f"]],
                               zmin=0, zmax=max(float(np.nanpercentile(S, 98)), 1.0),
                               colorbar=dict(title="%", thickness=12),
                               hovertemplate="%{z:.1f} %<extra></extra>"))
    if pol is not None:
        x, y = pol.exterior.xy
        fig.add_scatter(x=list(x), y=list(y), mode="lines", line=dict(color="#0b0b0b", width=2), hoverinfo="skip")
    fig.update_yaxes(scaleanchor="x", showgrid=False, title="N (m)", tickformat=",.0f")
    fig.update_xaxes(title="E (m)", tickformat=",.0f")
    return _base(fig, "Declividade do terreno (%)", 460, legenda=False)


# ---------------------------------------------------------------------------
# Manejo e custos
# ---------------------------------------------------------------------------
def manejo(bal):
    fig = make_subplots(rows=3, cols=1, shared_xaxes=True, vertical_spacing=0.06, row_heights=[0.4, 0.3, 0.3],
                        subplot_titles=("ETc e chuva efetiva (mm/d)", "Saldo climático acumulado (mm)",
                                        "Irrigação bruta recomendada (mm)"))
    fig.add_scatter(x=bal.index, y=bal["etc"], mode="lines", line=dict(width=2, color=CAT[0]), name="ETc", row=1, col=1)
    fig.add_bar(x=bal.index, y=bal["pe"], marker_color=CAT[2], name="Chuva efetiva", row=1, col=1)
    fig.add_scatter(x=bal.index, y=bal["saldo"], mode="lines", line=dict(width=2, color=CAT[1]), name="Saldo",
                    fill="tozeroy", fillcolor="rgba(235,104,52,0.10)", row=2, col=1)
    fig.add_bar(x=bal.index, y=bal["irrig_bruta"], marker_color=CAT[6], name="Irrigação bruta", row=3, col=1)
    if "previsao" in bal:
        prev = bal.index[bal["previsao"].astype(bool)]
        if len(prev):
            fig.add_vrect(x0=prev.min(), x1=prev.max(), fillcolor="rgba(140,139,134,0.10)", line_width=0,
                          annotation_text="Previsão", annotation_position="top left")
    return _base(fig, None, 620)


def orcamento_grupos(por_grupo: dict):
    itens = sorted(por_grupo.items(), key=lambda kv: kv[1])
    fig = go.Figure(go.Bar(x=[v for _, v in itens], y=[k for k, _ in itens], orientation="h", marker_color=CAT[0],
                           marker=dict(cornerradius=4), text=[f"R$ {v:,.0f}".replace(",", ".") for _, v in itens],
                           textposition="outside", hovertemplate="%{y}: R$ %{x:,.0f}<extra></extra>"))
    fig.update_xaxes(title="R$", showgrid=True, gridcolor="rgba(140,139,134,0.18)")
    return _base(fig, "Investimento por grupo", 320, legenda=False)


def cronograma_gantt(df):
    fig = go.Figure()
    for _, r in df.iterrows():
        h0 = int(r["Início"][:2]) + int(r["Início"][3:5]) / 60
        dur = int(r["Duração"].split("h")[0]) + int(r["Duração"].split("h")[1]) / 60
        base = (r["Dia do turno"] - 1) * 24 + h0
        fig.add_bar(x=[dur], y=[f"Setor {r['Setor']}"], base=[base], orientation="h", marker_color=CAT[0],
                    marker=dict(cornerradius=4), showlegend=False,
                    hovertemplate=f"Setor {r['Setor']} — dia {r['Dia do turno']}<br>{r['Início']} → {r['Término']}<extra></extra>")
    fig.update_yaxes(autorange="reversed")
    fig.update_xaxes(title="Horas desde o início do turno de rega (dia 1, 0 h)")
    return _base(fig, "Cronograma de operação dos setores", max(260, 26 * len(df) + 80), legenda=False)
