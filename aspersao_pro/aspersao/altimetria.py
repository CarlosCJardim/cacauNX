"""Altimetria: obtenção de cotas (APIs de MDE, Google, Earth Engine, GeoTIFF,
levantamento topográfico), modelo digital de elevação em grade, declividade,
curvas de nível e perfis longitudinais.

O MDE é armazenado no projeto como grade regular em lon/lat:
``{"lon": [...], "lat": [...], "z": [[...]], "fonte": str}`` (z[i_lat][j_lon]).
"""

from __future__ import annotations

import io
import math
import time

import numpy as np
import requests
from scipy.interpolate import RegularGridInterpolator, griddata

from .clima.fontes import CABECALHO_HTTP, ErroFonteDados

PROVEDORES = {
    "open_meteo": "Open-Meteo — Copernicus DEM GLO-90 (90 m, sem chave)",
    "opentopodata_srtm30m": "OpenTopoData — SRTM 30 m (sem chave, 1 req/s)",
    "opentopodata_aster30m": "OpenTopoData — ASTER GDEM 30 m",
    "opentopodata_mapzen": "OpenTopoData — Mapzen (fusão de MDEs)",
    "open_elevation": "Open-Elevation — SRTM (sem chave)",
    "google": "Google Maps Elevation API (requer chave)",
    "gee": "Google Earth Engine — SRTM/NASADEM/Copernicus 30 m (requer conta)",
}


def _lotes(seq, n):
    for i in range(0, len(seq), n):
        yield seq[i:i + n]


def cotas_open_meteo(lats, lons):
    out = []
    for lote in _lotes(list(zip(lats, lons)), 100):
        params = {"latitude": ",".join(f"{a:.6f}" for a, _ in lote),
                  "longitude": ",".join(f"{b:.6f}" for _, b in lote)}
        try:
            r = requests.get("https://api.open-meteo.com/v1/elevation", params=params, timeout=30,
                             headers=CABECALHO_HTTP)
            r.raise_for_status()
        except requests.RequestException as exc:
            raise ErroFonteDados(f"Open-Meteo (altimetria) indisponível: {exc}") from exc
        out += r.json()["elevation"]
    return np.asarray(out, dtype=float)


def cotas_opentopodata(lats, lons, dataset="srtm30m"):
    out = []
    lotes = list(_lotes(list(zip(lats, lons)), 100))
    for i, lote in enumerate(lotes):
        loc = "|".join(f"{a:.6f},{b:.6f}" for a, b in lote)
        try:
            r = requests.get(f"https://api.opentopodata.org/v1/{dataset}",
                             params={"locations": loc, "interpolation": "bilinear"}, timeout=40,
                             headers=CABECALHO_HTTP)
            r.raise_for_status()
        except requests.RequestException as exc:
            raise ErroFonteDados(f"OpenTopoData indisponível: {exc}") from exc
        js = r.json()
        if js.get("status") != "OK":
            raise ErroFonteDados(f"OpenTopoData: {js.get('error', js)}")
        out += [res["elevation"] if res["elevation"] is not None else np.nan for res in js["results"]]
        if i < len(lotes) - 1:
            time.sleep(1.05)  # limite de 1 requisição por segundo
    return np.asarray(out, dtype=float)


def cotas_open_elevation(lats, lons):
    out = []
    for lote in _lotes(list(zip(lats, lons)), 200):
        corpo = {"locations": [{"latitude": a, "longitude": b} for a, b in lote]}
        try:
            r = requests.post("https://api.open-elevation.com/api/v1/lookup", json=corpo, timeout=60,
                              headers=CABECALHO_HTTP)
            r.raise_for_status()
        except requests.RequestException as exc:
            raise ErroFonteDados(f"Open-Elevation indisponível: {exc}") from exc
        out += [res["elevation"] for res in r.json()["results"]]
    return np.asarray(out, dtype=float)


def cotas_google(lats, lons, chave: str):
    """Google Maps Elevation API (até 512 pontos por requisição)."""
    if not chave:
        raise ErroFonteDados("Informe a chave da Google Maps Platform (Elevation API habilitada).")
    out = []
    for lote in _lotes(list(zip(lats, lons)), 200):
        loc = "|".join(f"{a:.6f},{b:.6f}" for a, b in lote)
        try:
            r = requests.get("https://maps.googleapis.com/maps/api/elevation/json",
                             params={"locations": loc, "key": chave}, timeout=40)
            r.raise_for_status()
        except requests.RequestException as exc:
            raise ErroFonteDados(f"Google Elevation API indisponível: {exc}") from exc
        js = r.json()
        if js.get("status") != "OK":
            raise ErroFonteDados(f"Google Elevation API: {js.get('status')} — {js.get('error_message', '')}")
        out += [res["elevation"] for res in js["results"]]
    return np.asarray(out, dtype=float)


