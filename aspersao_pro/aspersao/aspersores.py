"""Catálogo de aspersores e relações vazão-pressão-alcance.

O catálogo de referência é GENÉRICO: as vazões são calculadas pela equação do
orifício (Cd = 0,95) e os diâmetros molhados por relação empírica ajustada a
catálogos típicos de aspersores de impacto. Para projetos executivos, substitua
ou complemente com os dados do fabricante (importação CSV na interface).
"""

from __future__ import annotations

import io
import math
from dataclasses import asdict, dataclass, field

import numpy as np
import pandas as pd

from .unidades import G, KPA_POR_MCA


@dataclass
class Aspersor:
    id: str
    fabricante: str
    modelo: str
    tipo: str
    bocal: str
    d_bocal_mm: float  # diâmetro do bocal principal (usado nas perdas por evaporação)
    pressoes_kpa: list
    vazoes_m3h: list
    diametros_m: list
    angulo_graus: float = 25.0
    nota: str = ""
    perfil_padrao: str = "auto"
    radial: list = field(default_factory=list)  # [[r_m, lamina_rel], ...] opcional

    # ----------------------------------------------------------------- ajustes
    def coef_k_x(self):
        """Ajuste q = k · P^x (q em m³/h, P em kPa) por regressão log-log."""
        p = np.asarray(self.pressoes_kpa, dtype=float)
        q = np.asarray(self.vazoes_m3h, dtype=float)
        if len(p) < 2:
            return q[0] / math.sqrt(p[0]), 0.5
        x, lnk = np.polyfit(np.log(p), np.log(q), 1)
        return float(np.exp(lnk)), float(x)

    def vazao(self, p_kpa):
        k, x = self.coef_k_x()
        return k * np.asarray(p_kpa, dtype=float) ** x

    def diametro(self, p_kpa):
        p = np.asarray(self.pressoes_kpa, dtype=float)
        d = np.asarray(self.diametros_m, dtype=float)
        if len(p) < 2:
            return float(d[0])
        # interpolação linear com extrapolação limitada
        coef = np.polyfit(p, d, 1)
        val = np.polyval(coef, p_kpa)
        return float(np.clip(val, 0.6 * d.min(), 1.15 * d.max()))

    @property
    def p_min(self):
        return float(min(self.pressoes_kpa))

    @property
    def p_max(self):
        return float(max(self.pressoes_kpa))

    @property
    def p_nominal(self):
        return float(np.median(self.pressoes_kpa))

    def to_dict(self):
        return asdict(self)

    @property
    def rotulo(self):
        return f"{self.fabricante} {self.modelo} — bocal {self.bocal} mm"


def vazao_orificio(d_mm_lista, p_kpa, cd=0.95):
    """Vazão (m³/h) de bocais circulares pela equação do orifício."""
    h = p_kpa / KPA_POR_MCA
    area = sum(math.pi / 4.0 * (d / 1000.0) ** 2 for d in d_mm_lista)
    return cd * area * math.sqrt(2.0 * G * h) * 3600.0


def diametro_molhado_empirico(d_mm, p_kpa, fator=1.0):
    """Diâmetro molhado (m) estimado: Dm = 3,95 · d^0,5 · H^0,35 (d em mm, H em mca)."""
    h = p_kpa / KPA_POR_MCA
    return fator * 3.95 * math.sqrt(d_mm) * h ** 0.35


def _gerar(id_, tipo, bocais, pressoes, angulo=25.0, fator_alcance=1.0, nota=""):
    q = [round(vazao_orificio(bocais, p), 3) for p in pressoes]
    dm = [round(diametro_molhado_empirico(bocais[0], p, fator_alcance), 1) for p in pressoes]
    bocal_txt = " x ".join(f"{b:.1f}" for b in bocais)
    return Aspersor(
        id=id_, fabricante="Genérico", modelo=tipo, tipo=tipo, bocal=bocal_txt,
        d_bocal_mm=bocais[0], pressoes_kpa=list(pressoes), vazoes_m3h=q, diametros_m=dm,
        angulo_graus=angulo, nota=nota or "Valores de referência (equação do orifício). Confirme no catálogo do fabricante.",
    )


