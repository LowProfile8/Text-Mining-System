"""Strategia = portafoglio del cliente, sempre aggiornato: panoramica in diretta, tabella prodotti modificabile, nuove operazioni, documenti.
Gli avvisi e le correzioni stanno in fondo alla pagina, senza intralciare il lavoro."""

from __future__ import annotations

from datetime import date, datetime

import pandas as pd
import streamlit as st

from core import dati, live, strategia as stg
from core.config import CATEGORIE
from core.stile import bottone, bottone_link, gma, num_ch, riquadro
from modules import grafici, scheda_prodotto as sp

VALUTE = ["CHF", "EUR", "USD", "GBP", "JPY", "CAD", "AUD", "SEK", "NOK", "DKK"]
ETICHETTE_CAT = CATEGORIE | {"liquidita": "Liquidità", "deposito": "Depositi a termine"}
LIVELLI = {"verde": "🟢 oltre il 20%", "giallo": "🟡 sotto il 20%", "arancio": "🟠 sotto il 10%", "rosso": "🔴 sotto il 5%"}


@st.cache_data(ttl=3600, show_spinner=False)
def _fx_oggi(da: str, a: str):
    import core.calcolo as calcolo
    return calcolo.mercato_reale().fx(da, a, date.today().isoformat())


def _cerca(da, a):
    return _fx_oggi(da, a)


def _rerun_frammento():
    """Aggiorna solo il blocco (veloce); se non si è in un aggiornamento parziale ricarica la pagina."""
    try:
        st.rerun(scope="fragment")
    except st.errors.StreamlitAPIException:
        st.rerun()


def _e(x, d=0):
    return "–" if x is None else f"{x:,.{d}f}".replace(",", "’")


def _p(x, d=2):
    return "n.d." if x is None else f"{100 * x:+.{d}f}%"


# compatibilità con i moduli che usavano i grafici da qui
torta = grafici.torta
linea = grafici.linea


def _live(c, reg, pf, forza=False):
    """Ricalcola lo stato in diretta quando cambiano i dati (o su richiesta) e lo salva nel cliente."""
    f = live.firma(c, pf, reg)
    chiave = f"lv_{pf['id']}"
    L = pf.get("live") or {}
    if not st.session_state.get(f"auto_{pf['id']}"):               # alla prima apertura i prezzi si rileggono, ma solo se i dati salvati non sono freschi
        st.session_state[f"auto_{pf['id']}"] = True
        try:
            eta = (datetime.now() - datetime.fromisoformat(L["aggiornato"])).total_seconds() if L.get("aggiornato") else None
        except Exception:
            eta = None
        if eta is None or eta > 1800 or L.get("firma") != f:
            forza = True
    if forza or (L.get("firma") != f and st.session_state.get(chiave) != f):
        st.session_state[chiave] = f
        with st.spinner("Aggiorno prezzi e performance…"):
            live.aggiorna(c, pf, reg)
            dati.salva_cliente(c)
    return pf.get("live") or {}


# ───────────────────────── testata della strategia (dentro il riquadro unico in alto) ─────────────────────────
def testata(c, pf):
    a, b, d = st.columns([3, 1.4, 1])
    nome = a.text_input("Nome della strategia", pf["nome"], key=f"st_nome_{pf['id']}")
    cap = b.number_input(f"Capitale da investire ({pf['valuta']}) – facoltativo", min_value=0.0, value=float(pf.get("capitale") or 0.0), step=1000.0, format="%.2f", key=f"st_cap_{pf['id']}")
    val = d.selectbox("Valuta", VALUTE, index=VALUTE.index(pf["valuta"]) if pf["valuta"] in VALUTE else 0, key=f"st_val_{pf['id']}")
    s1, s2, _ = st.columns([1, 1, 3])
    with s1:
        if bottone("Salva", "verde", f"st_savetest_{pf['id']}", width="stretch"):
            pf.update(nome=nome.strip() or pf["nome"], capitale=cap, valuta=val)
            dati.salva_cliente(c)
            st.rerun()
    with s2:
        if bottone("Elimina strategia", "giallo", f"st_delpf_{pf['id']}", width="stretch"):
            st.session_state[f"st_delask_{pf['id']}"] = True
    if st.session_state.get(f"st_delask_{pf['id']}"):
        st.warning(f"Eliminare «{pf['nome']}» e tutti i suoi movimenti? Non si può annullare.")
        y1, y2, _ = st.columns([1, 1, 3])
        with y1:
            if bottone("Sì, elimina", "giallo", f"st_delpf_ok_{pf['id']}", width="stretch"):
                c["transazioni"] = [t for t in c["transazioni"] if dati._pf_di(c, t) != pf["id"]]
                c["saldi"] = [t for t in c["saldi"] if dati._pf_di(c, t) != pf["id"]]
                c["portafogli"] = [p for p in c["portafogli"] if p["id"] != pf["id"]]
                dati.salva_cliente(c)
                st.session_state.pop("cli_pf", None)
                st.rerun()
        with y2:
            if st.button("Annulla", key=f"st_delpf_no_{pf['id']}", width="stretch"):
                st.session_state.pop(f"st_delask_{pf['id']}", None)
                st.rerun()


# ───────────────────────── panoramica in diretta ─────────────────────────
def _panoramica(c, reg, pf, calc):
    L = _live(c, reg, pf)
    base = pf["valuta"]
    with riquadro("blu", f"pano_{pf['id']}"):
        cA, cB = st.columns([5, 1], vertical_alignment="bottom")
        cA.markdown("#### Panoramica in diretta")
        if cB.button("Aggiorna prezzi", key=f"st_agg_{pf['id']}", width="stretch"):
            from core.mercato import svuota_cache
            svuota_cache()
            _live(c, reg, pf, forza=True)
            st.rerun()
        if L.get("vuoto"):
            st.info("Nessun prodotto: premi «Acquista prodotto» qui sotto.")
            return L
        if L.get("errore"):
            st.caption(f"⚠ Prezzi di mercato non disponibili al momento ({L['errore']}). Mostro l'ultimo calcolo valido e gli importi investiti.")
        k = st.columns(6)
        k[0].metric("Valore", f"{base} {_e(L.get('valore'))}" if L.get("valore") is not None else "–")
        k[1].metric("Investito", f"{base} {_e(L.get('investito') if L.get('investito') is not None else calc['totale'])}")
        k[2].metric("Cedole incassate", f"{base} {_e(L.get('proventi'))}" if L.get("proventi") is not None else "–")
        k[3].metric("Risultato nominale", f"{base} {_e(L.get('pl_nominale'))}" if L.get("pl_nominale") is not None else "–")
        k[4].metric("Performance", _p(L.get("perf")))
        k[5].metric("Annualizzata", _p(L.get("xirr")))
        g1, g2, g3 = st.columns(3)
        with g1:
            st.caption("Per tipo di investimento")
            grafici.torta(L.get("allocazione") or calc["allocazione"], ETICHETTE_CAT)
        with g2:
            st.caption("Per area geografica")
            grafici.torta(L.get("aree") or calc["aree"], interno=45)
        with g3:
            st.caption("Andamento della performance")
            grafici.linea(L.get("serie") or [])
    return L


