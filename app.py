#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Athena Advisory Group Sagl — Text Mining System
"""

import streamlit as st
import pandas as pd
import io
import json
import zipfile
import re
from engine_ai import elabora_documenti_banana, genera_archivio_zip, esporta_per_banana, esporta_per_excel

# ==============================================================================
# 1. CONFIGURAZIONE PAGINA
# ==============================================================================
st.set_page_config(
    page_title="Athena Advisory Group Sagl",
    layout="wide",
    initial_sidebar_state="expanded"
)

LOGO_ATHENA_RAW = """<svg viewBox="0 0 350 350" fill="none" xmlns="http://www.w3.org/2000/svg" style="width:100%;height:100%;max-width:130px;">
    <path d="M175 20 L320 103.7 L320 271.3 L175 355 L30 271.3 L30 103.7 Z" stroke="#ffffff" stroke-width="6" stroke-linejoin="round"/>
    <path d="M175 20 L175 187.5 M175 187.5 L30 103.7 M175 187.5 L320 103.7" stroke="#ffffff" stroke-width="4" stroke-linejoin="round"/>
    <path d="M175 62 L285 125.5 L285 252.5 L175 316 L65 252.5 L65 125.5 Z" stroke="#ffffff" stroke-width="3" stroke-linejoin="round" opacity="0.35"/>
    <path d="M175 110 L245 150.4 L245 231.6 L175 272 L105 231.6 L105 150.4 Z" stroke="#ffffff" stroke-width="5" stroke-linejoin="round"/>
    <path d="M175 110 L175 191 M175 191 L105 150.4 M175 191 L245 150.4" stroke="#ffffff" stroke-width="4" stroke-linejoin="round"/>
</svg>"""

# ==============================================================================
# 2. CSS
# ==============================================================================
st.markdown("""
<style>
/* FONT GLOBALE */
* {
    font-family: "Helvetica Neue", Helvetica, Arial, sans-serif !important;
}

