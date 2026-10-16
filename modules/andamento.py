"""Andamento in tempo reale del portafoglio: valore, performance, scadenze, cedole, esposizioni, costi."""

from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
import streamlit as st

from core import dati
from core.calcolo import calcola_portafoglio
from core.config import CATEGORIE
from core.performance import DatoMancante
from core.stile import riquadro, gma
from modules import grafici


def _e(x, d=0):
    return "–" if x is None else f"{x:,.{d}f}".replace(",", "’")


def _p(x, d=2):
    return "n.d." if x is None else f"{100 * x:+.{d}f}%"


ETICHETTE = CATEGORIE | {"liquidita": "Liquidità", "deposito": "Depositi a termine"}


def _grafici_live(pf):
    """Grafici sempre disponibili (dati in diretta già calcolati): tipo di investimento, area geografica, settori, valute, andamento."""
    L = pf.get("live") or {}
    if not L.get("allocazione"):
        st.info("I grafici compaiono appena la strategia ha almeno un prodotto con un prezzo.")
        return
    with riquadro("blu", f"and_g1_{pf['id']}"):
        a, b = st.columns(2)
        with a:
            st.markdown("#### Per tipo di investimento")
            grafici.torta(L["allocazione"], ETICHETTE, interno=60)
        with b:
            st.markdown("#### Per area geografica")
            grafici.torta(L.get("aree") or {})
    with riquadro("blu", f"and_g2_{pf['id']}"):
        a, b = st.columns(2)
        with a:
            st.markdown("#### Per settore")
            grafici.barre_orizzontali(L.get("settori") or {})
        with b:
            st.markdown("#### Per valuta")
            grafici.barra_unica(L.get("valute") or {})
            st.markdown("#### Andamento della performance")
            grafici.linea(L.get("serie") or [])


