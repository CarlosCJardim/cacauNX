"""Rede ramificada (árvore) do sistema: modelagem, dimensionamento e simulação.

Etapas do dimensionamento:
1. Laterais — menor DN que mantém a variação de pressão ≤ tolerância (padrão 20 %),
   cálculo passo a passo com a cota real de cada aspersor (MDE);
2. Derivação, principal e adutora — velocidade máxima e, opcionalmente,
   diâmetro econômico (custo anual mínimo: capital + energia);
3. Verificação da variação de pressão entre as entradas das laterais de cada
   setor, com aumento iterativo de diâmetros e indicação de reguladores de pressão;
4. Carga requerida na captação para cada setor (turno) e setor crítico;
5. Simulação com vazões dependentes da pressão (q = k·P^x) para obter a
   pressão e a vazão reais de todos os aspersores do setor.
"""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, field

import numpy as np

from .hidraulica import (dimensionar_lateral, lateral_passo_a_passo, perda_carga, velocidade)
from .tubos import Tubo, classe_para_pressao, tubos_por_material


@dataclass
class Trecho:
    id: str
    de: str
    para: str
    tipo: str  # adutora | principal | derivacao
    comprimento: float
    coords: list
    tubo: Tubo | None = None
    q_proj: float = 0.0  # m³/h
    hf_proj: float = 0.0
    v_proj: float = 0.0
    p_max: float = 0.0  # pressão máxima de operação (mca)


@dataclass
class ConfigHidraulica:
    equacao: str = "HW"
    t_agua: float = 25.0
    mat_lateral: str = "Alumínio (engate rápido)"
    mat_derivacao: str = "PVC"
    mat_principal: str = "PVC"
    mat_adutora: str = "PVC"
    modo_lateral: str = "uniforme"  # uniforme | individual
    v_max_lateral: float = 2.0
    v_max_derivacao: float = 2.0
    v_max_principal: float = 1.8
    v_max_adutora: float = 1.5
    tol_lateral: float = 0.20
    tol_derivacao: float = 0.10
    perda_local_lateral: float = 0.0
    perda_local_rede: float = 0.10
    criterio_principal: str = "velocidade"  # velocidade | economico
    margem_pn: float = 1.20
    reguladores: str = "auto"  # auto | sempre | nunca
    limite_regulador: float = 0.10
    altura_haste: float = 1.0
    # parâmetros econômicos (diâmetro econômico)
    horas_ano: float = 2000.0
    tarifa_kwh: float = 0.70
    eta_conjunto: float = 0.65
    juros_aa: float = 0.08
    vida_anos: float = 20.0


@dataclass
class ResultadoRede:
    laterais: dict
    trechos: list
    setores: list
    setor_critico: int
    h_fonte_max: float  # carga piezométrica requerida na captação (m)
    p_fonte_max: float  # pressão requerida na saída da bomba (mca)
    q_max: float
    avisos: list = field(default_factory=list)

    def trecho(self, tid):
        return next(t for t in self.trechos if t.id == tid)


