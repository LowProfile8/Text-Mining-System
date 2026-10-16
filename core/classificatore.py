"""Classificazione automatica di settori e aree geografiche.

Ordine dei tentativi (il primo che funziona vince; si registra sempre da dove viene il dato):
  1. Obbligazioni: area dal prefisso dell'ISIN dell'emittente (IT, ES, DE, FR, US, CH…), settore «Governativo».
  2. Prodotti strutturati: media dei sottostanti (indici o titoli) → area/settore di ognuno.
  3. ETF / azioni: dati Yahoo (pesi settoriali dei fondi, settore e paese dei titoli) se disponibili,
     altrimenti regole sul nome dell'indice replicato, con pesi geografici INDICATIVI.
Tutto ciò che non si riesce a classificare resta «Non classificato»: si completa una volta sola per strumento
e vale per tutti i clienti. I pesi per indice sono stime di riferimento e vanno riviste periodicamente.
"""

from __future__ import annotations

import re
from typing import Optional

from core.config import AREE_GEO as AREE

_ISIN_SPECIFICO = {"IT": "Italia", "DE": "Germania", "FR": "Francia", "GB": "Regno Unito", "ES": "Spagna", "NL": "Paesi Bassi", "BE": "Belgio", "AT": "Austria",
                   "PT": "Portogallo", "IE": "Irlanda", "FI": "Paesi nordici", "SE": "Paesi nordici", "DK": "Paesi nordici", "NO": "Paesi nordici",
                   "US": "Stati Uniti", "CH": "Svizzera", "JP": "Giappone", "CN": "Cina", "HK": "Cina", "XS": "Europa", "EU": "Europa", "LU": "Europa", "CA": "Nord America"}

# settore da ticker (casi certi) e da parole nel nome (ETF tematici)
_TICKER_SETTORE = {"QUBT": "Calcolo quantistico", "RGTI": "Calcolo quantistico", "QBTS": "Calcolo quantistico", "IONQ": "Calcolo quantistico", "UEC": "Nucleare e uranio",
                   "CCJ": "Nucleare e uranio", "NATO": "Difesa", "WDEF": "Difesa", "DFND": "Difesa", "NVDA": "Semiconduttori", "ASML": "Semiconduttori", "TSM": "Semiconduttori"}
_REGOLE_SETTORE = [
    (r"quantum|quantistic", "Calcolo quantistico"), (r"defen[cs]e|aerospace|difesa|nato", "Difesa"), (r"uranium|nuclear|uranio", "Nucleare e uranio"),
    (r"semiconductor|chips?", "Semiconduttori"), (r"cyber", "Cybersecurity"), (r"robot|automation", "Robotica e automazione"), (r"artificial intelligence|ai", "Intelligenza artificiale"),
    (r"gold|silver|precious|miners", "Oro e metalli preziosi"), (r"clean energy|renewable|solar|wind", "Energie rinnovabili"), (r"water", "Acqua"),
    (r"bank", "Banche"), (r"insur", "Assicurazioni"), (r"biotech", "Biotecnologie"), (r"health", "Healthcare"), (r"real estate|reit", "Immobiliare"),
    (r"bitcoin|crypto|blockchain", "Cripto e blockchain"), (r"software|cloud", "Software e cloud"), (r"infrastructure", "Industriale"), (r"oil|gas|energy", "Energia"),
]


def settore_da_nome(nome: str, ticker: str = "") -> str:
    t = (ticker or "").upper().split(".")[0]
    if t in _TICKER_SETTORE:
        return _TICKER_SETTORE[t]
    n = (nome or "").lower()
    for pat, sett in _REGOLE_SETTORE:
        if re.search(pat, n):
            return sett
    return ""


def paese_da_isin(isin: str) -> Optional[str]:
    return _ISIN_SPECIFICO.get((isin or "")[:2].upper())

_ISIN_PAESE = {
    "IT": "Europa", "ES": "Europa", "DE": "Europa", "FR": "Europa", "NL": "Europa", "BE": "Europa", "AT": "Europa",
    "PT": "Europa", "FI": "Europa", "IE": "Europa", "XS": "Europa", "EU": "Europa", "GB": "Europa", "LU": "Europa",
    "US": "Stati Uniti", "CH": "Svizzera", "JP": "Asia", "CN": "Asia", "HK": "Asia",
}

