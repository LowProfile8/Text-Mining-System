"""Motore di calcolo della performance.

Principio (concordato con l'utente): il portafoglio si divide in due blocchi con regole di valutazione diverse.

  • Blocco «a scadenza» (obbligazioni, prodotti strutturati): si valutano AL COSTO + cedola maturata.
    Il prezzo di mercato non entra nel rendimento perché si porta il prodotto a scadenza/rimborso.
    Il report mostra invece il rendimento ATTESO a scadenza e, per le barriere, la distanza di sicurezza.
  • Blocco «a mercato» (ETF, azioni, opzioni) : quantità × prezzo di mercato.
    I fondi non quotati usano l'ultimo NAV inserito a mano.

Il rendimento del periodo è un Modified Dietz (corretto per i flussi); il rendimento annualizzato è un XIRR.
Tutti i flussi sono convertiti nella valuta base del cliente con il cambio del giorno.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Callable, Optional

from scipy.optimize import brentq

from core.config import SOGLIA_ARANCIO, SOGLIA_GIALLO, SOGLIA_VERDE

TIPI_REDDITO = ("dividendo", "cedola", "premio_opzione", "interesse")
TIPI_COSTO = ("costo_custodia", "costo", "imposta")
TIPI_ESCLUSI = ("cambio", "deposito", "prelievo", "trasferimento")      # movimenti di liquidità, non di investimento


class DatoMancante(Exception):
    """Manca un cambio o un prezzo indispensabile: il report non si può calcolare in modo affidabile."""


def D(s: str) -> date:
    return date.fromisoformat(s)


def aggiungi_mesi(d: date, mesi: int) -> date:
    m = d.month - 1 + mesi
    anno, mese = d.year + m // 12, m % 12 + 1
    giorni_mese = [31, 29 if anno % 4 == 0 and (anno % 100 != 0 or anno % 400 == 0) else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][mese - 1]
    return date(anno, mese, min(d.day, giorni_mese))


def xirr(flussi: list[tuple[date, float]]) -> Optional[float]:
    flussi = [(d, a) for d, a in flussi if abs(a) > 1e-9]
    if len(flussi) < 2 or not (any(a < 0 for _, a in flussi) and any(a > 0 for _, a in flussi)):
        return None
    t0 = min(d for d, _ in flussi)
    def f(r):
        return sum(a / (1 + r) ** ((d - t0).days / 365.0) for d, a in flussi)
    try:
        return brentq(f, -0.9999, 1000.0, maxiter=200)
    except (ValueError, RuntimeError):
        return None


def modified_dietz(v0: float, v1: float, flussi: list[tuple[date, float]], da: date, a: date) -> Optional[float]:
    """flussi dal punto di vista dell'investitore (acquisto = negativo, reddito/vendita = positivo)."""
    T = max((a - da).days, 1)
    contributi = [(d, -x) for d, x in flussi if da < d <= a]
    C = sum(c for _, c in contributi)
    pesato = sum(c * (a - d).days / T for d, c in contributi)
    base = v0 + pesato
    if base <= 1e-9:
        return None
    return (v1 - v0 - C) / base


@dataclass
class Contesto:
    base: str
    fx: Callable[[str, str, str], Optional[float]]          # (da, a, data_iso) -> tasso
    prezzo: Callable[[dict, str], dict]                       # (strumento, data_iso) -> {"prezzo","fonte","stato"}
    spot: Callable[[str, str], Optional[float]] = lambda t, d: None   # sottostanti delle barriere
    avvisi: list = field(default_factory=list)
    prezzi_usati: dict = field(default_factory=dict)

    def conv(self, importo: float, da: str, data: str) -> float:
        if da == self.base or importo == 0:
            return importo
        r = self.fx(da, self.base, data)
        if r is None:
            raise DatoMancante(f"Cambio {da}/{self.base} al {data} non disponibile")
        return importo * r


@dataclass
class Pos:
    chiave: str
    qty: float = 0.0
    costo_base: float = 0.0           # costo residuo della quantità ancora in portafoglio (valuta base)
    investito_base: float = 0.0       # somma di tutti gli acquisti (incl. spese)
    alloc_base: float = 0.0           # allocazione reale: nominale per i prodotti in %, altrimenti importo senza costi (valuta base)
    vendite_base: float = 0.0         # incassi da vendite e rimborsi
    reddito_base: float = 0.0
    realizzato_base: float = 0.0
    ultimo_reddito: str = ""
    flussi: list = field(default_factory=list)      # (date, importo_base)


