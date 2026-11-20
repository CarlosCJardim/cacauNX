"""Relatórios: memorial descritivo e de cálculo em PDF (ReportLab) e planilha Excel (openpyxl)."""

from __future__ import annotations

import io
import os
from datetime import date

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from . import NOME_PROGRAMA, __version__  # noqa: E402
from .clima.estatistica import MESES  # noqa: E402
from .unidades import horas_para_hhmm, mca_para_kpa  # noqa: E402

CAT = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"]


def _fmt(v, casas=2):
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return "—"
    s = f"{float(v):,.{casas}f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


# ---------------------------------------------------------------------------
# Figuras (matplotlib)
# ---------------------------------------------------------------------------
def _estilo(ax):
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(axis="y", color="#8c8b86", alpha=0.2, linewidth=0.6)
    ax.tick_params(labelsize=8)


def _png(fig):
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=170, bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    return buf


def fig_planta(lay):
    fig, ax = plt.subplots(figsize=(7.2, 6.0))
    x, y = lay.poligono.exterior.xy
    ax.plot(x, y, color="#d4a000", lw=1.6, label="Área")
    n = max(len(lay.setores), 1)
    cmap = plt.get_cmap("Blues")
    for s, ids in enumerate(lay.setores):
        cor = cmap(0.35 + 0.6 * s / max(n - 1, 1))
        for i in ids:
            l = lay.laterais[i]
            pts = np.vstack([np.asarray(l.entrada_xy)[None, :], l.aspersores_xy])
            ax.plot(pts[:, 0], pts[:, 1], color=cor, lw=0.9)
        if ids:
            c = np.vstack([lay.laterais[i].aspersores_xy for i in ids]).mean(axis=0)
            ax.text(c[0], c[1], str(s + 1), fontsize=7, ha="center", va="center", fontweight="bold",
                    bbox=dict(boxstyle="round,pad=0.15", fc="white", ec="none", alpha=0.85))
    for d in lay.derivacoes:
        c = np.asarray(d["coords"])
        ax.plot(c[:, 0], c[:, 1], color=CAT[1], lw=2.2)
    if len(lay.principal) > 1:
        c = np.asarray(lay.principal)
        ax.plot(c[:, 0], c[:, 1], color=CAT[7], lw=2.6)
    c = np.asarray(lay.adutora)
    ax.plot(c[:, 0], c[:, 1], color=CAT[6], lw=2.6, ls=":")
    ax.plot(*lay.fonte_xy, marker="s", color=CAT[0], ms=8)
    ax.annotate("Captação", lay.fonte_xy, fontsize=7, xytext=(4, -10), textcoords="offset points")
    ax.set_aspect("equal")
    ax.set_xlabel("E (m)", fontsize=8)
    ax.set_ylabel("N (m)", fontsize=8)
    ax.tick_params(labelsize=7)
    ax.ticklabel_format(useOffset=False, style="plain")
    from matplotlib.lines import Line2D
    ax.legend(handles=[Line2D([], [], color="#d4a000", lw=1.6, label="Área"),
                       Line2D([], [], color=cmap(0.7), lw=1, label="Laterais (cor = setor)"),
                       Line2D([], [], color=CAT[1], lw=2.2, label="Derivações"),
                       Line2D([], [], color=CAT[7], lw=2.6, label="Principal"),
                       Line2D([], [], color=CAT[6], lw=2.6, ls=":", label="Adutora")],
              fontsize=7, loc="upper center", bbox_to_anchor=(0.5, -0.1), ncol=5, frameon=False)
    return _png(fig)


def fig_clima(tab):
    fig, (a1, a2) = plt.subplots(2, 1, figsize=(7.2, 4.2), sharex=True)
    a1.bar(MESES, tab["ETo (mm/d)"], color=CAT[0], width=0.6)
    a1.set_ylabel("ETo (mm/d)", fontsize=8)
    a2.bar(MESES, tab["Chuva (mm)"], color=CAT[2], width=0.6)
    a2.set_ylabel("Chuva (mm/mês)", fontsize=8)
    for a in (a1, a2):
        _estilo(a)
    return _png(fig)


def fig_balanco(tab):
    fig, ax = plt.subplots(figsize=(7.2, 3.0))
    x = np.arange(12)
    w = 0.27
    ax.bar(x - w, tab["ETc (mm/mês)"], w, color=CAT[0], label="ETc")
    ax.bar(x, tab["Pe (mm/mês)"], w, color=CAT[2], label="Chuva efetiva")
    ax.bar(x + w, tab["NIL (mm/mês)"], w, color=CAT[1], label="Necessidade líquida")
    ax.set_xticks(x, MESES)
    ax.set_ylabel("mm/mês", fontsize=8)
    ax.legend(fontsize=7, frameon=False, ncol=3)
    _estilo(ax)
    return _png(fig)