# ───────────────────────── tabella dei prodotti (modificabile) ─────────────────────────
def _prezzo_attuale(x, s, prezzi_att):
    if s.get("valutazione") == "nominale":
        return 100.0                                           # i prodotti strutturati valgono sempre il 100% del nominale
    if s.get("valutazione") == "scadenza":
        return None
    navs = sorted(s.get("nav_manuale", []), key=lambda n: n["data"])
    return prezzi_att.get(x["strumento"], navs[-1]["nav"] if navs else None)


def _pn(v):
    """Numero da una cella: accetta 10'000,00, 10000.5 o un numero vero; vuoto/«–» → None."""
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return None if v != v else float(v)
    t = str(v).strip().replace("’", "").replace("'", "").replace(" ", "")
    if t in ("", "–", "-", "n.d."):
        return None
    t = t.replace("%", "")
    if "," in t:
        t = t.replace(".", "").replace(",", ".")
    try:
        return float(t)
    except ValueError:
        return None


_NUM_MOD = ("Investito", "Prezzo acquisto", "Quantità / nominale", "Costi", "Prezzo attuale")


def _salva_tabella(c, reg, pf, ed, orig):
    per_id = {t["id"]: t for t in c["transazioni"]}
    manuali = dati.carica_manuali()
    oggi = date.today().isoformat()
    avvisi = []
    for r in ed:
        tx = per_id.get(r["id"])
        if not tx:
            continue
        if r["Elimina"]:
            c["transazioni"].remove(tx)
            continue
        o = orig[r["id"]]
        s = reg.strumenti[tx["strumento"]]
        diff = lambda k_: k_ in r and k_ in o and abs((_pn(r[k_]) or 0) - (_pn(o[k_]) or 0)) > 1e-9
        if r["Prodotto"] and r["Prodotto"] != o["Prodotto"]:
            s["nome"] = str(r["Prodotto"]).strip()
        data = r["Data acquisto"].isoformat() if hasattr(r["Data acquisto"], "isoformat") else str(r["Data acquisto"])
        stg.modifica_acquisto(tx, s, data=data if data != (o["Data acquisto"].isoformat() if hasattr(o["Data acquisto"], "isoformat") else str(o["Data acquisto"])) else None,
                              prezzo=_pn(r["Prezzo acquisto"]) if diff("Prezzo acquisto") else None,
                              quantita=_pn(r["Quantità / nominale"]) if diff("Quantità / nominale") else None,
                              investito=_pn(r["Investito"]) if diff("Investito") and not diff("Quantità / nominale") else None,
                              commissioni=_pn(r["Costi"]) if diff("Costi") else None)
        pa = _pn(r.get("Prezzo attuale"))
        if diff("Prezzo attuale") and pa is not None:
            if s.get("valutazione") == "nominale":
                avvisi.append(f"{s['nome']}: il prezzo attuale di un prodotto strutturato è sempre 100%.")
            elif s.get("valutazione") == "manuale":
                s["nav_manuale"] = [n for n in s.get("nav_manuale", []) if n["data"] != oggi] + [{"data": oggi, "nav": float(pa)}]
            elif s.get("valutazione") == "mercato":
                manuali[f"{s['chiave']}@{oggi}"] = float(pa)          # prezzo inserito a mano: vale per oggi e sostituisce quello di mercato
            else:
                avvisi.append(f"{s['nome']}: depositi e liquidità valgono al costo più gli interessi maturati.")
    dati.salva_cliente(c)
    dati.salva_registro(reg)
    dati.salva_manuali(manuali)
    return avvisi


def _tab_sottostanti(L):
    ss = L.get("sottostanti") or []
    if not ss:
        return
    righe = []
    for p_ in ss:
        for d_ in p_.get("dettaglio", []):
            righe.append({"Prodotto": p_["nome"], "Sottostante": d_.get("nome"), "Ticker": d_.get("ticker"), "Livello iniziale": d_.get("livello_iniziale"), "Livello attuale": d_.get("spot"),
                          "Performance": (d_["perf"] - 1) if d_.get("perf") is not None else None, "Distanza dalla barriera": d_.get("distanza_barriera")})
    with st.expander("Sottostanti dei prodotti strutturati: livelli e distanza dalla barriera"):
        st.dataframe(pd.DataFrame(righe), hide_index=True, width="stretch", column_config={
            "Performance": st.column_config.NumberColumn(format="percent"), "Distanza dalla barriera": st.column_config.NumberColumn(format="percent"),
            "Livello iniziale": st.column_config.NumberColumn(format="%.2f"), "Livello attuale": st.column_config.NumberColumn(format="%.2f")})


ORDINE_CAT = ["obbligazione", "strutturato", "etf_azioni", "opzione", "alternativo", "deposito", "liquidita"]

_BASE = ["Elimina", "Prodotto", "Ticker", "ISIN", "Valuta", "Data acquisto", "Investito", "Prezzo acquisto", "Quantità / nominale", "Costi", "Prezzo attuale", "Performance", "Risultato"]
COLONNE_CAT = {                      # ogni asset class mostra solo i campi che la riguardano
    "obbligazione": _BASE + ["Cedola %", "Scadenza", "Peso %"],
    "strutturato": _BASE + ["Cedola %", "Barriera %", "Rebate %", "Protezione %", "Scadenza", "Peso %"],
    "etf_azioni": _BASE + ["Peso %"],
    "alternativo": _BASE + ["Peso %"],
    "opzione": _BASE + ["Scadenza", "Peso %"],
    "deposito": ["Elimina", "Prodotto", "Valuta", "Data acquisto", "Investito", "Cedola %", "Scadenza", "Risultato", "Peso %"],
    "liquidita": ["Elimina", "Prodotto", "Valuta", "Data acquisto", "Investito", "Peso %"],
}


