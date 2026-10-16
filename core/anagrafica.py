"""Anagrafica degli strumenti: riconoscimento automatico da nome/movimenti e collegamento simbolo ↔ ISIN.

Un movimento di acquisto riporta l'ISIN ma non sempre il simbolo con cui compare poi nei dividendi
(es. «Acquisto … ISIN FR0010655746 (CS1)», «Dividendo … (VHYL)» senza ISIN). L'anagrafica tiene
per ogni strumento tutti i simboli noti, così le due righe finiscono sulla stessa posizione.
"""

from __future__ import annotations

import re
from typing import Optional

from core.config import VALUTAZIONE_DEFAULT


def chiave_strumento(isin: str = "", simbolo: str = "") -> str:
    isin = (isin or "").strip().upper()
    simbolo = (simbolo or "").strip().upper()
    if isin:
        return isin
    return f"SYM:{simbolo}" if simbolo else ""


def classifica_da_nome(nome: str) -> tuple[str, str]:
    """(categoria, sottocategoria) ipotizzate dal nome. Sono solo un suggerimento: l'utente conferma una volta."""
    n = (nome or "").lower()
    if re.search(r"reverse conv|barrier reverse|\bbrc\b|multi barrier", n):
        return "strutturato", "Barrier Reverse Convertible"
    if re.search(r"capital protect|protection note|\bcpn\b|capital guarantee", n):
        return "strutturato", "Capital Protection Note"
    if "bullish shark" in n:
        return "strutturato", "Bullish Shark Note"
    if "bearish shark" in n:
        return "strutturato", "Bearish Shark Note"
    if "airbag" in n:
        return "strutturato", "Airbag Certificate"
    if re.search(r"certificate|tracker|express|autocall|note\b", n):
        return "strutturato", "Altro strutturato"
    if re.search(r"\betf\b|ucits|\bucis\b|index fund|\betc\b", n):
        return "etf_azioni", ""
    if re.search(r"immobil|real estate|property fund", n):
        return "alternativo", "Fondo immobiliare"
    if re.search(r"private equity|\bpe fund\b", n):
        return "alternativo", "Private equity"
    if re.search(r"\b(call|put)\b|option", n):
        return "opzione", ""
    if re.search(r"\bbtp\b|\bbund\b|\boat\b|obblig|bond|anleihe|treasury|govt|government|\d+(\.\d+)?%\s+\d{4}", n):
        return "obbligazione", ""
    return "etf_azioni", ""    # titolo azionario: caso più comune per un nome senza altre parole chiave


def cedola_da_nome(nome: str) -> Optional[float]:
    """'6.93% p.a. Multi Barrier Reverse Co' -> 6.93"""
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*%\s*p\.?\s*a\.?", nome or "", re.I)
    return float(m.group(1).replace(",", ".")) if m else None


def nuovo_strumento(isin: str = "", simbolo: str = "", nome: str = "", valuta: str = "", prezzo_in_percento: bool = False) -> dict:
    categoria, sotto = classifica_da_nome(nome)
    s = {
        "chiave": chiave_strumento(isin, simbolo), "isin": (isin or "").upper(),
        "simboli": [simbolo.upper()] if simbolo else [], "nome": nome, "valuta": valuta,
        "categoria": categoria, "sottocategoria": sotto,
        "valutazione": VALUTAZIONE_DEFAULT.get(categoria, "mercato"),
        "prezzo_in_percento": prezzo_in_percento or categoria in ("obbligazione", "strutturato"),
        "ticker_mercato": "", "ticker_controllo": "",
        "scadenza": "", "data_emissione": "", "cedola_annua_pct": cedola_da_nome(nome),
        "frequenza_cedola": None, "barriera_pct": None, "sottostanti": [],
        "protezione_pct": None, "rating": "",
        "settori": {}, "aree": {}, "classificazione_auto": "", "nav_manuale": [],
        "confermato": False,     # False finché l'utente non ha controllato i dati dedotti
    }
    return s


