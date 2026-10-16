"""Notizie e cambi per la home: RSS gratuiti (Yahoo Finance per titolo, Google News per il quadro macro) e tabella dei cambi BCE."""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from urllib.parse import quote

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"}
VALUTE_TABELLA = ["EUR", "USD", "GBP", "JPY", "CAD", "AUD", "SEK", "NOK", "DKK", "CNY"]


def parse_rss(xml: str, etichetta: str = "", limite: int = 8) -> list[dict]:
    out = []
    try:
        root = ET.fromstring(xml)
    except ET.ParseError:
        return out
    for it in root.iter("item"):
        titolo = (it.findtext("title") or "").strip()
        link = (it.findtext("link") or "").strip()
        if not titolo or not link:
            continue
        try:
            d = parsedate_to_datetime(it.findtext("pubDate") or "")
        except Exception:
            d = None
        fonte = (it.findtext("source") or "").strip()
        out.append({"titolo": re.sub(r"\s+-\s+[^-]+$", "", titolo) if fonte else titolo, "link": link, "data": d.isoformat() if d else "", "fonte": fonte, "etichetta": etichetta})
        if len(out) >= limite:
            break
    return out


def _get(url: str) -> str:
    import requests
    r = requests.get(url, headers=UA, timeout=12)
    return r.text if r.status_code == 200 else ""


def notizie_titolo(simbolo: str, etichetta: str = "", limite: int = 4) -> list[dict]:
    try:
        return parse_rss(_get(f"https://feeds.finance.yahoo.com/rss/2.0/headline?s={quote(simbolo)}&region=US&lang=en-US"), etichetta or simbolo, limite)
    except Exception:
        return []


def notizie_macro(limite: int = 12) -> list[dict]:
    try:
        q = quote("economia mercati banche centrali inflazione tassi")
        return parse_rss(_get(f"https://news.google.com/rss/search?q={q}&hl=it&gl=IT&ceid=IT:it"), "Macro", limite)
    except Exception:
        return []


def notizie_portafogli(simboli: list[tuple[str, str]], per_titolo: int = 3, totale: int = 18) -> list[dict]:
    """simboli: [(etichetta, simbolo Yahoo)]. Restituisce le più recenti, mescolate."""
    tutte = []
    for et, sim in simboli[:15]:
        tutte += notizie_titolo(sim, et, per_titolo)
    tutte.sort(key=lambda x: x["data"], reverse=True)
    visti, out = set(), []
    for n in tutte:
        if n["link"] not in visti:
            visti.add(n["link"]); out.append(n)
    return out[:totale]


def tabella_cambi(base: str = "CHF", valute: list[str] | None = None) -> list[dict]:
    """Per ogni valuta: quanti `base` per 1 unità, e variazione sul giorno precedente. Fonte: BCE via Frankfurter."""
    try:
        import requests
        v = [x for x in (valute or VALUTE_TABELLA) if x != base]
        r = requests.get("https://api.frankfurter.app/latest", params={"from": base, "to": ",".join(v)}, timeout=12)
        if r.status_code != 200:
            return []
        j = r.json()
        prima = requests.get(f"https://api.frankfurter.app/{_giorno_prima(j['date'])}", params={"from": base, "to": ",".join(v)}, timeout=12)
        j0 = prima.json() if prima.status_code == 200 else {"rates": {}}
        righe = []
        for x in v:
            if x in j["rates"] and j["rates"][x]:
                per_unita = 1 / j["rates"][x]
                var = None
                if j0["rates"].get(x):
                    var = per_unita / (1 / j0["rates"][x]) - 1
                righe.append({"Valuta": f"1 {x}", f"Vale in {base}": per_unita, f"1 {base} in valuta": j["rates"][x], "Variazione": var, "Data": j["date"]})
        return righe
    except Exception:
        return []


def _giorno_prima(iso: str) -> str:
    from datetime import date, timedelta
    return (date.fromisoformat(iso) - timedelta(days=1)).isoformat()
