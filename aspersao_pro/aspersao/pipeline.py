"""Encadeamento reativo de todas as etapas do projeto, com cache por etapa.

Cada etapa declara de quais seções do projeto e de quais outras etapas depende;
a chave de cache é o hash dessas entradas. Assim, alterar a cultura recalcula
apenas a necessidade hídrica e o que vem depois — nunca o clima ou a altimetria.
"""

from __future__ import annotations

import hashlib
import json
import math

import numpy as np
import pandas as pd

from . import altimetria as alt
from . import aspersores as asp_mod
from . import bomba as bmb
from . import custos as cst
from . import cultura as cult
from . import geo
from . import hidraulica as hid
from . import layout as lay_mod
from . import manejo as mnj
from . import necessidade as nec
from . import operacao as op_mod
from . import rede as rede_mod
from . import tubos as tub
from . import uniformidade as uni
from .clima import estatistica as est
from .clima import penman as pm
from .projeto import json_para_df
from .unidades import KPA_POR_MCA

DEPENDENCIAS = {
    "geo": (["area"], []),
    "elev": (["altimetria"], ["geo"]),
    "clima": (["clima"], ["geo"]),
    "kc": (["cultura"], ["clima"]),
    "aspersor": (["aspersor", "agronomico"], ["clima"]),
    "agronomico": (["agronomico"], ["kc", "aspersor", "geo"]),
    "layout": (["layout", "hidraulica"], ["geo", "elev", "aspersor"]),
    "operacao": (["operacao"], ["agronomico", "layout"]),
    "rede": (["hidraulica", "bomba", "custos"], ["operacao"]),
    "bomba": (["bomba"], ["rede"]),
    "custos": (["custos"], ["bomba"]),
}


class ErroEtapa(RuntimeError):
    """Dados insuficientes para uma etapa (mensagem amigável para a interface)."""


