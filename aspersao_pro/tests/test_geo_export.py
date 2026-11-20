import json
import zipfile
import io

from aspersao import exportar, geo
from aspersao.pipeline import executar_tudo
from aspersao.projeto import abrir, exemplo_openirri_trigo, salvar


def test_epsg_sirgas_brasil():
    assert geo.epsg_utm(-47.9, -15.8) == 31983  # SIRGAS 2000 / UTM 23S
    assert geo.epsg_utm(-39.0, -14.8) == 31984  # 24S
    assert geo.epsg_utm(26.0, -32.5) == 32735  # fora do Brasil: WGS 84 / UTM 35S


def test_kml_ida_e_volta():
    pol = geo.retangulo_lonlat(-12.0, -45.0, 300, 200)
    kml = geo.kml_poligono_simples("Teste", pol).encode()
    fe = geo.ler_kml(kml)
    assert fe[0]["tipo"] == "Polygon" and len(fe[0]["coords"]) == 5
    a, _ = geo.area_perimetro(fe[0]["coords"])
    assert abs(a - 60000) < 50


def test_kml_google_earth_com_namespace_gx():
    kml = b"""<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2" xmlns:gx="http://www.google.com/kml/ext/2.2">
<Document><Placemark><name>Talhao 1</name><Polygon><outerBoundaryIs><LinearRing><coordinates>
-45.0,-12.0,0 -44.99,-12.0,0 -44.99,-12.01,0 -45.0,-12.0,0</coordinates></LinearRing></outerBoundaryIs></Polygon></Placemark>
<Placemark><name>Bomba</name><Point><coordinates>-45.001,-12.002,0</coordinates></Point></Placemark></Document></kml>"""
    fe = geo.ler_kml(kml)
    assert {f["tipo"] for f in fe} == {"Polygon", "Point"}
    assert fe[0]["nome"] == "Talhao 1"


def test_exportacoes_e_projeto_json():
    p = exemplo_openirri_trigo()
    r = executar_tudo(p)
    assert not r["erros"]
    lay, rede = r["layout"]["layout"], r["rede"]
    kmz = exportar.kmz_projeto("x", lay, rede, p["area"]["poligono"])
    with zipfile.ZipFile(io.BytesIO(kmz)) as z:
        assert "doc.kml" in z.namelist()
        assert geo.ler_kml(z.read("doc.kml"))
    assert exportar.dxf_projeto(lay, rede).startswith(b"  0\nSECTION") or b"SECTION" in exportar.dxf_projeto(lay, rede)[:200]
    gj = json.loads(exportar.geojson_projeto(lay, rede))
    assert len(gj["features"]) > lay.n_aspersores
    p2 = abrir(salvar(p))
    assert p2["area"]["poligono"] == p["area"]["poligono"]
