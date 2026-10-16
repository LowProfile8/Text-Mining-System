"""Creazione e modifica di un prodotto: prima il tipo, poi solo i campi pertinenti.
Un solo ticker + la borsa di riferimento (menu a tendina); se il ticker non trova il prezzo si usa l'ISIN. Niente «opzioni avanzate»."""

from __future__ import annotations

from datetime import date

import pandas as pd
import streamlit as st

from core import classificatore, dati, ticker as tk
from core.completezza import problemi_strumento
from core.config import AREE_GEO, BORSA_DEFAULT, BORSE, OSSERVAZIONI, SETTORI, TIPI_PRODOTTO, VALUTAZIONE_DEFAULT
from core.stile import bottone, gma

VALUTE = ["CHF", "EUR", "USD", "GBP", "JPY", "CAD", "AUD", "SEK", "NOK", "DKK"]
FREQ = {None: "nessuna", 1: "annuale", 2: "semestrale", 4: "trimestrale", 12: "mensile"}
BORSE_LISTA = list(BORSE)
SUB_CON_REBATE = ("Capital Protection Note", "Shark Note con rebate (knock-out)", "Bullish Shark Note", "Bearish Shark Note")
SUB_SENZA_BARRIERA_INFERIORE = ("Capital Protection Note", "Shark Note con rebate (knock-out)", "Bullish Shark Note", "Bearish Shark Note", "Tracker / Participation")


def _d(s):
    try:
        return date.fromisoformat(s) if s else None
    except ValueError:
        return None


def tipo_di(s: dict) -> str:
    """Etichetta del tipo (Azione, ETF, Obbligazione…) di uno strumento esistente."""
    cat, sotto = s.get("categoria"), s.get("sottocategoria", "")
    if cat == "etf_azioni":
        return "ETF" if sotto.startswith("ETF") or "ETF" in s.get("nome", "").upper() else "Azione"
    for lab, (c, _) in TIPI_PRODOTTO.items():
        if c == cat:
            return lab
    return "Azione"


def problemi_testo(s: dict) -> list[tuple[str, str]]:
    return problemi_strumento(s)


def mostra_problemi(s: dict):
    pr = problemi_strumento(s)
    if not pr:
        st.success("Scheda completa.")
        return
    for g, t in pr:
        (st.warning if g == "bloccante" else st.info)(("Da inserire: " if g == "bloccante" else "Facoltativo: ") + t)


def _num(v):
    return float(v) if v is not None and v == v else None


def _con_pesi(titolo: str, opzioni: list[str], attuali: dict, chiave: str, aiuto: str = "") -> dict:
    """Menu a scelta multipla; se si scelgono più voci chiede il peso di ciascuna (precompilato in parti uguali, modificabile). Restituisce {voce: peso 0-1}."""
    extra = [k for k in attuali if k not in opzioni]
    sel = st.multiselect(titolo, sorted(set(opzioni) | set(extra)), default=list(attuali), key=f"{chiave}_sel", placeholder="Automatico", help=aiuto or None)
    if len(sel) <= 1:
        return {k: 1.0 for k in sel}
    n = len(sel)
    uguali = [round(100.0 / n, 2)] * n
    uguali[-1] = round(100.0 - sum(uguali[:-1]), 2)
    if set(attuali) == set(sel) and abs(sum(attuali.values()) - 1) < 1e-6:
        base = [round(100 * attuali[k], 2) for k in sel]
    else:
        base = uguali
    ed = st.data_editor(pd.DataFrame({"Voce": sel, "Peso %": base}), hide_index=True, width="stretch", disabled=["Voce"], key=f"{chiave}_w_{'|'.join(sel)}",
                        column_config={"Peso %": st.column_config.NumberColumn(min_value=0.0, max_value=100.0, format="%.2f")})
    pesi = {r["Voce"]: float(r["Peso %"] or 0.0) for r in ed.to_dict("records")}
    tot = sum(pesi.values())
    if tot <= 0:
        return {k: 1.0 / n for k in sel}
    if abs(tot - 100) > 0.05:
        st.caption(f"I pesi sommano {tot:.1f}%: li riporto a 100%.")
    return {k: v / tot for k, v in pesi.items() if v > 0}


