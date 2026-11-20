"""Exportação do projeto: KMZ para o Google Earth, DXF para CAD e GeoJSON para SIG."""

from __future__ import annotations

import io
import json

import numpy as np

from .geo import KMLBuilder, linha_utm_para_lonlat

CORES_SETOR = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"]


def _cor_setor(s, n):
    # rampa azul ordinal (ordem de operação), igual à da interface
    passos = ["#86b6ef", "#6da7ec", "#5598e7", "#3987e5", "#2a78d6", "#256abf", "#1c5cab", "#184f95", "#104281",
              "#0d366b"]
    if n <= 1:
        return passos[4]
    return passos[int(round(s / (n - 1) * (len(passos) - 1)))]


def kmz_projeto(nome, lay, res=None, poligono_lonlat=None, curvas=None) -> bytes:
    """KMZ com área, setores, laterais, aspersores, rede e curvas de nível — abre no Google Earth."""
    proj = lay.proj
    kb = KMLBuilder(nome)
    kb.estilo("area", "#ffd400", 3, "#ffd400", 30)
    kb.estilo("adutora", "#6250d6", 5)
    kb.estilo("principal", "#e34948", 5)
    kb.estilo("derivacao", "#eb6834", 4)
    kb.estilo("curva", "#ffffff", 1)
    kb.estilo("curva_m", "#fff3b0", 2)
    kb.estilo("asp", "#ffffff", 1, icone="http://maps.google.com/mapfiles/kml/shapes/placemark_circle.png", escala=0.35,
              cor_icone="#2a78d6")
    kb.estilo("bomba", "#2a78d6", 2, icone="http://maps.google.com/mapfiles/kml/shapes/water.png", escala=1.0)
    kb.estilo("valvula", "#ffffff", 1, icone="http://maps.google.com/mapfiles/kml/shapes/square.png", escala=0.6,
              cor_icone="#eda100")
    n = max(len(lay.setores), 1)
    for s in range(n):
        kb.estilo(f"setor{s}", _cor_setor(s, n), 2.5)

    pa = kb.pasta("Área do projeto")
    if poligono_lonlat:
        kb.poligono(pa, "Área", poligono_lonlat, "area", {"Área (ha)": f"{lay.area_ha:.2f}"})
    lon, lat = proj.geo(*lay.fonte_xy)
    kb.ponto(pa, "Captação / casa de bomba", lon, lat, "bomba")

    pl = kb.pasta("Linhas laterais (por setor)")
    for l in lay.laterais:
        pts = np.vstack([np.asarray(l.entrada_xy)[None, :], l.aspersores_xy])
        desc = {"Setor": l.setor + 1, "Aspersores": l.n, "Comprimento (m)": f"{l.comprimento:.1f}"}
        if res is not None and l.id in res.laterais:
            r = res.laterais[l.id]
            desc.update({"Tubo": r["tubo"].rotulo, "Pressão na entrada (mca)": f"{r['res'].h_entrada:.2f}",
                         "Vazão (m³/h)": f"{r['res'].q_entrada_m3h:.2f}",
                         "Variação de pressão (%)": f"{r['res'].var_pressao_pct:.1f}"})
        kb.linha(pl, f"Lateral {l.id + 1}", linha_utm_para_lonlat(proj, pts), f"setor{max(l.setor, 0)}", desc)

    pr = kb.pasta("Rede (adutora, principal, derivações)")
    if res is not None:
        for t in res.trechos:
            kb.linha(pr, f"{t.tipo.capitalize()} {t.id}", linha_utm_para_lonlat(proj, t.coords), t.tipo,
                     {"Tubo": t.tubo.rotulo, "Comprimento (m)": f"{t.comprimento:.1f}", "Vazão (m³/h)": f"{t.q_proj:.1f}",
                      "Velocidade (m/s)": f"{t.v_proj:.2f}", "Perda de carga (m)": f"{t.hf_proj:.2f}"})
    else:
        for d in lay.derivacoes:
            kb.linha(pr, f"Derivação {d['id'] + 1}", linha_utm_para_lonlat(proj, d["coords"]), "derivacao")
        if len(lay.principal) > 1:
            kb.linha(pr, "Linha principal", linha_utm_para_lonlat(proj, lay.principal), "principal")
        kb.linha(pr, "Adutora", linha_utm_para_lonlat(proj, lay.adutora), "adutora")

    pv = kb.pasta("Válvulas de setor")
    for s, ids in enumerate(lay.setores):
        if not ids:
            continue
        l0 = min((lay.laterais[i] for i in ids), key=lambda l: l.linha)
        lon, lat = proj.geo(*l0.entrada_xy)
        kb.ponto(pv, f"Válvula setor {s + 1}", float(lon), float(lat), "valvula")

    ps = kb.pasta("Aspersores", visivel=lay.n_aspersores <= 6000)
    a = lay.todos_aspersores()
    lon, lat = proj.geo(a[:, 0], a[:, 1])
    for i, (x, y) in enumerate(zip(np.atleast_1d(lon), np.atleast_1d(lat))):
        kb.ponto(ps, f"A{i + 1}", float(x), float(y), "asp")

    if curvas:
        pc = kb.pasta("Curvas de nível", visivel=False)
        for c in curvas:
            kb.linha(pc, f"{c['cota']:.1f} m", c["coords"], "curva")
    return kb.kmz()