def _tabella(c, reg, pf, calc, L):
    """Una tabella modificabile per ogni asset class, ciascuna con il proprio totale. Restituisce (record modificati, originali)."""
    righe_calc = calc["righe"]
    pid = pf["id"]
    base = pf["valuta"]
    if not righe_calc:
        return None
    prezzi_att = (L or {}).get("prezzi") or {}
    gruppi: dict[str, list] = {}
    for x in righe_calc:
        if x["attivo"]:                                           # i prodotti venduti o scaduti vanno nella tabella «Venduti e scaduti»
            gruppi.setdefault(x["categoria"] or "alternativo", []).append(x)
    prodotti_live = (L or {}).get("prodotti") or {}
    ordine = [k for k in ORDINE_CAT if k in gruppi] + [k for k in gruppi if k not in ORDINE_CAT]
    tot_att = calc["totale"] or 1.0
    orig_tutti, ed_tutti = {}, []
    n = lambda v, d=2: "" if v is None else num_ch(v, d)
    for cat in ordine:
        righe = []
        for x in gruppi[cat]:
            s = reg.strumenti.get(x["strumento"]) or {}
            pr = prodotti_live.get(x["strumento"]) or {}
            pa = _prezzo_attuale(x, s, prezzi_att)
            righe.append({"id": x["id"], "Elimina": False, "Prodotto": x["nome"], "Ticker": s.get("ticker_mercato") or s.get("ticker") or "", "ISIN": x["isin"],
                          "Valuta": x["valuta"], "Data acquisto": date.fromisoformat(x["data"]), "Investito": n(x["importo"]), "Prezzo acquisto": n(x["prezzo"], 4),
                          "Quantità / nominale": n(x["quantita"], 2), "Costi": n(x["commissioni"]), "Prezzo attuale": n(pa, 4),
                          "Performance": "" if pr.get("rend") is None else f"{100 * pr['rend']:+.2f}%".replace(".", ","), "Risultato": n(pr.get("risultato"), 0),
                          "Cedola %": n(x["cedola_annua_pct"]), "Barriera %": n(x["barriera_pct"], 0), "Rebate %": n(s.get("rebate_pct")), "Protezione %": n(x["protezione_pct"], 0),
                          "Scadenza": date.fromisoformat(x["scadenza"]) if x["scadenza"] else None, "Peso %": n(round(x["peso_eff_pct"], 1), 1)})
        attive = [x for x in gruppi[cat] if x["attivo"]]
        tot_cat = sum(x["importo_base"] for x in attive)
        costi_cat = sum(x["commissioni"] * x["tasso"] for x in gruppi[cat])
        st.markdown(f"**{ETICHETTE_CAT.get(cat, cat)}** · {len(attive)} attiv{'o' if len(attive) == 1 else 'i'} · "
                    f"totale **{base} {num_ch(tot_cat, 0)}** · {100 * tot_cat / tot_att:.1f}% del portafoglio · costi {base} {num_ch(costi_cat, 2)}")
        colonne = COLONNE_CAT.get(cat, _BASE + ["Peso %"])
        orig = {r["id"]: dict(r) for r in righe}
        df = pd.DataFrame(righe)[["id"] + colonne]
        modificabili = set(_NUM_MOD) | {"Prodotto", "Data acquisto", "Elimina"}
        ed = st.data_editor(df, hide_index=True, width="stretch", key=f"st_tab_{pid}_{cat}", column_config={
            "id": None, "Elimina": st.column_config.CheckboxColumn(width="small"), "Data acquisto": st.column_config.DateColumn(format="DD.MM.YYYY"),
            "Investito": st.column_config.TextColumn(help="Importo investito, senza costi. Per obbligazioni e strutturati è il nominale."),
            "Prezzo acquisto": st.column_config.TextColumn(help="In % del nominale per obbligazioni e strutturati."),
            "Costi": st.column_config.TextColumn(help="Commissioni e tasse dell'acquisto."),
            "Prezzo attuale": st.column_config.TextColumn(help="Strutturati: sempre 100%. Obbligazioni: in %. Puoi inserire a mano il prezzo di oggi."),
            "Performance": st.column_config.TextColumn(help="Rendimento del prodotto dall'acquisto, proventi inclusi."),
            "Risultato": st.column_config.TextColumn(help=f"Risultato nominale in {base}."),
            "Scadenza": st.column_config.DateColumn(format="DD.MM.YYYY")},
            disabled=[k_ for k_ in colonne if k_ not in modificabili])
        orig_tutti.update(orig)
        ed_tutti += ed.to_dict("records")
        if cat == "strutturato":
            _tab_sottostanti(L or {})
    chiusi = (L or {}).get("chiusi") or []
    if chiusi:
        st.markdown(f"**Venduti e scaduti** · {len(chiusi)}")
        st.dataframe(pd.DataFrame([{"Prodotto": r["nome"], "ISIN": r.get("isin", ""), "Acquisto": gma(r.get("apertura")), "Chiusura": gma(r.get("chiusura")), f"Investito ({base})": r.get("investito"),
                                    f"Incassato ({base})": (r.get("incassi") or 0) + (r.get("redditi") or 0), f"Risultato ({base})": r.get("risultato"), "Rendimento": r.get("rendimento"),
                                    "Annuo": r.get("rendimento_annuo")} for r in chiusi]), hide_index=True, width="stretch",
                     column_config={f"{k_} ({base})": st.column_config.NumberColumn(format="%.0f") for k_ in ("Investito", "Incassato", "Risultato")} | {
                         "Rendimento": st.column_config.NumberColumn(format="percent"), "Annuo": st.column_config.NumberColumn(format="percent")})
    costi_tot = sum(x["commissioni"] * x["tasso"] for x in righe_calc)
    st.markdown(f"**Totale portafoglio: {base} {_e(calc['totale'])}** · costi {base} {_e(costi_tot, 2)}"
                + (f" · di cui liquidità {base} {_e(calc['allocazione'].get('liquidita', 0.0))}" if calc["allocazione"].get("liquidita") else ""))
    return ed_tutti, orig_tutti