# (pattern sul nome, pesi per area, etichetta della regola)
_REGOLE_INDICE = [
    (r"s&p ?500|sp500|msci usa|nasdaq|russell|dow jones|\bus\b|u\.s\.", {"Stati Uniti": 1.0}, "indice USA"),
    (r"euro ?stoxx|stoxx europe|\bdax\b|\bcac\b|ibex|ftse mib|msci europe|msci emu|aex\b", {"Europa": 1.0}, "indice europeo"),
    (r"\bsmi\b|swiss|svizzera", {"Svizzera": 1.0}, "indice svizzero"),
    (r"nikkei|topix|msci japan|msci asia|hang seng|msci china|pacific", {"Asia": 1.0}, "indice asiatico"),
    (r"emerging|\bem\b|msci em", {"Mercati emergenti": 1.0}, "indice mercati emergenti"),
    (r"world|acwi|all-world|global|wrld|high div|hi div|\bvhyl\b|\biwde\b|\biwvl\b|value|\bmsci\b", {"Mondo": 1.0}, "indice mondiale"),
]

_TICKER_AREA = {
    "^GSPC": "Stati Uniti", "^SPX": "Stati Uniti", "^NDX": "Stati Uniti", "^DJI": "Stati Uniti", "SPY": "Stati Uniti",
    "^STOXX50E": "Europa", "^GDAXI": "Europa", "^FCHI": "Europa", "^IBEX": "Europa", "FTSEMIB.MI": "Europa", "SX5E": "Europa",
    "^SSMI": "Svizzera", "SMI": "Svizzera", "^N225": "Giappone", "^HSI": "Cina", "^GDAXI": "Germania", "^FCHI": "Francia", "FTSEMIB.MI": "Italia", "^FTSE": "Regno Unito", "^IBEX": "Spagna",
}
_PAESE_YAHOO = {"United States": "Stati Uniti", "Switzerland": "Svizzera", "Japan": "Giappone", "China": "Cina", "Hong Kong": "Cina", "Italy": "Italia", "Germany": "Germania",
                "France": "Francia", "United Kingdom": "Regno Unito", "Spain": "Spagna", "Netherlands": "Paesi Bassi", "Canada": "Nord America",
                "Taiwan": "Asia", "South Korea": "Asia", "India": "Mercati emergenti", "Brazil": "Mercati emergenti"}
_EUROPA_YAHOO = {"Germany", "France", "Italy", "Spain", "Netherlands", "Belgium", "Ireland", "Finland", "Austria", "Portugal",
                 "United Kingdom", "Denmark", "Sweden", "Norway", "Luxembourg"}

_SETTORI_YAHOO = {
    "technology": "Tecnologia", "healthcare": "Healthcare", "financial_services": "Finanziario", "financial services": "Finanziario",
    "industrials": "Industriale", "consumer_cyclical": "Consumi discrezionali", "consumer cyclical": "Consumi discrezionali",
    "consumer_defensive": "Altri settori", "energy": "Altri settori", "utilities": "Altri settori", "basic_materials": "Altri settori",
    "real_estate": "Altri settori", "communication_services": "Altri settori", "realestate": "Altri settori",
}


def _normalizza(pesi: dict) -> dict:
    tot = sum(pesi.values())
    return {k: v / tot for k, v in pesi.items()} if tot > 0 else {}


def area_da_isin(isin: str) -> Optional[str]:
    return _ISIN_PAESE.get((isin or "")[:2].upper())


def aree_da_nome_indice(nome: str) -> tuple[dict, str]:
    n = (nome or "").lower()
    for pattern, pesi, etichetta in _REGOLE_INDICE:
        if re.search(pattern, n):
            return dict(pesi), etichetta
    return {}, ""


def area_da_paese_yahoo(paese: str) -> str:
    if paese in _PAESE_YAHOO:
        return _PAESE_YAHOO[paese]
    if paese in _EUROPA_YAHOO:
        return "Europa"
    return "Altro" if paese else ""


def settori_da_pesi_yahoo(pesi_yahoo: dict) -> dict:
    out: dict[str, float] = {}
    for k, v in (pesi_yahoo or {}).items():
        nome = _SETTORI_YAHOO.get(str(k).lower().replace(" ", "_"), _SETTORI_YAHOO.get(str(k).lower(), "Altri settori"))
        out[nome] = out.get(nome, 0.0) + float(v)
    return _normalizza(out)


