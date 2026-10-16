"""Lettura delle posizioni di Interactive Brokers da screenshot (pagina «Portfolio → Positions») o da PDF.

- Immagine: riconoscimento del testo (Tesseract) e ricostruzione della tabella dalle posizioni delle parole.
- PDF: se contiene testo, si cercano le righe di «Open Positions»; se è una scansione/schermata si passa dall'OCR.
Il risultato va SEMPRE controllato dall'utente prima di importare (tabella modificabile con controllo quantità × prezzo = costo).
"""

from __future__ import annotations

import io
import re
from dataclasses import dataclass, field

NUM = re.compile(r"^[+-]?\d{1,3}(?:,\d{3})*(?:\.\d+)?$|^[+-]?\d+(?:\.\d+)?$")
VALUTE = {"USD", "EUR", "CHF", "GBP", "JPY", "CAD", "AUD", "SEK", "NOK", "DKK", "HKD"}
TICKER = re.compile(r"^[A-Z][A-Z0-9.\-]{0,9}$")


@dataclass
class PosizioneIB:
    simbolo: str
    nome: str = ""
    valuta: str = "USD"
    quantita: float = 0.0
    prezzo_medio: float | None = None
    costo_totale: float | None = None
    ultimo: float | None = None
    valore_mercato: float | None = None
    note: list = field(default_factory=list)

    def prezzo_effettivo(self) -> float | None:
        """Prezzo unitario d'acquisto: costo totale / quantità (più preciso del prezzo medio arrotondato dallo schermo)."""
        if self.costo_totale and self.quantita:
            return self.costo_totale / self.quantita
        return self.prezzo_medio


def _num(t: str) -> float | None:
    t = t.replace("%", "").strip()
    if not NUM.match(t):
        return None
    return float(t.replace(",", ""))


def _ocr_parole(img):
    import pytesseract
    from PIL import Image
    g = img.convert("L")
    if g.width < 2400:                       # schermate piccole: ingrandisco per leggere meglio le cifre
        f = 2400 / g.width
        g = g.resize((int(g.width * f), int(g.height * f)), Image.LANCZOS)
    d = pytesseract.image_to_data(g, config="--psm 11", output_type=pytesseract.Output.DICT)
    out = []
    for i, t in enumerate(d["text"]):
        t = t.strip()
        if t and float(d["conf"][i]) > 20:
            out.append({"t": t, "l": d["left"][i], "r": d["left"][i] + d["width"][i], "top": d["top"][i], "h": d["height"][i], "cy": d["top"][i] + d["height"][i] / 2})
    return out


