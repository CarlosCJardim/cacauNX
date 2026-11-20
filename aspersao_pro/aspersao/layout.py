"""Geração automática do layout do sistema de aspersão convencional sobre o
polígono da área (topologia em "pente"):

    captação → adutora → linha principal (paralela às laterais, na borda) →
    linhas de derivação (perpendiculares) → linhas laterais → aspersores

As laterais podem ser orientadas automaticamente em nível (perpendiculares à
declividade dominante do MDE), pelo maior lado da área ou por azimute manual.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
from shapely.geometry import LineString, Point, Polygon
from shapely.prepared import prep


@dataclass
class Lateral:
    id: int
    derivacao: int
    linha: int
    lado: str  # 'D' (sentido +u) ou 'E' (sentido −u)
    entrada_xy: tuple
    aspersores_xy: np.ndarray  # (n, 2), ordenados da entrada para o final
    comprimentos: np.ndarray  # n trechos (entrada → 1º, 1º → 2º, ...)
    cotas: np.ndarray = None  # n+1 (entrada + aspersores)
    setor: int = -1

    @property
    def n(self) -> int:
        return len(self.aspersores_xy)

    @property
    def comprimento(self) -> float:
        return float(np.sum(self.comprimentos))

    @property
    def no_entrada(self) -> str:
        return f"D{self.derivacao}_{self.linha}"


@dataclass
class Layout:
    proj: object
    poligono: Polygon
    azimute_laterais: float
    angulo_mat: float
    esp_asp: float
    esp_lat: float
    arranjo: str
    laterais: list
    derivacoes: list  # [{'id', 'coords': [(x, y), ...], 'nos': [(no_id, x, y)]}]
    principal: list  # coordenadas da linha principal (cabeceira)
    nos_principal: list  # [(no_id, x, y)] ordenados ao longo da principal
    adutora: list  # coordenadas da adutora (fonte → conexão)
    fonte_xy: tuple
    cotas_nos: dict = field(default_factory=dict)
    setores: list = field(default_factory=list)
    avisos: list = field(default_factory=list)

    @property
    def n_aspersores(self) -> int:
        return int(sum(l.n for l in self.laterais))

    @property
    def area_ha(self) -> float:
        return self.poligono.area / 10000.0

    @property
    def area_irrigada_ha(self) -> float:
        return self.n_aspersores * self.esp_asp * self.esp_lat / 10000.0

    def todos_aspersores(self):
        if not self.laterais:
            return np.zeros((0, 2))
        return np.vstack([l.aspersores_xy for l in self.laterais])

    def comprimento_laterais(self) -> float:
        return float(sum(l.comprimento for l in self.laterais))

    def comprimento_derivacoes(self) -> float:
        return float(sum(LineString(d["coords"]).length for d in self.derivacoes if len(d["coords"]) > 1))

    def comprimento_principal(self) -> float:
        return LineString(self.principal).length if len(self.principal) > 1 else 0.0

    def comprimento_adutora(self) -> float:
        return LineString(self.adutora).length if len(self.adutora) > 1 else 0.0

    def laterais_do_setor(self, s: int):
        return [l for l in self.laterais if l.setor == s]


class _Quadro:
    """Sistema de coordenadas girado: u ao longo das laterais, v perpendicular."""

    def __init__(self, cx, cy, ang_rad, sinal_v=1.0):
        self.cx, self.cy = cx, cy
        self.c, self.s = math.cos(ang_rad), math.sin(ang_rad)
        self.sv = sinal_v

    def para_uv(self, x, y):
        dx, dy = np.asarray(x) - self.cx, np.asarray(y) - self.cy
        return dx * self.c + dy * self.s, self.sv * (-dx * self.s + dy * self.c)

    def para_xy(self, u, v):
        u = np.asarray(u, dtype=float)
        v = self.sv * np.asarray(v, dtype=float)
        return self.cx + u * self.c - v * self.s, self.cy + u * self.s + v * self.c


def azimute_para_angulo(az):
    """Azimute (graus a partir do Norte, horário) → ângulo matemático (a partir do Leste, anti-horário)."""
    return (90.0 - az) % 180.0


def angulo_para_azimute(ang):
    return (90.0 - ang) % 180.0


def gerar_layout(pol_utm: Polygon, proj, esp_asp: float, esp_lat: float, azimute_laterais: float,
                 fonte_xy=None, arranjo: str = "retangular", posicao_derivacao: str = "central",
                 comp_max_lateral: float = 0.0, n_derivacoes: int = 0, elev=None, rota_adutora_xy=None) -> Layout:
    """Gera o layout completo. ``elev`` deve expor ``cota(x, y)`` (MDE ou terreno uniforme)."""
    avisos = []
    ang = math.radians(azimute_para_angulo(azimute_laterais))
    cen = pol_utm.centroid
    if fonte_xy is None:
        minx, miny, _, _ = pol_utm.bounds
        fonte_xy = (minx - 20.0, miny - 20.0)
        avisos.append("Captação não definida: adotado ponto próximo ao canto sudoeste da área.")
    q0 = _Quadro(cen.x, cen.y, ang)
    us, vs = q0.para_uv(*fonte_xy)
    ex_u, ex_v = q0.para_uv(*np.asarray(pol_utm.exterior.coords).T)
    sinal = 1.0 if vs <= (ex_v.min() + ex_v.max()) / 2.0 else -1.0
    q = _Quadro(cen.x, cen.y, ang, sinal)
    eu, ev = q.para_uv(*np.asarray(pol_utm.exterior.coords).T)
    pol_uv = Polygon(list(zip(eu, ev)))
    if not pol_uv.is_valid:
        pol_uv = pol_uv.buffer(0)
    pp = prep(pol_uv.buffer(0.05))
    umin, vmin, umax, vmax = pol_uv.bounds
    us, vs = q.para_uv(*fonte_xy)

    # colunas (ao longo das laterais) e linhas laterais
    ncols = max(1, int(math.floor((umax - umin) / esp_asp + 1e-9)))
    sobra_u = (umax - umin) - ncols * esp_asp
    u0 = umin + sobra_u / 2.0 + esp_asp / 2.0
    nlin = max(1, int(math.floor((vmax - vmin) / esp_lat + 1e-9)))
    sobra_v = (vmax - vmin) - nlin * esp_lat
    v0 = vmin + sobra_v / 2.0 + esp_lat / 2.0
    linhas_v = v0 + esp_lat * np.arange(nlin)

    # derivações
    largura = ncols * esp_asp
    if comp_max_lateral and comp_max_lateral > 0:
        lmax = comp_max_lateral
    else:
        lmax = largura if posicao_derivacao == "borda" else largura / 2.0
    if n_derivacoes and n_derivacoes > 0:
        nd = int(n_derivacoes)
    elif posicao_derivacao == "borda":
        nd = max(1, int(math.ceil(largura / max(lmax, esp_asp) - 1e-9)))
    else:
        nd = max(1, int(math.ceil(largura / (2.0 * max(lmax, esp_asp)) - 1e-9)))
    nd = min(nd, ncols)
    limites = np.round(np.linspace(0, ncols, nd + 1)).astype(int)
    u_der = []
    for d in range(nd):
        k0, k1 = limites[d], limites[d + 1]
        if posicao_derivacao == "borda":
            u_der.append(u0 + (k0 - 0.5) * esp_asp)
        else:
            meio = (k0 + k1) / 2.0
            kk = int(math.floor(meio))
            u_der.append(u0 + (kk - 0.5) * esp_asp if (k1 - k0) > 1 else u0 + (k0 - 0.5) * esp_asp)

    v_cab = vmin  # linha principal na borda voltada para a captação

    laterais = []
    der_nos = {d: [] for d in range(nd)}
    lid = 0
    for j, v in enumerate(linhas_v):
        desloc = esp_asp / 2.0 if (arranjo == "triangular" and j % 2 == 1) else 0.0
        cols_u = u0 + desloc + esp_asp * np.arange(ncols + (1 if desloc else 0))
        dentro = np.array([pp.contains(Point(u, v)) for u in cols_u])
        for d in range(nd):
            k0, k1 = limites[d], limites[d + 1]
            if d == nd - 1:
                k1 = len(cols_u)
            idx = np.arange(k0, k1)
            idx = idx[dentro[k0:k1]]
            if idx.size == 0:
                continue
            ud = u_der[d]
            criado = False
            for lado, sel in (("D", cols_u[idx] > ud + 1e-6), ("E", cols_u[idx] < ud - 1e-6)):
                uu = cols_u[idx][sel]
                if uu.size == 0:
                    continue
                uu = np.sort(uu) if lado == "D" else np.sort(uu)[::-1]
                dist = np.abs(uu - ud)
                comp = np.diff(np.concatenate([[0.0], dist]))
                xs, ys = q.para_xy(uu, np.full_like(uu, v))
                ex, ey = q.para_xy(ud, v)
                laterais.append(Lateral(lid, d, j, lado, (float(ex), float(ey)), np.column_stack([xs, ys]),
                                        comp))
                lid += 1
                criado = True
            # aspersor exatamente sobre a derivação (arranjo triangular): vai para a lateral direita
            sobre = idx[np.abs(cols_u[idx] - ud) <= 1e-6]
            if sobre.size and criado:
                lat_d = [l for l in laterais if l.derivacao == d and l.linha == j and l.lado == "D"]
                xs, ys = q.para_xy(cols_u[sobre], np.full(sobre.size, v))
                if lat_d:
                    l = lat_d[0]
                    l.aspersores_xy = np.vstack([np.column_stack([xs, ys]), l.aspersores_xy])
                    l.comprimentos = np.concatenate([[0.0], l.comprimentos])
            if criado:
                ex, ey = q.para_xy(ud, v)
                der_nos[d].append((f"D{d}_{j}", float(ex), float(ey), v))

    derivacoes = []
    nos_principal = []
    for d in range(nd):
        if not der_nos[d]:
            continue
        hx, hy = q.para_xy(u_der[d], v_cab)
        coords = [(float(hx), float(hy))] + [(x, y) for _, x, y, _ in der_nos[d]]
        derivacoes.append({"id": d, "coords": coords, "nos": [(f"H{d}", float(hx), float(hy))] +
                           [(n, x, y) for n, x, y, _ in der_nos[d]], "u": u_der[d]})
        nos_principal.append((f"H{d}", float(hx), float(hy), u_der[d]))

    if not derivacoes:
        raise ValueError("Nenhum aspersor coube na área com os espaçamentos informados.")

    u_ativos = [n[3] for n in nos_principal]
    u_con = float(np.clip(us, min(u_ativos), max(u_ativos)))
    cx_, cy_ = q.para_xy(u_con, v_cab)
    existe = [n for n in nos_principal if abs(n[3] - u_con) < 1e-6]
    if not existe:
        nos_principal.append(("C", float(cx_), float(cy_), u_con))
    nos_principal.sort(key=lambda n: n[3])
    no_conexao = existe[0][0] if existe else "C"
    principal = [(n[1], n[2]) for n in nos_principal]

    adutora = [tuple(map(float, fonte_xy))]
    if rota_adutora_xy:
        adutora += [tuple(map(float, p)) for p in rota_adutora_xy[1:]]
    adutora.append((float(cx_), float(cy_)))

    lay = Layout(proj=proj, poligono=pol_utm, azimute_laterais=azimute_laterais,
                 angulo_mat=math.degrees(ang), esp_asp=esp_asp, esp_lat=esp_lat, arranjo=arranjo,
                 laterais=laterais, derivacoes=derivacoes, principal=principal,
                 nos_principal=[(n[0], n[1], n[2]) for n in nos_principal], adutora=adutora,
                 fonte_xy=tuple(map(float, fonte_xy)), avisos=avisos)
    lay.no_conexao = no_conexao
    if elev is not None:
        atribuir_cotas(lay, elev)
    return lay


def atribuir_cotas(lay: Layout, elev):
    """Cotas de aspersores, entradas das laterais e nós da rede a partir do modelo de elevação."""
    for l in lay.laterais:
        pts = np.vstack([np.asarray(l.entrada_xy)[None, :], l.aspersores_xy])
        l.cotas = np.asarray(elev.cota(pts[:, 0], pts[:, 1]), dtype=float)
    nos = {"F": lay.fonte_xy}
    for d in lay.derivacoes:
        for n, x, y in d["nos"]:
            nos[n] = (x, y)
    for n, x, y in lay.nos_principal:
        nos[n] = (x, y)
    ids = list(nos)
    xy = np.array([nos[i] for i in ids])
    z = elev.cota(xy[:, 0], xy[:, 1])
    lay.cotas_nos = {i: float(v) for i, v in zip(ids, z)}


def _particionar(laterais, n_partes):
    """Divide uma sequência ordenada de laterais em ``n_partes`` contíguas com
    número de aspersores equilibrado (programação dinâmica simples)."""
    n_partes = int(max(1, min(n_partes, len(laterais))))
    pesos = np.array([l.n for l in laterais], dtype=float)
    acum = np.concatenate([[0.0], np.cumsum(pesos)])
    total = acum[-1]
    cortes = [0]
    for k in range(1, n_partes):
        alvo = total * k / n_partes
        i = int(np.argmin(np.abs(acum - alvo)))
        i = max(i, cortes[-1] + 1)
        i = min(i, len(laterais) - (n_partes - k))
        cortes.append(i)
    cortes.append(len(laterais))
    return [laterais[cortes[k]:cortes[k + 1]] for k in range(n_partes)]


def setorizar(lay: Layout, n_setores: int):
    """Divide as laterais em setores operacionais (cada setor opera em um turno).

    Sempre que o número de setores ≥ número de derivações, cada setor fica restrito
    a uma única derivação (válvula de setor na própria derivação), com o número de
    setores de cada derivação proporcional ao seu número de aspersores. Caso
    contrário, derivações inteiras e contíguas são agrupadas.
    """
    ordem = sorted(lay.laterais, key=lambda l: (l.derivacao, l.linha, 0 if l.lado == "E" else 1))
    n_setores = int(max(1, min(n_setores, len(ordem))))
    por_der = {}
    for l in ordem:
        por_der.setdefault(l.derivacao, []).append(l)
    ders = sorted(por_der)
    grupos = []
    if n_setores >= len(ders):
        pesos = np.array([sum(l.n for l in por_der[d]) for d in ders], dtype=float)
        bruto = pesos / pesos.sum() * n_setores
        k = np.maximum(1, np.floor(bruto)).astype(int)
        while k.sum() < n_setores:
            k[int(np.argmax(bruto - k))] += 1
        while k.sum() > n_setores:
            cand = np.where(k > 1)[0]
            k[cand[int(np.argmin((bruto - k)[cand]))]] -= 1
        for d, kd in zip(ders, k):
            grupos += _particionar(por_der[d], min(kd, len(por_der[d])))
    else:
        blocos = _particionar([type("B", (), {"n": sum(l.n for l in por_der[d]), "d": d}) for d in ders], n_setores)
        for b in blocos:
            grupos.append([l for bb in b for l in por_der[bb.d]])
    for s, g in enumerate(grupos):
        for l in g:
            l.setor = s
    lay.setores = [[l.id for l in g] for g in grupos]
    return lay.setores


def resumo_setores(lay: Layout, q_asp_m3h: float):
    import pandas as pd

    linhas = []
    for s, ids in enumerate(lay.setores):
        lats = [lay.laterais[i] for i in ids]
        n = sum(l.n for l in lats)
        linhas.append({"Setor": s + 1, "Laterais": len(lats), "Aspersores": n,
                       "Área (ha)": round(n * lay.esp_asp * lay.esp_lat / 10000.0, 2),
                       "Vazão (m³/h)": round(n * q_asp_m3h, 1),
                       "Derivações": ", ".join(sorted({str(l.derivacao + 1) for l in lats}))})
    return pd.DataFrame(linhas)