def render(c, reg, pf):
    v = dati.vista_portafoglio(c, pf["id"])
    tx = dati.transazioni_ordinate(v)
    if not tx:
        st.info("Nessun movimento in questa strategia: aggiungi un prodotto dalla scheda «Strategia» o importa un estratto conto.")
        return
    _grafici_live(pf)
    st.markdown("#### Dettaglio: scadenze, cedole, costi")
    oggi = date.today()
    inizio = date.fromisoformat(tx[0]["data"]) - timedelta(days=1)
    chiave = f"and_{pf['id']}"
    premuto = st.button("Calcola il dettaglio con i prezzi di oggi" if chiave not in st.session_state else "Aggiorna il dettaglio", key=f"{chiave}_btn", type="primary")
    if chiave not in st.session_state and not premuto:
        st.caption("Il calcolo usa i prezzi di mercato di oggi (due fonti a confronto): parte quando premi il pulsante.")
        return
    if premuto:
        try:
            st.session_state[chiave] = calcola_portafoglio(c, pf["id"], reg, inizio, oggi)
        except DatoMancante as e:
            st.session_state.pop(chiave, None)
            st.error(f"Dato mancante: {e}. Se è un prezzo, completa la scheda del prodotto (ticker, NAV) in «Prodotti»; se è un cambio o la fonte non risponde, riprova più tardi.")
            return
        except Exception as e:  # rete o fonte di prezzo non raggiungibile
            st.session_state.pop(chiave, None)
            st.error(f"Non riesco a calcolare l'andamento ({e}). Riprova fra poco.")
            return
    S = st.session_state[chiave]
    ris, base = S["ris"], S["ris"]["periodo"]["base"]
    t = ris["totale"]
    for p in S["problemi"]:
        st.warning(f"Prezzo da verificare: {p.get('chiave')} — {str(p.get('stato', '')).replace('_', ' ')}")
    k = st.columns(4)
    k[0].metric("Valore del portafoglio", f"{base} {_e(ris['valore_portafoglio'])}")
    k[1].metric("Proventi incassati", f"{base} {_e(sum(p['importo_base'] for p in ris['proventi']))}")
    k[2].metric("Performance dall'inizio", _p(t.get("rendimento_dall_inizio")))
    k[3].metric("Annualizzata (XIRR)", _p(t.get("xirr")) if t.get("xirr") is not None else "–")

    st.markdown("#### Prodotti attivi e scadenze")
    att = ris["attivi"]
    if att:
        righe = []
        for r in att:
            gg = (date.fromisoformat(r["scadenza"]) - oggi).days if r.get("scadenza") else None
            tot_gg = (date.fromisoformat(r["scadenza"]) - date.fromisoformat(r["apertura"])).days if r.get("scadenza") and r.get("apertura") else None
            avanz = max(0.0, min(1.0, 1 - gg / tot_gg)) if gg is not None and tot_gg else None
            righe.append({"Prodotto": r["nome"], "Acquisto": gma(r["apertura"]), "Scadenza": gma(r["scadenza"]) if r["scadenza"] else "–", "Giorni alla scadenza": gg, "Avanzamento": avanz,
                          f"Investito ({base})": r["investito"], f"Valore ({base})": r["valore"], "Proventi": r["redditi"], "Rendimento": r["rendimento"]})
        st.dataframe(pd.DataFrame(righe), hide_index=True, width="stretch", column_config={
            "Avanzamento": st.column_config.ProgressColumn(min_value=0.0, max_value=1.0, format="percent"),
            "Rendimento": st.column_config.NumberColumn(format="percent"),
            f"Investito ({base})": st.column_config.NumberColumn(format="%.0f"), f"Valore ({base})": st.column_config.NumberColumn(format="%.0f"),
            "Proventi": st.column_config.NumberColumn(format="%.0f")})
    else:
        st.caption("Nessun prodotto attivo.")
    barr = [b for b in ris["barriere"] if b.get("completo")]
    if barr:
        nomi = {r["chiave"]: r["nome"] for r in ris["attivi"]}
        pal = {"verde": "🟢 oltre il 20%", "giallo": "🟡 sotto il 20%", "arancio": "🟠 sotto il 10%", "rosso": "🔴 sotto il 5%"}
        st.markdown("**Distanza dalla barriera**")
        st.dataframe(pd.DataFrame([{"Prodotto": nomi.get(b["chiave"], b["chiave"]), "Distanza": f"{100 * b['buffer']:.0f}%", "Giudizio": pal[b["semaforo"]]} for b in barr]), hide_index=True, width="stretch")

    pr = ris["proventi"]
    if pr:
        st.markdown("#### Cedole e proventi incassati")
        df = pd.DataFrame(pr)
        df["mese"] = df["data"].str[:7]
        grafici.barre_verticali({k_: float(v_) for k_, v_ in df.groupby("mese")["importo_base"].sum().items()}, f"Proventi ({base})", "#14B8A6")
        with st.expander("Dettaglio"):
            st.dataframe(df[["data", "nome", "tipo", "valuta", "importo", "importo_base"]], hide_index=True, width="stretch")
    fut = ris["cedole_future"]
    if fut:
        st.markdown("#### Prossime cedole attese")
        st.dataframe(pd.DataFrame(fut)[["data", "nome", "valuta", "importo", "importo_base"]].head(24), hide_index=True, width="stretch")
    cd = ris["costi_dettaglio"]
    with st.expander("Costi e riconciliazione dei movimenti"):
        st.write(f"Commissioni {_e(cd['commissioni'], 2)} · custodia {_e(cd['custodia'], 2)} · spese {_e(cd['spese'], 2)} · imposte {_e(cd['imposte'], 2)} · **totale {_e(cd['totale'], 2)} {base}**")
        rc = ris["riconciliazione"]
        from core.riepiloghi import GRUPPI
        st.dataframe(pd.DataFrame([{"Voce": e_, "N.": rc["righe"][k_]["n"], f"Effetto ({base})": rc["righe"][k_]["base"]} for k_, e_ in GRUPPI if rc["righe"][k_]["n"]]), hide_index=True, width="stretch")
    for a in ris.get("avvisi", []):
        st.warning(a)
