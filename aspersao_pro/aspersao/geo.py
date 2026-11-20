"""Geoprocessamento: projeção UTM (SIRGAS 2000 no Brasil), polígonos,
importação/exportação KML/KMZ (Google Earth), GeoJSON e DXF (CAD)."""

from __future__ import annotations

import io
import json
import math
import re
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass

import numpy as np
from pyproj import Transformer
from shapely.geometry import LineString, Point, Polygon, mapping


# ---------------------------------------------------------------------------
# Projeção
# ---------------------------------------------------------------------------
def epsg_utm(lon: float, lat: float) -> int:
    """EPSG do fuso UTM. No território brasileiro usa SIRGAS 2000 (EPSG 31972–31985)."""
    fuso = int(math.floor((lon + 180.0) / 6.0)) + 1
    no_brasil = -34.0 <= lat <= 5.5 and -74.5 <= lon <= -28.0
    if no_brasil:
        if lat < 0 and 18 <= fuso <= 25:
            return 31960 + fuso  # 31978 (18S) … 31985 (25S)
        if lat >= 0 and 18 <= fuso <= 22:
            return 31954 + fuso  # 31972 (18N) … 31976 (22N)
    return (32700 if lat < 0 else 32600) + fuso


@dataclass
class Projecao:
    epsg: int

    def __post_init__(self):
        self._para_utm = Transformer.from_crs(4326, self.epsg, always_xy=True)
        self._para_geo = Transformer.from_crs(self.epsg, 4326, always_xy=True)

    @classmethod
    def para_ponto(cls, lon, lat):
        return cls(epsg_utm(lon, lat))

    def utm(self, lon, lat):
        return self._para_utm.transform(lon, lat)

    def geo(self, x, y):
        return self._para_geo.transform(x, y)

    @property
    def nome(self):
        if 31960 < self.epsg < 31990:
            fuso = self.epsg - 31960 if self.epsg >= 31978 else self.epsg - 31954
            hemi = "S" if self.epsg >= 31978 else "N"
            return f"SIRGAS 2000 / UTM {fuso}{hemi} (EPSG:{self.epsg})"
        fuso = self.epsg % 100
        hemi = "S" if self.epsg >= 32700 else "N"
        return f"WGS 84 / UTM {fuso}{hemi} (EPSG:{self.epsg})"


def poligono_utm(coords_lonlat, proj: Projecao) -> Polygon:
    xs, ys = proj.utm(np.array([c[0] for c in coords_lonlat]), np.array([c[1] for c in coords_lonlat]))
    pol = Polygon(list(zip(xs, ys)))
    if not pol.is_valid:
        pol = pol.buffer(0)
        if pol.geom_type == "MultiPolygon":
            pol = max(pol.geoms, key=lambda g: g.area)
    return pol


def area_perimetro(coords_lonlat):
    if len(coords_lonlat) < 3:
        return 0.0, 0.0
    lon0 = float(np.mean([c[0] for c in coords_lonlat]))
    lat0 = float(np.mean([c[1] for c in coords_lonlat]))
    pol = poligono_utm(coords_lonlat, Projecao.para_ponto(lon0, lat0))
    return pol.area, pol.length


def retangulo_lonlat(lat_c, lon_c, comprimento_m, largura_m, azimute_graus=0.0):
    """Retângulo (lista lon/lat) centrado no ponto, comprimento no eixo L-O girado."""
    proj = Projecao.para_ponto(lon_c, lat_c)
    xc, yc = proj.utm(lon_c, lat_c)
    a = math.radians(azimute_graus)
    ux, uy = math.cos(a), math.sin(a)
    vx, vy = -uy, ux
    pts = []
    for su, sv in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
        x = xc + su * comprimento_m / 2 * ux + sv * largura_m / 2 * vx
        y = yc + su * comprimento_m / 2 * uy + sv * largura_m / 2 * vy
        pts.append(list(proj.geo(x, y)))
    pts.append(pts[0])
    return pts


def angulo_maior_lado(pol: Polygon) -> float:
    """Ângulo (graus, a partir do eixo leste, anti-horário) do maior lado do
    retângulo mínimo envolvente — orientação natural para as linhas laterais."""
    mrr = pol.minimum_rotated_rectangle
    coords = list(mrr.exterior.coords)
    melhor, ang = -1.0, 0.0
    for (x1, y1), (x2, y2) in zip(coords[:-1], coords[1:]):
        comp = math.hypot(x2 - x1, y2 - y1)
        if comp > melhor:
            melhor, ang = comp, math.degrees(math.atan2(y2 - y1, x2 - x1))
    return ang % 180.0


