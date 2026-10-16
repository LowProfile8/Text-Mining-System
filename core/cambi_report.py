"""Tassi di cambio da confermare prima del report: valuta ≠ valuta del report, alla data di fine periodo.
Suggerimento: prima ICTax (Amministrazione federale delle contribuzioni, se raggiungibile e coerente), altrimenti BCE/Yahoo. L'utente conferma o corregge."""

from __future__ import annotations

from datetime import date

import core.calcolo as calcolo

URL_ICTAX = "https://www.ictax.admin.ch/extern/it.html#/ratelist/{anno}"
API_ICTAX = "https://www.ictax.admin.ch/extern/api/coreGadget/exchangeRates.json"
TOLLERANZA_ICTAX = 0.03          # un valore ICTax che si discosta oltre il 3% dal mercato viene scartato (struttura della risposta non verificata)


def valute_da_convertire(tx: list[dict], reg, base: str, a: str) -> list[str]:
    """Valute presenti nel portafoglio (movimenti e strumenti ancora in essere) diverse dalla valuta del report."""
    v = {t["valuta"] for t in tx if t["data"] <= a and t.get("valuta")}
    v |= {reg.strumenti[t["strumento"]].get("valuta") for t in tx if t.get("strumento") in reg.strumenti and t["data"] <= a}
    return sorted(x for x in v if x and x != base)


def _cerca_numeri(obj, out: dict):
    """Cerca coppie (codice valuta di 3 lettere maiuscole, tasso) in una risposta JSON di struttura non nota."""
    if isinstance(obj, dict):
        cod = next((x for x in obj.values() if isinstance(x, str) and len(x) == 3 and x.isalpha() and x.isupper()), None)
        num = next((float(x) for k, x in obj.items() if isinstance(x, (int, float)) and not isinstance(x, bool) and ("rate" in k.lower() or "kurs" in k.lower())), None)
        if cod and num:
            out[cod] = num
        for x in obj.values():
            _cerca_numeri(x, out)
    elif isinstance(obj, list):
        for x in obj:
            _cerca_numeri(x, out)


def da_ictax(data: str) -> dict[str, float]:
    """Tentativo di lettura dal servizio ICTax (struttura non documentata: il risultato va sempre confermato dall'utente)."""
    try:
        import requests
        r = requests.post(API_ICTAX, json={"date": data}, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
        if r.status_code != 200:
            return {}
        out: dict = {}
        _cerca_numeri(r.json(), out)
        return out
    except Exception:
        return {}


def suggerisci(valute: list[str], base: str, data: str, mercato=None) -> dict[str, dict]:
    """{valuta: {tasso (unità di `base` per 1 unità di valuta), fonte}}."""
    m = mercato or calcolo.mercato_reale()
    ict = da_ictax(data) if valute else {}
    out = {}
    for v in valute:
        rif = m.fx(v, base, data)
        t_ict = ict.get(v)
        if t_ict and rif and abs(t_ict - rif) / rif <= TOLLERANZA_ICTAX:
            out[v] = {"tasso": t_ict, "fonte": "ICTax"}
        elif rif:
            out[v] = {"tasso": rif, "fonte": "BCE / mercato (ICTax non disponibile)"}
        else:
            out[v] = {"tasso": None, "fonte": "da inserire a mano"}
    return out


def chiave(v: str, base: str, data: str) -> str:
    return f"{v}{base}@{data}"