@st.fragment
def _blocco_prodotti(c, reg, pf, calc, L):
    """Tabella + pulsanti + pannelli: si aggiorna da sola, senza ricaricare tutta la pagina a ogni modifica."""
    pid = pf["id"]
    with riquadro("blu", f"prod_{pid}"):
        st.markdown("#### Prodotti")
        st.caption("Modifica direttamente nella tabella e premi **Salva modifiche**. Cambiando **Investito** la quantità si ricalcola dal prezzo; cambiando prezzo o quantità l'investito segue.")
        _chiedi_capitale(c, pf)
        t = _tabella(c, reg, pf, calc, L)
        pannello = st.session_state.get(f"pan_{pid}")
        b = st.columns(5)
        with b[0]:
            if bottone("Salva modifiche", "verde", f"st_tabsave_{pid}", width="stretch", disabled=t is None):
                avvisi = _salva_tabella(c, reg, pf, *t)
                for a_ in avvisi:
                    st.session_state.setdefault("cli_avvisi", []).append(a_)
                st.session_state["cli_msg"] = ("Modifiche salvate: la panoramica si aggiorna con i nuovi dati.", st.session_state.pop("cli_avvisi", []))
                st.rerun()
        with b[1]:
            if bottone("Acquista prodotto", "blu", f"st_add_{pid}", width="stretch"):
                st.session_state[f"pan_{pid}"] = None if pannello == "add" else "add"
                _rerun_frammento()
        with b[2]:
            if bottone("Vendi prodotto", "blu", f"st_sell_{pid}", width="stretch", disabled=t is None):
                st.session_state[f"pan_{pid}"] = None if pannello == "sell" else "sell"
                _rerun_frammento()
        with b[3]:
            if bottone("Registra transazione", "azzurro", f"st_tx_{pid}", width="stretch"):
                st.session_state[f"pan_{pid}"] = None if pannello == "tx" else "tx"
                _rerun_frammento()
        with b[4]:
            if bottone("Elimina le righe spuntate", "giallo", f"st_tabdel_{pid}", width="stretch", disabled=t is None):
                ids = {r["id"] for r in t[0] if r["Elimina"]}
                c["transazioni"] = [x for x in c["transazioni"] if x["id"] not in ids]
                dati.salva_cliente(c)
                st.rerun()
        if pf.get("capitale"):
            r = st.columns([1, 3], vertical_alignment="center")
            with r[0]:
                if bottone("Calcola la liquidità", "verde", f"st_liq_{pid}", width="stretch", help="Capitale da investire meno quanto hai già investito nei prodotti."):
                    res = calc.get("liquidita_residua")
                    if res is None or res <= 0:
                        st.session_state["cli_msg"] = ("Il capitale è già tutto investito: nessuna liquidità residua.", [])
                    else:
                        stg.aggiungi_liquidita(c, pf, reg, round(res, 2), date.today().isoformat())
                        dati.salva_cliente(c); dati.salva_registro(reg)
                        st.session_state["cli_msg"] = (f"Liquidità aggiunta: {pf['valuta']} {_e(res, 2)} (capitale {_e(pf['capitale'])} − investito {_e(calc['investito_titoli'])}).", [])
                    st.rerun()
            r[1].caption(f"Capitale {pf['valuta']} {_e(pf['capitale'])} − investito {_e(calc.get('investito_titoli'))} = **{pf['valuta']} {_e(calc.get('liquidita_residua'))}** da tenere in liquidità. "
                         "Premi quando hai finito di inserire i prodotti.")
        if pannello == "add":
            with riquadro("blu", f"add_{pid}"):
                _pannello_aggiungi(c, reg, pf)
        elif pannello == "tx":
            with riquadro("blu", f"tx_{pid}"):
                _pannello_transazione(c, reg, pf, calc)
        elif pannello == "sell":
            with riquadro("blu", f"sell_{pid}"):
                _pannello_transazione(c, reg, pf, calc, vendita=True)
    return None


def _chiedi_capitale(c, pf):
    """Dopo l'inserimento di un deposito o di liquidità: chiede se aggiornare il capitale da investire."""
    q = st.session_state.get(f"cap_chiedi_{pf['id']}")
    if not q:
        return
    importo, nome = q
    with riquadro("blu", f"capq_{pf['id']}"):
        st.markdown(f"Hai aggiunto **{nome}** per {pf['valuta']} {_e(importo, 2)}. Vuoi **aggiornare il capitale da investire** della strategia "
                    f"(ora {pf['valuta']} {_e(pf.get('capitale') or 0)} → {pf['valuta']} {_e((pf.get('capitale') or 0) + importo)})?")
        a, b, _ = st.columns([1.3, 1, 3])
        with a:
            if bottone("Sì, aggiorna il capitale", "verde", f"capq_si_{pf['id']}", width="stretch"):
                pf["capitale"] = float(pf.get("capitale") or 0.0) + importo
                dati.salva_cliente(c)
                st.session_state.pop(f"cap_chiedi_{pf['id']}", None)
                st.rerun()
        with b:
            if bottone("No, lascia com'è", "giallo", f"capq_no_{pf['id']}", width="stretch"):
                st.session_state.pop(f"cap_chiedi_{pf['id']}", None)
                st.rerun()


# ───────────────────────── nuovo prodotto ─────────────────────────
def _prefisso(pid: str) -> str:
    return f"np_{pid}_{st.session_state.get(f'np_gen_{pid}', 0)}"


def _pannello_aggiungi(c, reg, pf):
    pid = pf["id"]
    cA, cB = st.columns([6, 1], vertical_alignment="center")
    modo = cA.radio("Come vuoi aggiungere?", ["Un prodotto, a mano", "Più prodotti da screenshot o PDF (Interactive Brokers)"], horizontal=True, key=f"add_modo_{pid}", label_visibility="collapsed")
    with cB:
        if st.button("Chiudi", key=f"add_chiudi_{pid}", width="stretch"):
            st.session_state[f"pan_{pid}"] = None
            _rerun_frammento()
    if modo.startswith("Un prodotto"):
        _nuovo_prodotto(c, reg, pf)
    else:
        _da_screenshot(c, reg, pf)


