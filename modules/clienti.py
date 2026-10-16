import streamlit as st

from core import dati
from core.config import VALUTE_BASE
from core.nav import vai
from core.stile import bottone, intestazione


def render():
    intestazione("Clienti", "Archivio dei clienti con le loro posizioni.")
    with st.container(border=True):                                           # stessa forma delle schede dei clienti
        a, b = st.columns([4, 1], vertical_alignment="center")
        a.markdown("**Nuovo cliente**  \n<span style='color:#9A9AA2'>Aggiungi un cliente all'archivio</span>", unsafe_allow_html=True)
        if b.button("Nuovo cliente", key="nc_apri", width="stretch"):
            st.session_state["nc_aperto"] = not st.session_state.get("nc_aperto", False)
            st.rerun()
    if st.session_state.get("nc_aperto"):
        with st.container(border=True):
            c1, c2 = st.columns(2)
            nome = c1.text_input("Nome", key="nc_nome")
            cognome = c2.text_input("Cognome", key="nc_cogn")
            c1, c2 = st.columns(2)
            valuta = c1.selectbox("Valuta di riferimento", VALUTE_BASE, key="nc_val")
            rischio = c2.selectbox("Grado di rischio (1 basso – 5 alto)", [1, 2, 3, 4, 5], index=1, key="nc_risc")
            if bottone("Crea cliente", "verde", "nc_crea") and (nome.strip() or cognome.strip()):
                c = dati.nuovo_cliente(nome, valuta, rischio, cognome=cognome)
                st.session_state.pop("nc_aperto", None)
                vai("cliente", cli_id=c["id"])
    elenco = dati.elenco_clienti()
    if not elenco:
        st.info("Nessun cliente. Creane uno qui sopra.")
        return
    for c in elenco:
        with st.container(border=True):
            a, b = st.columns([4, 1], vertical_alignment="center")
            a.markdown(f"**{c['nome']}**  \n<span style='color:#9A9AA2'>{c['valuta_base']} · rischio {c.get('rischio', '-')} · {len(c.get('portafogli', []))} portafogli</span>", unsafe_allow_html=True)
            if b.button("Apri", key=f"ap_{c['id']}", width="stretch"):
                vai("cliente", cli_id=c["id"])