class Registro:
    """Insieme degli strumenti con ricerca per ISIN o simbolo."""

    def __init__(self, strumenti: dict[str, dict] | None = None):
        self.strumenti: dict[str, dict] = dict(strumenti or {})
        for s in self.strumenti.values():                      # migrazione: i depositi a termine sono una classe di attivo a sé
            if s.get("categoria") == "obbligazione" and s.get("sottocategoria") == "Deposito a termine":
                s["categoria"] = "deposito"
        self._reindicizza()

    def _reindicizza(self):
        self._per_isin, self._per_simbolo = {}, {}
        for k, s in self.strumenti.items():
            if s.get("isin"):
                self._per_isin[s["isin"]] = k
            for sim in s.get("simboli", []):
                self._per_simbolo[sim.upper()] = k

    def trova(self, isin: str = "", simbolo: str = "") -> Optional[str]:
        isin, simbolo = (isin or "").upper(), (simbolo or "").upper()
        if isin and isin in self._per_isin:
            return self._per_isin[isin]
        if simbolo and simbolo in self._per_simbolo:
            return self._per_simbolo[simbolo]
        return None

    def assicura(self, isin: str = "", simbolo: str = "", nome: str = "", valuta: str = "", pct: bool = False) -> str:
        """Restituisce la chiave dello strumento, creandolo (non confermato) o completandolo se serve."""
        k = self.trova(isin, simbolo)
        if k is None:
            s = nuovo_strumento(isin, simbolo, nome, valuta, pct)
            k = s["chiave"]
            self.strumenti[k] = s
        else:
            s = self.strumenti[k]
            if isin and not s.get("isin"):
                # lo strumento era noto solo per simbolo (SYM:...): ora si conosce l'ISIN -> si promuove la chiave
                s["isin"] = isin.upper()
                nuova = s["isin"]
                if nuova != k:
                    self.strumenti.pop(k)
                    s["chiave"] = nuova
                    self.strumenti[nuova] = s
                    k = nuova
            if simbolo and simbolo.upper() not in s["simboli"]:
                s["simboli"].append(simbolo.upper())
            if nome and not s.get("nome"):
                s["nome"] = nome
            if valuta and not s.get("valuta"):
                s["valuta"] = valuta
        self._reindicizza()
        return k

    def allinea(self, cliente: dict) -> int:
        """Riallinea le chiavi dei prodotti nelle transazioni del cliente: se un prodotto è stato promosso da simbolo a ISIN
        (anche da un altro cliente), le sue righe non devono sparire dalle tabelle. Restituisce quante righe sono state corrette."""
        rimappa = self.mappa_chiavi()
        n = 0
        for t in cliente.get("transazioni", []):
            k = t.get("strumento") or ""
            if not k or k in self.strumenti:
                continue
            nuova = rimappa.get(k) or (self.trova(simbolo=k[4:]) if k.startswith("SYM:") else None)
            if nuova and nuova in self.strumenti:
                t["strumento"] = nuova
                n += 1
        return n

    def mappa_chiavi(self) -> dict[str, str]:
        """Dopo una promozione SYM:→ISIN, vecchia chiave -> nuova (per aggiornare le transazioni salvate)."""
        out = {}
        for k, s in self.strumenti.items():
            for sim in s.get("simboli", []):
                out[f"SYM:{sim.upper()}"] = k
        return out


def inferisci_frequenza(strumento: dict, transazioni: list[dict]) -> Optional[int]:
    """Frequenza cedolare (1,2,4,12) dal rapporto fra proventi di una data e nominale × cedola annua."""
    c = strumento.get("cedola_annua_pct")
    if not c:
        return None
    per_data: dict[str, tuple[float, float]] = {}
    for t in transazioni:
        if t.get("strumento") != strumento["chiave"] or t["tipo"] not in ("cedola", "premio_opzione"):
            continue
        tot, q = per_data.get(t["data"], (0.0, 0.0))
        per_data[t["data"]] = (tot + abs(t["importo_cassa"]), max(q, float(t.get("quantita") or 0)))
    stime = []
    for tot, q in per_data.values():
        if q > 0 and tot > 0:
            rapporto = tot / (q * c / 100)
            stime.append(rapporto)
    if not stime:
        return None
    media = sum(stime) / len(stime)
    return min((1, 2, 4, 12), key=lambda f: abs(media - 1 / f))
