"""Navigazione fra le viste (st.session_state['vista'])."""

import streamlit as st

# Chiavi di sessione di ogni vista: uscendo si azzerano, così rientrando si riparte da zero
_PREFISSI = {"report": ("rep_",), "cliente": ("cli_",)}


def vai(vista: str, **stato) -> None:
    attuale = st.session_state.get("vista")
    if attuale != vista:
        for prefisso in _PREFISSI.get(attuale, ()):
            for k in [k for k in st.session_state if isinstance(k, str) and k.startswith(prefisso)]:
                del st.session_state[k]
    st.session_state["vista"] = vista
    st.session_state.update(stato)
    st.rerun()