# ---------------------------------------------------------------------------
# KML / KMZ (Google Earth)
# ---------------------------------------------------------------------------
def _coords_kml(texto):
    pts = []
    for trio in re.split(r"\s+", (texto or "").strip()):
        if not trio:
            continue
        partes = trio.split(",")
        if len(partes) >= 2:
            try:
                pts.append([float(partes[0]), float(partes[1])])
            except ValueError:
                continue
    return pts


def ler_kml(conteudo: bytes, nome_arquivo: str = "") -> list[dict]:
    """Lê KML ou KMZ (Google Earth Pro) e retorna feições:
    [{'nome', 'tipo' ('Polygon'|'LineString'|'Point'), 'coords': [[lon, lat], ...]}]."""
    if nome_arquivo.lower().endswith(".kmz") or conteudo[:2] == b"PK":
        with zipfile.ZipFile(io.BytesIO(conteudo)) as z:
            kmls = [n for n in z.namelist() if n.lower().endswith(".kml")]
            if not kmls:
                raise ValueError("KMZ sem arquivo .kml interno.")
            conteudo = z.read("doc.kml" if "doc.kml" in kmls else kmls[0])
    texto = conteudo.decode("utf-8", errors="ignore")
    texto = re.sub(r'\sxmlns(:\w+)?="[^"]+"', "", texto, count=0)  # remove namespaces
    texto = re.sub(r"<(/?)\w+:", r"<\1", texto)  # remove prefixos (gx:, kml:)
    raiz = ET.fromstring(texto.encode("utf-8"))
    feicoes = []
    for pm in raiz.iter("Placemark"):
        nome_el = pm.find("name")
        nome = nome_el.text.strip() if nome_el is not None and nome_el.text else "Sem nome"
        for pol in pm.iter("Polygon"):
            outer = pol.find(".//outerBoundaryIs//coordinates")
            if outer is not None:
                feicoes.append({"nome": nome, "tipo": "Polygon", "coords": _coords_kml(outer.text)})
        for ls in pm.iter("LineString"):
            c = ls.find("coordinates")
            if c is not None:
                feicoes.append({"nome": nome, "tipo": "LineString", "coords": _coords_kml(c.text)})
        for pt in pm.iter("Point"):
            c = pt.find("coordinates")
            if c is not None:
                cc = _coords_kml(c.text)
                if cc:
                    feicoes.append({"nome": nome, "tipo": "Point", "coords": cc})
    return feicoes


def ler_geojson(conteudo: bytes) -> list[dict]:
    js = json.loads(conteudo.decode("utf-8", errors="ignore"))
    feats = js.get("features", [js] if js.get("type") == "Feature" else [])
    if js.get("type") in ("Polygon", "LineString", "Point"):
        feats = [{"type": "Feature", "geometry": js, "properties": {}}]
    out = []
    for f in feats:
        g = f.get("geometry") or {}
        nome = (f.get("properties") or {}).get("name", "Feição")
        t = g.get("type")
        if t == "Polygon":
            out.append({"nome": nome, "tipo": "Polygon", "coords": [list(c[:2]) for c in g["coordinates"][0]]})
        elif t == "MultiPolygon":
            out.append({"nome": nome, "tipo": "Polygon", "coords": [list(c[:2]) for c in g["coordinates"][0][0]]})
        elif t == "LineString":
            out.append({"nome": nome, "tipo": "LineString", "coords": [list(c[:2]) for c in g["coordinates"]]})
        elif t == "Point":
            out.append({"nome": nome, "tipo": "Point", "coords": [list(g["coordinates"][:2])]})
    return out


def _kml_cor(hex_rgb: str, alpha: int = 255) -> str:
    """'#RRGGBB' → 'AABBGGRR' (formato KML)."""
    h = hex_rgb.lstrip("#")
    return f"{alpha:02x}{h[4:6]}{h[2:4]}{h[0:2]}"