def _nuovo_prodotto(c, reg, pf):
    pid = pf["id"]
    pre = _prefisso(pid)
    ultimo = st.session_state.get(f"np_ultimo_{pid}") or {}
    v = sp.campi_prodotto(pre, {"valuta": pf["valuta"], **ultimo})
    pct, valuta, cat = v["prezzo_in_percento"], v["valuta"], v["categoria"]
    st.markdown("**Investimento**")
    semplice = cat in ("deposito", "liquidita")
    k_ = f"{pre}_{cat}_{int(pct)}"
    a1, a2, a3, a4 = st.columns(4)
    data = a1.date_input("Data di acquisto" if not semplice else "Data", value=v.get("data_emissione") if cat == "deposito" and v.get("data_emissione") else date.today(), format="DD.MM.YYYY", key=f"{pre}_data")
    if semplice:
        inv = a2.number_input(f"Importo ({valuta})", min_value=0.0, value=0.0, step=1000.0, format="%.2f", key=f"{k_}_inv")
        prezzo, qta, comm = 1.0, inv, 0.0
        st.info(f"{'Deposito' if cat == 'deposito' else 'Liquidità'} di **{valuta} {_e(inv, 2)}**")
    elif pct:
        inv = a2.number_input(f"Importo investito = nominale ({valuta})", min_value=0.0, value=0.0, step=1000.0, format="%.2f", key=f"{k_}_inv",
                              help="Il nominale che compri (es. 20'000). Il prezzo dice quanto paghi: nominale × prezzo.")
        prezzo = a3.number_input("Prezzo di acquisto (% del nominale)", min_value=0.0, value=100.0, format="%.4f", key=f"{k_}_p")
        comm = a4.number_input("Costi di acquisto (commissioni, tasse)", min_value=0.0, value=0.0, format="%.2f", key=f"{k_}_c")
        qta = stg.quantita_da_investito(inv, prezzo, True)
        st.info(f"Nominale **{valuta} {_e(qta, 2)}** · prezzo {prezzo:g}% → pagato **{valuta} {_e(stg.lordo(qta, prezzo, True), 2)}**" + (f" + costi {_e(comm, 2)}" if comm else ""))
    else:
        modi = ["Importo investito", "Quantità"]
        modo = st.radio("Cosa conosci?", modi, index=1 if cat in ("etf_azioni", "opzione") else 0, horizontal=True, key=f"{pre}_modo_{cat}")
        prezzo = a2.number_input("Prezzo di acquisto (per unità)", min_value=0.0, value=0.0, format="%.4f", key=f"{k_}_p")
        if modo == modi[0]:
            inv = a3.number_input(f"Importo investito ({valuta})", min_value=0.0, value=0.0, step=1000.0, format="%.2f", key=f"{k_}_inv")
            qta = stg.quantita_da_investito(inv, prezzo, False)
        else:
            qta = a3.number_input("Quantità", min_value=0.0, value=0.0, format="%.4f", key=f"{k_}_q")
            inv = stg.lordo(qta, prezzo, False)
        comm = a4.number_input("Costi di acquisto (commissioni, tasse)", min_value=0.0, value=0.0, format="%.2f", key=f"{k_}_c")
        st.info(f"Quantità **{_e(qta, 4).rstrip('0').rstrip('.')}** × prezzo {_e(prezzo, 4).rstrip('0').rstrip('.')} → investito **{valuta} {_e(inv, 2)}**" + (f" + costi {_e(comm, 2)}" if comm else ""))
    if bottone("Aggiungi il prodotto", "verde", f"{pre}_ok"):
        if not v["nome"].strip() and not semplice:
            st.error("Manca il nome del prodotto.")
            return
        if qta <= 0 or prezzo <= 0:
            st.error("Servono l'importo (o la quantità) e il prezzo.")
            return
        if semplice and not v["nome"].strip():
            v["nome"] = f"{'Deposito a termine' if cat == 'deposito' else 'Liquidità'} {valuta}" + (f" {v['cedola_annua_pct']:g}%" if v.get("cedola_annua_pct") else "")
        k = sp.crea_prodotto(reg, v)
        stg.aggiungi_acquisto(c, pf, reg, k, data.isoformat(), prezzo, comm, quantita=qta)
        dati.salva_cliente(c); dati.salva_registro(reg)
        if semplice:
            st.session_state[f"cap_chiedi_{pid}"] = (qta, v["nome"])
        st.session_state[f"np_ultimo_{pid}"] = {"categoria": cat, "sottocategoria": v["sottocategoria"] if cat == "etf_azioni" else ""}
        st.session_state[f"np_gen_{pid}"] = st.session_state.get(f"np_gen_{pid}", 0) + 1          # campi nuovi e vuoti per il prossimo prodotto
        st.session_state["cli_msg"] = (f"«{v['nome']}» aggiunto alla strategia.", [])
        st.rerun()