def cotas_earth_engine(lats, lons, projeto_gee: str = "", produto: str = "USGS/SRTMGL1_003"):
    """Amostra um MDE no Google Earth Engine. Requer ``earthengine-api`` instalado e
    autenticado (``earthengine authenticate``) e um projeto Cloud habilitado."""
    try:
        import ee  # type: ignore
    except ImportError as exc:
        raise ErroFonteDados("Pacote 'earthengine-api' não instalado (pip install earthengine-api).") from exc
    try:
        if projeto_gee:
            ee.Initialize(project=projeto_gee)
        else:
            ee.Initialize()
    except Exception as exc:  # noqa: BLE001
        raise ErroFonteDados(f"Falha ao iniciar o Earth Engine: {exc}") from exc
    if produto.startswith("COPERNICUS"):
        img = ee.ImageCollection(produto).select("DEM").mosaic()
    elif produto.startswith("NASA/NASADEM"):
        img = ee.Image(produto).select("elevation")
    else:
        img = ee.Image(produto).select("elevation")
    out = []
    for lote in _lotes(list(zip(lats, lons)), 4000):
        fc = ee.FeatureCollection([ee.Feature(ee.Geometry.Point([b, a]), {"i": i}) for i, (a, b) in enumerate(lote)])
        res = img.reduceRegions(collection=fc, reducer=ee.Reducer.first(), scale=30).getInfo()
        vals = {f["properties"]["i"]: f["properties"].get("first") for f in res["features"]}
        out += [vals.get(i, np.nan) if vals.get(i) is not None else np.nan for i in range(len(lote))]
    return np.asarray(out, dtype=float)


def cotas_geotiff(conteudo: bytes, lats, lons):
    """Amostra um MDE GeoTIFF enviado pelo usuário (qualquer SRC) nos pontos lon/lat."""
    try:
        import rasterio
        from rasterio.io import MemoryFile
        from rasterio.warp import transform as warp_transform
    except ImportError as exc:
        raise ErroFonteDados("Pacote 'rasterio' necessário para ler GeoTIFF.") from exc
    with MemoryFile(conteudo) as mem, mem.open() as ds:
        xs, ys = warp_transform("EPSG:4326", ds.crs, list(lons), list(lats))
        vals = np.array([v[0] for v in ds.sample(zip(xs, ys))], dtype=float)
        if ds.nodata is not None:
            vals[vals == ds.nodata] = np.nan
    return vals


def obter_cotas(provedor: str, lats, lons, chave_google: str = "", projeto_gee: str = "",
                produto_gee: str = "USGS/SRTMGL1_003", geotiff: bytes | None = None):
    lats = list(map(float, lats))
    lons = list(map(float, lons))
    if provedor == "open_meteo":
        return cotas_open_meteo(lats, lons)
    if provedor.startswith("opentopodata_"):
        return cotas_opentopodata(lats, lons, provedor.split("_", 1)[1])
    if provedor == "open_elevation":
        return cotas_open_elevation(lats, lons)
    if provedor == "google":
        return cotas_google(lats, lons, chave_google)
    if provedor == "gee":
        return cotas_earth_engine(lats, lons, projeto_gee, produto_gee)
    if provedor == "geotiff":
        return cotas_geotiff(geotiff, lats, lons)
    raise ValueError(f"Provedor desconhecido: {provedor}")


# ---------------------------------------------------------------------------
# Grade (MDE)
# ---------------------------------------------------------------------------
def grade_amostragem(coords_lonlat, n: int = 15, margem: float = 0.12, extras=()):
    """Grade regular lon/lat cobrindo o polígono (e pontos extras, ex.: captação)."""
    lons = [c[0] for c in coords_lonlat] + [e[0] for e in extras if e]
    lats = [c[1] for c in coords_lonlat] + [e[1] for e in extras if e]
    lo0, lo1, la0, la1 = min(lons), max(lons), min(lats), max(lats)
    dlo, dla = (lo1 - lo0) * margem + 1e-4, (la1 - la0) * margem + 1e-4
    glon = np.linspace(lo0 - dlo, lo1 + dlo, n)
    glat = np.linspace(la0 - dla, la1 + dla, n)
    return glon, glat


def montar_mde(glon, glat, valores, fonte: str) -> dict:
    z = np.asarray(valores, dtype=float).reshape(len(glat), len(glon))
    if np.isnan(z).any():
        # preenche falhas por vizinho mais próximo
        LON, LAT = np.meshgrid(glon, glat)
        ok = ~np.isnan(z)
        z = griddata((LON[ok], LAT[ok]), z[ok], (LON, LAT), method="nearest")
    return {"lon": [float(v) for v in glon], "lat": [float(v) for v in glat],
            "z": [[round(float(v), 2) for v in linha] for linha in z], "fonte": fonte}


