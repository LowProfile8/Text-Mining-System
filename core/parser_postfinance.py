"""Lettura automatica degli estratti conto PostFinance (conto TRADING, PDF con testo).

Il PDF non indica in che colonna (debito/credito) cade un importo: il segno si ricava dalla
variazione del saldo riga per riga. A fine lettura il parser esegue controlli di quadratura
(saldo iniziale + movimenti = saldo finale, totali debito/credito, saldi per valuta di pagina 1):
se qualcosa non torna lo segnala, e l'importazione non va confermata alla cieca.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field, asdict
from datetime import date
from decimal import Decimal
from typing import Optional

import pdfplumber

BANCA = "PostFinance"

_NUM = r"-?\d[\d’'`]*\.\d{2}"
_DATA = r"\d{2}\.\d{2}\.\d{4}"
_RE_RIGA_MOV = re.compile(
    rf"^(?P<data>{_DATA})\s+(?P<titolo>.+?)\s+(?:(?P<rif>\d{{7,}})\s+)?(?P<imp>{_NUM})\s+(?P<val>{_DATA})\s+(?P<saldo>{_NUM})$"
)
_RE_APERTURA = re.compile(rf"^(?P<data>{_DATA})\s+Saldo di apertura\s+(?P<saldo>{_NUM})$")
_RE_FINALE = re.compile(rf"^(?P<data>{_DATA})\s+Saldo finale\s+(?P<saldo>{_NUM})$")
_RE_INIZIO_RIGA_DATA = re.compile(rf"^{_DATA}\s")
_RE_KV = re.compile(
    r"^(Quantità|Prezzo|Importo|Commissione|Tasse|Totale|Piattaforma di trading|ISIN|Valor|Corso|Interessi maturati)\s*:\s*(.*)$"
)
_SALTA = (
    "Documento generato", "Dal ", "Signor", "Avviso senza firma", "PostFinance SA", "Contact Center",
    "Pagina ", "DATA INFORMAZIONE", "Si prega di verificare", "Contact ", "Estratto conto dal", "Il suo estratto",
)

_TIPI = [
    (r"^acquisto", "acquisto"), (r"^vendita", "vendita"), (r"dividend", "dividendo"),
    (r"^coupon|^cedola", "cedola"), (r"option premium|premio", "premio_opzione"),
    (r"rimborso|scadenza|riscatto", "rimborso"), (r"diritti di custodia|spese di custodia", "costo_custodia"),
    (r"cambio valuta", "cambio"), (r"interess", "interesse"),
    (r"^pagamento da|versamento|accredito|bonifico in|deposito|entrata", "deposito"),
    (r"^trasferimento", "trasferimento"),
    (r"^pagamento a\b|prelievo|bonifico out|uscita", "prelievo"),
    (r"commission|spes[ae]|tass[ae]|imposta", "costo"),
]


@dataclass
class Movimento:
    data: str                       # ISO yyyy-mm-dd (data operazione)
    data_valuta: str
    tipo: str                       # acquisto, vendita, dividendo, cedola, premio_opzione, rimborso, costo_custodia, cambio, interesse, deposito, prelievo, costo, altro
    titolo: str                     # testo originale della banca
    valuta: str
    importo_cassa: float            # effetto sul conto: positivo = entrata, negativo = uscita
    saldo: float
    rif: str = ""
    nome: str = ""
    simbolo: str = ""
    isin: str = ""
    quantita: Optional[float] = None
    prezzo: Optional[float] = None
    prezzo_in_percento: bool = False
    importo_lordo: Optional[float] = None
    commissione: float = 0.0
    tasse: float = 0.0
    piattaforma: str = ""
    cambio_coppia: str = ""
    cambio_tasso: Optional[float] = None
    note: str = ""


@dataclass
class ContoValuta:
    valuta: str
    saldo_iniziale: float
    saldo_finale: float
    tot_debito: float
    tot_credito: float


@dataclass
class Estratto:
    banca: str = BANCA
    cliente_nome: str = ""
    cliente_numero: str = ""
    tipo_conto: str = ""
    periodo_da: str = ""
    periodo_a: str = ""
    generato_il: str = ""
    conti: dict = field(default_factory=dict)       # valuta -> ContoValuta (come dict)
    movimenti: list = field(default_factory=list)   # list[Movimento] (come dict)
    controlli: list = field(default_factory=list)   # [{"ok": bool, "testo": str}]
    avvisi: list = field(default_factory=list)

    @property
    def quadra(self) -> bool:
        return all(c["ok"] for c in self.controlli)

    def a_dict(self) -> dict:
        return asdict(self)


# ─────────────────────────── utilità ───────────────────────────
def _pulisci(testo: str) -> str:
    testo = re.sub(r"\(cid:(\d+)\)", lambda m: chr(int(m.group(1))), testo)
    return testo.replace("’", "’")


def _num(s: str) -> Decimal:
    return Decimal(re.sub(r"[’'`\s]", "", s))


def _iso(s: str) -> str:
    g, m, a = s.split(".")
    return date(int(a), int(m), int(g)).isoformat()


def _tipo(titolo: str) -> str:
    t = titolo.lower().strip()
    for pattern, nome in _TIPI:
        if re.search(pattern, t):
            return nome
    return "altro"


def _importo_con_valuta(testo: str):
    """'EUR 1’840.00' -> (Decimal, 'EUR', False);  '99.96%' -> (Decimal, '', True)."""
    testo = testo.strip()
    m = re.match(rf"^([A-Z]{{3}})\s+({_NUM})$", testo)
    if m:
        return _num(m.group(2)), m.group(1), False
    m = re.match(r"^(-?\d+(?:\.\d+)?)\s*%$", testo)
    if m:
        return Decimal(m.group(1)), "", True
    m = re.match(rf"^({_NUM})$", testo)
    if m:
        return _num(m.group(1)), "", False
    return None, "", False


# ─────────────────────────── lettura ───────────────────────────
def leggi_righe(percorso_o_file) -> list[str]:
    righe: list[str] = []
    with pdfplumber.open(percorso_o_file) as pdf:
        for pagina in pdf.pages:
            testo = pagina.extract_text() or ""
            righe.extend(_pulisci(testo).splitlines())
    return [r.strip() for r in righe if r.strip()]


def riconosci(righe: list[str]) -> bool:
    testo = "\n".join(righe[:40])
    tutto = "\n".join(righe)
    return ("PostFinance" in tutto or "Swissquote" in tutto) and "estratto conto" in testo.lower()


def parse(percorso_o_file) -> Estratto:
    righe = leggi_righe(percorso_o_file)
    if not riconosci(righe):
        raise ValueError("Questo PDF non sembra un estratto conto PostFinance/Swissquote.")
    est = Estratto()
    if "Swissquote Bank" in "\n".join(righe) and "PostFinance SA" not in "\n".join(righe):
        est.banca = "Swissquote"
    saldi_p1: dict[str, Decimal] = {}

    # ── intestazione (pagina 1) ──
    for i, r in enumerate(righe):
        m = re.search(rf"dal ({_DATA}) al ({_DATA})", r)
        if m and not est.periodo_da and not r.startswith("Dal "):
            est.periodo_da, est.periodo_a = _iso(m.group(1)), _iso(m.group(2))
        m = re.search(rf"Documento generato il ({_DATA})", r)
        if m and not est.generato_il:
            est.generato_il = _iso(m.group(1))
        m = re.match(r"^Signor[a]?\s+(.+)$", r)
        if m and not est.cliente_nome:
            est.cliente_nome = m.group(1).strip()
        m = re.search(r"Cliente\s+(\d+)", r)
        if m and not est.cliente_numero:
            est.cliente_numero = m.group(1)
        m = re.search(r"Conto Tipo\s+(\w+)", r)
        if m and not est.tipo_conto:
            est.tipo_conto = m.group(1)
        if r.startswith("Saldo finale suddiviso"):
            nomi_riga = righe[i + 1] if i + 1 < len(righe) else ""
            numeri = re.findall(_NUM, righe[i + 2]) if i + 2 < len(righe) else []
            codici = righe[i + 3].split() if i + 3 < len(righe) else []
            if len(numeri) == len(codici):
                saldi_p1 = {c: _num(n) for c, n in zip(codici, numeri)}
            else:
                est.avvisi.append(f"Riepilogo valute di pagina 1 non leggibile ({nomi_riga!r}).")

    # ── sezioni per valuta ──
    valuta = None
    intest: dict[str, dict] = {}
    movimenti: dict[str, list] = {}
    corrente: Optional[dict] = None

    def chiudi():
        nonlocal corrente
        if corrente is not None and valuta is not None:
            movimenti[valuta].append(corrente)
        corrente = None

    for r in righe:
        m = re.match(r"^Estratto conto in ([A-Z]{3})$", r)
        if m:
            chiudi()
            valuta = m.group(1)
            intest.setdefault(valuta, {"saldi": [], "deb": None, "cred": None, "aperto": None, "chiuso": None})
            movimenti.setdefault(valuta, [])
            continue
        if valuta is None:
            continue
        m = re.match(rf"^Saldo in {_DATA}\s+({_NUM})\s+[A-Z]{{3}}$", r)
        if m:
            intest[valuta]["saldi"].append(_num(m.group(1)))
            continue
        m = re.match(rf"^Totale debito\s+({_NUM})", r)
        if m:
            intest[valuta]["deb"] = _num(m.group(1)); continue
        m = re.match(rf"^Totale credito\s+({_NUM})", r)
        if m:
            intest[valuta]["cred"] = _num(m.group(1)); continue
        m = _RE_APERTURA.match(r)
        if m:
            chiudi(); intest[valuta]["aperto"] = _num(m.group("saldo")); continue
        m = _RE_FINALE.match(r)
        if m:
            chiudi(); intest[valuta]["chiuso"] = _num(m.group("saldo")); continue
        m = _RE_RIGA_MOV.match(r)
        if m:
            chiudi()
            corrente = {"m": m, "dettagli": []}
            continue
        if _RE_INIZIO_RIGA_DATA.match(r):
            est.avvisi.append(f"Riga con data non riconosciuta in conto {valuta}: «{r}»")
            continue
        if r.startswith(_SALTA) or r.startswith("Saldo in "):
            continue
        if corrente is not None:
            corrente["dettagli"].append(r)
    chiudi()

    # ── costruzione movimenti con segno dal saldo ──
    for val, blocchi in movimenti.items():
        h = intest[val]
        saldo_prec = h["aperto"] if h["aperto"] is not None else (h["saldi"][0] if h["saldi"] else Decimal(0))
        somma_deb = Decimal(0)
        somma_cred = Decimal(0)
        for blocco in blocchi:
            m = blocco["m"]
            imp = _num(m.group("imp"))
            saldo = _num(m.group("saldo"))
            delta = saldo - saldo_prec
            if abs(abs(delta) - imp) > Decimal("0.005"):
                est.avvisi.append(
                    f"{val} {m.group('data')} «{m.group('titolo')}»: importo {imp} non coerente con la variazione del saldo {delta}."
                )
            segno = 1 if delta >= 0 else -1
            if segno > 0:
                somma_cred += imp
            else:
                somma_deb += imp
            saldo_prec = saldo
            mov = _costruisci_movimento(m, blocco["dettagli"], val, segno, imp, saldo, est)
            est.movimenti.append(asdict(mov))
        saldo_fin = h["chiuso"] if h["chiuso"] is not None else (h["saldi"][-1] if h["saldi"] else saldo_prec)
        saldo_ini = h["aperto"] if h["aperto"] is not None else (h["saldi"][0] if h["saldi"] else Decimal(0))
        est.conti[val] = asdict(ContoValuta(
            val, float(saldo_ini), float(saldo_fin),
            float(h["deb"] if h["deb"] is not None else somma_deb),
            float(h["cred"] if h["cred"] is not None else somma_cred),
        ))
        # controlli di quadratura
        quadra_saldo = abs(saldo_ini + somma_cred - somma_deb - saldo_fin) <= Decimal("0.01")
        est.controlli.append({"ok": quadra_saldo, "testo": f"{val}: saldo iniziale {saldo_ini} + entrate {somma_cred} − uscite {somma_deb} = saldo finale {saldo_fin}"})
        if h["deb"] is not None and h["cred"] is not None:
            ok = abs(h["deb"] - somma_deb) <= Decimal("0.01") and abs(h["cred"] - somma_cred) <= Decimal("0.01")
            est.controlli.append({"ok": ok, "testo": f"{val}: totali debito/credito dichiarati ({h['deb']} / {h['cred']}) = somma dei movimenti ({somma_deb} / {somma_cred})"})
        if val in saldi_p1:
            ok = abs(saldi_p1[val] - saldo_fin) <= Decimal("0.01")
            est.controlli.append({"ok": ok, "testo": f"{val}: saldo finale di pagina 1 ({saldi_p1[val]}) = saldo del conto ({saldo_fin})"})
    for val in saldi_p1:
        if val not in est.conti and saldi_p1[val] != 0:
            est.controlli.append({"ok": False, "testo": f"Conto {val} con saldo {saldi_p1[val]} dichiarato in pagina 1 ma non trovato nelle pagine"})
    if not est.movimenti and not est.conti:
        est.avvisi.append("Nessun conto o movimento trovato.")
    for d in est.movimenti:     # prezzo in % non dichiarato dalla banca: lo si riconosce dall'importo (quantità × prezzo / 100 = importo)
        q, pr, lordo = d.get("quantita"), d.get("prezzo"), d.get("importo_lordo")
        if q and pr and lordo and not d.get("prezzo_in_percento") and abs(q * pr / 100 - lordo) < 0.5 and abs(q * pr - lordo) > 0.5:
            d["prezzo_in_percento"] = True
    return est


def _costruisci_movimento(m, dettagli: list[str], valuta: str, segno: int, imp: Decimal, saldo: Decimal, est: Estratto) -> Movimento:
    titolo = m.group("titolo").strip()
    tipo = _tipo(titolo)
    if tipo == "altro":
        est.avvisi.append(f"Tipo di movimento non riconosciuto: «{titolo}» ({m.group('data')}, {valuta}). Controllarlo nell'anteprima.")
    mov = Movimento(
        data=_iso(m.group("data")), data_valuta=_iso(m.group("val")), tipo=tipo, titolo=titolo, valuta=valuta,
        importo_cassa=float(imp * segno), saldo=float(saldo), rif=m.group("rif") or "",
    )
    descr: list[str] = []
    for d in dettagli:
        kv = _RE_KV.match(d)
        if kv:
            chiave, valore = kv.group(1), kv.group(2).strip()
            if chiave == "Quantità":
                mov.quantita = float(_num(valore + ".00")) if re.fullmatch(r"-?\d+", valore.replace("’", "")) else _a_float(valore)
            elif chiave in ("Prezzo", "Corso"):
                v, _, pct = _importo_con_valuta(valore)
                mov.prezzo, mov.prezzo_in_percento = (float(v) if v is not None else None), pct
            elif chiave == "Importo":
                v, _, _ = _importo_con_valuta(valore)
                mov.importo_lordo = float(v) if v is not None else None
            elif chiave == "Commissione":
                v, _, _ = _importo_con_valuta(valore); mov.commissione = float(v or 0)
            elif chiave == "Tasse":
                v, _, _ = _importo_con_valuta(valore); mov.tasse = float(v or 0)
            elif chiave == "Piattaforma di trading":
                mov.piattaforma = valore
            elif chiave == "ISIN":
                mov.isin = valore.upper()
            elif chiave == "Valor":
                mov.simbolo = mov.simbolo or valore
            # «Totale» è ridondante: l'effetto sul conto è già importo_cassa
            continue
        mc = re.match(r"^([A-Z]{3}) - ([A-Z]{3})$", d)
        if mc:
            mov.cambio_coppia = d; continue
        mt = re.match(r"^1 ([A-Z]{3}) = (\d+\.\d+) ([A-Z]{3})$", d)
        if mt:
            mov.cambio_tasso = float(mt.group(2))
            mov.cambio_coppia = mov.cambio_coppia or f"{mt.group(1)} - {mt.group(3)}"
            continue
        if d.strip().lower() == titolo.lower():
            continue   # es. «Diritti di custodia» ripetuto
        descr.append(d)
    testo = " ".join(descr).strip()
    if testo:
        ms = re.search(r"\(([A-Za-z0-9.]+)\)\s*$", testo)
        if ms:
            mov.simbolo = ms.group(1).upper()
            testo = testo[: ms.start()].strip()
        mov.nome = testo
    return mov


def _a_float(s: str) -> float:
    s = re.sub(r"[’'`\s]", "", s)
    try:
        return float(s)
    except ValueError:
        return float("nan")