def _da_screenshot(c, reg, pf):
    from core import parser_ibkr
    st.caption("Carica uno screenshot (o un PDF) della pagina Portfolio → Positions di Interactive Brokers: leggo simboli, quantità e costi. Controlla la tabella prima di importare.")
    f = st.file_uploader("Screenshot o PDF", type=["png", "jpg", "jpeg", "pdf"], key=f"ib_up_{pf['id']}")
    if not f:
        return
    try:
        pos = parser_ibkr.leggi(f)
    except Exception as e:
        st.error(f"Non riesco a leggere il file: {e}")
        return
    from core.anagrafica import classifica_da_nome
    from core.config import BORSA_DEFAULT
    gia = {(x["strumento"], round(x["quantita"], 6)) for x in stg.calcola(c, pf, reg)["righe"]}
    borse = sp.BORSE_LISTA
    righe = []
    for i, p in enumerate(pos):
        cat, sub = classifica_da_nome(p.nome)
        k = reg.trova("", p.simbolo)
        esiste = bool(k and (k, round(p.quantita, 6)) in gia)
        pe = p.prezzo_effettivo()
        ok = bool(p.costo_totale and p.quantita and p.prezzo_medio and abs(p.quantita * p.prezzo_medio - p.costo_totale) <= max(0.01 * p.costo_totale, 1))
        righe.append({"_i": i, "Importa": not esiste, "Ticker": p.simbolo, "Borsa": BORSA_DEFAULT if p.valuta == "USD" else borse[1], "Nome": p.nome,
                      "Tipo": "ETF" if (sub or "").startswith("ETF") or "ETF" in p.nome.upper() or "ISHARES" in p.nome.upper() or "UCITS" in p.nome.upper() else "Azione",
                      "Valuta": p.valuta, "Quantità": p.quantita, "Costo totale": p.costo_totale, "Prezzo medio": round(pe, 4) if pe else None, "Data acquisto": date.today(),
                      "Controllo": "già presente" if esiste else ("✓" if ok else "⚠ controlla")})
    ed = st.data_editor(pd.DataFrame(righe), hide_index=True, width="stretch", key=f"ib_ed_{pf['id']}", disabled=["Controllo"],
                        column_config={"_i": None, "Tipo": st.column_config.SelectboxColumn(options=["Azione", "ETF"]), "Valuta": st.column_config.SelectboxColumn(options=sp.VALUTE),
                                       "Borsa": st.column_config.SelectboxColumn(options=borse), "Data acquisto": st.column_config.DateColumn(format="DD.MM.YYYY")})
    st.caption("La data di acquisto non è nello screenshot: parte da oggi, impostala per ogni riga. Controlla la **borsa** di ogni titolo (USA per i titoli americani, Xetra/Londra/Milano per gli ETF europei).")
    if bottone("Importa le righe spuntate", "verde", f"ib_ok_{pf['id']}"):
        n = 0
        from core import ticker as tk
        for r in ed.to_dict("records"):
            if not r["Importa"] or not r["Quantità"] or not r["Costo totale"]:
                continue
            k = reg.trova("", r["Ticker"]) or reg.assicura("", r["Ticker"], r["Nome"], r["Valuta"], False)
            s = reg.strumenti[k]
            s.update(categoria="etf_azioni", sottocategoria="ETF azionario" if r["Tipo"] == "ETF" else "Azione ordinaria", valuta=r["Valuta"], valutazione="mercato", prezzo_in_percento=False,
                     ticker=str(r["Ticker"]).upper(), borsa=r["Borsa"], confermato=True)
            tk.applica(s)
            d = r["Data acquisto"]
            stg.aggiungi_acquisto(c, pf, reg, k, d.isoformat() if hasattr(d, "isoformat") else str(d), r["Costo totale"] / r["Quantità"], 0.0, quantita=float(r["Quantità"]))
            n += 1
        dati.completa_strumenti(c, reg, nuovi_solo=set(reg.strumenti))
        dati.salva_cliente(c); dati.salva_registro(reg)
        st.session_state["cli_msg"] = (f"Importate {n} posizioni.", [])
        st.session_state[f"pan_{pf['id']}"] = None
        st.rerun()


