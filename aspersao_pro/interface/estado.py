"""Estado da sessão e componentes de formulário vinculados ao projeto."""

from __future__ import annotations

import streamlit as st

from aspersao.pipeline import ErroEtapa, Pipeline
from aspersao.projeto import projeto_padrao

PREFIXO = "w__"


def iniciar():
    if "projeto" not in st.session_state:
        st.session_state["projeto"] = projeto_padrao()
    if "cache_pipeline" not in st.session_state:
        st.session_state["cache_pipeline"] = {}
    st.session_state.setdefault("segredos", {"google_key": "", "gee_projeto": ""})
    st.session_state.setdefault("geracao", 0)
    st.session_state.setdefault("versoes", {})


def P() -> dict:
    return st.session_state["projeto"]


def pipe() -> Pipeline:
    return Pipeline(P(), st.session_state["cache_pipeline"])


def carregar_projeto(novo: dict):
    """Troca o projeto. A geração dos widgets é incrementada para que o navegador não
    reenvie valores antigos dos formulários."""
    st.session_state["projeto"] = novo
    st.session_state["cache_pipeline"] = {}
    st.session_state["geracao"] = st.session_state.get("geracao", 0) + 1
    st.session_state["versoes"] = {}
    for k in list(st.session_state.keys()):
        if isinstance(k, str) and (k.startswith(PREFIXO) or k.startswith("tmp_")):
            del st.session_state[k]


def chave(secao, campo):
    ver = st.session_state.get("versoes", {}).get(f"{secao}.{campo}", 0)
    return f"{PREFIXO}{st.session_state.get('geracao', 0)}_{ver}__{secao}__{campo}"


def renovar(secao, campo):
    """Força a recriação do widget do campo (novo valor vindo do projeto)."""
    v = st.session_state.setdefault("versoes", {})
    v[f"{secao}.{campo}"] = v.get(f"{secao}.{campo}", 0) + 1


def definir(secao, campo, valor):
    """Altera um valor do projeto por código e recria o widget correspondente."""
    P()[secao][campo] = valor
    renovar(secao, campo)


def num(rotulo, secao, campo, minimo=None, maximo=None, passo=None, fmt=None, ajuda=None, alvo=None, inteiro=False,
        desabilitado=False):
    alvo = alvo or st
    atual = P()[secao].get(campo)
    if inteiro:
        atual = int(atual or 0)
        minimo = None if minimo is None else int(minimo)
        maximo = None if maximo is None else int(maximo)
        passo = int(passo or 1)
    else:
        atual = float(atual if atual is not None else (minimo or 0.0))
        minimo = None if minimo is None else float(minimo)
        maximo = None if maximo is None else float(maximo)
        passo = None if passo is None else float(passo)
        if minimo is not None:
            atual = max(atual, minimo)
        if maximo is not None:
            atual = min(atual, maximo)
    v = alvo.number_input(rotulo, min_value=minimo, max_value=maximo, value=atual, step=passo, format=fmt,
                          help=ajuda, key=chave(secao, campo), disabled=desabilitado)
    P()[secao][campo] = v
    return v


def sel(rotulo, secao, campo, opcoes, formato=None, ajuda=None, alvo=None, horizontal=False, radio=False):
    alvo = alvo or st
    chaves = list(opcoes.keys()) if isinstance(opcoes, dict) else list(opcoes)
    fmt = formato or ((lambda k: opcoes[k]) if isinstance(opcoes, dict) else str)
    atual = P()[secao].get(campo)
    idx = chaves.index(atual) if atual in chaves else 0
    if radio:
        v = alvo.radio(rotulo, chaves, index=idx, format_func=fmt, help=ajuda, key=chave(secao, campo),
                       horizontal=horizontal)
    else:
        v = alvo.selectbox(rotulo, chaves, index=idx, format_func=fmt, help=ajuda, key=chave(secao, campo))
    P()[secao][campo] = v
    return v


def txt(rotulo, secao, campo, ajuda=None, alvo=None, area=False):
    alvo = alvo or st
    fn = alvo.text_area if area else alvo.text_input
    v = fn(rotulo, value=str(P()[secao].get(campo) or ""), help=ajuda, key=chave(secao, campo))
    P()[secao][campo] = v
    return v


def chk(rotulo, secao, campo, ajuda=None, alvo=None):
    alvo = alvo or st
    v = alvo.toggle(rotulo, value=bool(P()[secao].get(campo)), help=ajuda, key=chave(secao, campo))
    P()[secao][campo] = v
    return v


def deslizante(rotulo, secao, campo, minimo, maximo, passo, ajuda=None, alvo=None, fmt=None):
    alvo = alvo or st
    atual = float(P()[secao].get(campo) or minimo)
    atual = min(max(atual, float(minimo)), float(maximo))
    v = alvo.slider(rotulo, float(minimo), float(maximo), atual, float(passo), help=ajuda, key=chave(secao, campo),
                    format=fmt)
    P()[secao][campo] = v
    return v


def etapa(nome, mensagem_sem_dados=True):
    """Obtém o resultado de uma etapa; exibe aviso amigável se faltar informação."""
    try:
        return pipe().get(nome)
    except ErroEtapa as exc:
        if mensagem_sem_dados:
            st.warning(f"⚠️ {exc}")
        return None


def avisos(lista, tipo="warning"):
    for a in lista or []:
        getattr(st, tipo)(a, icon="⚠️" if tipo == "warning" else "ℹ️")


def fmt_br(valor, casas=2):
    """Número no formato brasileiro (1.234,56)."""
    if valor is None:
        return "—"
    try:
        s = f"{float(valor):,.{casas}f}"
    except (TypeError, ValueError):
        return str(valor)
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


def cabecalho(titulo, subtitulo=None, icone=None):
    st.title(f"{icone + ' ' if icone else ''}{titulo}")
    if subtitulo:
        st.caption(subtitulo)