def _valutazione_default(cat: str, sotto: str, ticker: str, esistente: str | None) -> str:
    if sotto == "Criptovaluta":
        return "mercato"
    if cat == "obbligazione":
        if ticker:
            return "mercato"
        return "scadenza" if esistente == "scadenza" else "manuale"
    return VALUTAZIONE_DEFAULT.get(cat, "mercato")


def campi_prodotto(p: str, s: dict) -> dict:
    """Disegna i campi e restituisce i valori inseriti (nessun st.form: i menu dipendenti si aggiornano subito)."""
    out: dict = {}
    tipi = list(TIPI_PRODOTTO)
    t0 = tipo_di(s) if s.get("categoria") else "Azione"
    tipo = st.radio("Che tipo di prodotto è?", tipi, index=tipi.index(t0), horizontal=True, key=f"{p}_tipo")
    cat, sotto_opz = TIPI_PRODOTTO[tipo]
    out["categoria"] = cat
    cur_sub = s.get("sottocategoria") if s.get("sottocategoria") in sotto_opz else sotto_opz[0]
    c1, c2 = st.columns(2)
    out["sottocategoria"] = c1.selectbox("Tipologia", sotto_opz, index=sotto_opz.index(cur_sub), key=f"{p}_sub_{tipo}")
    sub = out["sottocategoria"]
    out["nome"] = c2.text_input("Nome del prodotto", s.get("nome", ""), key=f"{p}_nome")
    c1, c2, c3 = st.columns(3)
    out["valuta"] = c1.selectbox("Valuta", VALUTE, index=VALUTE.index(s["valuta"]) if s.get("valuta") in VALUTE else 0, key=f"{p}_val")
    out["isin"] = c2.text_input("ISIN (serve se il ticker non trova il prezzo)", s.get("isin", ""), key=f"{p}_isin").strip().upper()
    pct = cat in ("obbligazione", "strutturato")
    out["prezzo_in_percento"] = pct
    c3.markdown(f"<div style='padding-top:1.9rem;color:#9A9FAD;font-size:0.85rem'>Prezzo: <b style='color:#F4EFE6'>{'in % del nominale' if pct else 'valore per unità'}</b></div>", unsafe_allow_html=True)

    for k in ("ticker", "borsa", "ticker_mercato", "ticker_controllo"):
        out[k] = s.get(k, "")
    out["data_emissione"] = _d(s.get("data_emissione"))
    out["scadenza"] = _d(s.get("scadenza"))
    for k in ("frequenza_cedola", "cedola_annua_pct", "barriera_pct", "protezione_pct", "strike", "rebate_pct", "barriera_superiore_pct", "partecipazione_pct", "osservazione"):
        out[k] = s.get(k)
    out["sottostanti"] = s.get("sottostanti", [])

    # ── un solo ticker + borsa ──
    usa_ticker = cat in ("etf_azioni", "opzione") or sub == "Criptovaluta" or cat == "obbligazione"
    if usa_ticker:
        c1, c2 = st.columns([1, 2])
        t_att = s.get("ticker") or ((s.get("ticker_mercato") or "") if not s.get("borsa") else "")
        out["ticker"] = c1.text_input("Ticker" + (" (facoltativo)" if cat == "obbligazione" else ""), t_att, key=f"{p}_tick",
                                      help="Il ticker così come lo conosci (es. QUBT, VHYL, ENI). Se è già completo (BTC-USD, ^GSPC, VHYL.L) lascio com'è.").strip().upper()
        b_att = s.get("borsa") if s.get("borsa") in BORSE_LISTA else (BORSE_LISTA[-1] if ("." in t_att or t_att.startswith("^") or "-" in t_att) else BORSA_DEFAULT)
        out["borsa"] = c2.selectbox("Borsa di riferimento", BORSE_LISTA, index=BORSE_LISTA.index(b_att), key=f"{p}_borsa",
                                    help="Il prezzo si cerca con ticker + borsa; se non si trova, con l'ISIN.")
        if out["ticker"]:
            st.caption(f"Cercherò il prezzo come **{tk.simbolo_yahoo(out['ticker'], out['borsa'])}**" + (f" (controllo: {tk.simbolo_stooq(out['ticker'], out['borsa'])})" if tk.simbolo_stooq(out["ticker"], out["borsa"]) else "")
                       + (" · in alternativa con l'ISIN." if out["isin"] else ". Se non lo trova, aggiungi l'ISIN."))
        elif cat != "obbligazione" and not out["isin"]:
            st.caption("Senza ticker né ISIN il prezzo non si può trovare.")
        elif cat == "obbligazione":
            st.caption("Senza ticker il prezzo dell'obbligazione (in %) lo aggiorni tu nella tabella.")

    if cat == "opzione":
        c1, c2 = st.columns(2)
        out["strike"] = c1.number_input("Strike", value=float(s.get("strike") or 0.0), format="%.4f", key=f"{p}_strike")
        out["scadenza"] = c2.date_input("Scadenza dell'opzione", value=_d(s.get("scadenza")), format="DD.MM.YYYY", key=f"{p}_sc")
    if cat == "etf_azioni":
        c1, c2 = st.columns(2)
        out["cedola_annua_pct"] = c1.number_input("Dividendo / distribuzione annua stimata % (facoltativo)", min_value=0.0, value=float(s.get("cedola_annua_pct") or 0.0), format="%.2f",
                                                  key=f"{p}_dist", help="Se l'ETF o l'azione distribuisce proventi: serve per le cedole attese. Gli incassi veri li registri con «Registra transazione».") or None
        fk = list(FREQ)
        out["frequenza_cedola"] = c2.selectbox("Frequenza della distribuzione", fk, index=fk.index(s.get("frequenza_cedola")) if s.get("frequenza_cedola") in fk else 0,
                                               format_func=lambda x: FREQ[x], key=f"{p}_frd")
    if cat == "deposito":
        c1, c2 = st.columns(2)
        out["data_emissione"] = c1.date_input("Inizio del deposito", value=_d(s.get("data_emissione")), format="DD.MM.YYYY", key=f"{p}_em")
        out["scadenza"] = c2.date_input("Scadenza", value=_d(s.get("scadenza")), format="DD.MM.YYYY", key=f"{p}_sc")
        c1, c2 = st.columns(2)
        out["cedola_annua_pct"] = c1.number_input("Tasso d'interesse annuo %", value=float(s.get("cedola_annua_pct") or 0.0), format="%.4f", key=f"{p}_ced") or None
        fk = list(FREQ)
        out["frequenza_cedola"] = c2.selectbox("Pagamento interessi", fk, index=fk.index(s.get("frequenza_cedola") or 1), format_func=lambda x: FREQ[x], key=f"{p}_fr")
    if cat in ("obbligazione", "strutturato"):
        c1, c2 = st.columns(2)
        out["data_emissione"] = c1.date_input("Emissione / data di fissazione iniziale", value=_d(s.get("data_emissione")), format="DD.MM.YYYY", key=f"{p}_em")
        out["scadenza"] = c2.date_input("Scadenza / rimborso", value=_d(s.get("scadenza")), format="DD.MM.YYYY", key=f"{p}_sc")
        c1, c2 = st.columns(2)
        out["cedola_annua_pct"] = c1.number_input("Cedola annua %", value=float(s.get("cedola_annua_pct") or 0.0), format="%.4f", key=f"{p}_ced") or None
        fk = list(FREQ)
        out["frequenza_cedola"] = c2.selectbox("Frequenza cedola", fk, index=fk.index(s.get("frequenza_cedola")) if s.get("frequenza_cedola") in fk else 0,
                                               format_func=lambda x: FREQ[x], key=f"{p}_fr")
    if cat == "strutturato":
        rebate_ok = sub in SUB_CON_REBATE
        c1, c2, c3 = st.columns(3)
        if sub not in SUB_SENZA_BARRIERA_INFERIORE:
            out["barriera_pct"] = c1.number_input("Barriera % del livello iniziale", min_value=0.0, value=float(s.get("barriera_pct") or 0.0), format="%.2f", key=f"{p}_bar",
                                                  help="Esempio 60 = la barriera è al 60% del livello iniziale (distanza 40%). 0 = nessuna barriera.") or None
            osk = list(OSSERVAZIONI)
            out["osservazione"] = c2.selectbox("Osservazione della barriera", osk, index=osk.index(s.get("osservazione")) if s.get("osservazione") in osk else 0, format_func=lambda x: OSSERVAZIONI[x],
                                               key=f"{p}_osv", help="Europea: conta solo il livello alla data finale. Americana: basta un tocco in un qualsiasi giorno.")
        else:
            out["barriera_pct"], out["osservazione"] = None, s.get("osservazione")
        out["protezione_pct"] = c3.number_input("Capitale protetto % del nominale", min_value=0.0, value=float(s.get("protezione_pct") or 0.0), format="%.2f", key=f"{p}_prot",
                                                help="Es. 100 per una Capital Protection Note al 100%. 0 = nessuna protezione.") or None
        if rebate_ok:
            c1, c2, c3 = st.columns(3)
            out["partecipazione_pct"] = c1.number_input("Partecipazione al rialzo %", min_value=0.0, value=float(s.get("partecipazione_pct") or 0.0), format="%.2f", key=f"{p}_part") or None
            out["barriera_superiore_pct"] = c2.number_input("Barriera superiore (knock-out) % del livello iniziale", min_value=0.0, value=float(s.get("barriera_superiore_pct") or 0.0), format="%.2f", key=f"{p}_bsup") or None
            out["rebate_pct"] = c3.number_input("Rebate % del nominale (se il knock-out scatta)", min_value=0.0, value=float(s.get("rebate_pct") or 0.0), format="%.2f", key=f"{p}_reb") or None
        st.caption("Sottostanti: ticker (una volta sola) + borsa; per gli indici scegli «ticker completo» (es. ^GSPC, ^STOXX50E, ^SSMI). Il livello iniziale è la chiusura alla data di fissazione.")
        righe = []
        for u in s.get("sottostanti", []):
            righe.append({"Ticker": u.get("ticker_base") or u.get("ticker", ""), "Borsa": u.get("borsa") if u.get("borsa") in BORSE_LISTA else (BORSE_LISTA[-1] if not u.get("ticker_base") else BORSA_DEFAULT),
                          "Nome": u.get("nome", ""), "Livello iniziale": u.get("livello_iniziale")})
        righe = righe or [{"Ticker": "", "Borsa": BORSA_DEFAULT, "Nome": "", "Livello iniziale": None}]
        ed = st.data_editor(pd.DataFrame(righe), num_rows="dynamic", hide_index=True, width="stretch", key=f"{p}_sott",
                            column_config={"Borsa": st.column_config.SelectboxColumn(options=BORSE_LISTA, default=BORSA_DEFAULT, required=True)})
        sott = []
        for r in ed.to_dict("records"):
            t_ = str(r["Ticker"] or "").strip().upper()
            if not t_ and not str(r["Nome"] or "").strip():
                continue
            b_ = r["Borsa"] if r["Borsa"] in BORSE_LISTA else BORSA_DEFAULT
            sott.append({"ticker": tk.simbolo_yahoo(t_, b_), "ticker_base": t_, "borsa": b_, "nome": str(r["Nome"] or "").strip() or t_, "livello_iniziale": _num(r["Livello iniziale"])})
        out["sottostanti"] = sott
    if cat == "alternativo" and sub != "Criptovaluta":
        nav = "\n".join(f"{x['data']};{x['nav']}" for x in s.get("nav_manuale", []))
        out["_nav_testo"] = st.text_area("Valore (NAV) – una riga per data: AAAA-MM-GG;valore", nav, key=f"{p}_nav", height=90)

    if cat not in ("liquidita", "deposito"):
        st.markdown("**Settore e area geografica** (facoltativi: se li lasci vuoti li ricavo io)")
        c1, c2 = st.columns(2)
        man = s.get("classificazione_manuale")
        with c1:
            out["_settori"] = _con_pesi("Settore", SETTORI, s.get("settori") or {} if man else {}, f"{p}_set", "Se ne scegli più d'uno ti chiedo il peso di ciascuno.")
        with c2:
            out["_aree"] = _con_pesi("Area geografica", AREE_GEO, s.get("aree") or {} if man else {}, f"{p}_are", "Se ne scegli più d'una ti chiedo il peso di ciascuna. «Mondo» per i fondi globali (es. MSCI World).")
    else:
        out["_settori"], out["_aree"] = {}, {}

    out["valutazione"] = _valutazione_default(cat, sub, out["ticker"] or out["ticker_mercato"], s.get("valutazione") if s.get("categoria") == cat else None)
    return out


