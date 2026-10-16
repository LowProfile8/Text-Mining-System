"""Cedole non ancora registrate: le date si ricavano da emissione e frequenza, l'importo dal nominale in portafoglio. Sono solo suggerimenti da confermare."""

from __future__ import annotations

from datetime import date, timedelta

from core.performance import D, aggiungi_mesi

FINESTRA_GIORNI = 20          # un incasso entro ±20 giorni dalla data teorica conta come già registrato


def _qty_a(tx: list[dict], chiave: str, data: str) -> float:
    q = 0.0
    for t in tx:
        if t.get("strumento") == chiave and t["data"] <= data and t["tipo"] in ("acquisto", "vendita", "rimborso"):
            q += (t.get("quantita") or 0.0) * (1 if t["tipo"] == "acquisto" else -1)
    return q


def suggerisci(tx: list[dict], strumenti: dict, a: str) -> list[dict]:
    """Cedole teoriche fino alla data `a` (compresa) senza un incasso registrato vicino. Solo prodotti con cedola periodica su nominale
    (obbligazioni, strutturati, depositi): per azioni ed ETF i dividendi non sono prevedibili."""
    out = []
    per_k: dict[str, list] = {}
    for t in tx:
        if t.get("strumento"):
            per_k.setdefault(t["strumento"], []).append(t)
    for k, mov in per_k.items():
        s = strumenti.get(k)
        if not s or s.get("categoria") not in ("obbligazione", "strutturato", "deposito"):
            continue
        if not (s.get("cedola_annua_pct") and s.get("frequenza_cedola") and s.get("data_emissione")):
            continue
        acquisti = [m["data"] for m in mov if m["tipo"] == "acquisto"]
        if not acquisti:
            continue
        primo = min(acquisti)
        f = int(s["frequenza_cedola"])
        passo = 12 // f
        incassi = [D(m["data"]) for m in mov if m["tipo"] in ("cedola", "interesse")]
        fine = min(a, s["scadenza"]) if s.get("scadenza") else a
        i = 1
        while True:
            teorica = aggiungi_mesi(D(s["data_emissione"]), passo * i)
            i += 1
            if teorica.isoformat() > fine:
                break
            if teorica.isoformat() <= primo:
                continue                                  # prima dell'acquisto la cedola non spetta
            q = _qty_a(mov, k, teorica.isoformat())
            if q <= 1e-9:
                continue                                  # prodotto già venduto o rimborsato
            if any(abs((d - teorica).days) <= FINESTRA_GIORNI for d in incassi):
                continue
            out.append({"chiave": k, "nome": s.get("nome") or k, "data": teorica.isoformat(), "valuta": s.get("valuta"),
                        "importo": round(q * s["cedola_annua_pct"] / 100 / f, 2),
                        "tipo": "interesse" if s.get("categoria") in ("deposito",) else "cedola",
                        "condizionata": s.get("sottocategoria") not in ("Barrier Reverse Convertible", "Capital Protection Note", "Deposito a termine") and s.get("categoria") == "strutturato"})
    out.sort(key=lambda x: (x["data"], x["nome"]))
    return out