class Rede:
    def __init__(self, lay, perda_local=0.10, equacao="HW", t_agua=25.0):
        self.lay = lay
        self.perda_local = perda_local
        self.equacao = equacao
        self.t_agua = t_agua
        self.trechos: list[Trecho] = []
        self.z = dict(lay.cotas_nos)
        con = getattr(lay, "no_conexao", "C")
        self._add("A0", "F", con, "adutora", lay.adutora)
        nos_p = lay.nos_principal
        idx_con = next(i for i, n in enumerate(nos_p) if n[0] == con)
        for i in range(idx_con, len(nos_p) - 1):
            self._add(f"P{i}", nos_p[i][0], nos_p[i + 1][0], "principal", [nos_p[i][1:], nos_p[i + 1][1:]])
        for i in range(idx_con, 0, -1):
            self._add(f"P{i}m", nos_p[i][0], nos_p[i - 1][0], "principal", [nos_p[i][1:], nos_p[i - 1][1:]])
        for d in lay.derivacoes:
            nos = d["nos"]
            for k in range(len(nos) - 1):
                self._add(f"D{d['id']}_{k}", nos[k][0], nos[k + 1][0], "derivacao", [nos[k][1:], nos[k + 1][1:]])
        self._por_id = {t.id: t for t in self.trechos}
        # árvore
        self.pai = {}
        self.filhos = defaultdict(list)
        for t in self.trechos:
            self.pai[t.para] = t
            self.filhos[t.de].append(t)
        self.ordem = []
        fila = deque(["F"])
        while fila:
            n = fila.popleft()
            self.ordem.append(n)
            for t in self.filhos[n]:
                fila.append(t.para)

    def _add(self, tid, de, para, tipo, coords):
        coords = [tuple(map(float, c)) for c in coords]
        comp = float(sum(np.hypot(coords[i + 1][0] - coords[i][0], coords[i + 1][1] - coords[i][1])
                         for i in range(len(coords) - 1)))
        self.trechos.append(Trecho(tid, de, para, tipo, max(comp, 0.1), coords))

    def trecho_por_id(self, tid):
        return self._por_id[tid]

    def caminho(self, no):
        trechos = []
        while no in self.pai:
            t = self.pai[no]
            trechos.append(t)
            no = t.de
        return trechos[::-1]

    def vazoes(self, demandas: dict) -> dict:
        """Vazão (m³/h) em cada trecho para as demandas nodais informadas."""
        acum = defaultdict(float, {n: q for n, q in demandas.items()})
        for n in reversed(self.ordem):
            if n in self.pai:
                acum[self.pai[n].de] += acum[n]
        return {t.id: acum[t.para] for t in self.trechos}

    def perdas(self, vaz: dict) -> dict:
        hf = {}
        for t in self.trechos:
            q = vaz.get(t.id, 0.0)
            hf[t.id] = 0.0 if q <= 0 or t.tubo is None else float(
                perda_carga(q / 3600.0, t.tubo, t.comprimento, self.equacao, self.t_agua)) * (1.0 + self.perda_local)
        return hf

    def cargas(self, h_fonte: float, hf: dict) -> dict:
        """Carga piezométrica em cada nó a partir da carga na captação."""
        h = {"F": h_fonte}
        for n in self.ordem[1:]:
            t = self.pai[n]
            h[n] = h[t.de] - hf[t.id]
        return h

    def carga_requerida(self, demandas: dict, h_req: dict):
        vaz = self.vazoes(demandas)
        hf = self.perdas(vaz)
        melhor, critico = -1e9, None
        for n in demandas:
            h = self.z[n] + h_req[n] + sum(hf[t.id] for t in self.caminho(n))
            if h > melhor:
                melhor, critico = h, n
        return melhor, critico, vaz, hf


def _tubos_candidatos(material, catalogo):
    return tubos_por_material(material, catalogo)


def _escolher_por_velocidade(q_m3h, candidatos, v_max):
    for t in candidatos:
        if velocidade(q_m3h / 3600.0, t.d_m) <= v_max:
            return t
    return candidatos[-1]


def _frc(i, n):
    return i * (1 + i) ** n / ((1 + i) ** n - 1) if i > 0 else 1.0 / n