def applica_campi(s: dict, v: dict):
    iso = lambda d: d.isoformat() if d else ""
    s.update(nome=v["nome"].strip() or s.get("nome", ""), categoria=v["categoria"], valuta=v["valuta"], sottocategoria=v["sottocategoria"], valutazione=v["valutazione"],
             ticker=(v.get("ticker") or "").strip(), borsa=v.get("borsa") or "", prezzo_in_percento=v["prezzo_in_percento"],
             data_emissione=iso(v["data_emissione"]), scadenza=iso(v["scadenza"]), frequenza_cedola=v["frequenza_cedola"], cedola_annua_pct=v["cedola_annua_pct"] or None,
             barriera_pct=v["barriera_pct"] or None, protezione_pct=v["protezione_pct"] or None, rebate_pct=v.get("rebate_pct") or None,
             barriera_superiore_pct=v.get("barriera_superiore_pct") or None, partecipazione_pct=v.get("partecipazione_pct") or None,
             osservazione=v.get("osservazione") if v.get("barriera_pct") else (s.get("osservazione") if v["categoria"] == "strutturato" else ""), sottostanti=v["sottostanti"])
    if s.get("ticker"):
        tk.applica(s)
    else:
        s["ticker_mercato"] = v.get("ticker_mercato", "") if v["categoria"] not in ("etf_azioni", "opzione", "obbligazione") else ""
        s["ticker_controllo"] = ""
    if v.get("strike"):
        s["strike"] = v["strike"]
    if v["isin"]:
        s["isin"] = v["isin"]
    if "_nav_testo" in v:
        navs = []
        for r in v["_nav_testo"].splitlines():
            q = [x.strip() for x in r.split(";")]
            if len(q) == 2:
                try:
                    navs.append({"data": q[0], "nav": float(q[1].replace(",", "."))})
                except ValueError:
                    pass
        s["nav_manuale"] = navs
    # classificazione: scelta manuale (con pesi) oppure automatica
    if v["_settori"] or v["_aree"]:
        auto = classificatore.classifica(s, None)
        s["settori"] = v["_settori"] or auto["settori"] or s.get("settori", {})
        s["aree"] = v["_aree"] or auto["aree"] or s.get("aree", {})
        s["classificazione_manuale"] = True
        s["classificazione_auto"] = "scelta manuale"
    else:
        if s.get("classificazione_manuale"):
            s["classificazione_manuale"] = False
            s["settori"], s["aree"] = {}, {}
        classificatore.applica(s, None)
    s["confermato"] = True