def fig_uniformidade(sim, ea, el):
    fig, ax = plt.subplots(figsize=(4.6, 4.0))
    im = ax.pcolormesh(sim["X"], sim["Y"], sim["L"], cmap="Blues", shading="auto")
    cb = fig.colorbar(im, ax=ax, shrink=0.85)
    cb.set_label("mm/h", fontsize=8)
    ax.set_aspect("equal")
    ax.set_xlabel("Ao longo da lateral (m)", fontsize=8)
    ax.set_ylabel("Entre laterais (m)", fontsize=8)
    ax.tick_params(labelsize=7)
    ax.set_title(f"CUC {sim['CUC']:.1f}% · CUD {sim['CUD']:.1f}%", fontsize=9)
    return _png(fig)


def fig_lateral(r, h_servico):
    fig, (a1, a2) = plt.subplots(2, 1, figsize=(7.2, 3.8), sharex=True, gridspec_kw={"height_ratios": [2, 1]})
    a1.plot(r.distancias, r.h_bocal, color=CAT[0], lw=2, marker="o", ms=3)
    a1.axhline(h_servico, color="#8c8b86", ls="--", lw=1)
    a1.set_ylabel("Pressão no bocal (mca)", fontsize=8)
    a2.fill_between(np.concatenate([[0], r.distancias]), r.cotas, r.cotas.min() - 1, color="#8a7f6a", alpha=0.25)
    a2.plot(np.concatenate([[0], r.distancias]), r.cotas, color="#8a7f6a", lw=1.5)
    a2.set_ylabel("Cota (m)", fontsize=8)
    a2.set_xlabel("Distância da entrada (m)", fontsize=8)
    for a in (a1, a2):
        _estilo(a)
    return _png(fig)


def fig_bomba(bm):
    curva, hsis = bm["curva"], bm["h_sis"]
    q = np.linspace(0, max(curva.q_max, bm["Q"] * 1.4), 100)
    fig, (a1, a2) = plt.subplots(2, 1, figsize=(7.2, 4.6), sharex=True, gridspec_kw={"height_ratios": [2, 1]})
    h = curva.h(q)
    m = h > 0
    a1.plot(q[m], h[m], color=CAT[0], lw=2, label="Bomba")
    a1.plot(q, hsis(q), color=CAT[1], lw=2, ls="--", label="Sistema (setor crítico)")
    pts = bm["pontos_setores"]
    a1.scatter([p["Q (m³/h)"] for p in pts], [p["Hman requerida (m)"] for p in pts], color=CAT[2], s=18, zorder=3,
               label="Setores")
    if bm["ponto"]:
        a1.scatter([bm["ponto"][0]], [bm["ponto"][1]], color="black", marker="D", s=40, zorder=4, label="Ponto de operação")
    a1.set_ylabel("H (m)", fontsize=8)
    a1.set_ylim(bottom=0)
    a1.legend(fontsize=7, frameon=False)
    a2.plot(q, 100 * curva.eta(q), color=CAT[5], lw=2)
    a2.set_ylabel("η (%)", fontsize=8)
    a2.set_xlabel("Vazão (m³/h)", fontsize=8)
    for a in (a1, a2):
        _estilo(a)
    return _png(fig)


# ---------------------------------------------------------------------------
# PDF
# ---------------------------------------------------------------------------
def _registrar_fonte():
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    base = os.path.join(matplotlib.get_data_path(), "fonts", "ttf")
    try:
        pdfmetrics.registerFont(TTFont("DejaVu", os.path.join(base, "DejaVuSans.ttf")))
        pdfmetrics.registerFont(TTFont("DejaVu-Bold", os.path.join(base, "DejaVuSans-Bold.ttf")))
        from reportlab.lib.fonts import addMapping
        addMapping("DejaVu", 0, 0, "DejaVu")
        addMapping("DejaVu", 1, 0, "DejaVu-Bold")
        return "DejaVu", "DejaVu-Bold"
    except Exception:  # noqa: BLE001
        return "Helvetica", "Helvetica-Bold"


