"""Mapas interativos (folium) com imagens de satélite do Google Earth/Google Maps,
Esri World Imagery e camadas topográficas."""

from __future__ import annotations

import base64

import folium
import numpy as np
from folium import plugins

from aspersao.geo import linha_utm_para_lonlat

from .graficos import CAT, ordinal

CAMADAS = {
    "Google Satélite (Google Earth)": ("https://mt1.google.com/vt/lyrs=s&x={x}&y={y}&z={z}", "Imagens © Google"),
    "Google Híbrido": ("https://mt1.google.com/vt/lyrs=y&x={x}&y={y}&z={z}", "Imagens © Google"),
    "Google Terreno": ("https://mt1.google.com/vt/lyrs=p&x={x}&y={y}&z={z}", "© Google"),
    "Esri World Imagery": ("https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
                           "Tiles © Esri — Maxar, Earthstar Geographics"),
    "OpenTopoMap (curvas)": ("https://{s}.tile.opentopomap.org/{z}/{x}/{y}.png", "© OpenTopoMap (CC-BY-SA)"),
    "OpenStreetMap": ("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", "© OpenStreetMap"),
}


def mapa_base(centro, zoom=15, desenho=True, camada_inicial="Google Híbrido"):
    m = folium.Map(location=centro, zoom_start=zoom, max_zoom=21, tiles=None, control_scale=True)
    ordem = [camada_inicial] + [c for c in CAMADAS if c != camada_inicial]
    for nome in ordem:
        url, attr = CAMADAS[nome]
        folium.TileLayer(tiles=url, attr=attr, name=nome, max_zoom=21, max_native_zoom=20 if "Google" in nome else 19,
                         overlay=False, control=True).add_to(m)
    plugins.Fullscreen(position="topleft", title="Tela cheia", title_cancel="Sair").add_to(m)
    plugins.MeasureControl(position="topleft", primary_length_unit="meters", secondary_length_unit="kilometers",
                           primary_area_unit="hectares", secondary_area_unit="sqmeters").add_to(m)
    plugins.MousePosition(position="bottomright", separator=" | ", prefix="Lat/Lon:", num_digits=6).add_to(m)
    plugins.Geocoder(position="topright", collapsed=True, add_marker=False).add_to(m)
    if desenho:
        plugins.Draw(
            export=False, position="topleft",
            draw_options={"polyline": {"shapeOptions": {"color": CAT[6], "weight": 4}},
                          "polygon": {"allowIntersection": False, "showArea": True,
                                      "shapeOptions": {"color": "#ffd400", "weight": 3}},
                          "rectangle": {"shapeOptions": {"color": "#ffd400", "weight": 3}},
                          "circle": False, "circlemarker": False, "marker": True},
            edit_options={"edit": True, "remove": True},
        ).add_to(m)
    return m


def adicionar_area(m, poligono, fonte=None, rota=None):
    if poligono and len(poligono) >= 4:
        folium.Polygon([(c[1], c[0]) for c in poligono], color="#ffd400", weight=3, fill=True, fill_opacity=0.08,
                       tooltip="Área do projeto").add_to(m)
    if rota and len(rota) >= 2:
        folium.PolyLine([(c[1], c[0]) for c in rota], color=CAT[6], weight=4, dash_array="6,6",
                        tooltip="Rota da adutora").add_to(m)
    if fonte:
        folium.Marker((fonte[1], fonte[0]), tooltip="Captação / casa de bomba",
                      icon=folium.Icon(color="blue", icon="tint", prefix="fa")).add_to(m)


