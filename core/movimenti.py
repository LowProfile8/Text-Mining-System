"""Movimenti di banca/piattaforma: inserimento manuale senza doppioni, stato di ogni riga e confronto dei saldi di fine mese con gli estratti conto."""

from __future__ import annotations

TOLLERANZA = 0.05          # differenza ammessa fra saldo calcolato e saldo dell'estratto (arrotondamenti)
TIPI_CON_PRODOTTO = ("acquisto", "vendita", "rimborso", "dividendo", "cedola", "interesse", "premio_opzione")


def chiave(t: dict) -> tuple:
    return (t["data"], t["tipo"], round(float(t.get("importo_cassa") or 0.0), 2), t.get("valuta"), t.get("banca") or "", t.get("conto") or "", t.get("strumento") or "")


def e_duplicato(transazioni: list[dict], nuovo: dict) -> bool:
    k = chiave(nuovo)
    return any(chiave(t) == k for t in transazioni)


def stato_riga(t: dict) -> str:
    """«previsto» = inserito in fase di strategia e non ancora confermato da un estratto; «da completare» = mancano dati; altrimenti «registrato»."""
    if t["tipo"] in TIPI_CON_PRODOTTO and not t.get("strumento"):
        return "da completare"
    if t["tipo"] == "acquisto" and (not t.get("quantita") or not t.get("prezzo")):
        return "da completare"
    if not t.get("importo_cassa"):
        return "da completare"
    if t.get("fonte") == "strategia":
        return "previsto"
    return "registrato"


def riconcilia(transazioni: list[dict], saldi: list[dict]) -> list[dict]:
    """Per ogni conto: saldo dell'estratto a fine periodo contro saldo precedente + movimenti del periodo. Restituisce una riga per saldo."""
    out = []
    gruppi: dict[tuple, list[dict]] = {}
    for s in saldi:
        gruppi.setdefault((s["banca"], s["conto"], s["valuta"]), []).append(s)
    for (banca, conto, val), lista in gruppi.items():
        lista.sort(key=lambda s: s["data"])
        mov = [t for t in transazioni if (t.get("banca") or "") == banca and (t.get("conto") or "") == conto and t.get("valuta") == val]
        prec = None
        for s in lista:
            riga = {"banca": banca, "conto": conto, "valuta": val, "data": s["data"], "saldo_estratto": s["saldo"], "saldo_calcolato": None, "differenza": None, "esito": "punto di partenza"}
            if prec is not None:
                calc = prec["saldo"] + sum(float(t.get("importo_cassa") or 0.0) for t in mov if prec["data"] < t["data"] <= s["data"])
                riga.update(saldo_calcolato=calc, differenza=s["saldo"] - calc, esito="ok" if abs(s["saldo"] - calc) <= TOLLERANZA else "errore")
            out.append(riga)
            prec = s
    out.sort(key=lambda r: (r["data"], r["banca"], r["conto"]))
    return out
