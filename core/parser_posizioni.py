"""Documenti con le POSIZIONI a una data (non movimenti): servono a partire da valori e quantità iniziali.

  • «Performance del portafoglio» PostFinance / Swissquote  → quantità, ISIN, prezzo d'acquisto, liquidità
  • «Estratto patrimoniale» UBS                              → in più scadenza, cedola, barriera, sottostanti, emittente

Ogni lettura restituisce un dict con `posizioni`, `liquidita`, `controlli` (quadratura sul totale della banca) e, quando c'è,
`banca_dichiara` (performance calcolata dalla banca: utile per confrontarla con quella dell'app)."""

from __future__ import annotations

import re
from datetime import datetime

import pdfplumber

_APOS = "’'`"
_VAL = r"(?:CHF|EUR|USD|GBP|JPY|CAD|AUD)"
_MESI = {"jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6, "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12}


def _n(s: str) -> float:
    s = s.strip()
    neg = s.startswith("-")
    for c in _APOS + " -":
        s = s.replace(c, "")
    return -float(s) if neg else float(s)


def _iso(d: str, fmt="%d.%m.%Y") -> str:
    return datetime.strptime(d, fmt).date().isoformat()


def _righe(src, **kw) -> list[str]:
    out: list[str] = []
    with pdfplumber.open(src) as pdf:
        for p in pdf.pages:
            out.extend((p.extract_text(**kw) or "").splitlines())
    return [r.strip() for r in out if r.strip()]


# ───────────────────────── PostFinance / Swissquote: «Performance del portafoglio» ─────────────────────────
def riconosci_performance(righe: list[str]) -> bool:
    t = "\n".join(righe[:60])
    return "Performance del portafoglio in data" in t and ("PostFinance" in t or "Swissquote" in t)


_POS = re.compile(
    r"^(\d{1,3}(?:[’'`]\d{3})*)\s*(.+?)\s*([A-Z]{2}[A-Z0-9]{9}\d)\s+([\d.]+)%\s+([\d.]+)%\s+(\d\d\.\d\d\.\d{4})\s+(.*)$")
_CASH = re.compile(rf"^({_VAL})\s*(\d{{6,}})\s+(.+?)\s+(-?[\d’'`]+\.\d\d)\s+([\d.]+)\s+(-?[\d’'`]+\.\d\d)")
_SEZ = re.compile(rf"^(.*?)\s*in\s*({_VAL})$")


