"""Riepiloghi per il report: proventi incassati, cedole attese, strumenti attivi e chiusi, costi, riconciliazione di tutti i movimenti."""

from __future__ import annotations

from datetime import date

from core.performance import D, TIPI_COSTO, TIPI_ESCLUSI, TIPI_REDDITO, aggiungi_mesi

# gruppo di presentazione di ogni tipo di movimento: OGNI voce dell'estratto deve finire in una di queste righe
GRUPPI = [
    ("acquisto", "Acquisti di titoli (importo investito)"), ("vendita", "Vendite di titoli"), ("rimborso", "Rimborsi a scadenza"),
    ("cedola", "Cedole incassate"), ("dividendo", "Dividendi incassati"), ("premio_opzione", "Premi di opzione incassati"),
    ("interesse", "Interessi"), ("commissioni", "Commissioni e spese di acquisto/vendita"), ("costo_custodia", "Diritti di custodia"),
    ("costo", "Altre spese bancarie"), ("imposta", "Imposte"), ("cambio", "Cambi di valuta"),
    ("deposito", "Versamenti sul conto"), ("prelievo", "Prelievi dal conto"), ("trasferimento", "Trasferimenti tra conti propri"), ("altro", "Altri movimenti"),
]
ETICHETTA = dict(GRUPPI)


def _conv(ctx, importo, valuta, data):
    try:
        return ctx.conv(importo, valuta, data)
    except Exception:
        return 0.0