def catalogo_referencia() -> list[Aspersor]:
    cat = []
    for d in (2.0, 2.5, 3.0):
        cat.append(_gerar(f"MINI-{d:.1f}", "Mini-aspersor rotativo", [d], [150, 200, 250, 300], 20.0, 0.95))
    for d in (3.2, 3.6, 4.0):
        cat.append(_gerar(f"SUBCOPA-{d:.1f}", "Subcopa (ângulo baixo)", [d], [150, 200, 250, 300], 7.0, 0.80,
                          "Aspersor de jato baixo para irrigação sob a copa (cacau, citros, café)."))
    for d in (3.2, 3.6, 4.0, 4.4):
        cat.append(_gerar(f"IMP-P-{d:.1f}", "Impacto pequeno (1 bocal)", [d], [200, 250, 300, 350]))
    for b in ((4.0, 2.4), (4.4, 2.4), (4.8, 2.4), (5.0, 3.2), (5.6, 3.2), (6.0, 3.2), (6.5, 3.2)):
        cat.append(_gerar(f"IMP-M-{b[0]:.1f}x{b[1]:.1f}", "Impacto médio (2 bocais)", list(b), [250, 300, 350, 400, 450]))
    for b in ((7.0, 3.2), (8.0, 4.0), (9.0, 4.0), (10.0, 4.0)):
        cat.append(_gerar(f"IMP-G-{b[0]:.1f}x{b[1]:.1f}", "Impacto grande (2 bocais)", list(b), [350, 400, 450, 500, 550]))
    for d in (14.0, 16.0, 18.0, 20.0, 22.0):
        cat.append(_gerar(f"CANHAO-{d:.0f}", "Canhão hidráulico", [d], [400, 500, 600, 700], 24.0, 0.98))
    return cat


def aspersor_estudo_caso_openirri() -> Aspersor:
    """Aspersor do estudo de caso de El-Naggar (2026) — Tabela 1 (520 L/h @ 276 kPa, Dm 28 m).

    Curva q-P completada com x = 0,5 (bocal de orifício) para permitir análise hidráulica.
    """
    p = [207.0, 241.0, 276.0, 310.0, 345.0]
    q = [round(0.520 * math.sqrt(pi / 276.0), 4) for pi in p]
    dm = [26.5, 27.3, 28.0, 28.6, 29.1]
    return Aspersor(
        id="CASO-OPENIRRI", fabricante="Estudo de caso", modelo="Impacto 4,0 x 2,0 mm (El-Naggar, 2026)",
        tipo="Impacto médio (2 bocais)", bocal="4.0 x 2.0", d_bocal_mm=4.0, pressoes_kpa=p, vazoes_m3h=q,
        diametros_m=dm, angulo_graus=23.0,
        nota="Ponto 276 kPa / 520 L/h / Dm 28 m conforme El-Naggar (2026), Tab. 1; demais pontos por x = 0,5.",
    )


def catalogo_completo(usuario: list | None = None) -> list[Aspersor]:
    cat = catalogo_referencia() + [aspersor_estudo_caso_openirri()]
    for d in usuario or []:
        try:
            cat.append(Aspersor(**d))
        except TypeError:
            continue
    return cat


def buscar_aspersor(asp_id: str, usuario: list | None = None) -> Aspersor:
    for a in catalogo_completo(usuario):
        if a.id == asp_id:
            return a
    return catalogo_referencia()[10]


def catalogo_df(cat: list[Aspersor]) -> pd.DataFrame:
    linhas = []
    for a in cat:
        k, x = a.coef_k_x()
        linhas.append({
            "ID": a.id, "Fabricante": a.fabricante, "Tipo": a.tipo, "Bocal (mm)": a.bocal,
            "Pressões (kPa)": f"{a.p_min:.0f}–{a.p_max:.0f}",
            "Vazão (m³/h)": f"{min(a.vazoes_m3h):.2f}–{max(a.vazoes_m3h):.2f}",
            "Diâm. molhado (m)": f"{min(a.diametros_m):.1f}–{max(a.diametros_m):.1f}",
            "k": round(k, 5), "x": round(x, 3),
        })
    return pd.DataFrame(linhas)