class Pipeline:
    def __init__(self, projeto: dict, cache: dict | None = None):
        self.p = projeto
        self.cache = cache if cache is not None else {}
        self._chaves = {}

    # ----------------------------------------------------------------- cache
    def chave(self, etapa):
        if etapa in self._chaves:
            return self._chaves[etapa]
        secoes, deps = DEPENDENCIAS[etapa]
        conteudo = {s: self.p.get(s) for s in secoes}
        conteudo["_deps"] = [self.chave(d) for d in deps]
        h = hashlib.sha1(json.dumps(conteudo, sort_keys=True, default=str).encode()).hexdigest()
        self._chaves[etapa] = h
        return h

    def get(self, etapa):
        k = self.chave(etapa)
        item = self.cache.get(etapa)
        if item and item[0] == k:
            return item[1]
        valor = getattr(self, f"_calc_{etapa}")()
        self.cache[etapa] = (k, valor)
        return valor

    def tentar(self, etapa):
        try:
            return self.get(etapa), None
        except ErroEtapa as exc:
            return None, str(exc)

    # ----------------------------------------------------------------- etapas
    def _calc_geo(self):
        a = self.p["area"]
        pol = a.get("poligono") or []
        if len(pol) >= 4:
            lon0 = float(np.mean([c[0] for c in pol[:-1]]))
            lat0 = float(np.mean([c[1] for c in pol[:-1]]))
        else:
            lat0, lon0 = a.get("centro", [-15.79, -47.88])
        proj = geo.Projecao.para_ponto(lon0, lat0)
        pol_utm = geo.poligono_utm(pol, proj) if len(pol) >= 4 else None
        fonte_xy = proj.utm(*a["fonte"]) if a.get("fonte") else None
        rota = [proj.utm(*c) for c in a.get("rota_adutora") or []]
        return {"proj": proj, "pol_utm": pol_utm, "fonte_xy": fonte_xy, "lat": lat0, "lon": lon0, "rota": rota,
                "area_ha": pol_utm.area / 1e4 if pol_utm is not None else 0.0}

    def _calc_elev(self):
        g = self.get("geo")
        al = self.p["altimetria"]
        if al["modo"] == "mde" and al.get("mde"):
            m = alt.ModeloElevacao(al["mde"], g["proj"])
            info = {"tipo": "MDE", "fonte": al["mde"].get("fonte", "")}
            if g["pol_utm"] is not None:
                LON, LAT, X, Y, Z = m.grade_utm(60)
                from shapely.geometry import Point
                from shapely.prepared import prep
                pp = prep(g["pol_utm"])
                mask = np.array([pp.contains(Point(x, y)) for x, y in zip(X.ravel(), Y.ravel())]).reshape(X.shape)
                if mask.sum() >= 3:
                    info.update(alt.ajuste_plano(X, Y, Z, mask))
                    zin = Z[mask]
                    info.update({"cota_min": float(zin.min()), "cota_max": float(zin.max())})
            return m, info
        ref_xy = g["pol_utm"].centroid.coords[0] if g["pol_utm"] is not None else (0.0, 0.0)
        e = alt.ElevacaoUniforme(al["cota_referencia"], ref_xy[0], ref_xy[1], al["declividade_pct"],
                                 (90.0 - al["direcao_graus"]) % 360.0)
        info = {"tipo": "Uniforme", "declividade_pct": al["declividade_pct"],
                "direcao_descida_graus": (90.0 - al["direcao_graus"]) % 360.0,
                "direcao_curva_nivel_graus": ((90.0 - al["direcao_graus"]) + 90.0) % 180.0,
                "cota_media": al["cota_referencia"], "fonte": "Terreno plano/declividade uniforme"}
        return e, info

    def _calc_clima(self):
        c = self.p["clima"]
        g = self.get("geo")
        lat = c.get("lat") if c.get("lat") is not None else g["lat"]
        z = c.get("altitude") if c.get("altitude") is not None else self.p["altimetria"]["cota_referencia"]
        n = c["normais"]
        arr = lambda k: np.array([np.nan if v is None else float(v) for v in n.get(k, [None] * 12)])  # noqa: E731
        diario = None
        if c["modo"] == "diario":
            diario = json_para_df(c.get("diario"))
            if diario is None or diario.empty:
                raise ErroEtapa("Carregue uma série climática diária (NASA POWER, Open-Meteo ou arquivo).")
            d = pm.et0_diario_df(diario, lat, z, c.get("krs", 0.16))
            if c.get("metodo_eto_diario") == "fonte" and "eto_fonte" in d and d["eto_fonte"].notna().mean() > 0.8:
                d["eto"] = d["eto_fonte"].fillna(d["eto_pm"])
            else:
                d["eto"] = d["eto_pm"]
            if "chuva" not in d:
                d["chuva"] = 0.0
            if "urmin" not in d or d["urmin"].isna().all():
                ea = pm.calcular_ea(d["tmax"].values, d["tmin"].values,
                                    tdew=d["tdew"].values if "tdew" in d else None,
                                    urmed=d["ur"].values if "ur" in d else None)
                d["urmin"] = pm.urmin_estimada(d["tmax"].values, ea)
            normais = est.normais_de_serie(d, "eto")
            diario = d
            eto = normais["eto"].values
            chuva = normais["chuva"].values if "chuva" in normais else np.zeros(12)
            u2 = normais["u2"].values if "u2" in normais else np.full(12, 2.0)
            urmin = normais["urmin"].values
            tmax = normais["tmax"].values if "tmax" in normais else np.full(12, np.nan)
            tmin = normais["tmin"].values if "tmin" in normais else np.full(12, np.nan)
            ea_m = pm.calcular_ea(tmax, tmin, urmed=normais["ur"].values if "ur" in normais else None)
            metodo = "Penman-Monteith diário (FAO-56)"
        elif c["modo"] == "eto_mensal":
            eto = arr("eto")
            if np.isnan(eto).any():
                raise ErroEtapa("Informe a ETo média diária dos 12 meses.")
            chuva = np.nan_to_num(arr("chuva"))
            u2 = np.where(np.isnan(arr("u2")), 2.0, arr("u2"))
            ur = np.where(np.isnan(arr("ur")), 60.0, arr("ur"))
            tmax, tmin = arr("tmax"), arr("tmin")
            urmin = np.clip(ur - 20.0, 20, 90)
            ea_m = None
            metodo = "ETo mensal informada"
            normais = None
        else:
            tmax, tmin = arr("tmax"), arr("tmin")
            if np.isnan(tmax).any() or np.isnan(tmin).any():
                raise ErroEtapa("Informe as temperaturas máxima e mínima médias dos 12 meses.")
            u2 = arr("u2")
            u2 = None if np.isnan(u2).all() else np.where(np.isnan(u2), np.nanmean(u2), u2)
            ur = arr("ur")
            ur = None if np.isnan(ur).all() else np.where(np.isnan(ur), np.nanmean(ur), ur)
            eto, metodo_rs, _ = pm.et0_mensal_normais(tmax, tmin, lat, z, u2=u2, urmed=ur,
                                                       insolacao=arr("insolacao"), rs=arr("rs"),
                                                       krs=c.get("krs", 0.16))
            chuva = np.nan_to_num(arr("chuva"))
            ea_m = pm.calcular_ea(tmax, tmin, urmed=ur)
            urmin = pm.urmin_estimada(tmax, ea_m)
            u2 = np.full(12, 2.0) if u2 is None else u2
            metodo = f"Penman-Monteith mensal (FAO-56) — radiação: {metodo_rs}"
            normais = None
        if ea_m is not None and not np.isnan(tmax).all():
            dpv = pm.deficit_pressao_vapor(tmax, tmin, ea_m)
        else:
            dpv = np.full(12, 1.2)
        tab = pd.DataFrame({"Mês": est.MESES, "ETo (mm/d)": np.round(eto, 2), "Chuva (mm)": np.round(chuva, 1),
                            "u2 (m/s)": np.round(u2, 2), "URmín (%)": np.round(urmin, 0),
                            "DPV (kPa)": np.round(dpv, 2)}, index=range(1, 13))
        return {"eto": np.asarray(eto, float), "chuva": np.asarray(chuva, float), "u2": np.asarray(u2, float),
                "urmin": np.asarray(urmin, float), "dpv": np.asarray(dpv, float), "tabela": tab, "diario": diario,
                "metodo": metodo, "lat": lat, "altitude": z, "normais_serie": normais,
                "fonte": c.get("fonte", "")}

    def _cultura_obj(self):
        cfg = self.p["cultura"]
        if cfg["nome"] == "Personalizada" and cfg.get("personalizada"):
            c = cult.Cultura(**cfg["personalizada"])
        else:
            c = cult.obter_cultura(cfg["nome"])
        if cfg.get("kc_mensal") and len(cfg["kc_mensal"]) == 12 and c.perene:
            c.kc_mensal = [float(v) for v in cfg["kc_mensal"]]
        return c

    def _calc_kc(self):
        cl = self.get("clima")
        cfg = self.p["cultura"]
        c = self._cultura_obj()
        kc_df = cult.kc_mensal(c, cl["u2"], cl["urmin"], cfg["mes_plantio"], cfg["dia_plantio"],
                               cfg["ajuste_climatico"])
        kc_mid, kc_end, clima_aj = cult.kc_ajustados(c, cl["u2"], cl["urmin"], cfg["mes_plantio"],
                                                     cfg["dia_plantio"], cfg["ajuste_climatico"])
        return {"cultura": c, "kc_df": kc_df, "kc_mid": kc_mid, "kc_end": kc_end, "clima_ajuste": clima_aj}

    def aspersor_obj(self):
        a = self.p["aspersor"]
        return asp_mod.buscar_aspersor(a["id"], a.get("catalogo_usuario"))

    def _calc_aspersor(self):
        a = self.p["aspersor"]
        ag = self.p["agronomico"]
        cl = self.get("clima")
        asp = self.aspersor_obj()
        p = float(a["pressao_kpa"])
        q = float(asp.vazao(p))
        dm = asp.diametro(p)
        k, x = asp.coef_k_x()
        n_boc = len(asp.bocal.split("x"))
        perfil = a["perfil"] if a["perfil"] != "auto" else uni.perfil_automatico(p, asp.p_min, asp.p_max, n_boc)
        sim = uni.simular_malha(q, dm, a["esp_asp"], a["esp_lat"], a["arranjo"], perfil, a["vento_ms"],
                                a["dir_vento"], 28, a.get("radial") or None)
        m_crit = int(np.nanargmax(cl["eto"]))
        dpv = float(cl["dpv"][m_crit])
        perdas = uni.perdas_evaporacao_deriva(asp.d_bocal_mm, dpv, p, a["vento_ms"])
        ed = uni.eficiencia_distribuicao(sim["CUC"], ag["adequacao"])
        ea_calc = uni.eficiencia_aplicacao(sim["CUC"], ag["adequacao"], perdas, ag["ef_conducao"])
        ea = ea_calc if ag["ea_modo"] == "calculada" else float(ag["ea_informada"])
        ia = 1000.0 * q / (a["esp_asp"] * a["esp_lat"])
        esp_rec = asp_mod.espacamento_maximo_recomendado(dm, a["vento_ms"], a["arranjo"])
        avisos = []
        if p < asp.p_min * 0.95 or p > asp.p_max * 1.05:
            avisos.append(f"Pressão fora da faixa do catálogo ({asp.p_min:.0f}–{asp.p_max:.0f} kPa).")
        if ia > ag["vib"]:
            avisos.append(f"Intensidade de aplicação ({ia:.1f} mm/h) maior que a VIB do solo ({ag['vib']:.1f} mm/h) — "
                          "risco de escoamento superficial.")
        if sim["CUC"] < 80:
            avisos.append(f"CUC simulado de {sim['CUC']:.1f}% abaixo de 80% — reduza o espaçamento ou ajuste a pressão.")
        return {"asp": asp, "pressao": p, "h_servico": p / KPA_POR_MCA, "q": q, "dm": dm, "k": k, "x": x,
                "perfil": perfil, "sim": sim, "perdas_evap": perdas, "ed": ed, "ea_calc": ea_calc, "ea": ea,
                "ia": ia, "esp_rec": esp_rec, "dpv_critico": dpv, "avisos": avisos}

    def _calc_agronomico(self):
        ag = self.p["agronomico"]
        cl = self.get("clima")
        kc = self.get("kc")
        a = self.get("aspersor")
        g = self.get("geo")
        area = g["area_ha"] or (self.p["area"]["retangulo"]["comprimento"] * self.p["area"]["retangulo"]["largura"] / 1e4)
        tab = nec.tabela_mensal(cl["eto"], cl["chuva"], kc["kc_df"], a["ea"], area, ag["metodo_pe"], ag["frac_pe"])
        prob = None
        if ag["metodo_etc"] == "probabilistico":
            if cl["diario"] is None:
                raise ErroEtapa("O método probabilístico exige série climática diária.")
            cfg = self.p["cultura"]
            c = kc["cultura"]
            d = cl["diario"]
            if c.perene or c.ciclo == 0:
                kcs = pd.Series(kc["kc_df"]["kc"].values[d.index.month - 1], index=d.index)
            else:
                partes = []
                for ano in sorted(set(d.index.year)):
                    s = cult.kc_por_data(c, d.index[d.index.year >= ano], cfg["mes_plantio"], cfg["dia_plantio"],
                                         kc["kc_mid"], kc["kc_end"], ano_plantio=ano)
                    partes.append(s[(s.index.year == ano) | (s.index < pd.Timestamp(ano, 1, 1) + pd.Timedelta(days=c.ciclo + 400))])
                kcs = pd.concat(partes)
                kcs = kcs[~kcs.index.duplicated(keep="first")].reindex(d.index)
            etc = (d["eto"] * kcs).dropna()
            prob = est.etc_projeto_probabilistico(etc, int(ag["turno_rega"]), ag["prob"])
        pe_m = tab["Pe (mm/mês)"].values
        etc_p, mes_c, desc = nec.etc_projeto(ag["metodo_etc"], cl["eto"], kc["kc_df"], pe_m, prob, ag["considerar_chuva"])
        pe_proj = 0.0
        if ag["considerar_chuva"] and mes_c:
            pe_proj = float(pe_m[mes_c - 1] / est.DIAS_MES[mes_c - 1])
        proj = nec.projeto_agronomico(etc_p, ag["turno_rega"], a["ea"], pe_proj if ag["metodo_etc"] != "ciclo" else 0.0,
                                      ag.get("lamina_max") or None)
        proj["Ti"] = proj["LB"] / a["ia"]
        return {"tabela": tab, "etc_proj": etc_p, "mes_critico": mes_c, "descricao": desc, "prob": prob,
                "projeto": proj, "area_ha": area}

    def _calc_layout(self):
        g = self.get("geo")
        if g["pol_utm"] is None:
            raise ErroEtapa("Defina a área do projeto (desenho no mapa, KML/KMZ ou retângulo) na página Área e Mapa.")
        elev, info = self.get("elev")
        a = self.get("aspersor")
        L = self.p["layout"]
        h = self.p["hidraulica"]
        if L["orientacao"] == "curva_nivel" and info.get("declividade_pct", 0) > 0.05:
            azim = lay_mod.angulo_para_azimute(info["direcao_curva_nivel_graus"])
            orient = "Laterais em nível (curvas de nível do MDE)"
        elif L["orientacao"] == "manual":
            azim = float(L["azimute"])
            orient = "Azimute manual"
        else:
            azim = lay_mod.angulo_para_azimute(geo.angulo_maior_lado(g["pol_utm"]))
            orient = "Paralelas ao maior lado da área"
        comp_max = float(L.get("comp_max_lateral") or 0.0)
        info_lmax = None
        if comp_max <= 0:
            tubo = self.tubo_referencia_lateral()
            ang_lat = math.radians(lay_mod.azimute_para_angulo(azim))
            decl = 0.0
            if info.get("declividade_pct"):
                dd = math.radians(info["direcao_descida_graus"])
                decl = -info["declividade_pct"] / 100.0 * abs(math.cos(dd - ang_lat))
            n_max, comp_max = hid.comprimento_maximo_lateral(
                self.p["aspersor"]["esp_asp"], a["k"], a["x"], tubo, a["h_servico"], decl, 0.5,
                self.p["aspersor"]["altura_haste"], h["tol_lateral"] / 100.0, 400, h["equacao"],
                h["perda_local_lateral"] / 100.0)
            info_lmax = {"tubo": tubo.rotulo, "n": n_max, "comprimento": comp_max}
        layout = lay_mod.gerar_layout(g["pol_utm"], g["proj"], self.p["aspersor"]["esp_asp"],
                                      self.p["aspersor"]["esp_lat"], azim, g["fonte_xy"],
                                      self.p["aspersor"]["arranjo"], L["posicao_derivacao"], comp_max,
                                      int(L.get("n_derivacoes") or 0), elev, g["rota"] or None)
        return {"layout": layout, "azimute": azim, "orientacao": orient, "comp_max": comp_max, "info_lmax": info_lmax}

    def _calc_operacao(self):
        o = self.p["operacao"]
        ag = self.get("agronomico")
        a = self.get("aspersor")
        lo = self.get("layout")
        lay = lo["layout"]
        pr = ag["projeto"]
        res = op_mod.dimensionar_operacao(pr["LB"], a["ia"], o["jornada_h"], pr["TR"], int(o["folga_d"]),
                                          o["t_mudanca_h"], lay.n_aspersores, a["q"], o["q_fonte_m3h"] or None,
                                          int(o["n_setores"] or 0), lay.area_irrigada_ha, a["ea"])
        lay_mod.setorizar(lay, res["n_setores"])
        setores = lay_mod.resumo_setores(lay, a["q"])
        res["setores"] = setores
        res["Q_sistema"] = float(setores["Vazão (m³/h)"].max())
        if o["q_fonte_m3h"] and res["Q_sistema"] > o["q_fonte_m3h"] and res["fonte_ok"]:
            res["fonte_ok"] = False
            res["avisos"].append("Após a setorização real, o maior setor excede a vazão da fonte.")
        res["cronograma"] = op_mod.cronograma(res["n_setores"], res["Ti"], o["t_mudanca_h"], res["posicoes_dia"],
                                              res["dias_uteis"], o.get("hora_inicio", 21.5),
                                              setores["Vazão (m³/h)"].values)
        return res

    def tubo_referencia_lateral(self):
        """Tubo de referência para o comprimento máximo das laterais (define o nº de derivações)."""
        h = self.p["hidraulica"]
        cands = tub.tubos_por_material(h["mat_lateral"], self._catalogo_tubos())
        ref = h.get("dn_ref_lateral", "auto")
        if ref and ref != "auto":
            achado = [t for t in cands if t.dn == ref]
            if achado:
                return achado[0]
        alvo = 73.0 if h["mat_lateral"].startswith("Alumínio") else 50.0
        return min(cands, key=lambda t: abs(t.di_mm - alvo))

    def _catalogo_tubos(self):
        js = self.p["hidraulica"].get("catalogo_tubos")
        if js:
            return [tub.Tubo(**t) for t in js]
        return tub.catalogo_tubos()

    def config_hidraulica(self):
        h = self.p["hidraulica"]
        b = self.p["bomba"]
        cu = self.p["custos"]
        return rede_mod.ConfigHidraulica(
            equacao=h["equacao"], t_agua=h["t_agua"], mat_lateral=h["mat_lateral"], mat_derivacao=h["mat_derivacao"],
            mat_principal=h["mat_principal"], mat_adutora=h["mat_adutora"], modo_lateral=h["modo_lateral"],
            v_max_lateral=h["v_max_lateral"], v_max_derivacao=h["v_max_derivacao"],
            v_max_principal=h["v_max_principal"], v_max_adutora=h["v_max_adutora"],
            tol_lateral=h["tol_lateral"] / 100.0, tol_derivacao=h["tol_derivacao"] / 100.0,
            perda_local_lateral=h["perda_local_lateral"] / 100.0, perda_local_rede=h["perda_local_rede"] / 100.0,
            criterio_principal=h["criterio_principal"], margem_pn=h["margem_pn"], reguladores=h["reguladores"],
            limite_regulador=h["limite_regulador"] / 100.0, altura_haste=self.p["aspersor"]["altura_haste"],
            horas_ano=self._horas_ano_estimadas(), tarifa_kwh=b["tarifa_kwh"] * (1 - b["desconto_noturno"] / 100 * 0.6),
            eta_conjunto=b["eta_bomba"] * 0.9, juros_aa=cu["juros_aa"] / 100.0)

    def _horas_ano_estimadas(self):
        try:
            ag = self.get("agronomico")
            op = self.get("operacao")
            vol = ag["tabela"]["Volume (m³)"].sum()
            return float(vol / max(op["Q_sistema"], 1e-6))
        except Exception:  # noqa: BLE001
            return 2000.0

    def _calc_rede(self):
        lo = self.get("layout")
        op = self.get("operacao")
        a = self.get("aspersor")
        lay = lo["layout"]
        cfg = self.config_hidraulica()
        res = rede_mod.dimensionar(lay, a["k"], a["x"], a["h_servico"], cfg, self._catalogo_tubos())
        # perfil da adutora + principal até o setor crítico: ventosas e descargas
        elev, _ = self.get("elev")
        coords = list(lay.adutora)
        dist, cotas, xs, ys = alt.perfil_ao_longo(coords, elev, passo=5.0)
        altos, baixos = alt.pontos_notaveis(dist, cotas, 0.3)
        res.perfil_adutora = {"dist": dist, "cotas": cotas, "xs": xs, "ys": ys, "altos": altos, "baixos": baixos}
        res.n_ventosas = len(altos) + len(lay.derivacoes) + 1
        res.n_descargas = len(baixos) + len(lay.derivacoes)
        # golpe de aríete na adutora (fechamento da válvula do setor)
        tr = res.trechos[0]
        res.golpe = hid.golpe_ariete(tr.tubo, tr.comprimento + lay.comprimento_principal(), max(tr.v_proj, 0.1),
                                     self.p["hidraulica"].get("tempo_manobra_s", 10.0))
        return res

    def _calc_bomba(self):
        res = self.get("rede")
        op = self.get("operacao")
        b = self.p["bomba"]
        g = self.get("geo")
        cl = self.get("clima")
        crit = res.setores[res.setor_critico]
        q = crit["Q_m3h"]
        cat = self._catalogo_tubos()
        cand = tub.tubos_por_material("Aço galvanizado", cat)
        if b["dn_succao"] == "auto":
            t_suc = next((t for t in cand if hid.velocidade(q / 3600.0, t.d_m) <= 1.5), cand[-1])
        else:
            t_suc = next((t for t in cand if t.dn == b["dn_succao"]), cand[-1])
        # perdas na sucção: tubo + válvula de pé com crivo (K≈2,5) + curva (K≈0,4)
        v_s = float(hid.velocidade(q / 3600.0, t_suc.d_m))
        hf_suc = float(hid.perda_carga(q / 3600.0, t_suc, b["comp_succao"], "HW")) + 2.9 * v_s ** 2 / 19.62
        z_bomba = res.rede.z["F"]
        p_saida = crit["p_fonte"]
        hman = p_saida + b["altura_succao"] + hf_suc + b["h_cabecal"]
        pot = bmb.potencias(q, hman, b["eta_bomba"])
        npsh = bmb.npsh_disponivel(z_bomba, b["temp_agua"], b["altura_succao"], hf_suc)
        rpm = b["rpm"]
        if str(rpm) == "auto" or not rpm:
            rpm = 3500
            npshr_3500 = bmb.npsh_requerido_estimado(3500, q / 3600.0, hman)
            if npsh["NPSHd"] < npshr_3500 + 1.0 or bmb.rotacao_especifica(3500, q / 3600.0, hman) > 60:
                rpm = 1750
        rpm = float(rpm)
        nq = bmb.rotacao_especifica(rpm, q / 3600.0, hman)
        if b["curva"] == "usuario" and len(b.get("pontos_curva") or []) >= 3:
            pts = pd.DataFrame(b["pontos_curva"])
            curva = bmb.curva_de_pontos(pts["Q (m³/h)"], pts["H (m)"],
                                        pts["η (%)"] if "η (%)" in pts else None,
                                        pts["NPSHr (m)"] if "NPSHr (m)" in pts else None, n_rpm=rpm)
        else:
            curva = bmb.curva_sintetica(q, hman, b["eta_bomba"], rpm)
        # curva do sistema: parcela estática = altura de sucção + desnível + pressão mínima "fixa" (serviço)
        h_din = hf_suc + sum(crit["hf"][t.id] for t in res.rede.caminho(crit["no_critico"]))
        h_est = hman - h_din
        hsis = bmb.curva_sistema(h_est, h_din, q)
        ponto = bmb.ponto_operacao(curva, hsis)
        # pontos de operação de todos os setores
        pts_set = []
        for s in res.setores:
            if not s:
                continue
            hf_s = float(hid.perda_carga(s["Q_m3h"] / 3600.0, t_suc, b["comp_succao"], "HW")) + \
                2.9 * float(hid.velocidade(s["Q_m3h"] / 3600.0, t_suc.d_m)) ** 2 / 19.62
            pts_set.append({"Setor": s["setor"] + 1, "Q (m³/h)": round(s["Q_m3h"], 1),
                            "Hman requerida (m)": round(s["p_fonte"] + b["altura_succao"] + hf_s + b["h_cabecal"], 1)})
        npshr = float(curva.npshr(q)) if curva.coef_npsh is not None else bmb.npsh_requerido_estimado(rpm, q / 3600.0, hman)
        avisos = []
        if npsh["NPSHd"] < npshr + 0.6:
            avisos.append(f"NPSH disponível ({npsh['NPSHd']:.1f} m) insuficiente para NPSHr ({npshr:.1f} m) + 0,6 m "
                          "de margem — reduza a altura de sucção ou aumente o diâmetro da sucção.")
        if b["altura_succao"] > 6.5:
            avisos.append("Altura de sucção acima de 6,5 m: considere bomba afogada ou submersa.")
        rot = bmb.ajuste_rotacao(curva, q, hman)
        # energia anual pela necessidade de irrigação do projeto
        ag = self.get("agronomico")
        vol_ano = float(ag["tabela"]["Volume (m³)"].sum())
        q_med = float(np.mean([s["Q (m³/h)"] for s in pts_set])) if pts_set else q
        horas_ano = vol_ano / max(q_med, 1e-6)
        if b["energia"] == "eletrica":
            energia = bmb.custo_energia(pot["P_eletrica_kW"], horas_ano, b["tarifa_kwh"], b["desconto_noturno"],
                                        b["horas_desconto"], op["horas_operacao_dia"], b.get("demanda_rs_kw", 0.0))
        else:
            energia = bmb.custo_diesel(pot["P_eixo_kW"], horas_ano, b["preco_diesel"])
            energia["energia_kWh"] = pot["P_eixo_kW"] * horas_ano
        return {"Q": q, "Hman": hman, "p_saida": p_saida, "hf_succao": hf_suc, "tubo_succao": t_suc, "v_succao": v_s,
                "potencias": pot, "npsh": npsh, "npshr": npshr, "nq": nq, "tipo_rotor": bmb.tipo_rotor(nq),
                "curva": curva, "h_sis": hsis, "h_estatica": h_est, "ponto": ponto, "pontos_setores": pts_set,
                "rotacao_ideal": rot, "horas_ano": horas_ano, "volume_ano": vol_ano, "energia": energia,
                "z_bomba": z_bomba, "avisos": avisos, "rpm": rpm,
                "decomposicao": {
                    "Pressão de serviço (aspersor)": self.get("aspersor")["h_servico"],
                    "Altura da haste": self.p["aspersor"]["altura_haste"],
                    "Perdas na lateral crítica": max(crit["h_req"][crit["no_critico"]] - self.get("aspersor")["h_servico"] - self.p["aspersor"]["altura_haste"], 0.0),
                    "Desnível bomba → lateral crítica": res.rede.z[crit["no_critico"]] - z_bomba,
                    "Perdas na rede (adutora/principal/derivação)": sum(crit["hf"][t.id] for t in res.rede.caminho(crit["no_critico"])),
                    "Cabeçal de controle": b["h_cabecal"],
                    "Altura de sucção": b["altura_succao"],
                    "Perdas na sucção": hf_suc,
                }}

    def _calc_custos(self):
        lo = self.get("layout")
        res = self.get("rede")
        bm = self.get("bomba")
        a = self.get("aspersor")
        ag = self.get("agronomico")
        cu = self.p["custos"]
        lay = lo["layout"]
        df = cst.orcamento(lay, res, a["asp"].rotulo, self.p["operacao"]["tipo_sistema"],
                           bm["potencias"]["motor"]["motor_cv"], cu.get("precos") or {})
        lamina = float(ag["tabela"]["NIB (mm/mês)"].sum())
        eco = cst.analise_economica(df, lay.area_ha, bm["energia"]["custo_total"], bm["volume_ano"],
                                    cu["juros_aa"] / 100.0, cu["manutencao_pct"], cu["mao_obra_ano"],
                                    cu["tarifa_agua"], lamina)
        return {"orcamento": df, "economia": eco}


