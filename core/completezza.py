"""Cosa manca a un prodotto per calcolare un report affidabile. «Bloccante» = senza questo il dato sarebbe sbagliato o non calcolabile."""

from __future__ import annotations


def problemi_strumento(s: dict) -> list[tuple[str, str]]:
    """Elenco di (gravità, testo): gravità = 'bloccante' | 'consigliato'."""
    p: list[tuple[str, str]] = []
    cat, val = s.get("categoria"), s.get("valutazione")
    if not s.get("valuta"):
        p.append(("bloccante", "valuta mancante"))
    if val == "mercato":
        if not s.get("ticker_mercato"):
            p.append(("bloccante", "ticker per il prezzo di mercato mancante"))
        elif not s.get("ticker_controllo") and not s.get("ticker"):
            p.append(("consigliato", "ticker e borsa non indicati (solo ticker completo): il prezzo non sarà verificato su una seconda fonte"))
    if val == "manuale" and not s.get("nav_manuale"):
        p.append(("bloccante", "nessun NAV inserito"))
    if val in ("scadenza", "nominale") and cat != "liquidita":
        if not s.get("scadenza"):
            p.append(("bloccante", "data di scadenza mancante"))
        if s.get("cedola_annua_pct") and not s.get("frequenza_cedola"):
            p.append(("bloccante", "frequenza della cedola mancante"))
        if s.get("cedola_annua_pct") and not s.get("data_emissione"):
            p.append(("consigliato", "data di emissione/ultima cedola mancante: le cedole future non si calcolano"))
        if s.get("barriera_pct"):
            sott = s.get("sottostanti") or []
            if not sott:
                p.append(("bloccante", "sottostanti mancanti (servono per la distanza dalla barriera)"))
            else:
                for u in sott:
                    if not u.get("ticker"):
                        p.append(("bloccante", f"ticker mancante per il sottostante «{u.get('nome', '?')}»"))
                    if not u.get("livello_iniziale"):
                        p.append(("bloccante", f"livello iniziale mancante per «{u.get('nome', u.get('ticker', '?'))}»"))
        elif cat == "strutturato" and not s.get("protezione_pct"):
            p.append(("consigliato", "né barriera né protezione del capitale indicate"))
        if s.get("barriera_pct") and not s.get("osservazione"):
            p.append(("consigliato", "osservazione della barriera (europea o americana) non indicata"))
        if cat == "strutturato" and (s.get("protezione_pct") or s.get("rebate_pct")):
            sott = s.get("sottostanti") or []
            if not sott:
                p.append(("consigliato", "sottostanti mancanti: servono per vedere la distanza dai livelli nella piattaforma"))
            elif any(not u.get("ticker") or not u.get("livello_iniziale") for u in sott):
                p.append(("consigliato", "ticker o livello iniziale mancante per un sottostante"))
    if not (s.get("settori") and s.get("aree")):
        p.append(("consigliato", "settore/area geografica non classificati"))
    return p


def prodotti_del_cliente(cliente: dict, reg) -> dict[str, dict]:
    """Strumenti che compaiono nelle transazioni del cliente (con acquisto o proventi)."""
    out = {}
    for t in cliente.get("transazioni", []):
        k = t.get("strumento")
        if k and k in reg.strumenti:
            out[k] = reg.strumenti[k]
    return out


def riepilogo_cliente(cliente: dict, reg) -> dict:
    """{chiave: {'bloccanti': [...], 'consigliati': [...]}} solo per i prodotti con qualcosa da sistemare."""
    out = {}
    for k, s in prodotti_del_cliente(cliente, reg).items():
        pr = problemi_strumento(s)
        bl = [t for g, t in pr if g == "bloccante"]
        cs = [t for g, t in pr if g == "consigliato"]
        if bl or cs:
            out[k] = {"nome": s.get("nome") or k, "bloccanti": bl, "consigliati": cs}
    return out
