"""Tema scuro dell'app (i programmi di contabilità sono bianchi, quelli di finanza neri)."""

from __future__ import annotations

import base64

import streamlit as st

from core.config import ASSET

_CSS = """
<style>
:root { --bg:#000000; --pannello:#0A0C12; --bordo:#1F2433; --testo:#F4EFE6; --tenue:#9A9FAD; --accento:#FFFFFF; --verde:#34A853; --giallo:#FBBC04; --rosso:#EA4335; --blu:#2B4FD9; --azzurro:#38BDF8; --arancio:#F97316; --navy:#16233F; }
html, body, [data-testid="stAppViewContainer"], [data-testid="stApp"] { background:var(--bg) !important; color:var(--testo); }
[data-testid="stHeader"] { background:transparent; }
.block-container { max-width: 1280px; padding-top: 2.2rem; }
h1,h2,h3 { color:#FFFFFF; letter-spacing:-0.01em; }
h4 { color:#FFFFFF; letter-spacing:0.09em; text-transform:uppercase; font-size:0.86rem !important; font-weight:650; margin-top:0.6rem; }
h3 { font-weight:650; }
[data-testid="stCaptionContainer"], .stCaption { color:var(--tenue) !important; }

/* barra laterale */
[data-testid="stSidebar"] { background:#08080A !important; border-right:1px solid #1B1B1F; }
[data-testid="stSidebar"] h3 { font-size:1.05rem; margin-bottom:0; }
[data-testid="stSidebar"] .stButton > button { justify-content:flex-start; text-align:left; background:transparent; border:1px solid transparent; color:#D6D6DA; border-radius:999px; padding:0.45rem 0.9rem; }
[data-testid="stSidebar"] .stButton > button:hover { background:#17171B; color:#FFFFFF; border-color:#17171B; }
.st-key-side_attivo .stButton > button { background:#FFFFFF !important; color:#000000 !important; font-weight:650; border-color:#FFFFFF !important; }
.linea-menu { height:1px; width:48%; background:rgba(255,255,255,0.35); margin:10px 0 10px 0.7rem; }

/* pulsanti */
.stButton > button, .stDownloadButton > button { border-radius:10px; border:1px solid var(--bordo); background:#141418; color:var(--testo); }
.stButton > button:hover, .stDownloadButton > button:hover { border-color:#FFFFFF; color:#FFFFFF; background:#1B1B20; }
.stButton > button[kind="primary"], .stDownloadButton > button[kind="primary"], .stFormSubmitButton > button[kind="primary"] { background:#FFFFFF; color:#000000; border-color:#FFFFFF; font-weight:650; }
.stButton > button[kind="primary"]:hover { background:#E6E6E6; color:#000000; }
.stButton > button:disabled { opacity:0.35; }

/* pulsanti con bordo colorato: salva = verde, elimina = rosso, modifica/attenzione = giallo */
[class*="st-key-btn_verde"] button { background:#0D0D0F !important; color:#34A853 !important; border:1.5px solid #34A853 !important; font-weight:600; }
[class*="st-key-btn_verde"] button:hover { background:#34A853 !important; color:#000000 !important; }
[class*="st-key-btn_rosso"] button { background:#0D0D0F !important; color:#EA4335 !important; border:1.5px solid #EA4335 !important; font-weight:600; }
[class*="st-key-btn_rosso"] button:hover { background:#EA4335 !important; color:#000000 !important; }
[class*="st-key-btn_blu"] button { background:#0D0D0F !important; color:#7C9CFF !important; border:1.5px solid #2B4FD9 !important; font-weight:600; }
[class*="st-key-btn_blu"] button:hover { background:#2B4FD9 !important; color:#FFFFFF !important; }
[class*="st-key-btn_giallo"] button { background:#0D0D0F !important; color:#FBBC04 !important; border:1.5px solid #FBBC04 !important; font-weight:600; }
[class*="st-key-btn_giallo"] button:hover { background:#FBBC04 !important; color:#000000 !important; }
[class*="st-key-btn_azzurro"] button { background:#0D0D0F !important; color:#38BDF8 !important; border:1.5px solid #38BDF8 !important; font-weight:600; }
[class*="st-key-btn_azzurro"] button:hover { background:#38BDF8 !important; color:#000000 !important; }
[class*="st-key-btn_arancio"] a, [class*="st-key-btn_arancio"] button { background:#0D0D0F !important; color:#F97316 !important; border:1.5px solid #F97316 !important; font-weight:600; border-radius:10px; }
[class*="st-key-btn_arancio"] a:hover, [class*="st-key-btn_arancio"] button:hover { background:#F97316 !important; color:#000000 !important; }
[class*="st-key-btn_blu"] a, [class*="st-key-btn_azzurro"] a, [class*="st-key-btn_verde"] a, [class*="st-key-btn_giallo"] a { border-radius:10px; font-weight:600; }
[class*="st-key-btn_blu"] a { background:#0D0D0F !important; color:#7C9CFF !important; border:1.5px solid #2B4FD9 !important; }
[class*="st-key-btn_blu"] a:hover { background:#2B4FD9 !important; color:#FFFFFF !important; }
[class*="st-key-btn_bianco"] button, [class*="st-key-btn_bianco"] a { background:#0D0D0F !important; color:#FFFFFF !important; border:1.5px solid #FFFFFF !important; font-weight:600; border-radius:10px; }
[class*="st-key-btn_bianco"] button:hover, [class*="st-key-btn_bianco"] a:hover { background:#FFFFFF !important; color:#000000 !important; }
[class*="st-key-btn_blubianco"] button, [class*="st-key-btn_blubianco"] a { background:#0D0D0F !important; color:#FFFFFF !important; border:1.5px solid #2B4FD9 !important; font-weight:600; border-radius:10px; }
[class*="st-key-btn_blubianco"] button:hover, [class*="st-key-btn_blubianco"] a:hover { background:#2B4FD9 !important; color:#FFFFFF !important; }
[class*="st-key-btn_"] button, [class*="st-key-btn_"] a { min-height:2.6rem; }
[class*="st-key-btn_grigio"] button, [class*="st-key-btn_grigio"] a { background:var(--pannello) !important; color:#FFFFFF !important; border:1px solid var(--bordo) !important; font-weight:600; border-radius:10px; }
[class*="st-key-btn_grigio"] button:hover, [class*="st-key-btn_grigio"] a:hover { border-color:#FFFFFF !important; }
/* pulsanti di invio dei moduli: verdi come «Salva» */
.stFormSubmitButton > button { background:#0D0D0F !important; color:#34A853 !important; border:1.5px solid #34A853 !important; font-weight:600; border-radius:10px; }
.stFormSubmitButton > button:hover { background:#34A853 !important; color:#000000 !important; }
/* pulsanti principali della home: grandi */
[class*="st-key-btn_bianco_home_"] button { min-height:5.4rem; font-size:1.2rem; letter-spacing:0.02em; border-radius:14px; }
/* pulsanti dei documenti: più quadrati, angoli smussati */
[class*="st-key-btn_blu_st_pdf"] button, [class*="st-key-btn_blu_st_rep"] button, [class*="st-key-btn_arancio_st_claude"] a, [class*="st-key-btn_arancio_rep_claude"] a, [class*="st-key-btn_arancio_rep_claude"] button
  { min-height:4.6rem; border-radius:8px; white-space:normal; line-height:1.25; }
/* logo e campo password staccati */
.spazio-accesso { height:2.2rem; }

/* riquadri con bordo colorato */
[class*="st-key-box_blu"] { border:1.5px solid #2B4FD9 !important; border-radius:14px; }
[class*="st-key-box_verde"] { border:1.5px solid #34A853 !important; border-radius:14px; }
[class*="st-key-box_verdescuro"] { border:1.5px solid #1E6B33 !important; border-radius:14px; }
[class*="st-key-box_bianco"] { border:1.5px solid #FFFFFF !important; border-radius:14px; }
[class*="st-key-box_giallo"] { border:1.5px solid #FBBC04 !important; border-radius:14px; }
[class*="st-key-box_azzurro"] { border:1.5px solid #38BDF8 !important; border-radius:14px; }
[class*="st-key-box_arancio"] { border:1.5px solid #F97316 !important; border-radius:14px; }
[class*="st-key-box_"] > [data-testid="stVerticalBlockBorderWrapper"], [class*="st-key-box_"][data-testid="stVerticalBlockBorderWrapper"] { border-color:transparent !important; }

/* riquadri, tabelle, campi */
[data-testid="stVerticalBlockBorderWrapper"] { border-color:var(--bordo) !important; border-radius:14px; background:var(--pannello); }
[data-testid="stMetric"] { background:var(--pannello); border:1px solid var(--bordo); border-radius:12px; padding:0.8rem 1rem; }
[data-testid="stMetricLabel"] { color:var(--tenue); }
[data-testid="stMetricValue"] { font-size:1.45rem; }
.stTextInput input, .stNumberInput input, .stTextArea textarea, .stDateInput input, [data-baseweb="select"] > div { background:#101013 !important; border-color:var(--bordo) !important; color:var(--testo) !important; }
[data-testid="stTabs"] [role="tab"] { color:var(--tenue); }
[data-testid="stTabs"] [aria-selected="true"] { color:#FFFFFF; }
[data-testid="stExpander"] { border:1px solid var(--bordo); border-radius:12px; background:var(--pannello); }
hr { border-color:#1E1E22; }

/* home */
.hero-etichetta { font-size:0.72rem; letter-spacing:0.16em; color:var(--tenue); margin-bottom:0.2rem; }
.tile-icona { width:44px; height:44px; border-radius:12px; display:flex; align-items:center; justify-content:center; background:#17171B; margin-bottom:0.5rem; }
.tab-quota { width:100%; border-collapse:collapse; font-size:0.9rem; }
.tab-quota th { text-align:left; color:var(--tenue); font-weight:500; font-size:0.78rem; padding:4px 8px; border-bottom:1px solid var(--bordo); }
.tab-quota td { padding:7px 8px; border-bottom:1px solid #12141c; }
.tab-quota td.num { text-align:right; font-variant-numeric:tabular-nums; white-space:nowrap; }
.barra-quota { display:flex; align-items:center; gap:8px; }
.barra-quota .pista { flex:1; height:8px; background:#14201a; border-radius:5px; overflow:hidden; min-width:90px; }
.barra-quota .riemp { height:100%; background:#34A853; border-radius:5px; }
.sem { display:inline-block; width:10px; height:10px; border-radius:50%; margin-right:6px; }
.sem-verde { background:var(--verde); } .sem-giallo { background:var(--giallo); } .sem-rosso { background:var(--rosso); }

/* stato cloud (in basso a sinistra) */
.cloud-fisso { position:fixed; left:1rem; bottom:0.9rem; z-index:999; font-size:0.76rem; color:#FFFFFF; display:flex; align-items:center; gap:7px; }
.cloud-pallino { width:8px; height:8px; border-radius:50%; display:inline-block; }
.cloud-verde { background:#22C55E; box-shadow:0 0 5px #22C55E; } .cloud-giallo { background:#F59E0B; box-shadow:0 0 5px #F59E0B; }

/* accesso */
.accesso-titolo { text-align:center; font-size:0.95rem; letter-spacing:0.12em; color:var(--tenue); margin:1rem 0 0.4rem; }
.accesso-errore { text-align:center; color:#EA4335; font-size:0.85rem; }
</style>
"""

