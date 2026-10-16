"""Fonti di riserva per l'ULTIMO prezzo, quando Yahoo non trova il titolo né con ticker né con ISIN.
Ogni fonte restituisce (prezzo, valuta, nome fonte) oppure None. L'ordine di prova segue la riuscita passata: chi trova più prezzi passa avanti.
Sono letture di pagine pubbliche: se un sito cambia struttura quella fonte smette di rispondere e si passa alla successiva."""

from __future__ import annotations

import re
import time
from typing import Optional

UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"}


def _num(txt: str) -> Optional[float]:
    t = txt.strip().replace("’", "").replace("'", "").replace(" ", "")
    if "," in t and "." in t:
        t = t.replace(".", "").replace(",", ".") if t.rfind(",") > t.rfind(".") else t.replace(",", "")
    elif "," in t:
        t = t.replace(",", ".")
    try:
        return float(t)
    except ValueError:
        return None


# ── TradingView: cerca il simbolo (per ticker o ISIN) e legge l'ultimo prezzo dallo scanner ──
def tv_parse_ricerca(j) -> list[dict]:
    out = []
    for x in j if isinstance(j, list) else []:
        if x.get("symbol") and x.get("exchange"):
            out.append({"simbolo": re.sub(r"</?em>", "", x["symbol"]), "borsa": x["exchange"], "valuta": x.get("currency_code") or ""})
    return out


def tv_parse_scanner(j) -> Optional[tuple[float, str]]:
    try:
        d = j["data"][0]["d"]
        return float(d[0]), str(d[1] or "")
    except (KeyError, IndexError, TypeError, ValueError):
        return None


class TradingViewFonte:
    nome = "TradingView"

    def ultimo(self, ticker: str, isin: str, valuta: str) -> Optional[tuple[float, str, str]]:
        import requests
        for testo in [x for x in (ticker, isin) if x]:
            try:
                r = requests.get("https://symbol-search.tradingview.com/symbol_search/", params={"text": testo, "type": ""}, headers=UA | {"Origin": "https://www.tradingview.com"}, timeout=12)
                if r.status_code != 200:
                    continue
                cand = tv_parse_ricerca(r.json())
                cand.sort(key=lambda c: 0 if c["valuta"].upper() == (valuta or "").upper() else 1)        # prima le quotazioni nella valuta del prodotto
                for c in cand[:4]:
                    q = requests.post("https://scanner.tradingview.com/global/scan", json={"symbols": {"tickers": [f"{c['borsa']}:{c['simbolo']}"]}, "columns": ["close", "currency"]}, headers=UA, timeout=12)
                    if q.status_code == 200:
                        res = tv_parse_scanner(q.json())
                        if res:
                            return res[0], res[1] or c["valuta"], self.nome
            except Exception:
                continue
        return None


# ── justETF: per ISIN, utile per ETF europei ──
def justetf_parse(html: str) -> Optional[tuple[float, str]]:
    for rx in (r'class="val"[^>]*>\s*<span>([A-Z]{3})</span>\s*<span>([\d.,]+)</span>', r'"latestQuote"\s*:\s*\{[^}]*?"raw"\s*:\s*([\d.]+)[^}]*?"currency"\s*:\s*"([A-Z]{3})"'):
        m = re.search(rx, html, re.S)
        if m:
            a, b = m.group(1), m.group(2)
            if a.isalpha():
                v = _num(b)
                return (v, a) if v else None
            v = _num(a)
            return (v, b) if v else None
    return None


class JustEtfFonte:
    nome = "justETF"

    def ultimo(self, ticker: str, isin: str, valuta: str) -> Optional[tuple[float, str, str]]:
        if not isin:
            return None
        import requests
        try:
            r = requests.get("https://www.justetf.com/it/etf-profile.html", params={"isin": isin}, headers=UA, timeout=15)
            if r.status_code == 200:
                res = justetf_parse(r.text)
                if res:
                    return res[0], res[1], self.nome
        except Exception:
            pass
        return None


# ── Google Finance: pagina pubblica del titolo, quando il simbolo è del tipo TICKER:BORSA ──
def google_parse(html: str) -> Optional[tuple[float, str]]:
    m = re.search(r'data-last-price="([\d.,]+)"', html)
    if not m:
        return None
    v = _num(m.group(1))
    c = re.search(r'data-currency-code="([A-Z]{3})"', html)
    return (v, c.group(1)) if v else None


class GoogleFinanceFonte:
    nome = "Google Finance"
    BORSE = ["NYSEARCA", "NASDAQ", "NYSE", "BIT", "ETR", "LON", "EPA", "AMS", "SWX", "TSE"]

    def ultimo(self, ticker: str, isin: str, valuta: str) -> Optional[tuple[float, str, str]]:
        if not ticker:
            return None
        import requests
        base = ticker.split(".")[0].upper()
        for borsa in self.BORSE:
            try:
                r = requests.get(f"https://www.google.com/finance/quote/{base}:{borsa}", headers=UA | {"Accept-Language": "en"}, timeout=10)
                if r.status_code == 200:
                    res = google_parse(r.text)
                    if res and (not valuta or res[1].upper() == valuta.upper()):
                        return res[0], res[1], self.nome
            except Exception:
                continue
        return None


class CatenaRiserva:
    """Prova le fonti in ordine di riuscita (le statistiche vivono nella cache condivisa, quindi durano finché l'app è accesa)."""

    def __init__(self, fonti=None, statistiche: dict | None = None):
        self.fonti = fonti or [GoogleFinanceFonte(), TradingViewFonte(), JustEtfFonte()]
        self.stat = statistiche if statistiche is not None else _STAT

    def ordinate(self):
        return list(self.fonti)                        # ordine fisso voluto: Google Finance, TradingView, justETF

    def ultimo(self, ticker: str, isin: str, valuta: str):
        for f in self.ordinate():
            try:
                r = f.ultimo(ticker, isin, valuta)
            except Exception:
                r = None
            st = self.stat.setdefault(f.nome, [0, 0])
            if r:
                st[0] += 1
                return r
            st[1] += 1
        return None


_STAT: dict = {}