def crea_prodotto(reg, v: dict) -> str:
    sim = "" if v["isin"] else "MAN" + dati.db.nuovo_id()[:8].upper()
    k = reg.assicura(v["isin"], sim, v["nome"].strip(), v["valuta"], v["prezzo_in_percento"])
    applica_campi(reg.strumenti[k], v)
    return k


def clienti_del_prodotto(k: str) -> list[str]:
    return sorted({c["nome"] for c in dati.elenco_clienti() if any(t.get("strumento") == k for t in c.get("transazioni", []))})


def elimina_prodotto(c: dict, reg, k: str, pid: str) -> None:
    """Toglie il prodotto da questa strategia (tutte le sue transazioni); lo cancella dall'anagrafica se nessuna strategia di nessun cliente lo usa più."""
    c["transazioni"] = [t for t in c["transazioni"] if not (t.get("strumento") == k and dati._pf_di(c, t) == pid)]
    dati.salva_cliente(c)
    usato = any(t.get("strumento") == k for x in dati.elenco_clienti() for t in x.get("transazioni", []))
    if not usato:
        reg.strumenti.pop(k, None)
        dati.salva_registro(reg)


def acquisti_registrati(c: dict, k: str):
    tx = [t for t in dati.transazioni_ordinate(c) if t.get("strumento") == k and t["tipo"] in ("acquisto", "vendita", "rimborso")]
    if not tx:
        return
    st.markdown("**Operazioni registrate**")
    st.dataframe(pd.DataFrame([{"Data": gma(t["data"]), "Operazione": dati.ETICHETTE_TIPO.get(t["tipo"], t["tipo"]), "Quantità": t.get("quantita"),
                                "Prezzo": (f"{t['prezzo']:g}%" if t.get("prezzo_in_percento") and t.get("prezzo") else t.get("prezzo")), "Commissioni": (t.get("commissione") or 0) + (t.get("tasse") or 0),
                                "Importo": t["importo_cassa"], "Valuta": t["valuta"], "Origine": t.get("fonte", "")} for t in tx]), hide_index=True, width="stretch")