def dati_yahoo(ticker: str) -> dict:
    """Best effort: settore/paese di un titolo o pesi settoriali di un fondo. Ritorna {} se non disponibile."""
    try:
        import yfinance as yf
        t = yf.Ticker(ticker)
        out: dict = {}
        try:
            fd = t.funds_data
            sw = fd.sector_weightings
            if sw:
                out["settori_fondo"] = dict(sw)
        except Exception:
            pass
        info = {}
        try:
            info = t.info or {}
        except Exception:
            pass
        if info.get("sector"):
            out["settore"] = info["sector"]
        if info.get("country"):
            out["paese"] = info["country"]
        return out
    except Exception:
        return {}


def classifica(strumento: dict, yahoo: Optional[dict] = None) -> dict:
    """Ritorna {'settori': {...}, 'aree': {...}, 'nota': str}; pesi sommano a 1 oppure dict vuoto."""
    cat = strumento.get("categoria")
    nome = strumento.get("nome", "")
    # 1. obbligazioni
    if cat in ("deposito", "liquidita"):
        v = (strumento.get("valuta") or "").upper()
        return {"settori": {"Liquidità": 1.0}, "aree": {{"CHF": "Svizzera", "EUR": "Europa", "USD": "Stati Uniti", "GBP": "Regno Unito", "JPY": "Giappone"}.get(v, "Altro"): 1.0},
                "nota": "da valuta"}
    if cat == "obbligazione":
        area = paese_da_isin(strumento.get("isin", "")) or area_da_isin(strumento.get("isin", "")) or ""
        if area:
            return {"settori": {"Governativo": 1.0}, "aree": {area: 1.0}, "nota": f"da ISIN ({strumento['isin'][:2]}): emittente governativo presunto, verificare"}
        return {"settori": {}, "aree": {}, "nota": "obbligazione: emittente da indicare"}
    # 2. strutturati: media dei sottostanti
    if cat == "strutturato":
        sott = strumento.get("sottostanti") or []
        if not sott:
            return {"settori": {}, "aree": {}, "nota": "strutturato: sottostanti da indicare"}
        aree: dict[str, float] = {}
        for u in sott:
            a = _TICKER_AREA.get(str(u.get("ticker", "")).upper())
            if not a:
                a2, _ = aree_da_nome_indice(u.get("nome", ""))
                a = max(a2, key=a2.get) if a2 else ""
            if a:
                aree[a] = aree.get(a, 0.0) + 1.0
        settori = {"Diversificato": 1.0} if all(str(u.get("ticker", "")).startswith("^") or u.get("ticker") in _TICKER_AREA for u in sott) else {}
        return {"settori": settori, "aree": _normalizza(aree), "nota": "media dei sottostanti"}
    # 3. ETF / azioni
    if cat in ("etf_azioni", "opzione"):
        settori, aree, note = {}, {}, []
        y = yahoo or {}
        if y.get("settori_fondo"):
            settori = settori_da_pesi_yahoo(y["settori_fondo"]); note.append("settori: Yahoo (fondo)")
        elif y.get("settore"):
            settori = {_SETTORI_YAHOO.get(str(y["settore"]).lower().replace(" ", "_"), "Altri settori"): 1.0}; note.append("settore: Yahoo (titolo)")
        if y.get("paese"):
            aree = {area_da_paese_yahoo(y["paese"]): 1.0}; note.append("area: Yahoo (paese)")
        if not aree:
            aree, etichetta = aree_da_nome_indice(nome)
            if aree:
                note.append(f"area: regola «{etichetta}»")
        if not settori:
            sn = settore_da_nome(nome, (strumento.get("ticker") or strumento.get("ticker_mercato") or (strumento.get("simboli") or [""])[0]))
            if sn:
                settori = {sn: 1.0}; note.append(f"settore: «{sn}» da nome/ticker")
        if not settori and strumento.get("categoria") == "etf_azioni" and aree:
            settori = {"Diversificato": 1.0}; note.append("settori: ETF su indice, non scomposto")
        return {"settori": settori, "aree": aree, "nota": "; ".join(note) or "non classificabile automaticamente"}
    return {"settori": {}, "aree": {}, "nota": ""}


def applica(strumento: dict, yahoo: Optional[dict] = None, sovrascrivi: bool = False) -> dict:
    """Compila settori/aree dello strumento se vuoti (o se richiesto), senza toccare ciò che l'utente ha inserito a mano."""
    if strumento.get("classificazione_manuale") and not sovrascrivi:
        return strumento
    r = classifica(strumento, yahoo)
    if r["settori"] or r["aree"]:
        strumento["settori"], strumento["aree"] = r["settori"], r["aree"]
    strumento["classificazione_auto"] = r["nota"]
    return strumento
