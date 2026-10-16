"""Stato «in diretta» dei portafogli: valore, performance, allocazione e serie storica. Si calcola quando cambiano i dati e si salva nel cliente,
così la home legge tutto senza ricalcolare."""

from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, timedelta

import core.calcolo as calcolo
from core import dati
from core.performance import Contesto, calcola

RIFERIMENTO = "CHF"        # valuta in cui si sommano i portafogli di clienti diversi


def _fine_mesi(da: date, a: date) -> list[date]:
    out, y, m = [], da.year, da.month
    while True:
        ultimo = date(y + (m == 12), (m % 12) + 1, 1) - timedelta(days=1)
        if ultimo >= a:
            break
        if ultimo > da:
            out.append(ultimo)
        y, m = y + (m == 12), (m % 12) + 1
    return out + [a]


def firma(c: dict, pf: dict, reg) -> str:
    v = dati.vista_portafoglio(c, pf["id"])
    chiavi = {t.get("strumento") for t in v["transazioni"] if t.get("strumento")}
    base = [(t["id"], t["data"], t["tipo"], round(t["importo_cassa"], 4), t.get("quantita")) for t in v["transazioni"]]
    strum = {k: {x: reg.strumenti[k].get(x) for x in ("valutazione", "nav_manuale", "ticker_mercato", "scadenza", "cedola_annua_pct", "frequenza_cedola", "barriera_pct", "sottostanti", "settori", "aree", "prezzo_in_percento")}
             for k in chiavi if k in reg.strumenti}
    man = dati.carica_manuali()
    blob = json.dumps(["v4", pf["valuta"], date.today().isoformat(), base, strum, v["saldi"], man], sort_keys=True, default=str)
    return hashlib.sha1(blob.encode()).hexdigest()[:16]


def aggiorna(c: dict, pf: dict, reg, mercato=None) -> dict:
    """Ricalcola e salva pf['live']. Non solleva eccezioni: in caso di errore registra il messaggio e tiene l'ultimo stato valido."""
    v = dati.vista_portafoglio(c, pf["id"])
    tx = dati.transazioni_ordinate(v)
    vecchio = pf.get("live") or {}
    if not tx:
        pf["live"] = {"aggiornato": datetime.now().isoformat(timespec="seconds"), "firma": firma(c, pf, reg), "vuoto": True, "base": pf["valuta"], "serie": [], "errore": None}
        return pf["live"]
    try:
        m = mercato or calcolo.mercato_reale(manuali=dati.carica_manuali())
        oggi = date.today()
        from core.scadenze import con_scadenze
        tx, av_scad = con_scadenze(tx, reg.strumenti, oggi.isoformat())
        primo = date.fromisoformat(tx[0]["data"])
        inizio = primo - timedelta(days=1)
        base = pf["valuta"]
        ctx_args = dict(base=base, fx=m.fx, prezzo=m.prezzo, spot=m.spot)
        if hasattr(m, "precarica"):                                  # storici e cambi scaricati in parallelo, una volta sola
            usati = [reg.strumenti[k] for k in {t.get("strumento") for t in tx} if k in reg.strumenti]
            valute = {x.get("valuta") for x in usati if x.get("valuta")} | {t["valuta"] for t in tx if t.get("valuta")}
            m.precarica(usati, [(x, base) for x in valute if x and x != base] + ([(base, RIFERIMENTO)] if base != RIFERIMENTO else []))
        saldi = dati.saldi_a_data(v, oggi.isoformat())
        ris = calcola(tx, reg.strumenti, inizio.isoformat(), oggi.isoformat(), Contesto(**ctx_args), saldi_liquidita=saldi)
        # serie storica: i punti dei mesi passati si riusano finché movimenti e condizioni dei prodotti prima di quella data non cambiano
        vecchi = vecchio.get("serie_punti") or {}
        strum_sig = json.dumps({k: reg.strumenti[k] for k in {t.get("strumento") for t in tx} if k in reg.strumenti}, sort_keys=True, default=str)
        man_sig = json.dumps(dati.carica_manuali(), sort_keys=True, default=str)
        punti, serie = {}, []
        for d in _fine_mesi(primo, oggi):
            if d == oggi:
                p = ris["totale"].get("rendimento_dall_inizio")
            else:
                sig = hashlib.sha1(json.dumps([base, [(t["id"], t["data"], t["tipo"], round(t["importo_cassa"], 4), t.get("quantita")) for t in tx if t["data"] <= d.isoformat()], strum_sig, man_sig], default=str).encode()).hexdigest()[:12]
                hit = vecchi.get(d.isoformat())
                if hit and hit.get("sig") == sig:
                    p = hit.get("p")
                else:
                    try:
                        p = calcola(tx, reg.strumenti, inizio.isoformat(), d.isoformat(), Contesto(**ctx_args), saldi_liquidita={})["totale"].get("rendimento_dall_inizio")
                    except Exception:
                        continue
                punti[d.isoformat()] = {"sig": sig, "p": p}
            if p is not None:
                serie.append([d.isoformat(), round(100 * p, 3)])
        fx = m.fx(base, RIFERIMENTO, oggi.isoformat()) if base != RIFERIMENTO else 1.0
        t = ris["totale"]
        investito = sum(r.get("investito_alloc", r["investito"]) for r in ris["attivi"])
        problemi = []
        for p_ in m.problemi():
            k_ = str(p_.get("chiave", "")).split("@")[0]
            st_ = reg.strumenti.get(k_, {})
            problemi.append({**{x: p_.get(x) for x in ("tipo", "chiave", "stato", "prezzo", "prezzo_controllo", "fonte", "fonte_controllo", "scarto", "tasso", "alternativo", "nota")},
                             "nome": st_.get("nome", k_), "isin": st_.get("isin", ""), "ticker": st_.get("ticker_mercato", "")})
        pf["live"] = {
            "aggiornato": datetime.now().isoformat(timespec="seconds"), "firma": firma(c, pf, reg), "base": base, "fx_rif": fx, "errore": None,
            "valore": ris["valore_portafoglio"], "valore_titoli": ris["valore_titoli"], "investito": investito,
            "perf": t.get("rendimento_dall_inizio"), "xirr": t.get("xirr"), "proventi": sum(p_["importo_base"] for p_ in ris["proventi"]),
            "costi": ris["costi_dettaglio"]["totale"], "allocazione": ris["allocazione"], "settori": ris["settori"], "aree": ris["aree"], "valute": ris["valute"],
            "prezzi": {r["chiave"]: r["prezzo"] for r in ris["posizioni"] if r.get("prezzo") is not None}, "serie": serie, "serie_punti": punti, "avvisi": (ris.get("avvisi", []) + av_scad)[:20], "problemi_prezzi": problemi,
            "pl_nominale": t.get("pl_dall_inizio"), "barriere": ris.get("barriere", []), "sottostanti": ris.get("sottostanti", []), "attese": ris.get("attese", []),
            "cedole_future": ris.get("cedole_future", [])[:80],
            "prodotti": {r["chiave"]: {"rend": r.get("rendimento"), "risultato": r.get("risultato"), "valore": r.get("valore")} for r in ris["attivi"]},
            "chiusi": [{k_: r.get(k_) for k_ in ("chiave", "nome", "isin", "apertura", "chiusura", "investito", "incassi", "redditi", "risultato", "rendimento", "rendimento_annuo")} for r in ris["chiusi"]],
        }
    except Exception as e:          # rete assente, prezzo mancante…
        pf["live"] = {**vecchio, "errore": f"{type(e).__name__}: {e}"[:300], "firma": "", "base": pf["valuta"], "serie": vecchio.get("serie", [])}
    return pf["live"]