def gerar_pdf(projeto: dict, r: dict) -> bytes:
    """Gera o memorial descritivo e de cálculo. ``r`` é a saída de :func:`pipeline.executar_tudo`."""
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import cm
    from reportlab.platypus import (Image, KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table,
                                    TableStyle)

    fonte, fonte_b = _registrar_fonte()
    est = getSampleStyleSheet()
    for s in est.byName.values():
        s.fontName = fonte
    H1 = ParagraphStyle("H1", parent=est["Heading1"], fontName=fonte_b, fontSize=14, spaceBefore=10, spaceAfter=6,
                        textColor=colors.HexColor("#0d366b"))
    H2 = ParagraphStyle("H2", parent=est["Heading2"], fontName=fonte_b, fontSize=11, spaceBefore=6, spaceAfter=4,
                        textColor=colors.HexColor("#1c5cab"))
    N = ParagraphStyle("N", parent=est["BodyText"], fontName=fonte, fontSize=9, leading=12.5)
    PEQ = ParagraphStyle("P", parent=N, fontSize=7.5, leading=10, textColor=colors.HexColor("#52514e"))
    EQ = ParagraphStyle("EQ", parent=N, fontName=fonte, fontSize=9, leftIndent=18, textColor=colors.HexColor("#0b0b0b"),
                        backColor=colors.HexColor("#f3f6fb"), borderPadding=4, spaceBefore=3, spaceAfter=3)

    def tabela(dados, larguras=None, cab=True, fs=7.8):
        t = Table(dados, colWidths=larguras, repeatRows=1 if cab else 0)
        estilo = [("FONTNAME", (0, 0), (-1, -1), fonte), ("FONTSIZE", (0, 0), (-1, -1), fs),
                  ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#c3c2b7")),
                  ("ROWBACKGROUNDS", (0, 1 if cab else 0), (-1, -1), [colors.white, colors.HexColor("#f7f7f5")]),
                  ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2)]
        if cab:
            estilo += [("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1c5cab")),
                       ("TEXTCOLOR", (0, 0), (-1, 0), colors.white), ("FONTNAME", (0, 0), (-1, 0), fonte_b)]
        t.setStyle(TableStyle(estilo))
        return t

    def df_tab(df, larguras=None, fs=7.2, max_linhas=60):
        d = df.head(max_linhas)
        dados = [list(map(str, d.columns))]
        for _, row in d.iterrows():
            dados.append([_fmt(v, 2) if isinstance(v, (float, np.floating)) else str(v) for v in row.values])
        return tabela(dados, larguras, True, fs)

    info = projeto["info"]
    buf = io.BytesIO()

    def rodape(canvas, doc):
        canvas.saveState()
        canvas.setFont(fonte, 7)
        canvas.setFillColor(colors.HexColor("#8c8b86"))
        canvas.drawString(2 * cm, 1.2 * cm, f"{NOME_PROGRAMA} v{__version__} — {info['nome']}")
        canvas.drawRightString(A4[0] - 2 * cm, 1.2 * cm, f"Página {doc.page}")
        canvas.restoreState()

    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=2 * cm, rightMargin=2 * cm, topMargin=1.8 * cm,
                            bottomMargin=1.8 * cm, title=f"Memorial — {info['nome']}", author=info.get("responsavel", ""))
    W = A4[0] - 4 * cm
    e = []
    # ------------------------------------------------------------------ capa
    e += [Spacer(1, 3 * cm),
          Paragraph("MEMORIAL DESCRITIVO E DE CÁLCULO", ParagraphStyle("c0", parent=H1, alignment=TA_CENTER, fontSize=18)),
          Paragraph("Sistema de irrigação por aspersão convencional com manejo pelo clima",
                    ParagraphStyle("c1", parent=N, alignment=TA_CENTER, fontSize=11)),
          Spacer(1, 1.2 * cm)]
    capa = [["Projeto", info["nome"]], ["Cliente / produtor", info.get("cliente") or "—"],
            ["Propriedade", info.get("propriedade") or "—"],
            ["Município / UF", f"{info.get('municipio') or '—'} / {info.get('uf') or '—'}"],
            ["Responsável técnico", info.get("responsavel") or "—"], ["Registro / ART", info.get("registro") or "—"],
            ["Data", date.today().strftime("%d/%m/%Y")]]
    e.append(tabela(capa, [5 * cm, W - 5 * cm], cab=False, fs=9.5))
    if info.get("observacoes"):
        e += [Spacer(1, 0.6 * cm), Paragraph(info["observacoes"], N)]
    e += [Spacer(1, 4 * cm), Paragraph(f"Documento gerado pelo {NOME_PROGRAMA} v{__version__}. Os cálculos seguem FAO-56, "
                                       "Christiansen (1942), Keller &amp; Bliesner (1990) e as equações de Hazen-Williams/"
                                       "Darcy-Weisbach. Confira catálogos de fabricantes e cotações antes da execução.", PEQ),
          PageBreak()]

    erros = r.get("erros", {})
    geo_, cl, kc, asp, agr = r.get("geo"), r.get("clima"), r.get("kc"), r.get("aspersor"), r.get("agronomico")
    lo, op, rede, bm, cu = r.get("layout"), r.get("operacao"), r.get("rede"), r.get("bomba"), r.get("custos")

    # ------------------------------------------------------------------ 1. resumo
    e.append(Paragraph("1. Resumo do projeto", H1))
    linhas = [["Parâmetro", "Valor"]]
    if lo:
        lay = lo["layout"]
        linhas += [["Área do polígono", f"{_fmt(lay.area_ha)} ha"], ["Área irrigada (aspersores × espaçamento)", f"{_fmt(lay.area_irrigada_ha)} ha"],
                   ["Número de aspersores", _fmt(lay.n_aspersores, 0)], ["Laterais / derivações", f"{len(lay.laterais)} / {len(lay.derivacoes)}"]]
    if kc:
        linhas.append(["Cultura", kc["cultura"].nome])
    if agr:
        pr = agr["projeto"]
        linhas += [["ETc de projeto", f"{_fmt(agr['etc_proj'])} mm/d"], ["Turno de rega", f"{pr['TR']:.0f} dias"],
                   ["Lâmina líquida / bruta", f"{_fmt(pr['LL'], 1)} / {_fmt(pr['LB'], 1)} mm"],
                   ["Eficiência de aplicação", f"{_fmt(pr['Ea'] * 100, 1)} %"]]
    if asp:
        linhas += [["Aspersor", asp["asp"].rotulo], ["Pressão de serviço / vazão", f"{asp['pressao']:.0f} kPa / {_fmt(asp['q'], 3)} m³/h"],
                   ["Espaçamento / arranjo", f"{projeto['aspersor']['esp_asp']:g} × {projeto['aspersor']['esp_lat']:g} m — {projeto['aspersor']['arranjo']}"],
                   ["Intensidade de aplicação", f"{_fmt(asp['ia'])} mm/h"], ["CUC / CUD simulados", f"{_fmt(asp['sim']['CUC'], 1)} % / {_fmt(asp['sim']['CUD'], 1)} %"]]
    if op:
        linhas += [["Tempo de aplicação por setor", horas_para_hhmm(op["Ti"])], ["Número de setores", str(op["n_setores"])],
                   ["Vazão do sistema", f"{_fmt(op['Q_sistema'], 1)} m³/h"]]
    if bm:
        linhas += [["Altura manométrica total", f"{_fmt(bm['Hman'], 1)} m"],
                   ["Motor", f"{bm['potencias']['motor']['motor_cv']:g} cv ({_fmt(bm['potencias']['P_eixo_cv'], 1)} cv no eixo)"],
                   ["Energia anual estimada", f"{_fmt(bm['energia']['energia_kWh'], 0)} kWh"]]
    if cu:
        eco = cu["economia"]
        linhas += [["Investimento total", f"R$ {_fmt(eco['investimento'], 0)}"], ["Investimento por hectare", f"R$ {_fmt(eco['investimento_ha'], 0)}/ha"],
                   ["Custo anual total", f"R$ {_fmt(eco['custo_anual_total'], 0)}"]]
    e.append(tabela(linhas, [7 * cm, W - 7 * cm]))
    if erros:
        e.append(Spacer(1, 6))
        e.append(Paragraph("<b>Etapas incompletas:</b> " + "; ".join(f"{k}: {v}" for k, v in erros.items()), PEQ))

    # ------------------------------------------------------------------ 2. área
    if lo:
        lay = lo["layout"]
        e += [PageBreak(), Paragraph("2. Localização, área e layout", H1)]
        e.append(Paragraph(f"Sistema de coordenadas: {lay.proj.nome}. Centro aproximado: lat. {geo_['lat']:.5f}°, "
                           f"long. {geo_['lon']:.5f}°. Laterais com azimute de {lo['azimute']:.1f}° "
                           f"({lo['orientacao']}); comprimento máximo de lateral {lo['comp_max']:.0f} m.", N))
        e.append(Image(fig_planta(lay), width=W, height=W * 0.86))
        el = r.get("elev")
        if el:
            info_e = el[1]
            txt = f"Altimetria: {info_e.get('fonte', '')}."
            if "declividade_pct" in info_e:
                txt += f" Declividade média {info_e['declividade_pct']:.2f}%."
            if "cota_min" in info_e:
                txt += f" Cotas na área entre {info_e['cota_min']:.1f} e {info_e['cota_max']:.1f} m."
            e.append(Paragraph(txt, N))

    # ------------------------------------------------------------------ 3. clima
    if cl:
        e += [PageBreak(), Paragraph("3. Clima e evapotranspiração de referência", H1),
              Paragraph(f"Método: {cl['metodo']}. Fonte dos dados: {cl.get('fonte') or '—'}. Latitude {cl['lat']:.4f}°, "
                        f"altitude {cl['altitude']:.0f} m.", N),
              Paragraph("ETo = [0,408 Δ (Rn − G) + γ (900/(T + 273)) u2 (es − ea)] / [Δ + γ (1 + 0,34 u2)]  — FAO-56, Eq. 6", EQ),
              Image(fig_clima(cl["tabela"]), width=W, height=W * 0.58), df_tab(cl["tabela"])]

    # ------------------------------------------------------------------ 4. necessidade
    if agr and kc:
        c = kc["cultura"]
        pr = agr["projeto"]
        e += [PageBreak(), Paragraph("4. Cultura e necessidade hídrica (manejo pelo clima)", H1),
              Paragraph(f"Cultura: <b>{c.nome}</b> — Kc inicial {c.kc_ini:.2f}, intermediário {c.kc_mid:.2f} "
                        f"(ajustado {kc['kc_mid']:.3f}), final {c.kc_end:.2f} (ajustado {kc['kc_end']:.3f}). {c.nota}", N),
              Paragraph("Kc ajustado = Kc tab + [0,04 (u2 − 2) − 0,004 (URmín − 45)] (h/3)^0,3  — FAO-56, Eq. 62", EQ),
              Paragraph("O manejo será realizado pelo clima: a lâmina de cada irrigação repõe a ETc acumulada desde a "
                        "irrigação anterior, descontada a chuva efetiva; o turno de rega é fixado operacionalmente e não "
                        "depende da água disponível no solo.", N),
              Paragraph("ETc = Kc × ETo;  LL = ETc_proj × TR;  LB = LL / Ea;  Ti = LB / Ia", EQ),
              Paragraph(f"Critério da ETc de projeto: {agr['descricao']}. ETc_proj = {_fmt(agr['etc_proj'])} mm/d; "
                        f"TR = {pr['TR']:.0f} d; LL = {_fmt(pr['LL'], 1)} mm; Ea = {_fmt(pr['Ea'], 3)}; "
                        f"LB = {_fmt(pr['LB'], 1)} mm; Ti = {horas_para_hhmm(pr['Ti'])}.", N),
              Image(fig_balanco(agr["tabela"]), width=W, height=W * 0.42), df_tab(agr["tabela"], fs=6.8)]

    # ------------------------------------------------------------------ 5. aspersor
    if asp:
        a = projeto["aspersor"]
        e += [PageBreak(), Paragraph("5. Aspersor, espaçamento e uniformidade", H1)]
        dados = [["Item", "Valor"], ["Aspersor", asp["asp"].rotulo], ["Tipo", asp["asp"].tipo],
                 ["Pressão de serviço", f"{asp['pressao']:.0f} kPa ({_fmt(asp['h_servico'], 1)} mca)"],
                 ["Vazão", f"{_fmt(asp['q'], 3)} m³/h"], ["Equação vazão-pressão", f"q = {asp['k']:.5f} · P^{asp['x']:.3f}"],
                 ["Diâmetro molhado", f"{_fmt(asp['dm'], 1)} m"], ["Espaçamento", f"{a['esp_asp']:g} × {a['esp_lat']:g} m ({a['arranjo']})"],
                 ["Intensidade de aplicação", f"{_fmt(asp['ia'])} mm/h (VIB {projeto['agronomico']['vib']:.1f} mm/h)"],
                 ["Vento considerado", f"{a['vento_ms']:.1f} m/s"], ["CUC / CUD / CUH", f"{_fmt(asp['sim']['CUC'], 1)} / {_fmt(asp['sim']['CUD'], 1)} / {_fmt(asp['sim']['CUH'], 1)} %"],
                 ["Perdas por evaporação e deriva (Trimmer)", f"{_fmt(asp['perdas_evap'], 1)} %"],
                 ["Eficiência de distribuição (Ed a)", f"{_fmt(asp['ed'], 1)} %"], ["Eficiência de aplicação adotada", f"{_fmt(asp['ea'] * 100, 1)} %"]]
        e.append(KeepTogether([tabela(dados, [6.5 * cm, W - 6.5 * cm]), Spacer(1, 6),
                               Image(fig_uniformidade(asp["sim"], a["esp_asp"], a["esp_lat"]), width=9 * cm, height=7.8 * cm)]))
        e.append(Paragraph("CUC = 100 (1 − Σ|xi − x̄| / (n x̄))  — Christiansen (1942)", EQ))
        e.append(Paragraph("Pe = [1,98 D^−0,72 + 0,22 (es − ea)^0,63 + 3,6·10⁻⁴ h^1,16 + 0,14 W^0,7]^4,2  — Trimmer (1987)", EQ))

    # ------------------------------------------------------------------ 6. operação
    if op:
        e += [PageBreak(), Paragraph("6. Dimensionamento operacional e setorização", H1),
              Paragraph(f"Tipo de sistema: {projeto['operacao']['tipo_sistema']}. Jornada {projeto['operacao']['jornada_h']:.1f} h/dia; "
                        f"{op['posicoes_dia']} posição(ões) por dia; {op['dias_uteis']} dia(s) úteis; {op['n_setores']} setores "
                        f"(máximo {op['n_setores_max']}). Vazão do sistema {_fmt(op['Q_sistema'], 1)} m³/h "
                        f"({_fmt(op['vazao_especifica_ls_ha'])} L/s/ha).", N),
              df_tab(op["setores"]), Spacer(1, 6), Paragraph("Cronograma de operação", H2), df_tab(op["cronograma"])]
        for av in op["avisos"] + op["recomendacoes"]:
            e.append(Paragraph(f"• {av}", PEQ))

    # ------------------------------------------------------------------ 7. hidráulica
    if rede and lo:
        lay = lo["layout"]
        e += [PageBreak(), Paragraph("7. Dimensionamento hidráulico", H1),
              Paragraph(f"Equação: {'Hazen-Williams' if projeto['hidraulica']['equacao'] == 'HW' else 'Darcy-Weisbach (Swamee-Jain)'}. "
                        f"Tolerância de variação de pressão na lateral: {projeto['hidraulica']['tol_lateral']:.0f}% da PS; entre "
                        f"laterais do setor: {projeto['hidraulica']['tol_derivacao']:.0f}%. Perdas localizadas na rede: "
                        f"{projeto['hidraulica']['perda_local_rede']:.0f}% do atrito.", N),
              Paragraph("hf = 10,646 L Q^1,852 / (C^1,852 D^4,87);  F = [a N^m + Σ j^m] / [(N − 1 + a) N^m];  "
                        "Pin = PS + ¾ hf + ½ ΔZ + Ha", EQ)]
        crit_lat = max(rede.laterais, key=lambda i: rede.laterais[i]["res"].h_entrada)
        rl = rede.laterais[crit_lat]
        e.append(Paragraph(f"Lateral crítica: nº {crit_lat + 1} ({lay.laterais[crit_lat].n} aspersores, {rl['tubo'].rotulo}) — "
                           f"pressão na entrada {_fmt(rl['res'].h_entrada)} mca, variação {_fmt(rl['res'].var_pressao_pct, 1)}%.", N))
        e.append(Image(fig_lateral(rl["res"], asp["h_servico"]), width=W, height=W * 0.53))
        from .rede import trechos_agrupados
        tab = trechos_agrupados(rede)
        e += [Paragraph("Adutora, principal e derivações (trechos com o mesmo tubo agrupados)", H2),
              df_tab(tab, fs=6.6, max_linhas=120)]
        resumo = pd.DataFrame([{"Tipo": "Lateral", "Tubo": v["tubo"].rotulo, "L (m)": lay.laterais[i].comprimento}
                               for i, v in rede.laterais.items()]).groupby(["Tipo", "Tubo"], as_index=False)["L (m)"].sum().round(1)
        e += [Paragraph("Quantitativo de tubos das laterais", H2), df_tab(resumo)]
        e.append(Paragraph(f"Pressão requerida na saída da bomba (setor crítico {rede.setor_critico + 1}): "
                           f"{_fmt(rede.p_fonte_max)} mca ({_fmt(mca_para_kpa(rede.p_fonte_max), 0)} kPa).", N))
        g = rede.golpe
        e.append(Paragraph(f"Golpe de aríete na adutora: celeridade {g['celeridade']:.0f} m/s, tempo crítico "
                           f"{g['tempo_critico']:.1f} s, sobrepressão {g['sobrepressao']:.1f} mca ({g['regime']}).", N))
        for av in rede.avisos:
            e.append(Paragraph(f"• {av}", PEQ))

    # ------------------------------------------------------------------ 8. bomba
    if bm:
        pot = bm["potencias"]
        e += [PageBreak(), Paragraph("8. Conjunto motobomba e energia", H1)]
        dec = [["Parcela", "m"]] + [[k, _fmt(v)] for k, v in bm["decomposicao"].items()] + [["Altura manométrica total", _fmt(bm["Hman"])]]
        e.append(tabela(dec, [10 * cm, 3 * cm]))
        e.append(Paragraph("TDH = H estática + H atrito + H localizadas + H operação;  Ph = ρ g Q H / 1000;  "
                           "P eixo = Ph / η bomba;  P motor = P eixo / η motor", EQ))
        dados = [["Item", "Valor"], ["Vazão de projeto", f"{_fmt(bm['Q'], 1)} m³/h"], ["Altura manométrica", f"{_fmt(bm['Hman'], 1)} m"],
                 ["Potência hidráulica", f"{_fmt(pot['P_hidraulica_kW'])} kW"], ["Potência no eixo", f"{_fmt(pot['P_eixo_kW'])} kW ({_fmt(pot['P_eixo_cv'], 1)} cv)"],
                 ["Motor comercial", f"{pot['motor']['motor_cv']:g} cv (folga {pot['motor']['folga'] * 100:.0f}%)"],
                 ["Rotação / nq", f"{bm['rpm']:.0f} rpm / {bm['nq']:.0f} — {bm['tipo_rotor']}"],
                 ["NPSH disponível / requerido", f"{_fmt(bm['npsh']['NPSHd'], 1)} / {_fmt(bm['npshr'], 1)} m"],
                 ["Tubo de sucção", f"{bm['tubo_succao'].rotulo} (v = {bm['v_succao']:.2f} m/s)"],
                 ["Horas de bombeamento/ano", _fmt(bm["horas_ano"], 0)], ["Energia anual", f"{_fmt(bm['energia']['energia_kWh'], 0)} kWh"],
                 ["Custo anual de energia", f"R$ {_fmt(bm['energia']['custo_total'], 0)}"]]
        e.append(tabela(dados, [6.5 * cm, W - 6.5 * cm]))
        e.append(Image(fig_bomba(bm), width=W, height=W * 0.64))
        for av in bm["avisos"]:
            e.append(Paragraph(f"• {av}", PEQ))

    # ------------------------------------------------------------------ 9. orçamento
    if cu:
        eco = cu["economia"]
        e += [PageBreak(), Paragraph("9. Orçamento e análise econômica", H1),
              df_tab(cu["orcamento"].drop(columns=["Grupo"]), fs=6.6, max_linhas=80), Spacer(1, 6)]
        dados = [["Indicador", "Valor"], ["Investimento total", f"R$ {_fmt(eco['investimento'], 0)}"],
                 ["Investimento por hectare", f"R$ {_fmt(eco['investimento_ha'], 0)}/ha"],
                 ["Recuperação do capital (anual)", f"R$ {_fmt(eco['custo_capital_anual'], 0)}"],
                 ["Manutenção (anual)", f"R$ {_fmt(eco['manutencao_anual'], 0)}"], ["Energia (anual)", f"R$ {_fmt(eco['energia_anual'], 0)}"],
                 ["Custo anual total", f"R$ {_fmt(eco['custo_anual_total'], 0)}"], ["Custo por hectare·ano", f"R$ {_fmt(eco['custo_anual_ha'], 0)}"],
                 ["Custo da água aplicada", f"R$ {_fmt(eco['custo_m3'], 3)}/m³"]]
        e.append(tabela(dados, [7 * cm, W - 7 * cm]))
        e.append(Paragraph("Preços de referência — atualizar com cotações locais antes da contratação.", PEQ))

    # ------------------------------------------------------------------ 10. manejo
    if agr and asp:
        pr = agr["projeto"]
        e += [PageBreak(), Paragraph("10. Recomendações de manejo da irrigação pelo clima", H1)]
        for t in [
            "1) Obtenha diariamente a ETo (estação meteorológica automática da propriedade, estação do INMET mais próxima, "
            "previsão numérica do tempo ou tanque Classe A com ETo = Kp × ECA).",
            f"2) Calcule a ETc = Kc × ETo com o Kc da fase da cultura (Kc intermediário ajustado = {kc['kc_mid']:.2f}).",
            f"3) Acumule o saldo: S = S anterior + ETc − Pe, considerando chuva efetiva apenas acima de "
            f"{projeto['manejo']['limiar_pe']:.0f} mm, com aproveitamento de {projeto['manejo']['frac_pe'] * 100:.0f}%.",
            f"4) No dia previsto (turno de rega de {pr['TR']:.0f} dias), aplique a lâmina líquida igual ao saldo. "
            f"Lâmina bruta = saldo / {pr['Ea']:.2f}.",
            f"5) Tempo de funcionamento de cada setor = lâmina bruta / {asp['ia']:.2f} mm/h. Exemplo: para o saldo de "
            f"projeto ({pr['LL']:.1f} mm), {horas_para_hhmm(pr['Ti'])} por setor.",
            "6) Adie a irrigação quando a previsão de chuva para as próximas 48 h cobrir o saldo; registre lâminas "
            "aplicadas (hidrômetro) e confira periodicamente a uniformidade em campo (ensaio de coletores).",
            "7) Priorize a operação no período noturno (menor vento e evaporação e tarifa de energia com desconto).",
        ]:
            e.append(Paragraph(t, N))
        e.append(Paragraph("S_t = máx(S_t−1 + ETc_t − Pe_t − I_t ; −C máx)   I = S (no dia de irrigar);   T setor = (I / Ea) / Ia", EQ))

    # ------------------------------------------------------------------ referências
    e += [PageBreak(), Paragraph("Referências", H1)]
    for ref in [
        "ALLEN, R. G.; PEREIRA, L. S.; RAES, D.; SMITH, M. Crop evapotranspiration — Guidelines for computing crop water "
        "requirements. FAO Irrigation and Drainage Paper 56. Roma: FAO, 1998.",
        "BERNARDO, S.; MANTOVANI, E. C.; SILVA, D. D.; SOARES, A. A. Manual de irrigação. 9. ed. Viçosa: UFV, 2019.",
        "CHRISTIANSEN, J. E. Irrigation by sprinkling. California Agricultural Experiment Station Bulletin 670, 1942.",
        "EL-NAGGAR, A. G. OpenIrri: An open-source Python platform for solid-set sprinkler irrigation system design. "
        "SoftwareX, v. 35, 102912, 2026.",
        "KELLER, J.; BLIESNER, R. D. Sprinkle and trickle irrigation. New York: Van Nostrand Reinhold, 1990.",
        "SNYDER, R. L. Equation for evaporation pan to evapotranspiration conversions. J. Irrig. Drain. Eng., v. 118, n. 6, 1992.",
        "SWAMEE, P. K.; JAIN, A. K. Explicit equations for pipe-flow problems. J. Hydraul. Div. ASCE, v. 102, 1976.",
        "TRIMMER, W. L. Sprinkler evaporation loss equation. J. Irrig. Drain. Eng., v. 113, n. 4, p. 616–620, 1987.",
        "AGÊNCIA NACIONAL DE ENERGIA ELÉTRICA. Resolução Normativa nº 1.000/2021 (descontos para irrigação e aquicultura).",
    ]:
        e.append(Paragraph(ref, PEQ))
    e += [Spacer(1, 1.5 * cm), Paragraph("_______________________________________", N),
          Paragraph(f"{info.get('responsavel') or 'Responsável técnico'} — {info.get('registro') or 'registro profissional'}", N)]
    doc.build(e, onFirstPage=rodape, onLaterPages=rodape)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Excel
