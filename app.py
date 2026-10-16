"""app.py — punto d'ingresso. Avvio locale:  streamlit run app.py

Viste (st.session_state["vista"]):
    home              scelta del programma
    clienti           elenco clienti
    cliente           scheda cliente: estratti conto, movimenti, posizioni, dati
    report            crea report (trimestrale / semestrale / annuale)
    archivio_report   report salvati
"""

import streamlit as st

from core import db
from core.config import NOME_STUDIO, TITOLO_PAGINA
from core.nav import vai
from core.stile import applica_stile, logo_html, nascondi_barra_laterale
from modules import archivio_report, cliente, clienti, home, report

VISTE = {
    "home": home.render,
    "clienti": clienti.render,
    "cliente": cliente.render,
    "report": report.render,
    "archivio_report": archivio_report.render,
}
VOCE_MENU = {"home": "home", "clienti": "clienti", "cliente": "clienti", "report": "report", "archivio_report": "archivio_report"}


def _password_attesa() -> str | None:
    """APP_PASSWORD dai secrets. In locale (senza Supabase) vale 'Athena'. Con il cloud collegato e senza
    APP_PASSWORD l'accesso viene RIFIUTATO: i dati dei clienti non devono stare dietro una password di default."""
    try:
        return str(st.secrets["APP_PASSWORD"])
    except Exception:
        pass
    stato, _ = db.stato_cloud()
    return "Athena" if stato == "locale" else None


def _accesso_consentito() -> bool:
    if st.session_state.get("_autenticato"):
        return True
    nascondi_barra_laterale()
    attesa = _password_attesa()
    _, centro, _ = st.columns([1, 1.3, 1])
    with centro:
        st.markdown(logo_html(260, centrato=True), unsafe_allow_html=True)
        if attesa is None:
            st.error("Accesso bloccato: il cloud è collegato ma manca `APP_PASSWORD` nei Secrets di Streamlit. "
                     "Impostala (Settings → Secrets) e riavvia l'app.")
            return False
        st.markdown("<div class='spazio-accesso'></div>", unsafe_allow_html=True)
        col_campo, col_tasto = st.columns([4, 1], gap="small", vertical_alignment="bottom")
        with col_campo:
            codice = st.text_input("Password", key="campo_password", type="password", label_visibility="collapsed")
        with col_tasto:
            st.button("→", key="invia_password")
        if codice and codice != attesa:
            st.markdown("<p class='accesso-errore'>Codice non corretto.</p>", unsafe_allow_html=True)
    if codice and codice == attesa:
        st.session_state["_autenticato"] = True
        st.session_state.pop("campo_password", None)
        st.rerun()
    return False


def _voce_menu(etichetta: str, vista: str) -> None:
    attiva = VOCE_MENU.get(st.session_state.get("vista", "home")) == vista
    chiave = "side_attivo" if attiva else f"side_{vista}"
    with st.container(key=chiave):
        if st.button(etichetta, key=f"menu_{vista}", width="stretch"):
            vai(vista)


def _barra_laterale() -> None:
    with st.sidebar:
        st.markdown(logo_html(150), unsafe_allow_html=True)
        st.divider()
        _voce_menu("Home", "home")
        st.write("")
        _voce_menu("Clienti", "clienti")
        _voce_menu("Crea report", "report")
        _voce_menu("Archivio report", "archivio_report")


def _stato_fisso() -> None:
    stato, _ = db.stato_cloud()
    if stato == "attivo":
        html = "<span class='cloud-pallino cloud-verde'></span>Cloud collegato"
    else:
        html = "<span class='cloud-pallino cloud-giallo'></span>Cloud scollegato"
    st.markdown(f"<div class='cloud-fisso'>{html}</div>", unsafe_allow_html=True)


def _avviso_cloud() -> None:
    stato, dettaglio = db.stato_cloud()
    if stato == "attivo":
        return
    if stato == "locale":
        st.warning("**Cloud non collegato.** I dati si salvano solo su questo computer (su Streamlit Cloud si azzerano a ogni riavvio): usa solo dati di prova.  \n"
                   "Per collegarlo: Settings → Secrets, inserisci `SUPABASE_URL` e `SUPABASE_KEY`, poi riavvia l'app.")
    else:
        st.warning("**Il cloud non risponde.** I dati non vengono salvati finché non torna attivo.  \n"
                   "1. Controlla la connessione e ricarica la pagina.  \n"
                   "2. Il piano gratuito di Supabase va in pausa dopo 7 giorni senza attività: apri supabase.com, scegli il progetto e premi **Restore project**.  \n"
                   "3. Verifica `SUPABASE_URL` e `SUPABASE_KEY` nei Secrets.  \n"
                   f"_Dettaglio tecnico: {dettaglio}_")
        st.stop()


def _riscalda_prezzi() -> None:
    """All'apertura del sito scarica in background storici e cambi di tutti i clienti: quando apri una strategia i prezzi sono già pronti."""
    if st.session_state.get("_riscaldato"):
        return
    st.session_state["_riscaldato"] = True
    import threading

    def lavoro():
        try:
            from core import calcolo, dati as d
            from core.live import RIFERIMENTO
            reg = d.carica_registro()
            m = calcolo.mercato_reale(manuali=d.carica_manuali())
            strum, coppie = {}, set()
            for c in d.elenco_clienti():
                for pf in c.get("portafogli", []):
                    for t in c.get("transazioni", []):
                        x = reg.strumenti.get(t.get("strumento"))
                        if x and x.get("valutazione") == "mercato":
                            strum[x["chiave"]] = x
                        if x and x.get("valuta") and x["valuta"] != pf["valuta"]:
                            coppie.add((x["valuta"], pf["valuta"]))
                    if pf["valuta"] != RIFERIMENTO:
                        coppie.add((pf["valuta"], RIFERIMENTO))
            m.precarica(list(strum.values()), sorted(coppie))
        except Exception:
            pass
    threading.Thread(target=lavoro, daemon=True).start()


def main() -> None:
    st.set_page_config(page_title=TITOLO_PAGINA, layout="wide", initial_sidebar_state="expanded")
    applica_stile()
    if not _accesso_consentito():
        return
    _riscalda_prezzi()
    _barra_laterale()
    _stato_fisso()
    _avviso_cloud()
    vista = st.session_state.get("vista", "home")
    if vista not in VISTE:
        vai("home")
        return
    try:
        VISTE[vista]()
    except (OSError, ConnectionError) as errore:
        st.warning(f"Non riesco a leggere o scrivere i dati ({errore}). Controlla il messaggio qui sopra e riprova.")
        st.stop()


if __name__ == "__main__":
    main()