# ───────────────────────── aggregazione su tutti i clienti ─────────────────────────
def aggrega(clienti: list[dict]) -> dict:
    """Allocazione totale (in CHF) e performance totale con peso uguale per ogni cliente, più la serie storica."""
    alloc: dict[str, float] = {}
    valore_tot = 0.0
    perf_clienti, serie_clienti = [], []
    senza_cambio = 0
    for c in clienti:
        pesi, perfs, serie_pf = [], [], []
        for pf in c.get("portafogli", []):
            L = pf.get("live") or {}
            if not L.get("valore") and not L.get("serie"):
                continue
            fx = L.get("fx_rif")
            if fx is None:
                senza_cambio += 1
                continue
            val = (L.get("valore") or 0.0) * fx
            valore_tot += val
            for k, x in (L.get("allocazione") or {}).items():
                alloc[k] = alloc.get(k, 0.0) + x * fx
            w = max((L.get("investito") or 0.0) * fx, 1.0)
            if L.get("perf") is not None:
                pesi.append(w); perfs.append(L["perf"])
            serie_pf.append((w, {d: p for d, p in L.get("serie", [])}))
        if perfs:
            perf_clienti.append(sum(p * w for p, w in zip(perfs, pesi)) / sum(pesi))
        if serie_pf:
            serie_clienti.append(serie_pf)
    date_tutte = sorted({d for sp in serie_clienti for _, s in sp for d in s})
    serie = []
    for d in date_tutte:
        valori = []
        for sp in serie_clienti:
            pw = [(w, s[d]) for w, s in sp if d in s]
            if pw:
                valori.append(sum(w * p for w, p in pw) / sum(w for w, _ in pw))
        if valori:
            serie.append((d, sum(valori) / len(valori)))
    return {"allocazione": alloc, "valore": valore_tot, "perf_media": (sum(perf_clienti) / len(perf_clienti)) if perf_clienti else None,
            "n_clienti_con_dati": len(perf_clienti), "serie": serie, "senza_cambio": senza_cambio}


def serie_cliente(c: dict) -> list[tuple[str, float]]:
    return aggrega([c])["serie"]