def dimensionar(lay, asp_k, asp_x, h_servico, cfg: ConfigHidraulica, catalogo=None,
                n_setores_ativos=None) -> ResultadoRede:
    """Dimensionamento completo da rede para o layout setorizado."""
    avisos = []
    cand_lat = [t for t in _tubos_candidatos(cfg.mat_lateral, catalogo) if t.di_mm <= 160]
    if not cand_lat:
        cand_lat = _tubos_candidatos(cfg.mat_lateral, catalogo)

    # --------------------------------------------------------------- laterais
    res_lat = {}
    for l in lay.laterais:
        t, r, ok = dimensionar_lateral(l.n, lay.esp_asp, asp_k, asp_x, cand_lat, h_servico, l.cotas, 0.5,
                                       cfg.altura_haste, cfg.tol_lateral, cfg.v_max_lateral, cfg.equacao,
                                       cfg.perda_local_lateral, cfg.t_agua, comprimentos=l.comprimentos)
        res_lat[l.id] = {"tubo": t, "res": r, "atende": ok}
    if cfg.modo_lateral == "uniforme" and res_lat:
        maior = max((v["tubo"] for v in res_lat.values()), key=lambda t: t.di_mm)
        for l in lay.laterais:
            if res_lat[l.id]["tubo"].di_mm < maior.di_mm:
                r = lateral_passo_a_passo(l.n, lay.esp_asp, asp_k, asp_x, maior, l.cotas, 0.5, cfg.altura_haste,
                                          h_servico=h_servico, equacao=cfg.equacao,
                                          perda_local=cfg.perda_local_lateral, t_c=cfg.t_agua,
                                          comprimentos=l.comprimentos)
                res_lat[l.id] = {"tubo": maior, "res": r,
                                 "atende": r.var_pressao_pct <= cfg.tol_lateral * 100 + 1e-9}
    nao_atende = [lid for lid, v in res_lat.items() if not v["atende"]]
    if nao_atende:
        avisos.append(f"{len(nao_atende)} lateral(is) excedem a variação de pressão de "
                      f"{cfg.tol_lateral * 100:.0f}% mesmo com o maior diâmetro — reduza o comprimento "
                      f"(mais derivações) ou use regulador de pressão por aspersor.")

    # --------------------------------------------------------------- demandas por setor
    def demandas_setor(s):
        dem, hreq = defaultdict(float), {}
        for l in lay.laterais_do_setor(s):
            r = res_lat[l.id]["res"]
            dem[l.no_entrada] += r.q_entrada_m3h
            hreq[l.no_entrada] = max(hreq.get(l.no_entrada, 0.0), r.h_entrada)
        return dict(dem), hreq

    n_set = len(lay.setores)
    dem_set = [demandas_setor(s) for s in range(n_set)]

    rede = Rede(lay, cfg.perda_local_rede, cfg.equacao, cfg.t_agua)
    q_proj = defaultdict(float)
    for dem, _ in dem_set:
        for tid, q in rede.vazoes(dem).items():
            q_proj[tid] = max(q_proj[tid], q)
    mats = {"adutora": cfg.mat_adutora, "principal": cfg.mat_principal, "derivacao": cfg.mat_derivacao}
    vmax = {"adutora": cfg.v_max_adutora, "principal": cfg.v_max_principal, "derivacao": cfg.v_max_derivacao}
    cands = {tipo: _tubos_candidatos(m, catalogo) for tipo, m in mats.items()}
    for t in rede.trechos:
        t.q_proj = q_proj[t.id]
        t.tubo = _escolher_por_velocidade(max(t.q_proj, 0.01), cands[t.tipo], vmax[t.tipo])

    # --------------------------------------------------------------- diâmetro econômico
    if cfg.criterio_principal == "economico":
        frc = _frc(cfg.juros_aa, cfg.vida_anos)
        horas_setor = cfg.horas_ano / max(n_set, 1)
        for t in rede.trechos:
            if t.tipo not in ("adutora", "principal") or t.q_proj <= 0:
                continue
            lista = cands[t.tipo]
            i0 = lista.index(t.tubo)
            melhor, custo_min = t.tubo, 1e18
            for tub in lista[i0:i0 + 5]:
                energia = 0.0
                for dem, _ in dem_set:
                    q = rede.vazoes(dem)[t.id]
                    if q <= 0:
                        continue
                    hf = float(perda_carga(q / 3600.0, tub, t.comprimento, cfg.equacao, cfg.t_agua)) * (
                        1 + cfg.perda_local_rede)
                    energia += 9.81 * (q / 3600.0) * hf / cfg.eta_conjunto * horas_setor
                custo = frc * tub.preco_m * t.comprimento + energia * cfg.tarifa_kwh
                if custo < custo_min:
                    melhor, custo_min = tub, custo
            t.tubo = melhor

    # --------------------------------------------------------------- variação na derivação
    # Critério: a variação da pressão disponível entre as entradas das laterais ativas
    # de um setor deve ser ≤ tol_derivacao·PS. Aumenta-se, de forma gulosa, o trecho
    # de derivação com maior redução de variação por real investido; se nenhum
    # aumento reduzir a variação (efeito do relevo), indicam-se reguladores.
    def variacao_setor(dem, hreq):
        h_f, crit, vaz, hf = rede.carga_requerida(dem, hreq)
        h = rede.cargas(h_f, hf)
        p_disp = [h[n] - rede.z[n] for n in dem]
        return max(p_disp) - min(p_disp), hf

    lim_der = cfg.tol_derivacao * h_servico
    setores_relevo = set()
    for s, (dem, hreq) in enumerate(dem_set):
        if not dem:
            continue
        zs = [rede.z[n] for n in dem]
        if max(zs) - min(zs) > lim_der:
            # só o desnível já excede a tolerância: aumentar diâmetros não resolve
            setores_relevo.add(s)
            continue
        for _ in range(40):
            var, hf = variacao_setor(dem, hreq)
            if var <= lim_der + 1e-6:
                break
            usados = {tr.id for n in dem for tr in rede.caminho(n) if tr.tipo in ("derivacao", "principal")}
            melhor, ganho_max = None, 0.0
            for tid in usados:
                tr = rede.trecho_por_id(tid)
                lista = cands[tr.tipo]
                i = lista.index(tr.tubo)
                if i + 1 >= len(lista):
                    continue
                antigo = tr.tubo
                tr.tubo = lista[i + 1]
                var_n, _ = variacao_setor(dem, hreq)
                tr.tubo = antigo
                ganho = (var - var_n) / max((lista[i + 1].preco_m - antigo.preco_m) * tr.comprimento, 1.0)
                if var - var_n > 0.02 and ganho > ganho_max:
                    melhor, ganho_max = (tr, lista[i + 1]), ganho
            if melhor is None:
                setores_relevo.add(s)
                break
            melhor[0].tubo = melhor[1]
    # diâmetros não crescentes da entrada para o final de cada derivação (telescópica)
    for d in lay.derivacoes:
        ids = [f"D{d['id']}_{k}" for k in range(len(d["nos"]) - 1)]
        trs = [rede.trecho_por_id(t) for t in ids]
        maior = None
        for tr in reversed(trs):
            if maior is not None and tr.tubo.di_mm < maior.di_mm:
                tr.tubo = maior
            maior = tr.tubo if maior is None or tr.tubo.di_mm >= maior.di_mm else maior
    if setores_relevo:
        avisos.append(f"Setor(es) {', '.join(str(s + 1) for s in sorted(setores_relevo))}: a variação de pressão "
                      f"entre laterais é dominada pelo relevo — reguladores de pressão são recomendados.")

    # --------------------------------------------------------------- avaliação por setor
    setores = []
    for s, (dem, hreq) in enumerate(dem_set):
        if not dem:
            setores.append(None)
            continue
        h_f, crit, vaz, hf = rede.carga_requerida(dem, hreq)
        h = rede.cargas(h_f, hf)
        excesso = {n: (h[n] - rede.z[n]) - hreq[n] for n in dem}
        if cfg.reguladores == "sempre":
            regs = list(dem)
        elif cfg.reguladores == "nunca":
            regs = []
        else:
            regs = [n for n, e in excesso.items() if e > cfg.limite_regulador * h_servico]
        for t in rede.trechos:
            p_de = h[t.de] - rede.z.get(t.de, 0.0)
            t.p_max = max(t.p_max, p_de)
            q = vaz[t.id]
            if q > 0:
                t.hf_proj = max(t.hf_proj, hf[t.id])
                t.v_proj = max(t.v_proj, float(velocidade(q / 3600.0, t.tubo.d_m)))
        setores.append({
            "setor": s, "Q_m3h": float(sum(dem.values())), "h_fonte": float(h_f),
            "p_fonte": float(h_f - rede.z["F"]), "no_critico": crit,
            "excesso_max": float(max(excesso.values())),
            "variacao_pct": float(100 * max(excesso.values()) / h_servico),
            "reguladores": regs, "cargas": h, "hf": hf, "vazoes": vaz, "demandas": dem, "h_req": hreq,
        })
    validos = [x for x in setores if x]
    crit = max(validos, key=lambda x: x["h_fonte"])
    # classe de pressão
    for t in rede.trechos:
        p_proj = t.p_max * cfg.margem_pn
        nova = classe_para_pressao(t.tubo.material, t.tubo.dn, p_proj, catalogo)
        if nova is None:
            avisos.append(f"Trecho {t.id}: nenhuma classe de {t.tubo.material} DN {t.tubo.dn} suporta "
                          f"{p_proj:.0f} mca — use material de maior resistência.")
        elif nova.pn_mca != t.tubo.pn_mca:
            t.tubo = nova
    total_regs = len({n for x in validos for n in x["reguladores"]})
    if total_regs:
        avisos.append(f"Recomendados {total_regs} regulador(es) de pressão na entrada das laterais "
                      f"(excesso > {cfg.limite_regulador * 100:.0f}% da pressão de serviço).")
    for t in rede.trechos:
        if t.v_proj > vmax[t.tipo] + 1e-6:
            avisos.append(f"Trecho {t.id} ({t.tipo}) com velocidade {t.v_proj:.2f} m/s acima do limite.")
    res = ResultadoRede(res_lat, rede.trechos, setores, crit["setor"], crit["h_fonte"], crit["p_fonte"],
                        max(x["Q_m3h"] for x in validos), avisos)
    res.rede = rede
    return res