# ---------------------------------------------------------------------------
# Manejo (fora do cache principal: depende de dados de previsão/estação)
# ---------------------------------------------------------------------------
def kc_serie_manejo(pipe: Pipeline, datas):
    kc = pipe.get("kc")
    cfg = pipe.p["cultura"]
    return cult.kc_por_data(kc["cultura"], datas, cfg["mes_plantio"], cfg["dia_plantio"], kc["kc_mid"], kc["kc_end"])


def simular_manejo(pipe: Pipeline, df: pd.DataFrame, estrategia=None):
    m = pipe.p["manejo"]
    ag = pipe.get("agronomico")
    a = pipe.get("aspersor")
    kcs = kc_serie_manejo(pipe, df.index)
    try:
        op = pipe.get("operacao")
        cap = op.get("capacidade_mm_dia")
    except ErroEtapa:
        cap = None
    return mnj.balanco_climatico(df, kcs, a["ea"], a["ia"], estrategia or m["estrategia"],
                                 int(ag["projeto"]["TR"]), ag["projeto"]["LL"], m["limiar_pe"], m["frac_pe"],
                                 m.get("credito_max"), cap, m.get("adiar_chuva_mm", 0.0))


def executar_tudo(projeto: dict) -> dict:
    """Executa todas as etapas (usado nos relatórios e testes)."""
    pipe = Pipeline(projeto)
    saida = {"pipeline": pipe, "erros": {}}
    for etapa in DEPENDENCIAS:
        try:
            saida[etapa] = pipe.get(etapa)
        except Exception as exc:  # noqa: BLE001 — relatório deve listar a falha e seguir
            saida[etapa] = None
            saida["erros"][etapa] = str(exc)
    return saida