_CSS_ACCESSO = """
<style>
[data-testid="stSidebar"], [data-testid="stSidebarCollapsedControl"] { display:none !important; }
.block-container { padding-top: 14vh; }
</style>
"""


def applica_stile() -> None:
    st.markdown(_CSS, unsafe_allow_html=True)


def nascondi_barra_laterale() -> None:
    st.markdown(_CSS_ACCESSO, unsafe_allow_html=True)


def logo_html(larghezza_px: int = 200, centrato: bool = False) -> str:
    p = ASSET / "logo_ui.png"
    if not p.exists():
        return ""
    b64 = base64.b64encode(p.read_bytes()).decode()
    stile = f"width:{larghezza_px}px;" + ("display:block;margin:0 auto;" if centrato else "")
    return f"<img src='data:image/png;base64,{b64}' style='{stile}'/>"


def intestazione(titolo: str, sottotitolo: str = "") -> None:
    st.markdown(f"## {titolo}")
    if sottotitolo:
        st.caption(sottotitolo)


def semaforo(colore: str, testo: str) -> str:
    return f"<span class='sem sem-{colore}'></span>{testo}"


def bottone(etichetta: str, colore: str, chiave: str, **kw) -> bool:
    """Pulsante con bordo colorato: 'verde' salva/conferma · 'giallo' elimina/attenzione · 'blu' azioni principali · 'azzurro' registra · 'arancio' Claude."""
    with st.container(key=f"btn_{colore}_{chiave}"):
        return st.button(etichetta, key=chiave, **kw)