def dxf_projeto(lay, res=None, curvas_utm=None) -> bytes:
    """Desenho DXF (coordenadas UTM) com camadas separadas por elemento."""
    import ezdxf

    doc = ezdxf.new("R2010", setup=True)
    msp = doc.modelspace()
    camadas = {"AREA": 2, "LATERAIS": 5, "ASPERSORES": 4, "DERIVACAO": 30, "PRINCIPAL": 1, "ADUTORA": 6,
               "CAPTACAO": 3, "TEXTOS": 7, "CURVAS_NIVEL": 8}
    for nome, cor in camadas.items():
        doc.layers.add(nome, color=cor)
    msp.add_lwpolyline(list(lay.poligono.exterior.coords), dxfattribs={"layer": "AREA"}, close=True)
    for l in lay.laterais:
        pts = np.vstack([np.asarray(l.entrada_xy)[None, :], l.aspersores_xy])
        msp.add_lwpolyline([tuple(p) for p in pts], dxfattribs={"layer": "LATERAIS"})
        for p in l.aspersores_xy:
            msp.add_circle(tuple(p), 0.4, dxfattribs={"layer": "ASPERSORES"})
    if res is not None:
        for t in res.trechos:
            camada = {"adutora": "ADUTORA", "principal": "PRINCIPAL", "derivacao": "DERIVACAO"}[t.tipo]
            msp.add_lwpolyline(t.coords, dxfattribs={"layer": camada})
            c = np.asarray(t.coords).mean(axis=0)
            msp.add_text(f"{t.tubo.material} DN{t.tubo.dn} PN{t.tubo.pn_mca:.0f} L={t.comprimento:.0f}m",
                         dxfattribs={"layer": "TEXTOS", "height": 1.5}).set_placement(tuple(c))
    else:
        for d in lay.derivacoes:
            msp.add_lwpolyline(d["coords"], dxfattribs={"layer": "DERIVACAO"})
        if len(lay.principal) > 1:
            msp.add_lwpolyline(lay.principal, dxfattribs={"layer": "PRINCIPAL"})
        msp.add_lwpolyline(lay.adutora, dxfattribs={"layer": "ADUTORA"})
    msp.add_circle(lay.fonte_xy, 2.0, dxfattribs={"layer": "CAPTACAO"})
    msp.add_text("CAPTACAO", dxfattribs={"layer": "TEXTOS", "height": 2.0}).set_placement(
        (lay.fonte_xy[0] + 3, lay.fonte_xy[1]))
    for s, ids in enumerate(lay.setores):
        if ids:
            c = np.vstack([lay.laterais[i].aspersores_xy for i in ids]).mean(axis=0)
            msp.add_text(f"SETOR {s + 1}", dxfattribs={"layer": "TEXTOS", "height": 3.0}).set_placement(tuple(c))
    for c in curvas_utm or []:
        msp.add_lwpolyline(c["coords"], dxfattribs={"layer": "CURVAS_NIVEL"})
    buf = io.StringIO()
    doc.write(buf)
    return buf.getvalue().encode("utf-8")


def geojson_projeto(lay, res=None) -> str:
    proj = lay.proj
    feats = []
    xy = list(lay.poligono.exterior.coords)
    feats.append({"type": "Feature", "properties": {"tipo": "area", "area_ha": round(lay.area_ha, 3)},
                  "geometry": {"type": "Polygon", "coordinates": [linha_utm_para_lonlat(proj, xy)]}})
    for l in lay.laterais:
        pts = np.vstack([np.asarray(l.entrada_xy)[None, :], l.aspersores_xy])
        props = {"tipo": "lateral", "id": l.id + 1, "setor": l.setor + 1, "aspersores": l.n,
                 "comprimento_m": round(l.comprimento, 1)}
        if res is not None and l.id in res.laterais:
            props["tubo"] = res.laterais[l.id]["tubo"].rotulo
            props["pressao_entrada_mca"] = round(res.laterais[l.id]["res"].h_entrada, 2)
        feats.append({"type": "Feature", "properties": props,
                      "geometry": {"type": "LineString", "coordinates": linha_utm_para_lonlat(proj, pts)}})
        for p in l.aspersores_xy:
            lon, lat = proj.geo(*p)
            feats.append({"type": "Feature", "properties": {"tipo": "aspersor", "lateral": l.id + 1, "setor": l.setor + 1},
                          "geometry": {"type": "Point", "coordinates": [float(lon), float(lat)]}})
    if res is not None:
        for t in res.trechos:
            feats.append({"type": "Feature",
                          "properties": {"tipo": t.tipo, "id": t.id, "tubo": t.tubo.rotulo, "comprimento_m": round(t.comprimento, 1),
                                         "vazao_m3h": round(t.q_proj, 2), "velocidade_ms": round(t.v_proj, 2)},
                          "geometry": {"type": "LineString", "coordinates": linha_utm_para_lonlat(proj, t.coords)}})
    lon, lat = proj.geo(*lay.fonte_xy)
    feats.append({"type": "Feature", "properties": {"tipo": "captacao"},
                  "geometry": {"type": "Point", "coordinates": [float(lon), float(lat)]}})
    return json.dumps({"type": "FeatureCollection", "features": feats}, ensure_ascii=False)