# ---------------------------------------------------------------------------
# Simulação com vazões dependentes da pressão
# ---------------------------------------------------------------------------
def simular_setor(lay, res: ResultadoRede, s: int, asp_k, asp_x, h_servico, cfg: ConfigHidraulica,
                  p_fonte: float | None = None, com_reguladores: bool = True, iter_max: int = 60):
    """Simula o setor ``s`` com pressão ``p_fonte`` na captação (padrão: a requerida).

    Retorna dict com pressões e vazões de todos os aspersores do setor.
    """
    rede: Rede = res.rede
    info = res.setores[s]
    if info is None:
        return None
    h_f = rede.z["F"] + (info["p_fonte"] if p_fonte is None else p_fonte)
    lats = lay.laterais_do_setor(s)
    regs = set(info["reguladores"]) if com_reguladores else set()
    # curvas de entrada das laterais: Q = c·h^y
    curvas = {}
    for l in lats:
        rl = res.laterais[l.id]
        hs = np.linspace(0.75, 1.4, 4) * rl["res"].h_entrada
        qs = [lateral_passo_a_passo(l.n, lay.esp_asp, asp_k, asp_x, rl["tubo"], l.cotas, 0.5, cfg.altura_haste,
                                    h_entrada=h, equacao=cfg.equacao, perda_local=cfg.perda_local_lateral,
                                    comprimentos=l.comprimentos).q_entrada_m3h for h in hs]
        y, lnc = np.polyfit(np.log(hs), np.log(qs), 1)
        curvas[l.id] = (float(np.exp(lnc)), float(y))
    q_lat = {l.id: res.laterais[l.id]["res"].q_entrada_m3h for l in lats}
    for _ in range(iter_max):
        dem = defaultdict(float)
        for l in lats:
            dem[l.no_entrada] += q_lat[l.id]
        vaz = rede.vazoes(dem)
        hf = rede.perdas(vaz)
        h = rede.cargas(h_f, hf)
        novo = {}
        for l in lats:
            p = max(h[l.no_entrada] - rede.z[l.no_entrada], 0.5)
            if l.no_entrada in regs:
                p = min(p, info["h_req"][l.no_entrada])
            c, y = curvas[l.id]
            novo[l.id] = c * p ** y
        dif = max(abs(novo[i] - q_lat[i]) / max(q_lat[i], 1e-6) for i in novo)
        q_lat = {i: 0.5 * q_lat[i] + 0.5 * novo[i] for i in novo}
        if dif < 1e-4:
            break
    pressoes, vazoes, xy = [], [], []
    for l in lats:
        p_in = max(h[l.no_entrada] - rede.z[l.no_entrada], 0.5)
        if l.no_entrada in regs:
            p_in = min(p_in, info["h_req"][l.no_entrada])
        r = lateral_passo_a_passo(l.n, lay.esp_asp, asp_k, asp_x, res.laterais[l.id]["tubo"], l.cotas, 0.5,
                                  cfg.altura_haste, h_entrada=p_in, equacao=cfg.equacao,
                                  perda_local=cfg.perda_local_lateral, comprimentos=l.comprimentos)
        pressoes.append(r.h_bocal)
        vazoes.append(r.q)
        xy.append(l.aspersores_xy)
    p = np.concatenate(pressoes)
    q = np.concatenate(vazoes)
    cuc_q = 100.0 * (1 - np.abs(q - q.mean()).sum() / (q.size * q.mean()))
    n25 = max(1, int(0.25 * q.size))
    return {
        "pressoes": p, "vazoes": q, "xy": np.vstack(xy), "Q_total": float(q.sum()),
        "p_media": float(p.mean()), "p_min": float(p.min()), "p_max": float(p.max()),
        "var_pressao_pct": float(100 * (p.max() - p.min()) / h_servico),
        "cuc_vazao": float(cuc_q), "cud_vazao": float(100 * np.sort(q)[:n25].mean() / q.mean()),
        "p_fonte": float(h_f - rede.z["F"]),
    }