def _esc(txt) -> str:
    return (str(txt).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


class KMLBuilder:
    """Montagem simples de KML 2.2 com pastas e estilos."""

    def __init__(self, nome_documento: str):
        self.nome = nome_documento
        self.estilos = {}
        self.pastas = []  # (nome, [placemarks xml], visivel)

    def estilo(self, id_, cor_linha="#ffffff", largura=2.0, cor_pol=None, alpha_pol=80, icone=None, escala=0.6,
               cor_icone=None):
        partes = [f'<Style id="{id_}"><LineStyle><color>{_kml_cor(cor_linha)}</color><width>{largura}</width></LineStyle>']
        if cor_pol:
            partes.append(f"<PolyStyle><color>{_kml_cor(cor_pol, alpha_pol)}</color></PolyStyle>")
        else:
            partes.append("<PolyStyle><fill>0</fill></PolyStyle>")
        if icone:
            cor_i = f"<color>{_kml_cor(cor_icone)}</color>" if cor_icone else ""
            partes.append(f"<IconStyle>{cor_i}<scale>{escala}</scale><Icon><href>{icone}</href></Icon></IconStyle>"
                          "<LabelStyle><scale>0</scale></LabelStyle>")
        partes.append("</Style>")
        self.estilos[id_] = "".join(partes)

    def pasta(self, nome, visivel=True):
        self.pastas.append((nome, [], visivel))
        return self.pastas[-1][1]

    @staticmethod
    def _desc(desc: dict | str | None):
        if not desc:
            return ""
        if isinstance(desc, dict):
            linhas = "".join(f"<tr><td><b>{_esc(k)}</b></td><td>{_esc(v)}</td></tr>" for k, v in desc.items())
            return f"<description><![CDATA[<table>{linhas}</table>]]></description>"
        return f"<description><![CDATA[{desc}]]></description>"

    def poligono(self, lista, nome, coords, estilo, desc=None):
        c = " ".join(f"{x:.8f},{y:.8f},0" for x, y in coords)
        lista.append(f"<Placemark><name>{_esc(nome)}</name>{self._desc(desc)}<styleUrl>#{estilo}</styleUrl>"
                     f"<Polygon><tessellate>1</tessellate><outerBoundaryIs><LinearRing><coordinates>{c}</coordinates>"
                     f"</LinearRing></outerBoundaryIs></Polygon></Placemark>")

    def linha(self, lista, nome, coords, estilo, desc=None):
        c = " ".join(f"{x:.8f},{y:.8f},0" for x, y in coords)
        lista.append(f"<Placemark><name>{_esc(nome)}</name>{self._desc(desc)}<styleUrl>#{estilo}</styleUrl>"
                     f"<LineString><tessellate>1</tessellate><coordinates>{c}</coordinates></LineString></Placemark>")

    def ponto(self, lista, nome, lon, lat, estilo, desc=None):
        lista.append(f"<Placemark><name>{_esc(nome)}</name>{self._desc(desc)}<styleUrl>#{estilo}</styleUrl>"
                     f"<Point><coordinates>{lon:.8f},{lat:.8f},0</coordinates></Point></Placemark>")

    def xml(self) -> str:
        corpo = [f'<?xml version="1.0" encoding="UTF-8"?><kml xmlns="http://www.opengis.net/kml/2.2"><Document>'
                 f"<name>{_esc(self.nome)}</name>"]
        corpo += self.estilos.values()
        for nome, itens, vis in self.pastas:
            corpo.append(f"<Folder><name>{_esc(nome)}</name><visibility>{1 if vis else 0}</visibility>")
            corpo += itens
            corpo.append("</Folder>")
        corpo.append("</Document></kml>")
        return "".join(corpo)

    def kmz(self) -> bytes:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("doc.kml", self.xml())
        return buf.getvalue()


def kml_poligono_simples(nome, coords_lonlat) -> str:
    kb = KMLBuilder(nome)
    kb.estilo("area", "#ffd400", 3, "#ffd400", 40)
    pasta = kb.pasta("Área")
    kb.poligono(pasta, nome, coords_lonlat, "area")
    return kb.xml()


def geojson_feature(geom, props: dict):
    return {"type": "Feature", "geometry": mapping(geom), "properties": props}


def linha_utm_para_lonlat(proj: Projecao, coords_xy):
    xs = np.array([c[0] for c in coords_xy])
    ys = np.array([c[1] for c in coords_xy])
    lon, lat = proj.geo(xs, ys)
    return [[float(a), float(b)] for a, b in zip(np.atleast_1d(lon), np.atleast_1d(lat))]


def distancia_ponto_poligono(pt_xy, pol: Polygon) -> float:
    return Point(pt_xy).distance(pol)


def comprimento_linha(coords_xy) -> float:
    return LineString(coords_xy).length if len(coords_xy) >= 2 else 0.0
