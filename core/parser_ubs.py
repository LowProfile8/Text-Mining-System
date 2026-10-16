"""Estratto conto corrente UBS (mensile). Il segno dei movimenti è dedotto dalla variazione del saldo, con quadratura finale."""

from __future__ import annotations

import re
from datetime import datetime
from decimal import Decimal

import pdfplumber

from core.parser_postfinance import ContoValuta, Estratto, Movimento

BANCA = "UBS"
_NUM = re.compile(r"\d{1,3}(?: \d{3})*\.\d{2}-?|\d+\.\d{2}-?")
_RIGA = re.compile(r"^(\d\d\.\d\d\.\d\d)\s+(.*)$")
_DATA_VAL = re.compile(r"\b(\d\d\.\d\d\.\d\d)\b")
_TIPI = [
    (r"^storno interesse|^interesse", "interesse"), (r"^dividendo", "dividendo"), (r"^cedola|^coupon", "cedola"),
    (r"spese|commission|tenuta del conto|diritti", "costo"), (r"imposta", "imposta"),
    (r"ordine di pagamento|bonifico a favore|addebito", "prelievo"),
    (r"accredito|bonifico a favore del conto|versamento|pagamento in entrata", "deposito"),
    (r"cambio|divisa", "cambio"),
]


def _iso(d: str) -> str:
    return datetime.strptime(d, "%d.%m.%y").date().isoformat()


def _num(s: str) -> Decimal:
    neg = s.endswith("-")
    v = Decimal(s.rstrip("-").replace(" ", ""))
    return -v if neg else v


def riconosci(righe: list[str]) -> bool:
    t = "\n".join(righe[:60])
    return "UBS" in t and "Estratto del conto" in t and "Saldo iniziale" in "\n".join(righe)


def leggi_righe(src) -> list[str]:
    out: list[str] = []
    with pdfplumber.open(src) as pdf:
        for p in pdf.pages:
            out.extend((p.extract_text(x_tolerance=1) or "").splitlines())
    return [r.strip() for r in out if r.strip()]


def parse(src) -> Estratto:
    righe = leggi_righe(src)
    if not riconosci(righe):
        raise ValueError("Questo PDF non sembra un estratto conto corrente UBS.")
    est = Estratto(banca=BANCA)
    testo = "\n".join(righe)
    m = re.search(r"Conto corrente [^\n]*?\b([A-Z]{3})\b\s*$", testo, re.M)
    valuta = m.group(1) if m else "CHF"
    m = re.search(r"No\. di conto\s+([\d\-\.]+\w?)", testo)
    est.cliente_numero = m.group(1) if m else ""
    m = re.search(r"(\d\d\.\d\d\.\d{4}) - (\d\d\.\d\d\.\d{4})", testo)
    if m:
        est.periodo_da = datetime.strptime(m.group(1), "%d.%m.%Y").date().isoformat()
        est.periodo_a = datetime.strptime(m.group(2), "%d.%m.%Y").date().isoformat()
    m = re.search(r"^Signor[a]?\s*\n(?:No\. di conto[^\n]*\n)?([^\n]+)", testo, re.M)
    est.cliente_nome = m.group(1).strip() if m else ""
    est.tipo_conto = "Conto corrente"

    # raggruppa le righe in movimenti (riga con data + righe di dettaglio)
    blocchi: list[list[str]] = []
    for r in righe:
        if r.startswith(("Totale del movimento", "Comunicazione senza firma", "Vogliate verificare")):
            if blocchi and r.startswith("Totale del movimento"):
                est_tot = _NUM.findall(r)
                tot = [_num(x) for x in est_tot]
            continue
        if _RIGA.match(r) and not r.startswith("GNZKOA"):
            blocchi.append([r])
        elif blocchi and not r.startswith(("Pagina", "aUBS", "GNZ", "Spese per", "al ", "Estratto")):
            blocchi[-1].append(r)
    saldo_iniz = saldo_fin = None
    prec = None
    tot_deb = tot_cred = Decimal(0)
    for b in blocchi:
        d, resto = _RIGA.match(b[0]).groups()
        if resto.startswith("Saldo iniziale"):
            prec = saldo_iniz = _num(_NUM.findall(resto)[-1])
            continue
        if resto.startswith("Saldo finale"):
            saldo_fin = _num(_NUM.findall(resto)[-1])
            continue
        dv = _DATA_VAL.findall(resto)
        data_valuta = _iso(dv[-1]) if dv else _iso(d)
        senza_data = _DATA_VAL.sub(" ", resto)
        nums = [_num(x) for x in _NUM.findall(senza_data)]
        if len(nums) < 2 or prec is None:
            est.avvisi.append(f"Riga non interpretabile: {b[0]}")
            continue
        saldo, importo = nums[-1], nums[-2]
        delta = saldo - prec
        if abs(abs(delta) - abs(importo)) > Decimal("0.011"):
            est.avvisi.append(f"Il saldo non torna alla riga «{b[0]}»")
        prec = saldo
        titolo = re.split(r"\s+[\d ]+\.\d\d", resto)[0].strip()
        tipo = "altro"
        for pat, t in _TIPI:
            if re.search(pat, titolo, re.I):
                tipo = t
                break
        if tipo == "prelievo" and delta > 0:
            tipo = "deposito"
        dettaglio = [x for x in b[1:] if x]
        rif = ""
        for x in dettaglio:
            mm = re.match(r"^(?:VN\s?(\d+)|(P\d{6,}))", x)
            if mm:
                rif = mm.group(1) or mm.group(2)
                break
        nome = next((x for x in dettaglio if not re.match(r"^(VN\s?\d+|P\d{6,})", x)), "")
        if delta > 0:
            tot_cred += delta
        else:
            tot_deb += -delta
        est.movimenti.append(Movimento(
            data=_iso(d), data_valuta=data_valuta, tipo=tipo, titolo=(titolo + (" – " + nome if nome else ""))[:120], valuta=valuta,
            importo_cassa=float(delta), saldo=float(saldo), rif=f"{rif}:{len(est.movimenti)}" if rif else f"{d}:{len(est.movimenti)}",
            nome=nome if tipo in ("dividendo", "cedola") else "", simbolo=re.sub(r"\s+", "", nome).upper() if tipo in ("dividendo", "cedola") else "",
        ).__dict__)
    if saldo_iniz is None or saldo_fin is None:
        raise ValueError("Saldo iniziale/finale non trovati nell'estratto UBS.")
    est.conti[valuta] = ContoValuta(valuta, float(saldo_iniz), float(saldo_fin), float(tot_deb), float(tot_cred)).__dict__
    quadra = abs(saldo_iniz + tot_cred - tot_deb - saldo_fin) < Decimal("0.011")
    est.controlli.append({"ok": quadra, "testo": f"{valuta}: saldo iniziale {saldo_iniz} + entrate {tot_cred} − uscite {tot_deb} = saldo finale {saldo_fin}" if quadra else f"{valuta}: i movimenti NON portano dal saldo iniziale {saldo_iniz} al finale {saldo_fin}"})
    est.controlli.append({"ok": not est.avvisi, "testo": "Tutte le righe interpretate e coerenti con il saldo" if not est.avvisi else "Alcune righe non coerenti con il saldo"})
    return est