def bottone_link(etichetta: str, colore: str, chiave: str, url: str, **kw):
    with st.container(key=f"btn_{colore}_{chiave}"):
        return st.link_button(etichetta, url, **kw)


def riquadro(colore: str, chiave: str, altezza: int | None = None):
    """Riquadro con bordo colorato (blu, verdescuro, bianco, giallo solo per gli avvisi…). Con `altezza` il riquadro ha altezza fissa e scorre."""
    if altezza:
        return st.container(border=True, key=f"box_{colore}_{chiave}", height=altezza)
    return st.container(border=True, key=f"box_{colore}_{chiave}")


def gma(iso) -> str:
    """Data nel formato gg.mm.aaaa (da 2026-03-31 o da una data)."""
    t = iso.isoformat() if hasattr(iso, "isoformat") else str(iso or "")
    return f"{t[8:10]}.{t[5:7]}.{t[:4]}" if len(t) >= 10 and t[4] == "-" else t


def num_ch(x, dec: int = 2) -> str:
    """Numeri nel formato svizzero usato nei report: 18'610,00."""
    if x is None:
        return "–"
    return f"{x:,.{dec}f}".replace(",", "§").replace(".", ",").replace("§", "'")


# palette dei grafici: niente rosa/magenta
PALETTE = ["#3B82F6", "#14B8A6", "#F59E0B", "#8B5CF6", "#22C55E", "#06B6D4", "#EAB308", "#64748B", "#84CC16", "#0EA5E9", "#A8A29E", "#D97706", "#10B981", "#6366F1"]