# ---------------------------------------------------------------------------
def gerar_excel(projeto: dict, r: dict) -> bytes:
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as xw:
        info = projeto["info"]
        resumo = [("Projeto", info["nome"]), ("Cliente", info.get("cliente")), ("Propriedade", info.get("propriedade")),
                  ("Município/UF", f"{info.get('municipio')}/{info.get('uf')}"), ("Responsável", info.get("responsavel")),
                  ("Data", date.today().isoformat())]
        agr, asp, op, bm, cu, lo, rede = (r.get(k) for k in ("agronomico", "aspersor", "operacao", "bomba", "custos", "layout", "rede"))
        if agr:
            pr = agr["projeto"]
            resumo += [("ETc de projeto (mm/d)", round(agr["etc_proj"], 3)), ("Turno de rega (d)", pr["TR"]),
                       ("Lâmina líquida (mm)", round(pr["LL"], 2)), ("Lâmina bruta (mm)", round(pr["LB"], 2)),
                       ("Eficiência de aplicação", round(pr["Ea"], 3))]
        if asp:
            resumo += [("Aspersor", asp["asp"].rotulo), ("Pressão (kPa)", asp["pressao"]), ("Vazão (m³/h)", round(asp["q"], 4)),
                       ("Ia (mm/h)", round(asp["ia"], 3)), ("CUC (%)", round(asp["sim"]["CUC"], 2))]
        if op:
            resumo += [("Ti (h)", round(op["Ti"], 3)), ("Setores", op["n_setores"]), ("Vazão do sistema (m³/h)", round(op["Q_sistema"], 2))]
        if bm:
            resumo += [("Hman (m)", round(bm["Hman"], 2)), ("Motor (cv)", bm["potencias"]["motor"]["motor_cv"]),
                       ("Energia anual (kWh)", round(bm["energia"]["energia_kWh"], 0))]
        if cu:
            resumo += [("Investimento (R$)", round(cu["economia"]["investimento"], 2)),
                       ("Custo anual (R$)", round(cu["economia"]["custo_anual_total"], 2))]
        pd.DataFrame(resumo, columns=["Parâmetro", "Valor"]).to_excel(xw, sheet_name="Resumo", index=False)
        if r.get("clima"):
            r["clima"]["tabela"].to_excel(xw, sheet_name="Clima", index=False)
            if r["clima"]["diario"] is not None:
                r["clima"]["diario"].to_excel(xw, sheet_name="Clima diário")
        if agr:
            agr["tabela"].to_excel(xw, sheet_name="Balanço mensal", index=False)
        if op:
            op["setores"].to_excel(xw, sheet_name="Setores", index=False)
            op["cronograma"].to_excel(xw, sheet_name="Cronograma", index=False)
        if rede and lo:
            lay = lo["layout"]
            pd.DataFrame([{"Lateral": i + 1, "Setor": lay.laterais[i].setor + 1, "Aspersores": lay.laterais[i].n,
                           "Comprimento (m)": round(lay.laterais[i].comprimento, 2), "Tubo": v["tubo"].rotulo,
                           "Pin (mca)": round(v["res"].h_entrada, 3), "Q (m³/h)": round(v["res"].q_entrada_m3h, 3),
                           "ΔP (%)": round(v["res"].var_pressao_pct, 2), "ΔZ (m)": round(v["res"].dz, 2)}
                          for i, v in rede.laterais.items()]).to_excel(xw, sheet_name="Laterais", index=False)
            pd.DataFrame([{"Trecho": t.id, "Tipo": t.tipo, "Material": t.tubo.material, "DN": t.tubo.dn, "PN (mca)": t.tubo.pn_mca,
                           "DI (mm)": t.tubo.di_mm, "L (m)": round(t.comprimento, 2), "Q (m³/h)": round(t.q_proj, 2),
                           "v (m/s)": round(t.v_proj, 3), "hf (m)": round(t.hf_proj, 3)} for t in rede.trechos]
                         ).to_excel(xw, sheet_name="Rede", index=False)
        if bm:
            pd.DataFrame(list(bm["decomposicao"].items()) + [("Altura manométrica total", bm["Hman"])],
                         columns=["Parcela", "m"]).to_excel(xw, sheet_name="Bomba", index=False)
            pd.DataFrame(bm["pontos_setores"]).to_excel(xw, sheet_name="Bomba", index=False, startcol=4)
        if cu:
            cu["orcamento"].to_excel(xw, sheet_name="Orçamento", index=False)
        for ws in xw.book.worksheets:
            for cel in ws[1]:
                cel.font = Font(bold=True, color="FFFFFF")
                cel.fill = PatternFill("solid", fgColor="1C5CAB")
                cel.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
            for i, col in enumerate(ws.columns, 1):
                larg = max((len(str(c.value)) for c in col if c.value is not None), default=8)
                ws.column_dimensions[get_column_letter(i)].width = min(max(10, larg + 2), 60)
            ws.freeze_panes = "A2"
    return buf.getvalue()