def _replay(tx: list[dict], strumenti: dict, fino_a: str, ctx: Contesto) -> dict[str, Pos]:
    """Ricostruisce le posizioni con costo medio, cronologicamente, fino alla data indicata (inclusa)."""
    posizioni: dict[str, Pos] = {}
    for t in sorted(tx, key=lambda x: (x["data"], x.get("rif", ""))):
        if t["data"] > fino_a or t["tipo"] in TIPI_ESCLUSI:
            continue
        k = t.get("strumento") or ""
        if t["tipo"] in TIPI_COSTO and not k:
            k = "__COSTI__"
        if not k:
            ctx.avvisi.append(f"Movimento senza strumento ignorato: {t['data']} {t['tipo']} {t.get('titolo', '')}")
            continue
        p = posizioni.setdefault(k, Pos(k))
        cassa = ctx.conv(t["importo_cassa"], t["valuta"], t["data"])
        d = D(t["data"])
        if t["tipo"] == "acquisto":
            p.qty += float(t.get("quantita") or 0)
            p.costo_base += -cassa
            p.investito_base += -cassa
            if t.get("prezzo_in_percento") and t.get("quantita"):
                p.alloc_base += ctx.conv(float(t["quantita"]), t["valuta"], t["data"])
            else:
                p.alloc_base += -cassa - ctx.conv(float(t.get("commissione") or 0) + float(t.get("tasse") or 0), t["valuta"], t["data"])
            p.flussi.append((d, cassa))
        elif t["tipo"] in ("vendita", "rimborso"):
            qty_prima = p.qty
            venduta = float(t.get("quantita") or 0) or qty_prima
            frazione = min(venduta / qty_prima, 1.0) if qty_prima > 0 else 0.0
            costo_rimosso = p.costo_base * frazione
            p.costo_base -= costo_rimosso
            p.qty = max(qty_prima - venduta, 0.0)
            p.vendite_base += cassa
            p.realizzato_base += cassa - costo_rimosso
            p.flussi.append((d, cassa))
        elif t["tipo"] in TIPI_REDDITO:
            p.reddito_base += cassa
            p.ultimo_reddito = max(p.ultimo_reddito, t["data"])
            p.flussi.append((d, cassa))
        elif t["tipo"] in TIPI_COSTO:
            p.flussi.append((d, cassa))
            p.reddito_base += cassa          # per i costi la voce «reddito» è negativa: si legge in «costi»
        else:
            ctx.avvisi.append(f"Tipo movimento «{t['tipo']}» non gestito nel calcolo ({t['data']}).")
    return posizioni


