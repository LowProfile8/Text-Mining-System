"""Calcolo della performance di un portafoglio (usato dall'andamento in tempo reale e dal report)."""

from __future__ import annotations

from core import dati
from core.mercato import mercato_reale
from core.performance import Contesto, calcola


def calcola_portafoglio(c: dict, pid: str, reg, da, a, mercato=None) -> dict:
    manuali = dati.carica_manuali()
    m = mercato or mercato_reale(manuali=manuali)
    v = dati.vista_portafoglio(c, pid)
    pf = dati.portafoglio(c, pid) or {}
    base = pf.get("valuta") or v["valuta_base"]                 # ogni strategia ha la sua valuta
    ctx = Contesto(base=base, fx=m.fx, prezzo=m.prezzo, spot=m.spot)
    tx = dati.transazioni_ordinate(v)
    from core.scadenze import con_scadenze
    tx, av_scad = con_scadenze(tx, reg.strumenti, str(a))
    ris = calcola(tx, reg.strumenti, str(da), str(a), ctx, saldi_liquidita=dati.saldi_a_data(v, str(a)))
    ris["avvisi"] = list(ris.get("avvisi", [])) + av_scad
    incoerenti = [e for e in m.controllo_acquisti(tx, reg.strumenti) if e["stato"] == "incoerente"]
    return {"ris": ris, "problemi": m.problemi(), "incoerenti": incoerenti, "snapshot": m.snapshot_attuale(), "da": str(da), "a": str(a), "cliente": c["id"], "portafoglio": pid}