def mde_de_pontos(lons, lats, zs, coords_lonlat=None, n: int = 40, metodo="cubic", fonte="Levantamento topográfico"):
    """Interpola pontos de levantamento (GNSS/estação total) para a grade do MDE."""
    lons = np.asarray(lons, dtype=float)
    lats = np.asarray(lats, dtype=float)
    zs = np.asarray(zs, dtype=float)
    base = coords_lonlat if coords_lonlat else list(zip(lons, lats))
    glon, glat = grade_amostragem(base, n, margem=0.02)
    LON, LAT = np.meshgrid(glon, glat)
    z = griddata((lons, lats), zs, (LON, LAT), method=metodo)
    z_nn = griddata((lons, lats), zs, (LON, LAT), method="nearest")
    z = np.where(np.isnan(z), z_nn, z)
    return montar_mde(glon, glat, z.ravel(), fonte)


def mde_sintetico(coords_lonlat, cota_base=500.0, declividade_pct=2.0, direcao_graus=45.0, ondulacao_m=3.0,
                  n: int = 25, extras=()):
    """Terreno sintético para DEMONSTRAÇÃO (rampa + ondulação suave).
    Não use em projetos reais — substitua por altimetria real."""
    from .geo import Projecao

    glon, glat = grade_amostragem(coords_lonlat, n, extras=extras)
    lon0, lat0 = float(np.mean(glon)), float(np.mean(glat))
    proj = Projecao.para_ponto(lon0, lat0)
    LON, LAT = np.meshgrid(glon, glat)
    X, Y = proj.utm(LON, LAT)
    x0, y0 = proj.utm(lon0, lat0)
    a = math.radians(direcao_graus)
    s = declividade_pct / 100.0
    dist = (X - x0) * math.cos(a) + (Y - y0) * math.sin(a)
    larg = max(float(np.ptp(X)), float(np.ptp(Y)), 1.0)
    z = cota_base - s * dist + ondulacao_m * np.sin(2 * np.pi * (X - x0) / larg) * np.cos(np.pi * (Y - y0) / larg)
    return montar_mde(glon, glat, z.ravel(), "Terreno sintético (demonstração)")


class ModeloElevacao:
    """Interpolador do MDE em coordenadas UTM do projeto."""

    def __init__(self, mde: dict, proj):
        self.mde = mde
        self.proj = proj
        self.lon = np.asarray(mde["lon"], dtype=float)
        self.lat = np.asarray(mde["lat"], dtype=float)
        self.z = np.asarray(mde["z"], dtype=float)
        metodo = "cubic" if min(len(self.lon), len(self.lat)) >= 4 else "linear"
        self._interp = RegularGridInterpolator((self.lat, self.lon), self.z, method=metodo,
                                               bounds_error=False, fill_value=None)

    def cota_lonlat(self, lon, lat):
        lon = np.atleast_1d(np.asarray(lon, dtype=float))
        lat = np.atleast_1d(np.asarray(lat, dtype=float))
        lat_c = np.clip(lat, self.lat.min(), self.lat.max())
        lon_c = np.clip(lon, self.lon.min(), self.lon.max())
        return self._interp(np.column_stack([lat_c, lon_c]))

    def cota(self, x, y):
        lon, lat = self.proj.geo(np.atleast_1d(x), np.atleast_1d(y))
        return self.cota_lonlat(lon, lat)

    def grade_utm(self, n=80):
        """Grade fina em UTM para mapas e curvas de nível."""
        glon = np.linspace(self.lon.min(), self.lon.max(), n)
        glat = np.linspace(self.lat.min(), self.lat.max(), n)
        LON, LAT = np.meshgrid(glon, glat)
        Z = self.cota_lonlat(LON.ravel(), LAT.ravel()).reshape(LON.shape)
        X, Y = self.proj.utm(LON, LAT)
        return LON, LAT, X, Y, Z


class ElevacaoUniforme:
    """Terreno plano ou com declividade uniforme (quando não há MDE)."""

    def __init__(self, cota_ref, x_ref, y_ref, declividade_pct=0.0, direcao_graus=0.0):
        self.cota_ref = cota_ref
        self.x_ref, self.y_ref = x_ref, y_ref
        self.s = declividade_pct / 100.0
        a = math.radians(direcao_graus)  # direção de DESCIDA (a partir do leste, anti-horário)
        self.ux, self.uy = math.cos(a), math.sin(a)

    def cota(self, x, y):
        x = np.atleast_1d(np.asarray(x, dtype=float))
        y = np.atleast_1d(np.asarray(y, dtype=float))
        return self.cota_ref - self.s * ((x - self.x_ref) * self.ux + (y - self.y_ref) * self.uy)


