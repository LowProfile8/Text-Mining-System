"""Un solo ticker + la borsa di riferimento (menu a tendina): da qui si ricavano i simboli per le fonti di prezzo.
Se il ticker non si trova si usa l'ISIN (vedi Mercato._simbolo)."""

from __future__ import annotations

from core.config import BORSA_DEFAULT, BORSE

BORSA_LIBERA = "Indice / criptovaluta / altro (ticker completo)"


def _completo(t: str) -> bool:
    return t.startswith("^") or "." in t or "=" in t or "-" in t


def simbolo_yahoo(ticker: str, borsa: str) -> str:
    t = (ticker or "").strip().upper()
    if not t or borsa == BORSA_LIBERA or _completo(t):
        return t
    return t + BORSE.get(borsa, BORSE[BORSA_DEFAULT])[0]


def simbolo_stooq(ticker: str, borsa: str) -> str:
    """Seconda fonte (Stooq) solo dove copre la borsa; altrimenti vuoto."""
    t = (ticker or "").strip().lower()
    if not t or borsa == BORSA_LIBERA or _completo(t):
        return ""
    suff = BORSE.get(borsa, (None, None))[1]
    return t + suff if suff else ""


def applica(s: dict) -> dict:
    """Imposta ticker_mercato / ticker_controllo dello strumento a partire da `ticker` e `borsa`."""
    t = (s.get("ticker") or "").strip()
    if t:
        b = s.get("borsa") or BORSA_DEFAULT
        s["ticker_mercato"] = simbolo_yahoo(t, b)
        s["ticker_controllo"] = simbolo_stooq(t, b)
    return s


def tradingview(ticker: str, borsa: str) -> str:
    """Simbolo per i widget TradingView (BORSA:TICKER)."""
    pre = {"USA · NYSE / Nasdaq / AMEX": "", "Borsa Italiana (Milano)": "MIL:", "Xetra (Germania)": "XETR:", "Francoforte": "FWB:", "Euronext Parigi": "EURONEXT:",
           "Euronext Amsterdam": "EURONEXT:", "Euronext Bruxelles": "EURONEXT:", "Euronext Lisbona": "EURONEXT:", "Londra (LSE)": "LSE:", "SIX Swiss Exchange": "SIX:",
           "Madrid": "BME:", "Vienna": "VIE:", "Stoccolma": "OMXSTO:", "Copenaghen": "OMXCOP:", "Helsinki": "OMXHEX:", "Oslo": "OSL:", "Toronto": "TSX:", "Tokyo": "TSE:",
           "Hong Kong": "HKEX:", "Sydney (ASX)": "ASX:"}.get(borsa, "")
    t = (ticker or "").upper().split(".")[0]
    return f"{pre}{t}" if t else ""
