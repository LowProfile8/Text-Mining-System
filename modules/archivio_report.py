import streamlit as st

from core import dati
from core.stile import bottone, intestazione, riquadro


def render():
    intestazione("Archivio report", "Report già generati: i prezzi usati sono congelati.")
    elenco = dati.elenco_report()
    if not elenco:
        st.info("Nessun report archiviato.")
        return
    for r in elenco:
        with riquadro("bianco", f"arc_{r['id']}"):
            a, b, c = st.columns([4, 1.3, 1], vertical_alignment="center")
            a.markdown(f"**{r['cliente']}** — {r['tipo']}  \n<span style='color:#9A9AA2'>{r['da']} → {r['a']} · creato {r['creato'][:16].replace('T', ' ')}</span>", unsafe_allow_html=True)
            pdf = dati.pdf_report(r["id"])
            if pdf:
                b.download_button("PDF", pdf, file_name=f"Report_{r['cliente'].replace(' ', '_')}_{r['a']}.pdf", mime="application/pdf", key=f"dl_{r['id']}")
            if bottone("Elimina", "giallo", f"del_{r['id']}"):
                dati.elimina_report(r["id"])
                st.rerun()