# ---------------------------------------------------------------------------
# Importação de catálogo do fabricante (CSV)
# ---------------------------------------------------------------------------
MODELO_CSV_ASPERSOR = (
    "id;fabricante;modelo;tipo;bocal;d_bocal_mm;pressao_kpa;vazao_m3h;diametro_m;angulo\n"
    "FAB-A-4.6x3.2;Fabricante X;Modelo A;Impacto médio (2 bocais);4.6 x 3.2;4,6;250;1,62;27,0;26\n"
    "FAB-A-4.6x3.2;Fabricante X;Modelo A;Impacto médio (2 bocais);4.6 x 3.2;4,6;300;1,77;28,0;26\n"
    "FAB-A-4.6x3.2;Fabricante X;Modelo A;Impacto médio (2 bocais);4.6 x 3.2;4,6;350;1,92;29,0;26\n"
)


def importar_csv_aspersores(conteudo: bytes) -> list[dict]:
    """Importa catálogo do fabricante (uma linha por ponto pressão-vazão-diâmetro)."""
    texto = conteudo.decode("utf-8-sig", errors="ignore")
    sep = ";" if texto.count(";") >= texto.count(",") else ","
    df = pd.read_csv(io.StringIO(texto), sep=sep, decimal="," if sep == ";" else ".")
    df.columns = [c.strip().lower() for c in df.columns]
    obrig = {"id", "pressao_kpa", "vazao_m3h", "diametro_m"}
    if not obrig.issubset(df.columns):
        raise ValueError(f"Colunas obrigatórias: {sorted(obrig)}")
    saida = []
    for id_, g in df.groupby("id"):
        g = g.sort_values("pressao_kpa")
        primeira = g.iloc[0]
        saida.append(Aspersor(
            id=str(id_), fabricante=str(primeira.get("fabricante", "Usuário")),
            modelo=str(primeira.get("modelo", id_)), tipo=str(primeira.get("tipo", "Impacto")),
            bocal=str(primeira.get("bocal", "")), d_bocal_mm=float(primeira.get("d_bocal_mm", 4.0)),
            pressoes_kpa=[float(v) for v in g["pressao_kpa"]], vazoes_m3h=[float(v) for v in g["vazao_m3h"]],
            diametros_m=[float(v) for v in g["diametro_m"]], angulo_graus=float(primeira.get("angulo", 25.0)),
            nota="Importado do catálogo do fabricante pelo usuário.",
        ).to_dict())
    return saida


# ---------------------------------------------------------------------------
# Recomendações de espaçamento
# ---------------------------------------------------------------------------
TABELA_ESPACAMENTO = pd.DataFrame({
    "Vento (m/s)": ["0 – 2", "2 – 3,5", "> 3,5"],
    "Quadrado (% Dm)": [65, 55, 45],
    "Retangular — na linha (% Dm)": [50, 45, 40],
    "Retangular — entre linhas (% Dm)": [75, 65, 55],
    "Triangular (% Dm)": [70, 60, 50],
})


def espacamento_maximo_recomendado(dm: float, vento_ms: float, arranjo: str = "retangular"):
    """Espaçamentos máximos (na linha, entre linhas) em metros segundo a prática
    (Keller & Bliesner; Bernardo et al.). A verificação definitiva é o CUC simulado."""
    if vento_ms <= 2.0:
        lin = 0
    elif vento_ms <= 3.5:
        lin = 1
    else:
        lin = 2
    t = TABELA_ESPACAMENTO.iloc[lin]
    if arranjo == "triangular":
        e = t["Triangular (% Dm)"] / 100 * dm
        return e, e
    return t["Retangular — na linha (% Dm)"] / 100 * dm, t["Retangular — entre linhas (% Dm)"] / 100 * dm