# ───────────────────────── registra transazione ─────────────────────────
def _pannello_transazione(c, reg, pf, calc, vendita: bool = False):
    pid = pf["id"]
    gen = st.session_state.get(f"tx_gen_{pid}", 0)
    pre = f"{'sell' if vendita else 'tx'}_{pid}_{gen}"
    cA, cB = st.columns([6, 1], vertical_alignment="center")
    cA.markdown("**Vendi un prodotto** · il prodotto passa fra i «Venduti e scaduti» e il risultato entra nella performance" if vendita
                else "**Registra transazione** · cedole, interessi, dividendi, premi, rimborsi, vendite e costi (anche spese di deposito)")
    with cB:
        if st.button("Chiudi", key=f"tx_chiudi_{pid}", width="stretch"):
            st.session_state[f"pan_{pid}"] = None
            _rerun_frammento()
    prodotti = {x["strumento"]: x["nome"] for x in (calc["attive"] if vendita else calc["righe"])}
    tipi = ["vendita", "rimborso"] if vendita else list(stg.TIPI_TRANSAZIONE)
    a, b, d = st.columns(3)
    tipo = a.selectbox("Che transazione è?", tipi, format_func=lambda x: stg.TIPI_TRANSAZIONE[x][0], key=f"{pre}_tipo")
    serve_prod = stg.TIPI_TRANSAZIONE[tipo][1]
    if serve_prod:
        if not prodotti:
            st.info("Aggiungi prima un prodotto.")
            return
        k = b.selectbox("Prodotto", list(prodotti), format_func=lambda x: prodotti[x], key=f"{pre}_k")
    else:
        opz = [""] + list(prodotti)
        k = b.selectbox("A cosa si riferisce", opz, format_func=lambda x: "Costo del portafoglio" if not x else f"Costo del prodotto: {prodotti[x]}", key=f"{pre}_k")
    data = d.date_input("Data", format="DD.MM.YYYY", key=f"{pre}_d")
    val_def = reg.strumenti[k]["valuta"] if k else pf["valuta"]
    e, f_, g = st.columns(3)
    if tipo in ("rimborso", "vendita"):
        netto = sum(x["quantita"] for x in calc["attive"] if x["strumento"] == k)
        imp = e.number_input(f"Importo ricevuto ({val_def})", min_value=0.0, value=0.0, format="%.2f", key=f"{pre}_i",
                             help="Il rimborso riguarda il nominale: ciò che hai pagato in acquisto non ti viene restituito, conta solo quanto incassi.")
        qta = f_.number_input("Quantità / nominale chiuso (vuoto = tutto)", min_value=0.0, value=0.0, format="%.4f", key=f"{pre}_q")
        nota = g.text_input("Nota", key=f"{pre}_n")
        st.caption(f"In portafoglio: {_e(netto, 4).rstrip('0').rstrip('.')}.")
        if bottone("Registra", "verde", f"{pre}_ok"):
            if imp <= 0:
                st.error("Inserisci l'importo ricevuto.")
                return
            stg.registra_rimborso_o_vendita(c, pf, reg, k, tipo, data.isoformat(), imp, qta or None, nota)
            dati.salva_cliente(c)
            st.session_state[f"tx_gen_{pid}"] = gen + 1
            st.session_state["cli_msg"] = ("Transazione registrata.", [])
            st.rerun()
    elif serve_prod:
        imp = e.number_input(f"Importo ricevuto ({val_def})", min_value=0.0, value=0.0, format="%.2f", key=f"{pre}_i")
        tax = f_.number_input("Imposta trattenuta (facoltativa)", min_value=0.0, value=0.0, format="%.2f", key=f"{pre}_x")
        nota = g.text_input("Nota (es. cedola 2° trimestre)", key=f"{pre}_n")
        if bottone("Registra", "verde", f"{pre}_ok"):
            if imp <= 0:
                st.error("Inserisci l'importo.")
                return
            stg.registra_incasso(c, pf, reg, k, tipo, data.isoformat(), imp, tax, nota)
            dati.salva_cliente(c)
            st.session_state[f"tx_gen_{pid}"] = gen + 1
            st.session_state["cli_msg"] = ("Transazione registrata.", [])
            st.rerun()
    else:
        val = e.selectbox("Valuta", VALUTE, index=VALUTE.index(val_def) if val_def in VALUTE else 0, key=f"{pre}_v")
        imp = f_.number_input("Importo", min_value=0.0, value=0.0, format="%.2f", key=f"{pre}_i")
        desc = g.text_input("Descrizione (facoltativa)", key=f"{pre}_n")
        if bottone("Registra", "verde", f"{pre}_ok"):
            if imp <= 0:
                st.error("Inserisci l'importo.")
                return
            stg.registra_costo(c, pf, tipo, data.isoformat(), imp, val, desc, k, reg)
            dati.salva_cliente(c)
            st.session_state[f"tx_gen_{pid}"] = gen + 1
            st.session_state["cli_msg"] = ("Costo registrato.", [])
            st.rerun()
    v = dati.vista_portafoglio(c, pid)
    ordinati = dati.transazioni_ordinate(v)
    if serve_prod and k:
        movs = [t for t in ordinati if t.get("strumento") == k]                        # storia completa del prodotto: acquisto con spese, incassi, costi, vendita o rimborso
        titolo_storia = f"Storia di «{prodotti.get(k, '')}» ({len(movs)} movimenti)"
    elif k:
        movs = [t for t in ordinati if t.get("strumento") == k and t["tipo"] in list(stg.TIPI_COSTO_UI)]
        titolo_storia = f"Costi di «{prodotti.get(k, '')}» ({len(movs)})"
    else:
        movs = [t for t in ordinati if not t.get("strumento") and t["tipo"] in list(stg.TIPI_COSTO_UI)]
        titolo_storia = f"Costi del portafoglio ({len(movs)})"
    if movs:
        with st.expander(titolo_storia, expanded=True):
            df = pd.DataFrame([{"id": t["id"], "Elimina": False, "Data": date.fromisoformat(t["data"]), "Tipo": dati.ETICHETTE_TIPO.get(t["tipo"], t["tipo"]),
                                "Quantità": t.get("quantita"), "Prezzo": t.get("prezzo"), "Valuta": t["valuta"], "Importo": t["importo_cassa"],
                                "Costi": (t.get("commissione") or 0.0) + (t.get("tasse") or 0.0) or None, "Origine": t.get("fonte", "")} for t in movs])
            ed = st.data_editor(df, hide_index=True, width="stretch", key=f"inc_tab_{pid}_{k or 'portafoglio'}", column_config={"id": None, "Importo": st.column_config.NumberColumn(format="%.2f"), "Data": st.column_config.DateColumn(format="DD.MM.YYYY")},
                                disabled=["Tipo", "Quantità", "Prezzo", "Valuta", "Costi", "Origine"])
            st.caption("Acquisti e vendite si correggono dalla tabella dei prodotti; qui puoi correggere o eliminare incassi e costi.")
            if bottone("Salva modifiche agli incassi e ai costi", "verde", f"inc_tabsave_{pid}"):
                per_id = {t["id"]: t for t in c["transazioni"]}
                for r in ed.to_dict("records"):
                    t = per_id[r["id"]]
                    if t["tipo"] in ("acquisto", "vendita", "rimborso"):
                        if r["Elimina"] and t["tipo"] != "acquisto":
                            c["transazioni"].remove(t)
                        continue
                    if r["Elimina"]:
                        c["transazioni"].remove(t)
                    else:
                        t["data"] = t["data_valuta"] = r["Data"].isoformat() if hasattr(r["Data"], "isoformat") else str(r["Data"]); t["importo_cassa"] = float(r["Importo"])
                dati.salva_cliente(c)
                st.rerun()


# ───────────────────────── avvisi e correzioni (in fondo alla pagina) ─────────────────────────
def _url_google(ticker, isin, nome, cambio: bool = False) -> str:
    import urllib.parse
    q = (f"{ticker} price" if ticker else (f"{isin} price" if isin else (f"{nome} price" if nome else ""))) if not cambio else f"{ticker} exchange rate"
    return "https://www.google.com/search?q=" + urllib.parse.quote(q)


def prezzi_da_verificare(c, reg, pf, problemi: list[dict], chiave: str, dopo=None):
    """Tabella unica: vedi ticker, ISIN e nome, inserisci i valori e conferma tutto in una volta."""
    righe = []
    for p in [x for x in problemi if isinstance(x, dict) and x.get("chiave")]:
        if p.get("tipo") == "prezzo":
            righe.append({"chiave": p["chiave"], "Prodotto": p.get("nome", ""), "Ticker": p.get("ticker", ""), "ISIN": p.get("isin", ""), "Problema": str(p.get("stato", "")).replace("_", " "), "Cerca": _url_google(p.get("ticker"), p.get("isin"), p.get("nome")),
                          "Fonte principale": p.get("prezzo"), "Fonte di controllo": p.get("prezzo_controllo"), "Valore da usare": p.get("prezzo")})
        else:
            righe.append({"chiave": p["chiave"], "Prodotto": f"Cambio {str(p['chiave']).split('@')[0]}", "Ticker": "", "ISIN": "", "Problema": "discrepanza tra fonti", "Cerca": _url_google(f"{str(p['chiave']).split('@')[0]}", None, None, cambio=True),
                          "Fonte principale": p.get("tasso"), "Fonte di controllo": p.get("alternativo"), "Valore da usare": p.get("tasso")})
    if not righe:
        return
    df = pd.DataFrame(righe)
    ed = st.data_editor(df, hide_index=True, width="stretch", key=f"pv_{chiave}", column_config={"chiave": None, "Cerca": st.column_config.LinkColumn("Cerca il prezzo", display_text="🔎 Google"), "Fonte principale": st.column_config.NumberColumn(format="%.4f"),
                        "Fonte di controllo": st.column_config.NumberColumn(format="%.4f"), "Valore da usare": st.column_config.NumberColumn(format="%.6f")},
                        disabled=["Prodotto", "Ticker", "ISIN", "Problema", "Cerca", "Fonte principale", "Fonte di controllo"])
    if bottone("Conferma tutti i valori", "verde", f"pv_ok_{chiave}"):
        man = dati.carica_manuali()
        n = 0
        for r in ed.to_dict("records"):
            v = r["Valore da usare"]
            if v is not None and v == v and float(v) > 0:
                man[r["chiave"]] = float(v)
                n += 1
        dati.salva_manuali(man)
        if dopo:
            dopo()
        st.session_state["cli_msg"] = (f"Confermati {n} valori.", [])
        st.rerun()


