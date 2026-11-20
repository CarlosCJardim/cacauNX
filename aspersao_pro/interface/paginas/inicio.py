"""Página inicial: dados do projeto, exemplos, abrir/salvar e status do fluxo."""

from __future__ import annotations

import streamlit as st

from aspersao import NOME_PROGRAMA
from aspersao.projeto import EXEMPLOS, abrir, projeto_padrao

from .. import estado
from ..estado import P, txt

ETAPAS = [
    ("geo", "Área do projeto", "area"),
    ("elev", "Altimetria", "altimetria"),
    ("clima", "Clima e ETo", "clima"),
    ("kc", "Coeficiente de cultura", "cultura"),
    ("aspersor", "Aspersor e uniformidade", "aspersor"),
    ("agronomico", "Lâminas de projeto", "cultura"),
    ("layout", "Layout da rede", "layout"),
    ("operacao", "Setorização", "operacao"),
    ("rede", "Dimensionamento hidráulico", "hidraulica"),
    ("bomba", "Bomba e energia", "bomba"),
    ("custos", "Orçamento", "orcamento"),
]


def pagina():
    st.title(f"💧 {NOME_PROGRAMA}")
    st.markdown("#### Projeto profissional de irrigação por aspersão convencional com **manejo pelo clima**")
    st.markdown(
        '<div class="bloco-nota">Fluxo completo em uma única ferramenta: área sobre imagem do Google Earth → '
        "altimetria (MDE) → clima e ETo (FAO-56 Penman-Monteith) → Kc e lâminas de projeto → aspersor e "
        "uniformidade (Christiansen) → setorização → layout automático da rede → hidráulica passo a passo com "
        "cotas reais → bomba, NPSH e energia → orçamento → boletim de irrigação pelo clima → memorial em PDF.</div>",
        unsafe_allow_html=True)

    c1, c2, c3 = st.columns([1.2, 1, 1])
    with c1:
        st.subheader("Começar")
        ex = st.selectbox("Projetos-exemplo", list(EXEMPLOS.keys()), key="tmp_exemplo")
        b1, b2 = st.columns(2)
        if b1.button("📂 Carregar exemplo", type="primary", width="stretch"):
            estado.carregar_projeto(EXEMPLOS[ex]())
            st.rerun()
        if b2.button("🆕 Projeto em branco", width="stretch"):
            estado.carregar_projeto(projeto_padrao())
            st.rerun()
        arq = st.file_uploader("Abrir projeto salvo (.json)", type=["json"], key="tmp_abrir")
        if arq is not None and st.button("Abrir arquivo", width="stretch"):
            try:
                estado.carregar_projeto(abrir(arq.getvalue()))
                st.success("Projeto aberto.")
                st.rerun()
            except Exception as exc:  # noqa: BLE001
                st.error(f"Arquivo inválido: {exc}")
    with c2:
        st.subheader("Identificação")
        txt("Nome do projeto", "info", "nome")
        txt("Cliente / produtor", "info", "cliente")
        txt("Propriedade", "info", "propriedade")
        a, b = st.columns([3, 1])
        txt("Município", "info", "municipio", alvo=a)
        txt("UF", "info", "uf", alvo=b)
    with c3:
        st.subheader("Responsável técnico")
        txt("Engenheiro(a) responsável", "info", "responsavel")
        txt("Registro profissional (CREA/CFTA) e ART", "info", "registro")
        txt("Observações", "info", "observacoes", area=True)

    st.divider()
    st.subheader("Situação do projeto")
    p = estado.pipe()
    cols = st.columns(4)
    for i, (et, nome, _) in enumerate(ETAPAS):
        try:
            p.get(et)
            icone, msg = "✅", "concluída"
        except Exception as exc:  # noqa: BLE001
            icone, msg = "⬜", str(exc)[:120]
        cols[i % 4].markdown(f"{icone} **{nome}**  \n<small>{msg}</small>", unsafe_allow_html=True)

    with st.expander("Sobre o método e as referências"):
        st.markdown("""
- **Clima e ETo** — FAO-56 Penman-Monteith (Allen et al., 1998), com procedimentos para dados ausentes e
  Hargreaves-Samani; dados da NASA POWER, Open-Meteo (ERA5 e previsão) e estações automáticas do INMET.
- **Manejo pelo clima** — a lâmina repõe a ETc acumulada menos a chuva efetiva; o turno de rega é decisão
  operacional (não depende da água disponível no solo). ETc de projeto por Kc×ETo máxima, maior ETc mensal do
  ciclo ou análise de frequência (quantil dos máximos anuais da média móvel do turno de rega).
- **Uniformidade** — superposição de perfis radiais (CUC de Christiansen, CUD e CUH), com distorção pelo vento;
  eficiência de distribuição para a área adequadamente irrigada (Keller & Bliesner) e perdas por evaporação e
  deriva (Trimmer, 1987).
- **Hidráulica** — Hazen-Williams ou Darcy-Weisbach (Swamee-Jain); fator F de Christiansen e cálculo passo a passo
  com a cota de cada aspersor; variação de pressão ≤ 20 % na lateral; dimensionamento de derivações, principal e
  adutora por velocidade ou custo anual mínimo; reguladores de pressão; golpe de aríete (Joukowsky/Michaud).
- **Bombeamento** — altura manométrica, NPSH disponível × requerido, potências, motor comercial, curvas e ponto de
  operação, leis de afinidade (inversor) e tarifa noturna para irrigantes.
- Inspirado no fluxo do **OpenIrri** (El-Naggar, *SoftwareX* 35, 2026, 102912), estendido com altimetria,
  integração com Google Earth/Earth Engine e manejo pelo clima.
""")