def adicionar_layout(m, lay, res=None, mostrar_aspersores=True):
    proj = lay.proj
    n = max(len(lay.setores), 1)
    grupo_lat = folium.FeatureGroup(name="Linhas laterais (por setor)", show=True)
    for l in lay.laterais:
        pts = np.vstack([np.asarray(l.entrada_xy)[None, :], l.aspersores_xy])
        ll = linha_utm_para_lonlat(proj, pts)
        cor = ordinal(n, l.setor) if l.setor >= 0 else "#ffffff"
        dica = f"Lateral {l.id + 1} · setor {l.setor + 1} · {l.n} aspersores · {l.comprimento:.0f} m"
        if res is not None and l.id in res.laterais:
            r = res.laterais[l.id]
            dica += f"<br>{r['tubo'].rotulo}<br>Pin {r['res'].h_entrada:.1f} mca · ΔP {r['res'].var_pressao_pct:.1f}%"
        folium.PolyLine([(b, a) for a, b in ll], color=cor, weight=2, opacity=0.95, tooltip=dica).add_to(grupo_lat)
    grupo_lat.add_to(m)
    if mostrar_aspersores:
        grupo_asp = folium.FeatureGroup(name="Aspersores", show=True)
        a = lay.todos_aspersores()
        lon, lat = proj.geo(a[:, 0], a[:, 1])
        feats = [{"type": "Feature", "geometry": {"type": "Point", "coordinates": [float(x), float(y)]},
                  "properties": {}} for x, y in zip(np.atleast_1d(lon), np.atleast_1d(lat))]
        folium.GeoJson({"type": "FeatureCollection", "features": feats},
                       marker=folium.CircleMarker(radius=2, color="#ffffff", weight=1, fill=True, fill_color="#0b0b0b",
                                                  fill_opacity=1)).add_to(grupo_asp)
        grupo_asp.add_to(m)
    grupo_rede = folium.FeatureGroup(name="Adutora, principal e derivações", show=True)
    if res is not None:
        for t in res.trechos:
            ll = linha_utm_para_lonlat(proj, t.coords)
            cor = {"adutora": CAT[6], "principal": CAT[7], "derivacao": CAT[1]}[t.tipo]
            folium.PolyLine([(b, a) for a, b in ll], color=cor, weight=3 + t.tubo.di_mm / 60,
                            tooltip=f"{t.tipo.capitalize()} {t.id}: {t.tubo.rotulo}<br>Q={t.q_proj:.1f} m³/h · "
                                    f"v={t.v_proj:.2f} m/s · L={t.comprimento:.0f} m").add_to(grupo_rede)
    else:
        for d in lay.derivacoes:
            ll = linha_utm_para_lonlat(proj, d["coords"])
            folium.PolyLine([(b, a) for a, b in ll], color=CAT[1], weight=4, tooltip="Derivação").add_to(grupo_rede)
        for coords, cor, nome in ((lay.principal, CAT[7], "Linha principal"), (lay.adutora, CAT[6], "Adutora")):
            if len(coords) > 1:
                ll = linha_utm_para_lonlat(proj, coords)
                folium.PolyLine([(b, a) for a, b in ll], color=cor, weight=5, tooltip=nome).add_to(grupo_rede)
    grupo_rede.add_to(m)


def adicionar_curvas(m, curvas, mestre=5.0):
    g = folium.FeatureGroup(name="Curvas de nível", show=True)
    for c in curvas:
        principal = abs(c["cota"] / mestre - round(c["cota"] / mestre)) < 1e-6
        folium.PolyLine([(p[1], p[0]) for p in c["coords"]], color="#fff3b0" if principal else "#ffffff",
                        weight=2.2 if principal else 1.0, opacity=0.9, tooltip=f"Cota {c['cota']:.1f} m").add_to(g)
    g.add_to(m)


def adicionar_imagem_mde(m, png: bytes, lon, lat):
    url = "data:image/png;base64," + base64.b64encode(png).decode()
    folium.raster_layers.ImageOverlay(url, bounds=[[min(lat), min(lon)], [max(lat), max(lon)]], opacity=0.55,
                                      name="Modelo digital de elevação", show=False).add_to(m)


def finalizar(m):
    folium.LayerControl(position="topright", collapsed=True).add_to(m)
    return m