NOMES_TIPO = {"adutora": "Adutora", "principal": "Principal", "derivacao": "Derivação"}


def _linha_do_trecho(t: Trecho) -> str:
    if t.tipo == "adutora":
        return "Adutora"
    if t.tipo == "principal":
        return "Principal (sentido 1)" if not t.id.endswith("m") else "Principal (sentido 2)"
    return f"Derivação {int(t.id[1:].split('_')[0]) + 1}"


def trechos_agrupados(res: ResultadoRede):
    """Agrupa trechos consecutivos de uma mesma linha com o mesmo tubo (tabela compacta)."""
    import pandas as pd

    linhas = []
    atual = None
    for t in res.trechos:
        chave = (_linha_do_trecho(t), t.tubo.rotulo)
        if atual is None or atual["chave"] != chave:
            if atual:
                linhas.append(atual)
            ini = atual["fim"] if atual and atual["chave"][0] == chave[0] else 0.0
            atual = {"chave": chave, "ini": ini, "fim": ini, "L": 0.0, "Q": 0.0, "v": 0.0, "hf": 0.0, "pmax": 0.0,
                     "tubo": t.tubo}
        atual["fim"] += t.comprimento
        atual["L"] += t.comprimento
        atual["Q"] = max(atual["Q"], t.q_proj)
        atual["v"] = max(atual["v"], t.v_proj)
        atual["hf"] += t.hf_proj
        atual["pmax"] = max(atual["pmax"], t.p_max)
    if atual:
        linhas.append(atual)
    return pd.DataFrame([{
        "Linha": g["chave"][0], "De (m)": round(g["ini"], 1), "Até (m)": round(g["fim"], 1), "L (m)": round(g["L"], 1),
        "Tubo": f"{g['tubo'].material} DN {g['tubo'].dn} PN{g['tubo'].pn_mca:.0f}", "DI (mm)": g["tubo"].di_mm,
        "Q máx. (m³/h)": round(g["Q"], 1), "v máx. (m/s)": round(g["v"], 2), "Σhf (m)": round(g["hf"], 2),
        "P máx. (mca)": round(g["pmax"], 1),
    } for g in linhas])