def _avvisi(c, reg, pf, calc, L):
    pid = pf["id"]
    voci = []                              # (gravità, titolo, funzione che disegna)
    barr = [b for b in (L.get("barriere") or []) if b.get("completo")]
    vicine = [b for b in barr if b["semaforo"] != "verde"]
    prob = [x for x in (L.get("problemi_prezzi") or []) if isinstance(x, dict) and x.get("chiave")]
    schede = {}
    from core.completezza import riepilogo_cliente
    schede = riepilogo_cliente(dati.vista_portafoglio(c, pid), reg)
    schede_bl = {k: v for k, v in schede.items() if v["bloccanti"] or v["consigliati"]}
    cambi = [a for a in calc["avvisi"]]
    calcolo_av = []
    err = L.get("errore")
    n = len(vicine) + len(prob) + len(schede_bl) + len(cambi) + len(calcolo_av) + (1 if err else 0)
    if not n:
        return
    with st.container(border=True):
        st.markdown(f"#### Avvisi e correzioni ({n})")
        if barr:
            with st.expander(f"Distanza dalle barriere ({len(vicine)} sotto il 20%)", expanded=any(b["semaforo"] in ("arancio", "rosso") for b in barr)):
                nomi_osv = {b["chiave"]: b.get("osservazione") for b in barr}
                st.dataframe(pd.DataFrame([{"Prodotto": b["nome"], "Sottostante peggiore": b["peggiore"], "Distanza dalla barriera": b["buffer"], "Livello": LIVELLI[b["semaforo"]],
                                            "Osservazione": {"europea": "europea", "americana": "americana"}.get(nomi_osv.get(b["chiave"]), "–")} for b in sorted(barr, key=lambda x: x["buffer"])]),
                             hide_index=True, width="stretch", column_config={"Distanza dalla barriera": st.column_config.NumberColumn(format="percent")})
                st.caption("Avvisi a 20%, 10% e 5% di distanza. Con osservazione americana basta un tocco in un giorno qualsiasi; con quella europea conta il livello alla data finale.")
        if prob:
            with st.expander(f"Prezzi e cambi da verificare ({len(prob)})", expanded=True):
                prezzi_da_verificare(c, reg, pf, prob, f"{pid}")
        for a_ in cambi:                                  # il cambio del giorno si applica da solo; il tasso preciso si conferma solo al momento del report
            st.caption("ℹ " + a_.replace(" Inseriscilo a mano.", " Lo confermi alla creazione del report."))
        if schede_bl:
            with st.expander(f"Schede prodotto da completare ({len(schede_bl)})", expanded=any(v["bloccanti"] for v in schede_bl.values())):
                for k, v in schede_bl.items():
                    st.markdown(f"**{v['nome']}**: " + " · ".join(v["bloccanti"] + [f"(facoltativo) {t}" for t in v["consigliati"]]))
                    with st.expander(f"Correggi «{v['nome']}»"):
                        sp.scheda(reg, k, dati.vista_portafoglio(c, pid), f"av{pid}", cliente=c, pid=pid)
        if err:
            st.caption(f"⚠ Ultimo aggiornamento dei prezzi non riuscito: {err}")


# ───────────────────────── pagina ─────────────────────────
def render(c, reg, pf):
    pid = pf["id"]
    calc = stg.calcola(c, pf, reg, _cerca)
    L = _panoramica(c, reg, pf, calc)
    _blocco_prodotti(c, reg, pf, calc, L)

    st.markdown("#### Documenti")
    o1, o2, o3, _ = st.columns([1, 1, 1, 2])
    from core.strategia_pdf import genera_pdf_strategia
    with o1:
        if bottone("Prepara il PDF della strategia", "blu", f"st_pdf_{pid}", width="stretch"):
            st.session_state[f"st_pdfb_{pid}"] = genera_pdf_strategia(c, pf, calc)
    with o2:
        if bottone("Crea il report", "blu", f"st_rep_{pid}", width="stretch"):
            st.session_state[f"st_repopen_{pid}"] = not st.session_state.get(f"st_repopen_{pid}", False)
    with o3:
        testo = stg.testo_analisi(c, pf, calc)
        bottone_link("Analizza la strategia con Claude", "arancio", f"st_claude_{pid}", stg.link_claude(testo), width="stretch", icon=":material/auto_awesome:")
    if st.session_state.get(f"st_pdfb_{pid}"):
        st.download_button("Scarica il PDF della strategia", st.session_state[f"st_pdfb_{pid}"], file_name=f"Strategia_{c['nome'].replace(' ', '_')}_{date.today().isoformat()}.pdf",
                           mime="application/pdf", key=f"st_pdfd_{pid}")
    if st.session_state.get(f"rep_pdf_{pid}"):
        pdf, nome = st.session_state[f"rep_pdf_{pid}"]
        st.success("Report generato e archiviato.")
        st.download_button("Scarica il report", pdf, file_name=nome, mime="application/pdf", key=f"rep_dl_{pid}")
    with st.expander("Testo inviato a Claude (puoi copiarlo in una chat o in un progetto fisso)"):
        st.code(testo, language=None)
        st.download_button("Scarica il testo (.txt)", testo, file_name="analisi_strategia.txt", key=f"st_txt_{pid}")
        st.caption("Il pulsante apre una nuova chat di Claude con il testo già inserito. Per una chat fissa, crea un Progetto «Analisi strategie» su claude.ai e incolla il testo.")
    if st.session_state.get(f"st_repopen_{pid}"):
        from modules import report
        with riquadro("blu", f"rep_{pid}"):
            st.markdown("#### Report per il cliente")
            report.pannello(c, reg, pf)
    _avvisi(c, reg, pf, calc, L)