def parse_performance(src) -> dict:
    righe = _righe(src)
    if not riconosci_performance(righe):
        raise ValueError("Non sembra un «Performance del portafoglio» PostFinance/Swissquote.")
    testo = "\n".join(righe)
    banca = "Swissquote" if "Swissquote Bank" in testo and "PostFinance SA" not in testo else "PostFinance"
    m = re.search(r"in data (\d\d\.\d\d\.\d{4})", testo)
    data = _iso(m.group(1))
    m = re.search(r"Conto n(?:r|\.)\s*(\d+)", testo)
    conto = m.group(1) if m else ""
    m = re.search(r"valutato\s*in\s*(\w{3})", testo, re.I)
    base = m.group(1).upper() if m else "CHF"
    m = re.search(r"Signor[ae]?\s+([^\n]+?)(?:\n|$)", testo)
    titolare = m.group(1).strip() if m else ""
    m = re.search(r"Valutazione al (\d\d\.\d\d\.\d{4})\s+[\d’'`.]+\s*\n.*?Valutazione al (\d\d\.\d\d\.\d{4})", testo)
    out = {"tipo_documento": "posizioni", "banca": banca, "conto": conto, "data": data, "valuta_base": base, "titolare": titolare,
           "posizioni": [], "liquidita": [], "controlli": [], "avvisi": []}
    # dati dichiarati dalla banca (per confronto)
    d = {}
    m = re.search(r"Valutazione al \d\d\.\d\d\.\d{4}\s+([\d’'`.]+)\s", testo)
    for k, pat in (("totale", r"Valutazione al \d\d\.\d\d\.\d{4}\s+([\d’'`.]+)"), ("flussi_netti", r"Afflusso/deflusso di capitale netto\s+(-?[\d’'`.]+)"),
                   ("performance_assoluta", r"Performance Assoluta\s+(-?[\d’'`.]+)"), ("performance_pct", r"Performance (?:TWR|MWR)\s+(-?[\d.]+)\s*%")):
        mm = re.search(pat, testo)
        if mm:
            d[k] = _n(mm.group(1))
    mm = re.findall(r"Valutazione al (\d\d\.\d\d\.\d{4})", testo)
    if len(mm) >= 2:
        d["inizio"] = _iso(mm[1])
    mm = re.search(r"Performance (TWR|MWR)", testo)
    d["metodo"] = mm.group(1) if mm else ""
    out["banca_dichiara"] = d

    sez_val, sez_cat, inizio_tab = base, "", False
    last = None
    in_alloc = False
    for r in righe:
        if r.startswith("2. Allocazione"):
            in_alloc = True
        if not in_alloc or r.startswith(("PostFinance SA", "Swissquote Bank", "Contact", "Customer", "Performance del portafoglio", "Conto n")):
            continue
        if r.startswith(("Totale", "TOTALE")):
            last = None
            continue
        ms = _SEZ.match(r)
        if ms and not r.startswith(("Valuta", "Quantità")):
            sez_cat, sez_val = ms.group(1).strip(), ms.group(2)
            last = None
            continue
        mc = _CASH.match(r)
        if mc:
            out["liquidita"].append({"valuta": mc.group(1), "conto": mc.group(2), "descrizione": mc.group(3).strip(), "saldo": _n(mc.group(4)),
                                     "cambio": float(mc.group(5)), "valore_base": _n(mc.group(6))})
            last = None
            continue
        mp = _POS.match(r)
        if mp:
            resto = re.findall(r"-?[\d’'`]+\.\d\d", mp.group(7))
            val = _n(resto[0])
            val_base = _n(resto[1]) if sez_val != base and len(resto) > 1 else val
            last = {"isin": mp.group(3), "nome": mp.group(2).strip(), "valuta": sez_val, "quantita": _n(mp.group(1)),
                    "prezzo_acquisto_pct": float(mp.group(4)), "prezzo_mercato_pct": float(mp.group(5)), "data_prezzo": _iso(mp.group(6)),
                    "valore": val, "valore_base": val_base, "sezione": sez_cat}
            out["posizioni"].append(last)
            continue
        if last is not None and len(r) < 40 and not re.search(r"\d\d\.\d\d\.\d{4}", r) and not r.startswith(("Quantità", "Valuta")):
            last["nome"] = (last["nome"] + " " + r).strip()
    tot_pos = sum(p["valore_base"] for p in out["posizioni"]) + sum(c["valore_base"] for c in out["liquidita"])
    mt = re.search(r"(?:TOTALE PATRIMONIO IN|Totale attivo in)\s+\w{3}\s+([\d’'`.]+)", testo, re.I)
    if mt:
        tot_b = _n(mt.group(1))
        ok = abs(tot_pos - tot_b) < 0.06 * max(1, len(out["posizioni"]))
        out["controlli"].append({"ok": ok, "testo": f"Somma posizioni + liquidità {tot_pos:,.2f} = totale della banca {tot_b:,.2f} {base}".replace(",", "’") if ok
                                 else f"La somma delle posizioni ({tot_pos:,.2f}) non coincide con il totale della banca ({tot_b:,.2f}) {base}".replace(",", "’")})
        out["totale_banca"] = tot_b
    else:
        out["avvisi"].append("Totale del patrimonio non trovato: quadratura non eseguita.")
    if not out["posizioni"] and not out["liquidita"]:
        out["avvisi"].append("Nessuna posizione letta.")
    out["quadra"] = all(c["ok"] for c in out["controlli"]) and bool(out["controlli"])
    return out


# ───────────────────────── UBS: «Estratto patrimoniale» ─────────────────────────
def riconosci_ubs_patrimoniale(righe: list[str]) -> bool:
    t = "\n".join(righe[:80])
    return "UBS" in t and "Estratto patrimoniale" in t


_UPOS = re.compile(rf"^({_VAL})\s+(\d{{1,3}}(?: \d{{3}})*)\s+(.+?)\s+(?:(Nessun rating|AAA|AA[+-]?|A[+-]?|BBB[+-]?|BB[+-]?|B[+-]?)\s+)?(\d+(?:\.\d+)?)%\s+(\d+(?:\.\d+)?)%\s*[A-Z]?\s+(-?\d+\.\d+)%\s+(-?\d{{1,3}}(?: \d{{3}})*)\s+(-?\d+\.\d+)$")
_TICKER = {"SX5E": "^STOXX50E", "SMI": "^SSMI", "SPX": "^GSPC", "NDX": "^NDX", "DAX": "^GDAXI", "UKX": "^FTSE", "NKY": "^N225", "RACE": "RACE.MI", "P911": "P911.DE", "MBG": "MBG.DE"}
_FREQ = {"monthly": 12, "mensil": 12, "quarterly": 4, "trimestral": 4, "semi-annual": 2, "semiannual": 2, "semestral": 2, "annual": 1, "annuale": 1}


def _freq(testo: str):
    t = testo.lower()
    for k, v in _FREQ.items():
        if k in t:
            return v
    return None


def _data_en(s: str):
    m = re.match(r"(\d{1,2}) (\w{3})\w* (\d{4})", s.strip())
    if not m:
        return ""
    return datetime(int(m.group(3)), _MESI[m.group(2).lower()[:3]], int(m.group(1))).date().isoformat()