def parse_immagine(img) -> list[PosizioneIB]:
    parole = _ocr_parole(img)
    intest = {}
    for w in parole:
        T = w["t"].upper()
        if T == "INSTRUMENT":
            intest["instrument"] = w
        elif T == "POSITION":
            intest["position"] = w
        elif T == "LAST":
            intest["last"] = w
        elif T == "BASIS":
            intest["basis"] = w
        elif T == "PRICE" and "avg" not in intest and any(p["t"].upper() == "AVG" and abs(p["cy"] - w["cy"]) < 20 and p["r"] < w["l"] + 5 for p in parole):
            intest["avg"] = w
        elif T == "VALUE" and any(p["t"].upper() == "MARKET" and abs(p["cy"] - w["cy"]) < 20 for p in parole):
            intest["value"] = w
    if not {"instrument", "position", "basis"} <= set(intest):
        raise ValueError("Non riconosco la tabella delle posizioni di Interactive Brokers (servono le colonne INSTRUMENT, POSITION, COST BASIS). Usa la pagina Portfolio → Positions.")
    y0 = intest["instrument"]["top"] + intest["instrument"]["h"] + 5
    x_ini, x_pos = intest["instrument"]["l"] - 15, intest["position"]["l"] - 150
    # ancore: simboli in grassetto nella colonna strumento
    ancore = [w for w in parole if w["top"] > y0 and x_ini <= w["l"] <= x_ini + 80 and TICKER.match(w["t"]) and w["r"] < x_pos]
    ancore.sort(key=lambda w: w["top"])
    # un simbolo è seguito dal nome (riga sotto): tengo solo il primo di ogni gruppo di righe vicine
    righe_anc = []
    for w in ancore:
        if not righe_anc or w["top"] - righe_anc[-1]["top"] > 1.6 * righe_anc[-1]["h"] + 10:
            righe_anc.append(w)
    # i nomi (seconda riga) iniziano con lettere maiuscole nella stessa colonna: non sono ancore perché cadono entro 1.6 h dal simbolo
    colonne = {k: intest[k]["r"] for k in ("position", "last", "basis", "avg", "value") if k in intest}

    def vicino(banda, col, tol=60, escludi=()):
        c = [w for w in banda if _num(w["t"]) is not None and abs(w["r"] - colonne[col]) < tol and w not in escludi]
        return min(c, key=lambda w: abs(w["r"] - colonne[col])) if c else None

    out = []
    for i, a in enumerate(righe_anc):
        fine = righe_anc[i + 1]["top"] - 4 if i + 1 < len(righe_anc) else a["top"] + 4.5 * a["h"]
        banda = [w for w in parole if a["top"] - 0.8 * a["h"] <= w["top"] < fine]
        pos = vicino(banda, "position")
        costo = vicino(banda, "basis", 80)
        if not pos or not costo:
            continue
        nome = " ".join(w["t"] for w in sorted(banda, key=lambda w: (round(w["top"] / 10), w["l"])) if w is not a and x_ini <= w["l"] < x_pos and w["top"] > a["top"] + 0.5 * a["h"])
        val = next((w["t"] for w in banda if w["t"] in VALUTE and abs(w["r"] - colonne["basis"]) < 80), None)
        p = PosizioneIB(simbolo=a["t"], nome=nome.replace("|", "I").strip(), valuta=val or "USD", quantita=_num(pos["t"]), costo_totale=_num(costo["t"]))
        if "avg" in colonne and (m := vicino(banda, "avg", 70)):
            p.prezzo_medio = _num(m["t"])
        if "last" in colonne and (m := vicino(banda, "last", 70)):
            p.ultimo = _num(m["t"])
        if "value" in colonne and (m := vicino(banda, "value", 80)):
            p.valore_mercato = _num(m["t"])
        if not val:
            p.note.append("valuta non letta: controlla")
        out.append(p)
    if not out:
        raise ValueError("Nessuna posizione riconosciuta nell'immagine.")
    return out


# ───────────────────────── PDF ─────────────────────────
_RIGA_ACTIVITY = re.compile(r"^(?P<sym>[A-Z][A-Z0-9.\-]{0,9})\s+(?P<q>-?[\d,]+(?:\.\d+)?)\s+(?P<mult>\d+)\s+(?P<cp>[\d,]+\.\d+)\s+(?P<cb>[\d,]+\.\d+)\s+(?P<cl>[\d,]+\.\d+)\s+(?P<val>-?[\d,]+\.\d+)")


def parse_pdf(file) -> list[PosizioneIB]:
    import pdfplumber
    file.seek(0) if hasattr(file, "seek") else None
    with pdfplumber.open(file) as pdf:
        testo = "\n".join((p.extract_text() or "") for p in pdf.pages)
        out, valuta = [], "USD"
        for riga in testo.splitlines():
            r = riga.strip()
            if r in VALUTE:
                valuta = r
                continue
            m = _RIGA_ACTIVITY.match(r)
            if m and m["mult"] == "1":
                out.append(PosizioneIB(simbolo=m["sym"], valuta=valuta, quantita=float(m["q"].replace(",", "")), prezzo_medio=float(m["cp"].replace(",", "")),
                                       costo_totale=float(m["cb"].replace(",", "")), ultimo=float(m["cl"].replace(",", "")), valore_mercato=float(m["val"].replace(",", ""))))
        if out:
            return out
        # nessun testo utile: PDF di una schermata → OCR della prima pagina con tabella
        for pag in pdf.pages:
            im = pag.to_image(resolution=250).original
            try:
                return parse_immagine(im)
            except ValueError:
                continue
    raise ValueError("Nel PDF non trovo la tabella delle posizioni di Interactive Brokers.")


def leggi(file) -> list[PosizioneIB]:
    """file: oggetto caricato da Streamlit (immagine o PDF)."""
    nome = (getattr(file, "name", "") or "").lower()
    if nome.endswith(".pdf"):
        return parse_pdf(file)
    from PIL import Image
    return parse_immagine(Image.open(io.BytesIO(file.getvalue() if hasattr(file, "getvalue") else file.read())))