def recupera_livelli(reg, k: str, s: dict, ctx: str = "g"):
    """Livello iniziale = chiusura del sottostante alla data di fissazione. Da verificare con la scheda del prodotto."""
    mancanti = [u for u in s.get("sottostanti", []) if u.get("ticker") and not u.get("livello_iniziale")]
    if not mancanti:
        return
    with st.expander("Recupera i livelli iniziali dei sottostanti"):
        d = st.date_input("Data di fissazione iniziale (strike date)", value=_d(s.get("data_emissione")) or date.today(), format="DD.MM.YYYY", key=f"sp{ctx}_{k}_strike")
        if st.button("Recupera livelli mancanti", key=f"sp{ctx}_{k}_rec"):
            from core.mercato import mercato_reale
            m = mercato_reale()
            ok, ko = [], []
            for u in mancanti:
                v = m.spot(u["ticker"], d.isoformat())
                if v:
                    u["livello_iniziale"] = float(v)
                    ok.append(f"{u['ticker']} {v:,.2f}")
                else:
                    ko.append(u["ticker"])
            dati.salva_registro(reg)
            if ok:
                st.success("Recuperati: " + ", ".join(ok))
            if ko:
                st.warning("Non trovati (inserire a mano): " + ", ".join(ko))
            st.caption("Controlla i valori con il termsheet del prodotto prima di fidarti.")