def parse_ubs_patrimoniale(src) -> dict:
    righe = _righe(src, x_tolerance=1)
    if not riconosci_ubs_patrimoniale(righe):
        raise ValueError("Non sembra un estratto patrimoniale UBS.")
    testo = "\n".join(righe)
    m = re.search(r"Al (\d{1,2}) (\w+) (\d{4})", testo)
    mesi_it = {"gennaio": 1, "febbraio": 2, "marzo": 3, "aprile": 4, "maggio": 5, "giugno": 6, "luglio": 7, "agosto": 8, "settembre": 9, "ottobre": 10, "novembre": 11, "dicembre": 12}
    data = datetime(int(m.group(3)), mesi_it[m.group(2).lower()], int(m.group(1))).date().isoformat() if m else ""
    m = re.search(r"Portafoglio (\d{3}-\d+-\d+), valutazione in .*?\((\w{3})\)", testo)
    conto, base = (m.group(1), m.group(2)) if m else ("", "CHF")
    m = re.search(r"Portafoglio \S+, valutazione in [^\n]*\n([^\n,]+),", testo)
    titolare = m.group(1).strip() if m else ""
    out = {"tipo_documento": "posizioni", "banca": "UBS", "conto": conto, "data": data, "valuta_base": base, "titolare": titolare,
           "posizioni": [], "liquidita": [], "controlli": [], "avvisi": []}
    cambi = {}
    for mm in re.finditer(r"(EUR|USD|GBP)\s+1=\s+CHF\s+([\d.]+)", testo):
        cambi[mm.group(1)] = float(mm.group(2))
    out["cambi"] = cambi

    # liquidità: conti
    for mm in re.finditer(rf"^({_VAL})\s+(-?[\d.]+)\s+Conto corrente privato UBS\s+{_VAL}\s+(-?\d{{1,3}}(?: \d{{3}})*\.\d\d)\s+(?:([\d.]+)\s+)?(-?\d[\d ]*)\s+-?[\d.]+$\n([A-Z]{{2}}\d\d[\d ]+\w)", testo, re.M):
        out["liquidita"].append({"valuta": mm.group(1), "conto": mm.group(6).replace(" ", ""), "descrizione": "Conto corrente UBS",
                                 "saldo": _n(mm.group(2)), "valore_base": float(mm.group(5).replace(" ", ""))})
    # deposito a termine
    md = re.search(rf"^({_VAL})\s+(\d{{1,3}}(?: \d{{3}})*)\s+Deposito a termine UBS.*?\s(\d{{1,3}}(?: \d{{3}})*)\s+[\d.]+$\n.*?\nTasso d'interesse : ([\d.]+)%.*?\n(\d\d\.\d\d\.\d{{4}}) - (\d\d\.\d\d\.\d{{4}})", testo, re.M)
    if md:
        out["posizioni"].append({"isin": "", "nome": f"Deposito a termine UBS {md.group(1)} {md.group(4)}%", "valuta": md.group(1), "quantita": float(md.group(2).replace(" ", "")),
                                 "prezzo_acquisto_pct": 100.0, "prezzo_mercato_pct": 100.0, "valore_base": float(md.group(3).replace(" ", "")), "valore": float(md.group(2).replace(" ", "")),
                                 "categoria_hint": "deposito", "cedola_annua_pct": float(md.group(4)), "frequenza_cedola": 1, "data_emissione": _iso(md.group(5)), "scadenza": _iso(md.group(6)),
                                 "data_acquisto": _iso(md.group(5)), "emittente": "UBS", "sottostanti": []})

    # prodotti strutturati e simili
    blocchi: list[list[str]] = []
    for r in righe:
        if _UPOS.match(r):
            blocchi.append([r])
        elif blocchi and not r.startswith(("AIRQ", "Posizioni dettagliate", "Subtotale", "Totale", "Pagina", "Per il vostro", "Per categoria", "Quantità/Importo", "Settore", "Duration", "Rendimento Ultimo", "UBS Switzerland", "Estratto patrimoniale", "Simone", "Sommario", "Valutazione", "Informazioni")):
            blocchi[-1].append(r)
        elif r.startswith(("Subtotale", "Totale")):
            blocchi.append([]) if False else None
    for b in blocchi:
        mp = _UPOS.match(b[0])
        valuta, qty, nome, rating, pa, pm, _, vb, _ = mp.groups()
        corpo = "\n".join(b[1:])
        p = {"isin": "", "nome": nome.strip(), "valuta": valuta, "quantita": float(qty.replace(" ", "")), "prezzo_acquisto_pct": float(pa),
             "prezzo_mercato_pct": float(pm), "valore_base": float(vb.replace(" ", "")), "valore": float(qty.replace(" ", "")) * float(pm) / 100,
             "rating": "" if rating in (None, "Nessun rating") else rating, "sottostanti": [], "categoria_hint": "strutturato"}
        mi = re.search(r"ISIN (\w{12})", corpo)
        if mi:
            p["isin"] = mi.group(1)
        mi = re.search(r"issued by (.+?)(?:\s{2,}|\s+(?:Beni|Tutti|Tecnologia|Finanz|Salute|Industria|Energia|Materie|Beni)\b.*)?(?:\s+-?\d+\.\d+\s+-?\d+.*)?$", b[1] if len(b) > 1 else "")
        p["emittente"] = re.split(r"\s+(?:\d+\.\d{3,}|FLAT)", mi.group(1))[0].strip() if mi else ""
        mu = re.search(r"^on (.+?)(?:\s+\d{1,3}(?: \d{3})*\s+-?\d+\.\d+%)?$", corpo, re.M)
        if mu:
            sott = mu.group(1).strip()
            p["sottostanti_testo"] = sott
            if "/" in sott and not sott.lower().startswith("basket"):
                p["sottostanti"] = [{"ticker": _TICKER.get(x.strip().upper(), ""), "nome": x.strip(), "livello_iniziale": None} for x in sott.split("/")]
        md = re.search(r"(?:^|\n)(\d\d\.\d\d\.\d{4})\s*(?:\n|$)", corpo)
        if md:
            p["data_acquisto"] = _iso(md.group(1))
        mdu = re.search(r"Durata:\s+(\d{1,2} \w{3} \d{4}) - (\d{1,2} \w{3} \d{4})(?: \(expiration (\d{1,2} \w{3} \d{4})\))?", corpo)
        if mdu:
            p["data_emissione"] = _data_en(mdu.group(1))
            p["scadenza"] = _data_en(mdu.group(2))
            if mdu.group(3):
                p["data_rilevazione_finale"] = _data_en(mdu.group(3))
        mr = re.search(r"Rendimento:\s+([\d.]+)% p\.a\. coupon paid (\w[\w-]*)", corpo)
        if mr:
            p["cedola_annua_pct"] = float(mr.group(1))
            p["frequenza_cedola"] = _freq(mr.group(2))
        else:
            mr = re.search(r"Rendimento:\s+([\d.]+)% rebate subject to barrier ([\d.]+)%", corpo)
            if mr:
                p["rebate_pct"] = float(mr.group(1))
                p["barriera_superiore_pct"] = float(mr.group(2))
        mb = re.search(r"(?:subject to|below)[^\n]*?([\d.]+)%\s*\n?\s*barrier|subject to ([\d.]+)%\s*barrier", corpo)
        mb = re.search(r"subject to ([\d.]+)%\s*(?:\n\s*)?barrier", corpo) if "At risk" in corpo else None
        if mb:
            p["barriera_pct"] = float(mb.group(1))
        mc = re.search(r"Capitale:\s+([\d.]+)% minimum redemption", corpo)
        if mc:
            p["protezione_pct"] = float(mc.group(1))
        out["posizioni"].append(p)

    # quadratura sul totale della banca
    mt = re.search(r"Totale valore di mercato\s+(\d{1,3}(?: \d{3})*)", testo)
    if mt:
        tot_b = float(mt.group(1).replace(" ", ""))
        somma = sum(p["valore_base"] for p in out["posizioni"]) + sum(c["valore_base"] for c in out["liquidita"])
        ok = abs(somma - tot_b) <= 2 + len(out["posizioni"])
        out["controlli"].append({"ok": ok, "testo": f"Somma posizioni + conti {somma:,.0f} = totale valore di mercato della banca {tot_b:,.0f} {base}".replace(",", "’") if ok
                                 else f"Somma delle posizioni ({somma:,.0f}) diversa dal totale della banca ({tot_b:,.0f}) {base}".replace(",", "’")})
        out["totale_banca"] = tot_b
    out["quadra"] = all(c["ok"] for c in out["controlli"]) and bool(out["controlli"])
    d = {}
    for k, pat in (("performance_pct", r"Da inizio anno\s+(-?[\d.]+)%"), ("performance_assoluta", r"Da inizio anno\s+-?[\d.]+%\s+CHF\s+(-?\d[\d ]*)")):
        mm = re.search(pat, testo)
        if mm:
            d[k] = float(mm.group(1).replace(" ", ""))
    d["metodo"] = "TWR"
    out["banca_dichiara"] = d
    return out


# ───────────────────────── dispatcher ─────────────────────────
def leggi_posizioni(src) -> dict:
    righe = _righe(src, x_tolerance=1)
    if riconosci_performance(righe):
        return parse_performance(src)
    if riconosci_ubs_patrimoniale(righe):
        return parse_ubs_patrimoniale(src)
    raise ValueError("Documento di posizioni non riconosciuto.")