def _cedola_maturata(s: dict, p: Pos, data: str, ctx: Contesto) -> float:
    """Cedola maturata e non ancora incassata (valuta base), calcolata pro rata dall'ultimo stacco."""
    c, f = s.get("cedola_annua_pct"), s.get("frequenza_cedola")
    if not c or not f or p.qty <= 0:
        return 0.0
    ultimo = p.ultimo_reddito or s.get("data_emissione") or ""
    if not ultimo:
        return 0.0
    ultimo_d, oggi = D(ultimo), D(data)
    prossimo = aggiungi_mesi(ultimo_d, 12 // f)
    while prossimo <= oggi:                       # staccato ma non ancora registrato nell'estratto
        ultimo_d, prossimo = prossimo, aggiungi_mesi(prossimo, 12 // f)
    durata = max((prossimo - ultimo_d).days, 1)
    quota = (oggi - ultimo_d).days / durata
    importo_val = p.qty * c / 100 / f * quota
    return ctx.conv(importo_val, s.get("valuta") or ctx.base, data)


def _valuta_posizione(s: dict, p: Pos, data: str, ctx: Contesto) -> dict:
    """Valore a una data (valuta base) secondo la regola dello strumento."""
    modo = s.get("valutazione", "mercato")
    ccy = s.get("valuta") or ctx.base
    out = {"valore": p.costo_base, "stato": "ok", "fonte": "", "prezzo": None, "maturato": 0.0}
    if p.qty <= 1e-9:
        out["valore"] = 0.0
        return out
    if modo == "nominale":              # prodotti strutturati: sempre al 100% del nominale; le cedole contano quando incassate
        out.update(valore=ctx.conv(p.qty, ccy, data), stato="al_nominale")
        return out
    if modo == "scadenza":
        out["maturato"] = _cedola_maturata(s, p, data, ctx)
        out["valore"] = p.costo_base
        out["stato"] = "al_costo"
        return out
    if modo == "manuale":
        navs = sorted([n for n in s.get("nav_manuale", []) if n["data"] <= data], key=lambda n: n["data"])
        if navs:
            nav = navs[-1]
            unit = nav["nav"] / 100 if s.get("prezzo_in_percento") else nav["nav"]
            out.update(valore=ctx.conv(p.qty * unit, ccy, data), stato="nav_manuale", prezzo=nav["nav"], fonte=f"prezzo inserito a mano del {nav['data']}")
            return out
        out["stato"] = "nav_mancante"
        ctx.avvisi.append(f"{s.get('nome') or s['chiave']}: nessun NAV inserito, valutato al costo.")
        return out
    r = ctx.prezzo(s, data)
    if r.get("prezzo") is None:
        out["stato"] = "prezzo_mancante"
        ctx.avvisi.append(f"{s.get('nome') or s['chiave']}: prezzo di mercato non disponibile al {data}, valutato al costo.")
        return out
    unit = r["prezzo"] / 100 if s.get("prezzo_in_percento") else r["prezzo"]
    out.update(valore=ctx.conv(p.qty * unit, ccy, data), stato=r.get("stato", "ok"), prezzo=r["prezzo"], fonte=r.get("fonte", ""))
    ctx.prezzi_usati[f"{s['chiave']}@{data}"] = {"prezzo": r["prezzo"], "fonte": r.get("fonte", ""), "stato": r.get("stato", "")}
    return out


def _blocco(s: dict) -> str:
    return "scadenza" if s.get("valutazione") in ("scadenza", "nominale") else "mercato"


def _metriche(v0: float, v1: float, flussi: list[tuple[date, float]], da: date, a: date, ctx: Contesto | None = None) -> dict:
    nel_periodo = [(d, x) for d, x in flussi if da < d <= a]
    pl = v1 - v0 + sum(x for _, x in nel_periodo)
    out = {"valore_inizio": v0, "valore_fine": v1, "pl": pl, "rendimento_periodo": modified_dietz(v0, v1, nel_periodo, da, a)}
    out["acquisti"] = -sum(x for _, x in nel_periodo if x < 0)
    out["incassi"] = sum(x for _, x in nel_periodo if x > 0)
    return out


def _xirr_da_inizio(tutti_flussi: list[tuple[date, float]], v1: float, a: date) -> Optional[float]:
    fl = [(d, x) for d, x in tutti_flussi if d <= a]
    if not fl:
        return None
    return xirr(fl + [(a, v1)])


def calcola(tx: list[dict], strumenti: dict[str, dict], da: str, a: str, ctx: Contesto,
            saldi_liquidita: dict[str, float] | None = None) -> dict:
    """Calcola l'intero report. `tx` sono le transazioni del cliente (già collegate a uno strumento)."""
    pos_a = _replay(tx, strumenti, a, ctx)
    da_orig = da
    primo_flusso = min((d for p_ in pos_a.values() for d, _ in p_.flussi), default=None)
    if primo_flusso and D(da) < primo_flusso:             # periodo che parte prima dell'inizio: coincide con «dall'inizio»
        da = (primo_flusso - timedelta(days=1)).isoformat()
    pos_0 = _replay(tx, strumenti, da, ctx)
    da_d, a_d = D(da), D(a)
    costi_key = "__COSTI__"

    righe, blocchi = [], {"scadenza": {"v0": 0.0, "v1": 0.0, "fl": [], "maturato": 0.0}, "mercato": {"v0": 0.0, "v1": 0.0, "fl": [], "maturato": 0.0}}
    costi = {"v0": 0.0, "fl": []}
    per_cat: dict[str, dict] = {}
    tutti_flussi: list[tuple[date, float]] = []

    for k, p in pos_a.items():
        if k == costi_key:
            costi["fl"] = p.flussi
            tutti_flussi += p.flussi
            continue
        s = strumenti.get(k)
        if s is None:
            ctx.avvisi.append(f"Strumento {k} non presente in anagrafica.")
            continue
        p0 = pos_0.get(k, Pos(k))
        val1, val0 = _valuta_posizione(s, p, a, ctx), _valuta_posizione(s, p0, da, ctx)
        bl = _blocco(s)
        b = blocchi[bl]
        b["v0"] += val0["valore"] + val0["maturato"]
        b["v1"] += val1["valore"] + val1["maturato"]
        b["maturato"] += val1["maturato"]
        b["maturato0"] = b.get("maturato0", 0.0) + val0["maturato"]
        b["fl"] += p.flussi
        pc = per_cat.setdefault(s.get("categoria") or "altro", {"v0": 0.0, "v1": 0.0, "fl": []})
        pc["v0"] += val0["valore"] + val0["maturato"]
        pc["v1"] += val1["valore"] + val1["maturato"]
        pc["fl"] += p.flussi
        tutti_flussi += p.flussi
        nel = [(d, x) for d, x in p.flussi if da_d < d <= a_d]
        reddito_periodo = _reddito_periodo(tx, k, da, a, ctx)
        val_tot = val1["valore"] + val1["maturato"]
        pl_pos = val_tot + sum(x for _, x in p.flussi)         # dall'inizio della posizione
        righe.append({
            "chiave": k, "nome": s.get("nome") or k, "isin": s.get("isin", ""), "simbolo": (s.get("simboli") or [""])[0],
            "categoria": s.get("categoria"), "sottocategoria": s.get("sottocategoria", ""), "blocco": bl,
            "valuta": s.get("valuta"), "quantita": p.qty, "costo": p.costo_base, "valore": val_tot,
            "maturato": val1["maturato"], "prezzo": val1["prezzo"], "prezzo_in_percento": s.get("prezzo_in_percento", False),
            "stato_prezzo": val1["stato"], "fonte_prezzo": val1["fonte"],
            "reddito_periodo": reddito_periodo, "reddito_totale": p.reddito_base,
            "pl_totale": pl_pos, "rendimento_totale": (pl_pos / p.investito_base) if p.investito_base > 0 else None,
            "investito": p.investito_base, "investito_alloc": p.alloc_base, "realizzato": p.realizzato_base,
            "scadenza": s.get("scadenza", ""), "cedola_annua_pct": s.get("cedola_annua_pct"),
            "barriera_pct": s.get("barriera_pct"), "protezione_pct": s.get("protezione_pct"),
            "rating": s.get("rating", ""), "confermato": s.get("confermato", False),
        })
        if p.qty <= 1e-9 and abs(p.reddito_base) < 1e-9 and not nel:
            righe.pop()

    metr = {}
    for nome_b, b in blocchi.items():
        metr[nome_b] = _metriche(b["v0"], b["v1"], b["fl"], da_d, a_d)
        metr[nome_b]["maturato"] = b["maturato"]
        metr[nome_b]["maturato0"] = b.get("maturato0", 0.0)
        metr[nome_b]["xirr"] = _xirr_da_inizio(b["fl"], b["v1"], a_d)
    metr_costi = {"pl": sum(x for d, x in costi["fl"] if da_d < d <= a_d)}

    # performance per asset class e contributo alla performance complessiva del periodo
    v0_t = blocchi["scadenza"]["v0"] + blocchi["mercato"]["v0"]
    v1_t = blocchi["scadenza"]["v1"] + blocchi["mercato"]["v1"]
    tot_m = _metriche(v0_t, v1_t, tutti_flussi, da_d, a_d)
    den = (tot_m["pl"] / tot_m["rendimento_periodo"]) if tot_m.get("rendimento_periodo") else None
    per_asset = {}
    for cat_, b_ in per_cat.items():
        m_ = _metriche(b_["v0"], b_["v1"], b_["fl"], da_d, a_d)
        m_["contributo"] = (m_["pl"] / den) if den else None
        per_asset[cat_] = m_
    if costi["fl"]:
        pl_c = metr_costi["pl"]
        per_asset["costi"] = {"pl": pl_c, "valore_inizio": 0.0, "valore_fine": 0.0, "rendimento_periodo": None, "contributo": (pl_c / den) if den else None}

    # liquidità (saldi dei conti a fine periodo)
    liquidita = 0.0
    dettaglio_liq = {}
    for ccy, saldo in (saldi_liquidita or {}).items():
        v = ctx.conv(saldo, ccy, a)
        dettaglio_liq[ccy] = {"saldo": saldo, "valore_base": v}
        liquidita += v

    v0_tot = blocchi["scadenza"]["v0"] + blocchi["mercato"]["v0"]
    v1_tot = blocchi["scadenza"]["v1"] + blocchi["mercato"]["v1"]
    fl_periodo_tot = [(d, x) for d, x in tutti_flussi if da_d < d <= a_d]
    totale = _metriche(v0_tot, v1_tot, tutti_flussi, da_d, a_d)
    # «acquisti» e «incassi» del totale riguardano solo i titoli: le spese di custodia restano nella loro voce
    totale["acquisti"] = sum(metr[b]["acquisti"] for b in metr)
    totale["incassi"] = sum(metr[b]["incassi"] for b in metr)
    totale["xirr"] = _xirr_da_inizio(tutti_flussi, v1_tot, a_d)
    primo = min((d for d, _ in tutti_flussi), default=None)
    if primo:
        totale["rendimento_dall_inizio"] = modified_dietz(0.0, v1_tot, [(d, x) for d, x in tutti_flussi if d <= a_d], primo - timedelta(days=1), a_d)
        totale["data_inizio"] = primo.isoformat()
    totale["costi_periodo"] = metr_costi["pl"]
    # performance «nominale»: risultato in valore assoluto (valuta base), oltre alla percentuale
    totale["pl_dall_inizio"] = v1_tot + sum(x for d, x in tutti_flussi if d <= a_d)

    # allocazioni (valore a fine periodo)
    allocazione, valute, settori, aree = {}, {}, {}, {}
    for r in righe:
        if r["valore"] <= 0:
            continue
        allocazione[r["categoria"]] = allocazione.get(r["categoria"], 0.0) + r["valore"]
        valute[r["valuta"] or ctx.base] = valute.get(r["valuta"] or ctx.base, 0.0) + r["valore"]
        s = strumenti[r["chiave"]]
        for nome, peso in (s.get("settori") or {}).items():
            settori[nome] = settori.get(nome, 0.0) + r["valore"] * peso
        for nome, peso in (s.get("aree") or {}).items():
            aree[nome] = aree.get(nome, 0.0) + r["valore"] * peso
        if not (s.get("settori") and s.get("aree")) and r["categoria"] != "liquidita":
            settori["Non classificato"] = settori.get("Non classificato", 0.0) + r["valore"] * (1 - sum((s.get("settori") or {}).values()))
            aree["Non classificato"] = aree.get("Non classificato", 0.0) + r["valore"] * (1 - sum((s.get("aree") or {}).values()))
    if liquidita:
        allocazione["liquidita"] = liquidita
        for ccy, d in dettaglio_liq.items():
            valute[ccy] = valute.get(ccy, 0.0) + d["valore_base"]
        settori["Liquidità"] = liquidita
        aree["Liquidità"] = liquidita
    for dct in (settori, aree):
        for k in [k for k, v in dct.items() if abs(v) < 1e-6]:
            dct.pop(k)

    # attività del periodo (per la tabella movimenti)
    attivita = [t for t in sorted(tx, key=lambda x: x["data"]) if da < t["data"] <= a and t["tipo"] not in ("cambio",)]

    barriere = []
    sottostanti = []
    attese = []
    for r in righe:
        s = strumenti[r["chiave"]]
        if r["quantita"] <= 0:
            continue
        if s.get("valutazione") in ("scadenza", "nominale"):
            att = rendimento_atteso(s, pos_a[r["chiave"]], tx, a, ctx)
            if att:
                attese.append({"chiave": r["chiave"], "nome": r["nome"], **att})
        if s.get("categoria") == "strutturato" and s.get("sottostanti"):
            ss = stato_sottostanti(s, a, ctx)
            sottostanti.append({"chiave": r["chiave"], "nome": r["nome"], **ss})
        if s.get("barriera_pct") and s.get("sottostanti"):
            br = rischio_barriera(s, a, ctx)
            if br:
                barriere.append({"chiave": r["chiave"], "nome": r["nome"], "osservazione": s.get("osservazione", ""), **br})

    # posizioni dedotte dai redditi ma senza acquisto registrato
    for t in tx:
        k = t.get("strumento")
        if t["tipo"] in TIPI_REDDITO and k and t["data"] <= a and (k not in pos_a or pos_a[k].investito_base == 0) and float(t.get("quantita") or 0) > 0:
            msg = f"«{strumenti.get(k, {}).get('nome') or k}» ha proventi ma nessun acquisto registrato: inserire l'acquisto (data e prezzo originari) per calcolare la performance."
            if msg not in ctx.avvisi:
                ctx.avvisi.append(msg)

    ris = {
        "periodo": {"da": da_orig, "a": a, "base": ctx.base, "da_effettivo": da},
        "totale": totale, "blocchi": metr, "per_asset": per_asset, "posizioni": sorted(righe, key=lambda r: (r["categoria"] or "", -r["valore"])),
        "liquidita": {"totale": liquidita, "dettaglio": dettaglio_liq},
        "valore_portafoglio": v1_tot + liquidita, "valore_titoli": v1_tot,
        "allocazione": allocazione, "valute": valute, "settori": settori, "aree": aree,
        "attivita": attivita, "barriere": barriere, "sottostanti": sottostanti, "attese": attese, "costi": metr_costi,
        "avvisi": list(dict.fromkeys(ctx.avvisi)), "prezzi_usati": ctx.prezzi_usati,
    }
    from core import riepiloghi
    ris.update(riepiloghi.calcola_extra(tx, strumenti, pos_a, ris, ctx, da, a))
    ris["avvisi"] = list(dict.fromkeys(ctx.avvisi))
    return ris


def _reddito_periodo(tx: list[dict], chiave: str, da: str, a: str, ctx: Contesto) -> float:
    tot = 0.0
    for t in tx:
        if t.get("strumento") == chiave and t["tipo"] in TIPI_REDDITO and da < t["data"] <= a:
            tot += ctx.conv(t["importo_cassa"], t["valuta"], t["data"])
    return tot


def rendimento_atteso(s: dict, p: Pos, tx: list[dict], a: str, ctx: Contesto) -> Optional[dict]:
    """Rendimento a scadenza. Scenario base: cedole regolari e rimborso del nominale (o della protezione, per i prodotti a capitale protetto).

    Le cedole dei BRC sono INCONDIZIONATE: si incassano anche se la barriera viene toccata (la barriera riguarda solo il rimborso del capitale).
    Vengono mostrati anche gli scenari: barriera toccata (BRC) o rebate (CPN / Shark con knock-out)."""
    if not s.get("scadenza") or p.qty <= 0 or p.investito_base <= 0:
        return {"completo": False, "motivo": "scadenza o acquisto non registrati"}
    f, c = s.get("frequenza_cedola"), s.get("cedola_annua_pct")
    scad, a_d = D(s["scadenza"]), D(a)
    if scad <= a_d:
        return {"completo": False, "motivo": "scadenza già passata: registrare il rimborso"}
    ccy = s.get("valuta") or ctx.base
    fx_ora = ctx.conv(1.0, ccy, a)
    storici = [(d, x) for d, x in p.flussi if d <= a_d]
    futuri = []
    cedole_future = 0.0
    if c and f:
        ultimo = D(p.ultimo_reddito) if p.ultimo_reddito else (D(s["data_emissione"]) if s.get("data_emissione") else None)
        if ultimo:
            # cedole che sarebbero già dovute ma non compaiono negli estratti caricati: non si ignorano in silenzio (l'avviso è per l'utente, non per il cliente)
            attesa = aggiungi_mesi(ultimo, 12 // f)
            while attesa <= a_d:
                msg = (f"{s.get('nome') or s['chiave']}: la cedola attesa del {attesa.strftime('%d.%m.%Y')} non risulta registrata "
                       f"(registrala con «Registra transazione», oppure controlla frequenza e data di emissione): il rendimento atteso è sottostimato.")
                if msg not in ctx.avvisi:
                    ctx.avvisi.append(msg)
                attesa = aggiungi_mesi(attesa, 12 // f)
            n = 1
            while True:
                dt = aggiungi_mesi(ultimo, n * (12 // f))
                if dt > scad:
                    break
                if dt > a_d:
                    imp = p.qty * c / 100 / f * fx_ora
                    futuri.append((dt, imp)); cedole_future += imp
                n += 1
    outflow = -sum(x for _, x in storici if x < 0)

    def scenario(nome, rimborso_pct):
        rimb = p.qty * fx_ora * rimborso_pct / 100.0
        tutti = storici + futuri + [(scad, rimb)]
        inflow = sum(x for _, x in tutti if x > 0)
        return {"nome": nome, "rimborso_pct": rimborso_pct, "rimborso": rimb,
                "rendimento": (inflow - outflow) / outflow if outflow > 0 else None, "rendimento_annuo": xirr(tutti)}

    prot = s.get("protezione_pct")
    base_pct = float(prot) if prot else 100.0
    scenari = [scenario("Scenario base: rimborso a scadenza" if not prot else f"Capitale protetto al {base_pct:g}%: rimborso minimo", base_pct)]
    if s.get("rebate_pct"):
        scenari.append(scenario(f"Barriera superiore toccata: rebate al {float(s['rebate_pct']):g}%", float(s["rebate_pct"])))
    if s.get("barriera_pct") and not prot:
        scenari.append(scenario(f"Barriera violata e sottostante peggiore a fine vita al livello della barriera ({float(s['barriera_pct']):g}%)", float(s["barriera_pct"])))
    b = scenari[0]
    return {
        "completo": True, "scadenza": s["scadenza"], "cedole_future": cedole_future, "rimborso_atteso": b["rimborso"], "rimborso_pct": base_pct,
        "rendimento_totale_atteso": b["rendimento"], "rendimento_annuo_atteso": b["rendimento_annuo"], "cedole_incassate": p.reddito_base,
        "cedola_maturata": _cedola_maturata(s, p, a, ctx), "scenari": scenari, "cedole_incondizionate": True,
    }


def stato_sottostanti(s: dict, data: str, ctx: Contesto) -> dict:
    """Per ogni sottostante: livello iniziale, livello attuale, performance e distanza dalla barriera (se c'è)."""
    barriera = float(s["barriera_pct"]) / 100 if s.get("barriera_pct") else None
    dettaglio = []
    for u in s.get("sottostanti", []):
        iniz = u.get("livello_iniziale")
        spot = ctx.spot(u.get("ticker", ""), data) if u.get("ticker") else None
        perf = (spot / iniz) if (iniz and spot is not None) else None
        dist = ((perf - barriera) / perf) if (perf and barriera and perf > 0) else None
        dettaglio.append({"nome": u.get("nome") or u.get("ticker"), "ticker": u.get("ticker", ""), "perf": perf, "livello_iniziale": iniz, "spot": spot, "distanza_barriera": dist})
    return {"dettaglio": dettaglio, "barriera": barriera, "completo": bool(dettaglio) and all(d["perf"] is not None for d in dettaglio)}


def livello_avviso(buffer: float) -> str:
    """verde > 20% · giallo 20–10% · arancio 10–5% · rosso < 5% (o barriera raggiunta)."""
    if buffer >= SOGLIA_VERDE:
        return "verde"
    if buffer >= SOGLIA_GIALLO:
        return "giallo"
    if buffer >= SOGLIA_ARANCIO:
        return "arancio"
    return "rosso"


def rischio_barriera(s: dict, data: str, ctx: Contesto) -> Optional[dict]:
    """Distanza di sicurezza dalla barriera: di quanto può ancora scendere il sottostante peggiore.

    buffer = (perf_peggiore − barriera) / perf_peggiore, con perf = prezzo attuale / livello iniziale.
    """
    barriera = float(s["barriera_pct"]) / 100
    dettaglio = []
    for u in s.get("sottostanti", []):
        iniz = u.get("livello_iniziale")
        spot = ctx.spot(u.get("ticker", ""), data) if u.get("ticker") else None
        if not iniz or spot is None:
            dettaglio.append({"nome": u.get("nome") or u.get("ticker"), "perf": None, "livello_iniziale": iniz, "spot": spot})
            continue
        dettaglio.append({"nome": u.get("nome") or u.get("ticker"), "perf": spot / iniz, "livello_iniziale": iniz, "spot": spot})
    valide = [d for d in dettaglio if d["perf"] is not None]
    if not valide or len(valide) < len(dettaglio):
        return {"completo": False, "dettaglio": dettaglio, "motivo": "livelli iniziali o prezzi dei sottostanti mancanti"}
    peggiore = min(valide, key=lambda d: d["perf"])
    buffer = (peggiore["perf"] - barriera) / peggiore["perf"] if peggiore["perf"] > 0 else -1.0
    return {"completo": True, "peggiore": peggiore["nome"], "perf_peggiore": peggiore["perf"], "barriera": barriera,
            "buffer": buffer, "semaforo": livello_avviso(buffer), "dettaglio": dettaglio}