def scheda(reg, k: str, c: dict | None = None, ctx: str = "g", cliente: dict | None = None, pid: str = ""):
    s = reg.strumenti[k]
    mostra_problemi(s)
    if c is not None:
        acquisti_registrati(c, k)
    v = campi_prodotto(f"sp{ctx}_{k}", s)
    b1, b2, _ = st.columns([1, 1, 3])
    with b1:
        if bottone("Salva scheda", "verde", f"sp{ctx}_{k}_salva", width="stretch"):
            applica_campi(s, v)
            dati.salva_registro(reg)
            st.success("Salvato.")
            st.rerun()
    if cliente is not None:
        with b2:
            if bottone("Elimina il prodotto", "giallo", f"sp{ctx}_{k}_del", width="stretch"):
                st.session_state[f"sp{ctx}_{k}_delask"] = True
        if st.session_state.get(f"sp{ctx}_{k}_delask"):
            st.warning(f"Eliminare «{s.get('nome')}» da questo cliente con tutte le sue operazioni? Non si può annullare.")
            y1, y2, _ = st.columns([1, 1, 3])
            with y1:
                if bottone("Sì, elimina", "giallo", f"sp{ctx}_{k}_delok", width="stretch"):
                    elimina_prodotto(cliente, reg, k, pid)
                    st.session_state.pop(f"sp{ctx}_{k}_delask", None)
                    st.rerun()
            with y2:
                if st.button("Annulla", key=f"sp{ctx}_{k}_delno", width="stretch"):
                    st.session_state.pop(f"sp{ctx}_{k}_delask", None)
                    st.rerun()
    recupera_livelli(reg, k, s, ctx)
    st.caption(f"Settori: {s.get('settori') or '—'} · Aree: {s.get('aree') or '—'} · {s.get('classificazione_auto', '')}")
    if cliente is not None:
        st.caption("Detenuto da: " + (", ".join(clienti_del_prodotto(k)) or "—"))