/* SFONDO */
.stApp { background-color: #000000; color: #ffffff; }

/* TESTI */
h1, h2, h3, h4, h5, h6, p, label, span { color: #ffffff !important; }

/* BLOCCO CENTRALE */
.block-container {
    max-width: 860px !important;
    padding-top: 2.5rem !important;
    padding-bottom: 6rem !important;
}

/* SIDEBAR */
[data-testid="stSidebar"] {
    background-color: #0d0d0d !important;
    border-right: 1px solid #1c1c1e !important;
    padding-top: 1.5rem !important;
}
[data-testid="stSidebar"] * { color: #ffffff !important; }

/* Nasconde freccia collasso sidebar */
[data-testid="collapsedControl"],
[data-testid="stSidebarActionButton"] { display: none !important; }

/* ── FILE UPLOADER ── */
[data-testid="stFileUploaderDropzoneInstructions"],
[data-testid="stFileUploaderDropzoneInstructions"] * {
    display: none !important;
}
[data-testid="stFileUploaderDropzone"] button span,
[data-testid="stFileUploaderDropzone"] button p,
[data-testid="stFileUploaderDropzone"] button div {
    display: none !important;
}
[data-testid="stFileUploader"] {
    border: 1px dashed #2c2c2e !important;
    background-color: #09090b !important;
    border-radius: 10px !important;
    padding: 8px 14px !important;
}
[data-testid="stFileUploader"] > label {
    display: block !important;
    visibility: visible !important;
    font-size: 0.8rem !important;
    font-weight: 500 !important;
    color: #aeaeb2 !important;
    margin-bottom: 6px !important;
}
[data-testid="stFileUploaderDropzone"] button {
    background-color: #1c1c1e !important;
    color: transparent !important;
    border: 1px solid #2c2c2e !important;
    border-radius: 6px !important;
    font-size: 0 !important;
    padding: 4px 12px !important;
    min-width: 80px !important;
    min-height: 28px !important;
    position: relative !important;
}
[data-testid="stFileUploaderDropzone"] button::after {
    content: "Sfoglia" !important;
    font-size: 0.75rem !important;
    color: #aeaeb2 !important;
    position: absolute !important;
    left: 50% !important;
    top: 50% !important;
    transform: translate(-50%, -50%) !important;
}
[data-testid="stFileUploader"] [data-testid="stFileUploaderFile"] button,
[data-testid="stFileUploader"] li button,
[data-testid="stFileUploader"] ul button {
    background-color: transparent !important;
    border: 1px solid #3a3a3c !important;
    color: #aeaeb2 !important;
    font-size: 0.8rem !important;
    padding: 2px 8px !important;
    position: relative !important;
    min-width: unset !important;
}
[data-testid="stFileUploader"] [data-testid="stFileUploaderFile"] button span,
[data-testid="stFileUploader"] li button span,
[data-testid="stFileUploader"] ul button span {
    display: block !important;
    visibility: visible !important;
    color: #aeaeb2 !important;
    font-size: 0.8rem !important;
}
[data-testid="stFileUploader"] [data-testid="stFileUploaderFile"] button::after,
[data-testid="stFileUploader"] li button::after,
[data-testid="stFileUploader"] ul button::after {
    content: none !important;
}

/* INPUT TEXT / PASSWORD */
input[type="text"], input[type="password"] {
    background-color: #1c1c1e !important;
    color: #ffffff !important;
    border: 1px solid #2c2c2e !important;
    border-radius: 8px !important;
}

/* Nasconde label del form login */
[data-testid="stForm"] [data-testid="stTextInput"] > label {
    display: none !important;
}

/* ── TASTO LOGIN ── */
[data-testid="stForm"] div.stFormSubmitButton > button,
[data-testid="stForm"] [data-testid="stFormSubmitButton"] > button,
[data-testid="stForm"] button[kind="primaryFormSubmit"],
[data-testid="stForm"] button[kind="secondaryFormSubmit"],
[data-testid="stForm"] div.stButton > button {
    background-color: #1c1c1e !important;
    color: #ffffff !important;
    border: 1px solid #3a3a3c !important;
    border-radius: 8px !important;
    font-weight: 600 !important;
    font-size: 0.85rem !important;
    letter-spacing: 0.06em !important;
    padding: 0.55rem 2rem !important;
    width: 100% !important;
}
[data-testid="stForm"] div.stFormSubmitButton > button:hover,
[data-testid="stForm"] [data-testid="stFormSubmitButton"] > button:hover,
[data-testid="stForm"] button[kind="primaryFormSubmit"]:hover,
[data-testid="stForm"] button[kind="secondaryFormSubmit"]:hover,
[data-testid="stForm"] div.stButton > button:hover {
    background-color: #2c2c2e !important;
}

/* ── TASTO LOGOUT ── */
div.stButton > button[key="logout_btn"] {
    background-color: #1c1c1e !important;
    color: #ffffff !important;
    border: 1px solid #3a3a3c !important;
    border-radius: 8px !important;
    font-weight: 500 !important;
    font-size: 0.78rem !important;
    letter-spacing: 0.06em !important;
}
div.stButton > button[key="logout_btn"]:hover {
    background-color: #2c2c2e !important;
}

/* ── TASTO AVVIA ELABORAZIONE ── */
div.stButton > button[key="elabora_btn_main"],
div.stButton > button[key="elabora_btn_main"]:focus,
div.stButton > button[key="elabora_btn_main"]:active,
div.stButton > button[key="elabora_btn_main"]:hover,
div.stButton > button[key="elabora_btn_main"]:visited,
div.stButton > button[key="elabora_btn_main"]:focus-visible {
    background-color: #ffd60a !important;
    color: #000000 !important;
    border: 2.5px solid #ff9f0a !important;
    border-radius: 10px !important;
    font-weight: 700 !important;
    font-size: 0.85rem !important;
    letter-spacing: 0.08em !important;
    padding: 0.65rem 2.5rem !important;
    width: auto !important;
    outline: 2.5px solid #ff9f0a !important;
    box-shadow: 0 0 0 2px #ff9f0a !important;
}
div.stButton > button[key="elabora_btn_main"]:hover {
    background-color: #ffcc00 !important;
    border-color: #ff6d00 !important;
    outline-color: #ff6d00 !important;
    box-shadow: 0 0 0 2px #ff6d00 !important;
}

/* ── TASTI DOWNLOAD ── */
[data-testid="stDownloadButton"] button {
    background-color: #1d4a3e !important;
    color: #ffffff !important;
    border: none !important;
    border-radius: 10px !important;
    font-weight: 600 !important;
    font-size: 0.82rem !important;
    letter-spacing: 0.08em !important;
    height: 80px !important;
    width: 100% !important;
}
[data-testid="stDownloadButton"] button:hover {
    background-color: #255f50 !important;
}

/* BADGE */
.badge-container {
    display: flex; flex-wrap: wrap; gap: 8px;
    margin-top: 6px; margin-bottom: 26px;
}
.badge-item {
    padding: 5px 13px; border-radius: 6px;
    font-size: 0.75rem; font-weight: 600;
    color: #000000 !important;
    text-transform: uppercase; letter-spacing: 0.04em;
}
.badge-forma   { background-color: #d6bbf2; }
.badge-flusso  { background-color: #ffd60a; }
.badge-settore { background-color: #34c759; }
.badge-iva     { background-color: #0a84ff; }
.badge-saldo   { background-color: #bf5af2; }

/* SEPARATORI */
hr { border: none !important; border-top: 1px solid #1c1c1e !important; margin: 20px 0 !important; }

/* EXPANDER */
[data-testid="stExpander"] {
    background-color: #0d0d0d !important;
    border: 1px solid #1c1c1e !important;
    border-radius: 8px !important;
    margin-top: 12px !important;
}
[data-testid="stExpander"] summary {
    font-size: 0 !important;
    color: transparent !important;
    padding: 12px 16px !important;
    cursor: pointer !important;
    display: flex !important;
    align-items: center !important;
    overflow: hidden !important;
    position: relative !important;
    min-height: 44px !important;
}
[data-testid="stExpander"] summary::after {
    content: "Visualizza Tracciato Registrazioni" !important;
    font-size: 0.82rem !important;
    color: #aeaeb2 !important;
    position: absolute !important;
    left: 16px !important;
    top: 50% !important;
    transform: translateY(-50%) !important;
}
[data-testid="stExpander"] summary > * {
    display: none !important;
}

/* TABELLA */
[data-testid="stDataFrame"] { border: 1px solid #1c1c1e !important; border-radius: 8px !important; }

/* PROGRESS BAR */
.stProgress > div > div { background-color: #ffd60a !important; }

/* LABEL SEZIONE */
.section-label {
    font-size: 0.68rem; font-weight: 700;
    color: #636366 !important; letter-spacing: 0.07em;
    text-transform: uppercase; margin-top: 14px; margin-bottom: 6px;
}

/* LEGENDA COLORI */
.legenda-container {
    display: flex; flex-wrap: wrap; gap: 10px;
    margin-top: 10px; margin-bottom: 6px;
}
.legenda-item {
    display: flex; align-items: center; gap: 6px;
    font-size: 0.7rem; color: #aeaeb2;
}
.legenda-dot {
    width: 12px; height: 12px; border-radius: 3px; flex-shrink: 0;
}

/* ZIP FATTURE placeholder */
.zip-placeholder {
    height: 80px;
    display: flex; align-items: center; justify-content: center;
    flex-direction: column;
    background-color: #1d4a3e;
    border: none; border-radius: 10px;
    color: #ffffff; font-size: 0.82rem; font-weight: 600;
    letter-spacing: 0.08em; text-align: center;
    opacity: 0.4; cursor: not-allowed; width: 100%;
}
.zip-placeholder small {
    font-size: 0.65rem !important; color: #aaaaaa !important; margin-top: 3px;
}

/* FOOTER */
.footer-athena {
    text-align: center; font-size: 0.62rem; color: #48484a !important;
    margin-top: 8rem; border-top: 1px solid #1c1c1e;
    padding-top: 20px; letter-spacing: 0.25em; text-transform: uppercase;
}
</style>
""", unsafe_allow_html=True)

# ==============================================================================
# 3. SESSION STATE
# ==============================================================================
for k, v in [
    ("autenticato", False),
    ("df_registrazioni", None),
    ("indici_complesse", []),
    ("buffer_excel_val", None),
    ("buffer_banana_val", None),
    ("pdf_rinominati_zip", None),
    ("indici_errore", []),
    ("indici_rosso", []),
    ("indici_giallo_dare", []),
    ("indici_separatori", []),
    ("log_elaborazione", []),
]:
    if k not in st.session_state:
        st.session_state[k] = v

# ==============================================================================
# 4. SCHERMATA LOGIN
# ==============================================================================
if not st.session_state["autenticato"]:

    st.markdown("<div style='height:10vh;'></div>", unsafe_allow_html=True)

    col_l, col_c, col_r = st.columns([1, 1.6, 1])
    with col_c:
        st.markdown(f"""
        <div style="text-align:center; margin-bottom:28px;">
            <div style="display:inline-block; width:88px; height:88px; margin-bottom:16px;">
                {LOGO_ATHENA_RAW}
            </div>
            <h1 style="font-size:1.85rem; font-weight:700; letter-spacing:-0.03em;
                       margin:0; padding:0; color:#ffffff;">Athena Advisory Group</h1>
            <p style="color:#636366; font-size:0.72rem; letter-spacing:0.18em;
                      margin-top:8px; text-transform:uppercase; padding:0;">
                Strategy for your Wealth
            </p>
        </div>
        """, unsafe_allow_html=True)

        with st.form(key="login_form", border=False):
            pwd_input = st.text_input(
                label="Chiave di accesso",
                type="password",
                placeholder="••••••••",
                label_visibility="collapsed",
            )
            st.markdown("<div style='height:10px;'></div>", unsafe_allow_html=True)
            submitted = st.form_submit_button("ACCEDI", use_container_width=True)

        if submitted:
            if pwd_input == "AG":
                st.session_state["autenticato"] = True
                st.rerun()
            else:
                st.error("Credenziale non corretta.")

    st.markdown("<div style='height:8vh;'></div>", unsafe_allow_html=True)

# ==============================================================================
# 5. APPLICAZIONE PRINCIPALE
# ==============================================================================
else:

    # ── SIDEBAR ──────────────────────────────────────────────────────────────
    with st.sidebar:
        st.markdown(f"""
        <div style="display:flex; align-items:center; gap:12px; margin-bottom:4px;">
            <div style="width:34px; height:34px; flex-shrink:0;">{LOGO_ATHENA_RAW}</div>
            <div>
                <div style="font-weight:700; font-size:0.95rem; letter-spacing:-0.01em;
                            color:#ffffff; line-height:1.2;">Athena</div>
                <div style="color:#636366; font-size:0.68rem; letter-spacing:0.02em;">Advisory Group</div>
            </div>
        </div>
        <div style="color:#48484a; font-size:0.65rem; letter-spacing:0.05em; margin-bottom:2px;">
            Text Mining System
        </div>
        """, unsafe_allow_html=True)

        st.write("---")
        st.markdown("<div class='section-label'>AZIENDA CLIENTE</div>", unsafe_allow_html=True)
        nome_ricevente = st.text_input(
            "Nome / Ragione Sociale:",
            placeholder="Es. ABC Sagl",
            key="nome_ricevente_input",
            help="Il nome dell'azienda che RICEVE le fatture. Serve all'AI per non confonderlo col fornitore."
        )

        st.write("---")
        st.markdown("<div class='section-label'>PARAMETRI DI COMPILAZIONE</div>", unsafe_allow_html=True)

        forma_giuridica = st.selectbox(
            "Forma Giuridica:",
            ["Sagl", "Ditta individuale", "Società in nome collettivo", "SA"],
            index=0
        )
        tipo_flusso = st.radio(
            "Direzione Documenti:",
            ["Fatture d'Acquisto (Costi)", "Fatture emesse (Ricavi)"],
            index=0
        )
        settore = st.selectbox(
            "Settore di Attività:",
            [
                "Ristorante / Bar / Take-away", "Estetista", "Parrucchiere",
                "Chiosco", "Noleggio auto", "Noleggio barche",
                "Azienda di consulenza", "Azienda di architettura",
                "Holding", "Organizzazione eventi",
                "Trasporti / Logistica", "Servizi Generali",
            ]
        )
        metodo_iva = st.selectbox(
            "Regime Fiscale IVA:",
            ["Metodo Effettivo", "Aliquota a Saldo"]
        )

        mappa_aliquote_saldo = {}
        if metodo_iva == "Aliquota a Saldo" and "Ricavi" in tipo_flusso:
            st.write("---")
            st.markdown("<div class='section-label'>CORRISPETTIVI SALDO BANANA</div>", unsafe_allow_html=True)
            f1_val = st.selectbox("Codice F1 associato a:", ["8.1%", "2.6%", "Esente"])
            f2_val = st.selectbox("Codice F2 associato a:", ["2.6%", "8.1%", "Esente"])
            mappa_aliquote_saldo = {"F1": f1_val, "F2": f2_val}

        st.write("---")
        st.markdown("<div class='section-label'>CONNESSIONE AI</div>", unsafe_allow_html=True)
        api_key_input = st.text_input(
            "OpenAI API Key:",
            type="password",
            value=st.secrets.get("OPENAI_API_KEY", "")
        )

        st.write("---")
        if st.button("LOGOUT", key="logout_btn"):
            for k in ["autenticato", "df_registrazioni", "indici_complesse",
                      "buffer_excel_val", "buffer_banana_val", "pdf_rinominati_zip",
                      "indici_errore", "indici_rosso", "indici_giallo_dare", "indici_separatori"]:
                st.session_state[k] = False if k == "autenticato" else None
            st.rerun()

    # ── INTESTAZIONE ─────────────────────────────────────────────────────────
    st.markdown("""
    <h2 style="font-weight:700; letter-spacing:-0.02em; margin-bottom:2px; color:#ffffff;">
        Athena Advisory Group
    </h2>
    <p style="color:#8e8e93; font-size:1rem; font-weight:400; margin-bottom:22px;">
        Text Mining System
    </p>
    """, unsafe_allow_html=True)

    if nome_ricevente:
        st.markdown(f'''
        <div style="margin-bottom:10px;">
            <div style="
                display:inline-block;
                background-color:#000000;
                color:#38B6FF;
                border:2px solid white;
                border-radius:8px;
                padding:7px 16px;
                font-size:0.82rem;
                font-weight:600;
                letter-spacing:0.02em;
                box-shadow:0 2px 8px rgba(255,255,255,0.06);
            ">
                {nome_ricevente}
            </div>
        </div>
        ''', unsafe_allow_html=True)

    badges = f"""
    <div class="badge-container">
        <div class="badge-item badge-forma">{forma_giuridica}</div>
        <div class="badge-item badge-flusso">{tipo_flusso}</div>
        <div class="badge-item badge-settore">{settore}</div>
        <div class="badge-item badge-iva">{metodo_iva}</div>
    """
    if metodo_iva == "Aliquota a Saldo" and "Ricavi" in tipo_flusso:
        badges += f'<div class="badge-item badge-saldo">F1:{mappa_aliquote_saldo.get("F1")} F2:{mappa_aliquote_saldo.get("F2")}</div>'
    badges += "</div>"
    st.markdown(badges, unsafe_allow_html=True)

    # ── ARCHIVI STORICI ───────────────────────────────────────────────────────
    st.markdown("""<p style="font-size:0.7rem;font-weight:700;color:#636366;
        letter-spacing:0.07em;text-transform:uppercase;margin-bottom:10px;">
        ARCHIVI STORICI DI SUPPORTO</p>""", unsafe_allow_html=True)

    stringa_bilancio_ia   = "Nessun bilancio precedente."
    stringa_partitario_ia = "Nessun partitario."

    col_b, col_p = st.columns(2)

    with col_b:
        file_bilancio = st.file_uploader(
            label="Bilancio / Conto Economico Anno Precedente",
            type=["xlsx", "xls", "csv"],
            key="up_bilancio",
        )
        if file_bilancio:
            try:
                df_b = (pd.read_excel(file_bilancio)
                        if file_bilancio.name.endswith(("xlsx", "xls"))
                        else pd.read_csv(file_bilancio))
                stringa_bilancio_ia = f"Indice bilancio storico:\n{df_b.head(100).to_string()}"
                st.success("Bilancio registrato.")
            except Exception as e:
                st.error(f"Errore bilancio: {e}")

    with col_p:
        titolo_part = "Partitario Fornitori" if "Costi" in tipo_flusso else "Partitario Clienti"
        file_partitario = st.file_uploader(
            label=titolo_part,
            type=["xlsx", "xls", "csv"],
            key="up_partitario",
        )
        if file_partitario:
            try:
                df_p = (pd.read_excel(file_partitario)
                        if file_partitario.name.endswith(("xlsx", "xls"))
                        else pd.read_csv(file_partitario))
                stringa_partitario_ia = f"Partitario attivo:\n{df_p.head(50).to_string()}"
                st.success(f"{titolo_part} registrato.")
            except Exception as e:
                st.error(f"Errore partitario: {e}")

    st.write("---")

    # ── CARICAMENTO FATTURE ───────────────────────────────────────────────────
    st.markdown("""<h3 style="font-weight:600;letter-spacing:-0.01em;
        margin-bottom:10px;color:#ffffff;">Caricamento Documenti Ufficiali</h3>""",
        unsafe_allow_html=True)

    file_caricati = st.file_uploader(
        label="Trascina qui i file delle fatture correnti (PDF)",
        type=["pdf"],
        accept_multiple_files=True,
        key="up_fatture",
    )

    # ── LOGICA ELABORAZIONE ───────────────────────────────────────────────────
    if file_caricati and api_key_input:
        st.markdown(f"""<p style="font-size:0.82rem;color:#8e8e93;
            margin-top:8px;margin-bottom:14px;">
            Documenti totali rilevati:
            <strong style="color:#ffffff;">{len(file_caricati)}</strong></p>""",
            unsafe_allow_html=True)

        if st.button("AVVIA ELABORAZIONE DOCUMENTI", key="elabora_btn_main"):
            with st.spinner("Analisi fiduciaria in corso — elaborazione visiva OCR..."):
                import logging, io as _io
                _log_capture = _io.StringIO()
                _log_handler = logging.StreamHandler(_log_capture)
                _log_handler.setFormatter(logging.Formatter(
                    "[%(asctime)s] %(levelname)s — %(message)s", "%H:%M:%S"))
                logging.getLogger("athena.engine_ai").addHandler(_log_handler)

                barra = st.progress(0, text="")

                df_creato, indici_rosso, indici_verdi, indici_errore, indici_giallo_dare, indici_separatori, pdf_rinominati = \
                    elabora_documenti_banana(
                        file_caricati        = file_caricati,
                        api_key              = api_key_input,
                        forma_giuridica      = forma_giuridica,
                        tipo_flusso          = tipo_flusso,
                        settore              = settore,
                        metodo_iva           = metodo_iva,
                        mappa_aliquote_saldo = mappa_aliquote_saldo,
                        stringa_bilancio     = stringa_bilancio_ia,
                        stringa_partitario   = stringa_partitario_ia,
                        nome_ricevente       = nome_ricevente,
                    )

                barra.progress(100, text="Completato!")

                buf_xl_bytes  = esporta_per_excel(df_creato)
                buf_bn_bytes  = esporta_per_banana(df_creato)
                buf_zip_bytes = genera_archivio_zip(pdf_rinominati)

                st.session_state["df_registrazioni"]  = df_creato
                st.session_state["indici_complesse"]   = indici_verdi
                st.session_state["indici_rosso"]       = indici_rosso
                st.session_state["indici_errore"]      = indici_errore
                st.session_state["indici_giallo_dare"] = indici_giallo_dare
                st.session_state["indici_separatori"]  = indici_separatori
                logging.getLogger("athena.engine_ai").removeHandler(_log_handler)
                st.session_state["log_elaborazione"]   = _log_capture.getvalue()
                st.session_state["buffer_excel_val"]   = buf_xl_bytes
                st.session_state["buffer_banana_val"]  = buf_bn_bytes
                st.session_state["pdf_rinominati_zip"] = buf_zip_bytes
            st.rerun()

    elif file_caricati and not api_key_input:
        st.warning("Inserire la OpenAI API Key nella sidebar per procedere.")

    # ── ESPORTAZIONE DATI ─────────────────────────────────────────────────────
    if st.session_state["df_registrazioni"] is not None:
        st.write("---")
        st.markdown("""<p style="font-size:0.7rem;font-weight:700;color:#636366;
            letter-spacing:0.07em;text-transform:uppercase;margin-bottom:14px;">
            ESPORTAZIONE DATI</p>""", unsafe_allow_html=True)

        c1, c2, c3 = st.columns(3)
        with c1:
            st.download_button(
                "EXCEL",
                data=st.session_state["buffer_excel_val"],
                file_name="athena_export.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
            )
        with c2:
            st.download_button(
                "BANANA",
                data=st.session_state["buffer_banana_val"],
                file_name="athena_banana.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
            )
        with c3:
            if st.session_state["pdf_rinominati_zip"]:
                st.download_button(
                    "ZIP FATTURE",
                    data=st.session_state["pdf_rinominati_zip"],
                    file_name="fatture_rinominate.zip",
                    mime="application/zip",
                    use_container_width=True,
                )
            else:
                st.markdown("""
                <div class="zip-placeholder">
                    ZIP FATTURE<br>
                    <small>(in attesa elaborazione)</small>
                </div>
                """, unsafe_allow_html=True)

        st.write("---")

        # Legenda colori
        st.markdown("""
        <div class="legenda-container">
            <div class="legenda-item">
                <div class="legenda-dot" style="background:#3b0a0a;border:1px solid #ff6b6b;"></div>
                <span>Errore elaborazione</span>
            </div>
            <div class="legenda-item">
                <div class="legenda-dot" style="background:#3b2800;border:1px solid #ffd60a;"></div>
                <span>Tasso cambio da verificare</span>
            </div>
            <div class="legenda-item">
                <div class="legenda-dot" style="background:#1a331a;border:1px solid #8ce68c;"></div>
                <span>Riga differenza cambio</span>
            </div>
            <div class="legenda-item">
                <div class="legenda-dot" style="background:#3b3000;border:1px solid #ffd60a;"></div>
                <span>CtDare da verificare (fornitore sconosciuto)</span>
            </div>
            <div class="legenda-item">
                <div class="legenda-dot" style="background:#0a2a3b;border:1px solid #38B6FF;"></div>
                <span>Separatore fattura</span>
            </div>
        </div>
        """, unsafe_allow_html=True)

        with st.expander("Visualizza Tracciato Registrazioni"):
            df_show = st.session_state["df_registrazioni"]
            idx_v   = st.session_state["indici_complesse"]
            idx_e   = st.session_state.get("indici_errore", [])
            idx_r   = st.session_state.get("indici_rosso", [])
            idx_g   = st.session_state.get("indici_giallo_dare", [])
            idx_s   = st.session_state.get("indici_separatori", [])

            # Colonne visibili (escludi colonne interne)
            cols_visibili = [c for c in df_show.columns if c not in ("_flag_giallo_dare", "_flag_separatore")]
            df_view = df_show[cols_visibili]

            def stile_righe(row):
                idx = row.name
                n_col = len(row)

                # Errore: tutta la riga rossa
                if idx in idx_e:
                    return ["background-color:#3b0a0a; color:#ff6b6b; font-weight:600;"] * n_col

                # Tasso cambio da verificare: tutta la riga arancione
                if idx in idx_r:
                    return ["background-color:#3b2800; color:#ffd60a; font-weight:600;"] * n_col

                # Riga cambio: tutta la riga verde
                if idx in idx_v:
                    return ["background-color:#1a331a; color:#8ce68c;"] * n_col

                # Riga separatrice: solo cella Data azzurra, resto neutro
                if idx in idx_s:
                    stili = [""] * n_col
                    if "Data" in cols_visibili:
                        data_idx = cols_visibili.index("Data")
                        stili[data_idx] = "background-color:#0a2a3b; color:#38B6FF; font-weight:700;"
                    return stili

                # Fornitore sconosciuto: solo cella CtDare gialla
                if idx in idx_g:
                    stili = [""] * n_col
                    if "CtDare" in cols_visibili:
                        ct_dare_idx = cols_visibili.index("CtDare")
                        stili[ct_dare_idx] = "background-color:#3b3000; color:#ffd60a; font-weight:700;"
                    return stili

                return [""] * n_col

            st.dataframe(
                df_view.style.apply(stile_righe, axis=1),
                use_container_width=True
            )

        log_text = st.session_state.get("log_elaborazione", "")
        if log_text:
            with st.expander("Log Elaborazione AI"):
                st.markdown(
                    f'<pre style="font-size:0.7rem;color:#8e8e93;'
                    f'background:#0d0d0d;padding:12px;border-radius:8px;'
                    f'overflow-x:auto;white-space:pre-wrap;">{log_text}</pre>',
                    unsafe_allow_html=True
                )

    # ── FOOTER ────────────────────────────────────────────────────────────────
    st.markdown(
        "<div class='footer-athena'>created by Scianca &nbsp;·&nbsp; Athena Advisory Group Sagl</div>",
        unsafe_allow_html=True
    )