def ajuste_plano(X, Y, Z, mascara=None):
    """Plano médio z = a + b·x + c·y por mínimos quadrados.
    Retorna declividade (%), direção de descida (graus a partir do leste) e direção das curvas de nível."""
    x = np.asarray(X, dtype=float).ravel()
    y = np.asarray(Y, dtype=float).ravel()
    z = np.asarray(Z, dtype=float).ravel()
    if mascara is not None:
        m = np.asarray(mascara).ravel()
        x, y, z = x[m], y[m], z[m]
    x0, y0 = x.mean(), y.mean()
    A = np.column_stack([np.ones_like(x), x - x0, y - y0])
    (a, b, c), *_ = np.linalg.lstsq(A, z, rcond=None)
    decl = math.hypot(b, c) * 100.0
    descida = math.degrees(math.atan2(-c, -b)) % 360.0
    curva = (descida + 90.0) % 180.0
    return {"declividade_pct": decl, "direcao_descida_graus": descida, "direcao_curva_nivel_graus": curva,
            "cota_media": float(a)}


def declividade_grade(X, Y, Z):
    """Declividade local (%) por diferenças finitas na grade UTM."""
    dy = np.gradient(Y, axis=0)
    dx = np.gradient(X, axis=1)
    dzdy = np.gradient(Z, axis=0) / np.where(dy == 0, 1e-9, dy)
    dzdx = np.gradient(Z, axis=1) / np.where(dx == 0, 1e-9, dx)
    return np.hypot(dzdx, dzdy) * 100.0


def curvas_de_nivel(LON, LAT, Z, equidistancia=1.0):
    """Linhas de curva de nível em lon/lat: [{'cota': z, 'coords': [[lon, lat], ...]}]."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    zmin, zmax = float(np.nanmin(Z)), float(np.nanmax(Z))
    if zmax - zmin < 1e-6:
        return []
    niveis = np.arange(math.ceil(zmin / equidistancia) * equidistancia, zmax, equidistancia)
    if len(niveis) == 0:
        return []
    fig, ax = plt.subplots()
    cs = ax.contour(LON, LAT, Z, levels=niveis)
    linhas = []
    for nivel, segs in zip(cs.levels, cs.allsegs):
        for seg in segs:
            if len(seg) >= 2:
                linhas.append({"cota": float(nivel), "coords": [[float(p[0]), float(p[1])] for p in seg]})
    plt.close(fig)
    return linhas


def perfil_ao_longo(coords_xy, elev, passo=10.0):
    """Perfil longitudinal ao longo de uma polilinha (UTM). Retorna (distâncias, cotas, xs, ys)."""
    pts = np.asarray(coords_xy, dtype=float)
    dist_seg = np.hypot(np.diff(pts[:, 0]), np.diff(pts[:, 1]))
    acum = np.concatenate([[0.0], np.cumsum(dist_seg)])
    total = acum[-1]
    if total <= 0:
        z = elev.cota(pts[:1, 0], pts[:1, 1])
        return np.array([0.0]), z, pts[:1, 0], pts[:1, 1]
    s = np.linspace(0.0, total, max(2, int(total / passo) + 1))
    xs = np.interp(s, acum, pts[:, 0])
    ys = np.interp(s, acum, pts[:, 1])
    return s, elev.cota(xs, ys), xs, ys


def pontos_notaveis(dist, cotas, tolerancia=0.3):
    """Pontos altos (ventosas) e baixos (descargas) em um perfil."""
    altos, baixos = [], []
    z = np.asarray(cotas, dtype=float)
    for i in range(1, len(z) - 1):
        if z[i] >= z[i - 1] and z[i] > z[i + 1] and (z[i] - min(z[max(0, i - 5):i + 6])) >= tolerancia:
            altos.append(i)
        if z[i] <= z[i - 1] and z[i] < z[i + 1] and (max(z[max(0, i - 5):i + 6]) - z[i]) >= tolerancia:
            baixos.append(i)
    return altos, baixos


def imagem_mde_png(Z, cmap="terrain", alpha=0.65) -> bytes:
    """Imagem PNG colorida do MDE (para sobreposição no mapa)."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig = plt.figure(figsize=(6, 6), dpi=100)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.imshow(np.flipud(Z), cmap=cmap, alpha=alpha, interpolation="bilinear", aspect="auto")
    ax.axis("off")
    buf = io.BytesIO()
    fig.savefig(buf, format="png", transparent=True)
    plt.close(fig)
    return buf.getvalue()