def calcola_extra(tx: list[dict], strumenti: dict, pos_a: dict, ris: dict, ctx, da: str, a: str) -> dict:
    nomi = {k: (s.get("nome") or k) for k, s in strumenti.items()}

    # ── proventi incassati nel periodo (per tipo, mese, prodotto) ──
    proventi = []
    for t in tx:
        if da < t["data"] <= a and t["tipo"] in TIPI_REDDITO:
            proventi.append({"data": t["data"], "tipo": t["tipo"], "strumento": t.get("strumento", ""), "nome": nomi.get(t.get("strumento"), t.get("titolo", "")) or "Interessi sul conto",
                             "valuta": t["valuta"], "importo": t["importo_cassa"], "importo_base": _conv(ctx, t["importo_cassa"], t["valuta"], t["data"])})
    proventi.sort(key=lambda x: x["data"])

    # ── riconciliazione di tutti i movimenti del periodo ──
    rico: dict[str, dict] = {k: {"n": 0, "base": 0.0} for k, _ in GRUPPI}
    for t in tx:
        if not (da < t["data"] <= a):
            continue
        tipo = t["tipo"] if t["tipo"] in rico else "altro"
        cassa = _conv(ctx, t["importo_cassa"], t["valuta"], t["data"])
        comm = _conv(ctx, float(t.get("commissione") or 0) + float(t.get("tasse") or 0), t["valuta"], t["data"])
        if tipo in ("acquisto", "vendita") and comm:
            # la cassa comprende commissioni e tasse: si separano, per mostrarle come costo (il totale non cambia)
            rico["commissioni"]["n"] += 1
            rico["commissioni"]["base"] -= comm
            cassa += comm
        rico[tipo]["n"] += 1
        rico[tipo]["base"] += cassa
    totale_mov = sum(1 for t in tx if da < t["data"] <= a)

    costi = {"commissioni": -rico["commissioni"]["base"] + 0.0,
             "custodia": -rico["costo_custodia"]["base"] + 0.0, "spese": -rico["costo"]["base"] + 0.0, "imposte": -rico["imposta"]["base"] + 0.0}
    costi["totale"] = sum(costi.values())

    # ── strumenti attivi e chiusi (da sempre, fino alla data del report) ──
    attivi, chiusi = [], []
    per_k: dict[str, list] = {}
    for t in sorted(tx, key=lambda x: x["data"]):
        if t["data"] <= a and t.get("strumento") and t["tipo"] not in TIPI_ESCLUSI:
            per_k.setdefault(t["strumento"], []).append(t)
    for k, mov in per_k.items():
        s = strumenti.get(k)
        if not s or not any(m["tipo"] == "acquisto" for m in mov):
            continue
        investito = sum(-_conv(ctx, m["importo_cassa"], m["valuta"], m["data"]) for m in mov if m["tipo"] == "acquisto")
        alloc = sum((_conv(ctx, float(m["quantita"]), m["valuta"], m["data"]) if (m.get("prezzo_in_percento") and m.get("quantita"))
                     else -_conv(ctx, m["importo_cassa"] + float(m.get("commissione") or 0) + float(m.get("tasse") or 0), m["valuta"], m["data"]))
                    for m in mov if m["tipo"] == "acquisto")
        incassi = sum(_conv(ctx, m["importo_cassa"], m["valuta"], m["data"]) for m in mov if m["tipo"] in ("vendita", "rimborso"))
        redditi = sum(_conv(ctx, m["importo_cassa"], m["valuta"], m["data"]) for m in mov if m["tipo"] in TIPI_REDDITO)
        costi_k = sum(_conv(ctx, m["importo_cassa"], m["valuta"], m["data"]) for m in mov if m["tipo"] in TIPI_COSTO)
        apertura = next(m["data"] for m in mov if m["tipo"] == "acquisto")
        riga = {"chiave": k, "nome": nomi[k], "categoria": s.get("categoria"), "sottocategoria": s.get("sottocategoria", ""), "valuta": s.get("valuta"),
                "isin": s.get("isin", ""), "apertura": apertura, "scadenza": s.get("scadenza", ""), "cedola_annua_pct": s.get("cedola_annua_pct"),
                "investito": investito, "investito_alloc": alloc, "redditi": redditi, "incassi": incassi, "costi": costi_k, "quantita": pos_a[k].qty if k in pos_a else 0.0}
        if riga["quantita"] > 1e-9:
            prow = next((r for r in ris["posizioni"] if r["chiave"] == k), None)
            val = prow["valore"] if prow else investito
            riga["prezzo"] = prow["prezzo"] if prow else None
            riga["prezzo_pct"] = bool(prow["prezzo_in_percento"]) if prow else False
            riga["valore"] = val
            riga["risultato"] = val + incassi + redditi + costi_k - investito
            attivi.append(riga)
        else:
            chius = max((m["data"] for m in mov if m["tipo"] in ("vendita", "rimborso")), default=mov[-1]["data"])
            riga["chiusura"] = chius
            riga["risultato"] = incassi + redditi + costi_k - investito
            riga["rendimento"] = riga["risultato"] / investito if investito > 0 else None
            giorni = (D(chius) - D(apertura)).days
            riga["rendimento_annuo"] = ((1 + riga["rendimento"]) ** (365 / giorni) - 1) if riga["rendimento"] is not None and giorni >= 30 and riga["rendimento"] > -1 else None
            chiusi.append(riga)
    for r in attivi:
        r["rendimento"] = r["risultato"] / r["investito"] if r["investito"] > 0 else None
    attivi.sort(key=lambda r: (r["scadenza"] or "9999", r["nome"]))
    chiusi.sort(key=lambda r: r["chiusura"], reverse=True)

    # ── cedole attese nei 12 mesi successivi ──
    future, non_calc = [], []
    a_d = D(a)
    limite = aggiungi_mesi(a_d, 12)
    for k, p in pos_a.items():
        s = strumenti.get(k)
        if not s or p.qty <= 1e-9 or not s.get("cedola_annua_pct") or not s.get("frequenza_cedola"):
            continue
        f = int(s["frequenza_cedola"])
        ultimo = p.ultimo_reddito or s.get("data_emissione") or ""
        if not ultimo:
            non_calc.append(nomi[k])
            continue
        scad = D(s["scadenza"]) if s.get("scadenza") else limite
        prossima = aggiungi_mesi(D(ultimo), 12 // f)
        while prossima <= a_d:
            prossima = aggiungi_mesi(prossima, 12 // f)
        while prossima <= min(limite, scad):
            if s.get("categoria") in ("etf_azioni", "opzione"):          # azioni/ETF: la percentuale è un rendimento sul costo, non sul nominale
                imp_base = p.costo_base * s["cedola_annua_pct"] / 100 / f
                imp = imp_base / (_conv(ctx, 1.0, s.get("valuta") or ctx.base, a) or 1.0)
            else:
                imp = p.qty * s["cedola_annua_pct"] / 100 / f
                imp_base = _conv(ctx, imp, s.get("valuta") or ctx.base, a)
            future.append({"data": prossima.isoformat(), "nome": nomi[k], "valuta": s.get("valuta"), "importo": imp, "importo_base": imp_base,
                           "incondizionata": s.get("sottocategoria") in ("Barrier Reverse Convertible", "Capital Protection Note", "Deposito a termine") or s.get("categoria") in ("obbligazione", "deposito")})
            prossima = aggiungi_mesi(prossima, 12 // f)
    future.sort(key=lambda x: x["data"])

    return {"proventi": proventi, "riconciliazione": {"righe": rico, "movimenti_totali": totale_mov}, "costi_dettaglio": costi,
            "attivi": attivi, "chiusi": chiusi, "cedole_future": future, "cedole_future_non_calcolabili": non_calc}
