"""Strategia di un portafoglio: prodotti proposti con pesi, prezzi e quantità ideali; poi, a esecuzione avvenuta, valori reali e creazione del portafoglio."""

from __future__ import annotations

import urllib.parse
import uuid
from datetime import date

from core.config import CATEGORIE

TIPI_INCASSO = {"cedola": "Cedola", "interesse": "Interessi", "dividendo": "Dividendo / distribuzione", "premio_opzione": "Premio opzione"}
TIPI_COSTO_UI = {"costo_custodia": "Diritti di custodia / deposito", "costo": "Spese bancarie / commissioni", "imposta": "Imposte"}
# tutte le transazioni che si possono registrare a mano (etichetta, serve un prodotto?)
TIPI_TRANSAZIONE = {**{k: (v, True) for k, v in TIPI_INCASSO.items()}, "rimborso": ("Rimborso a scadenza", True), "vendita": ("Vendita", True),
                    **{k: (v, False) for k, v in TIPI_COSTO_UI.items()}}


def lordo(quantita: float, prezzo: float, in_percento: bool) -> float:
    """Controvalore: quantità (o nominale) × prezzo; il prezzo è in % del nominale per obbligazioni e strutturati."""
    return (quantita or 0.0) * (prezzo or 0.0) / (100.0 if in_percento else 1.0)


def quantita_da_investito(investito: float, prezzo: float, in_percento: bool) -> float:
    """Per obbligazioni e strutturati (prezzo in %) l'importo investito è il NOMINALE: il prezzo dice solo quanto si paga (nominale × prezzo).
    Per azioni, ETF e il resto è l'importo diviso il prezzo unitario."""
    if in_percento:
        return investito
    return investito / prezzo if prezzo else 0.0


def allocazione(quantita: float, prezzo: float, in_percento: bool) -> float:
    """Importo investito (allocazione reale, senza costi): nominale per i prodotti in %, altrimenti quantità × prezzo."""
    return quantita if in_percento else lordo(quantita, prezzo, False)


def cambio(pf: dict, valuta: str, base: str, cerca=None) -> tuple[float, bool]:
    """(tasso, affidabile). Priorità: tasso inserito a mano, poi mercato (se disponibile)."""
    if not valuta or valuta == base:
        return 1.0, True
    man = (pf.get("cambi") or {}).get(valuta)
    if man:
        return float(man), True
    if cerca:
        try:
            r = cerca(valuta, base)
            if r:
                pf.setdefault("cambi_auto", {})[valuta] = {"tasso": float(r), "data": date.today().isoformat()}      # ultimo cambio del giorno noto
                return float(r), True
        except Exception:
            pass
    ult = (pf.get("cambi_auto") or {}).get(valuta)
    if ult and ult.get("tasso"):                      # fonte momentaneamente non raggiungibile: si usa l'ultimo cambio automatico
        return float(ult["tasso"]), True
    return 1.0, False


# ───────────────────────── il portafoglio È la strategia: ogni acquisto è una riga ───────────────────────
def aggiungi_acquisto(cliente: dict, pf: dict, reg, chiave: str, data: str, prezzo: float, commissioni: float = 0.0, *,
                      investito: float | None = None, quantita: float | None = None) -> dict:
    """Registra un acquisto nel portafoglio. Si dà l'importo investito O la quantità/nominale: l'altro si calcola dal prezzo."""
    s = reg.strumenti[chiave]
    pct = bool(s.get("prezzo_in_percento"))
    if quantita is None:
        quantita = quantita_da_investito(investito or 0.0, prezzo, pct)
    lord = lordo(quantita, prezzo, pct)
    tx = {"id": f"strategia:{pf['id']}:{uuid.uuid4().hex[:8]}", "data": data, "data_valuta": data, "tipo": "acquisto", "titolo": f"Acquisto {s['nome']}", "valuta": s["valuta"],
          "importo_cassa": -(lord + commissioni), "quantita": quantita, "prezzo": prezzo, "prezzo_in_percento": pct, "importo_lordo": lord, "commissione": commissioni,
          "tasse": 0.0, "rif": "", "banca": "", "conto": "", "strumento": chiave, "fonte": "strategia", "portafoglio": pf["id"]}
    cliente["transazioni"].append(tx)
    pf["stato"] = "attivo"
    if s.get("valutazione") == "manuale" and not s.get("nav_manuale"):
        s["nav_manuale"] = [{"data": data, "nav": prezzo}]            # valore iniziale = prezzo d'acquisto, poi lo aggiorni tu
    return tx


def modifica_acquisto(tx: dict, s: dict, *, data=None, prezzo=None, quantita=None, investito=None, commissioni=None):
    """Aggiorna un acquisto. Se cambia l'investito si ricalcola la quantità; altrimenti l'investito segue quantità × prezzo."""
    pct = bool(s.get("prezzo_in_percento"))
    prezzo = tx.get("prezzo") if prezzo is None else prezzo
    comm = (tx.get("commissione") or 0.0) if commissioni is None else commissioni
    if investito is not None and quantita is None:
        quantita = quantita_da_investito(investito, prezzo, pct)
    quantita = tx.get("quantita") if quantita is None else quantita
    lord = lordo(quantita, prezzo, pct)
    tx.update(prezzo=prezzo, quantita=quantita, prezzo_in_percento=pct, importo_lordo=lord, commissione=comm, tasse=0.0, importo_cassa=-(lord + comm))
    if data:
        tx["data"] = tx["data_valuta"] = data


def registra_incasso(cliente: dict, pf: dict, reg, chiave: str, tipo: str, data: str, importo: float, imposta: float = 0.0, nota: str = "") -> None:
    s = reg.strumenti[chiave]
    base = {"data_valuta": data, "valuta": s["valuta"], "quantita": None, "prezzo": None, "prezzo_in_percento": False, "importo_lordo": None, "commissione": 0.0, "tasse": 0.0,
            "rif": "", "banca": "", "conto": "", "strumento": chiave, "fonte": "manuale", "portafoglio": pf["id"]}
    cliente["transazioni"].append({**base, "id": f"manuale:{uuid.uuid4().hex[:10]}", "data": data, "tipo": tipo, "titolo": f"{TIPI_INCASSO.get(tipo, tipo)} {s['nome']}" + (f" ({nota})" if nota else ""), "importo_cassa": importo})
    if imposta:
        cliente["transazioni"].append({**base, "id": f"manuale:{uuid.uuid4().hex[:10]}", "data": data, "tipo": "imposta", "titolo": f"Imposta su {TIPI_INCASSO.get(tipo, tipo).lower()} {s['nome']}", "importo_cassa": -abs(imposta)})


def registra_costo(cliente: dict, pf: dict, tipo: str, data: str, importo: float, valuta: str, descrizione: str = "", chiave: str = "", reg=None) -> None:
    """Costo del portafoglio (custodia, spese bancarie, imposte) o, se si indica il prodotto, costo di quel prodotto."""
    nome = ""
    if chiave and reg is not None and chiave in reg.strumenti:
        nome = reg.strumenti[chiave]["nome"]
    cliente["transazioni"].append({"id": f"manuale:{uuid.uuid4().hex[:10]}", "data": data, "data_valuta": data, "tipo": tipo,
                                   "titolo": descrizione or (f"{TIPI_COSTO_UI.get(tipo, tipo)} {nome}".strip()),
                                   "valuta": valuta, "importo_cassa": -abs(importo), "quantita": None, "prezzo": None, "prezzo_in_percento": False, "importo_lordo": None,
                                   "commissione": 0.0, "tasse": 0.0, "rif": "", "banca": "", "conto": "", "strumento": chiave, "fonte": "manuale", "portafoglio": pf["id"]})


def registra_rimborso_o_vendita(cliente: dict, pf: dict, reg, chiave: str, tipo: str, data: str, importo: float, quantita: float | None = None, nota: str = "") -> None:
    """Rimborso a scadenza o vendita: entra in cassa `importo` e si chiude la quantità indicata (tutta, se non specificata).
    Il rimborso riguarda il nominale investito: ciò che si è pagato in acquisto non viene restituito (conta solo la differenza)."""
    s = reg.strumenti[chiave]
    netto = sum((t.get("quantita") or 0) * (1 if t["tipo"] == "acquisto" else -1) for t in cliente["transazioni"]
                if t.get("strumento") == chiave and t["tipo"] in ("acquisto", "vendita", "rimborso") and t.get("portafoglio") == pf["id"])
    q = netto if quantita is None else quantita
    cliente["transazioni"].append({"id": f"manuale:{uuid.uuid4().hex[:10]}", "data": data, "data_valuta": data, "tipo": tipo, "valuta": s["valuta"],
                                   "titolo": f"{'Rimborso' if tipo == 'rimborso' else 'Vendita'} {s['nome']}" + (f" ({nota})" if nota else ""), "importo_cassa": abs(importo),
                                   "quantita": q, "prezzo": None, "prezzo_in_percento": s.get("prezzo_in_percento", False), "importo_lordo": abs(importo), "commissione": 0.0, "tasse": 0.0,
                                   "rif": "", "banca": "", "conto": "", "strumento": chiave, "fonte": "manuale", "portafoglio": pf["id"]})


def aggiungi_liquidita(cliente: dict, pf: dict, reg, importo: float, data: str, sostituisci_auto: bool = True) -> str:
    """Crea (o aggiorna) la riga «Liquidità» del portafoglio."""
    valuta = pf["valuta"]
    k = reg.assicura("", f"LIQ{valuta}", f"Liquidità {valuta}", valuta, False)
    s = reg.strumenti[k]
    s.update(categoria="liquidita", sottocategoria="Conto / liquidità", valutazione="scadenza", prezzo_in_percento=False, confermato=True, settori={"Liquidità": 1.0}, aree={},
             classificazione_manuale=True, classificazione_auto="liquidità")
    if sostituisci_auto:
        cliente["transazioni"] = [t for t in cliente["transazioni"] if not (t.get("strumento") == k and t.get("portafoglio") == pf["id"] and t.get("fonte") == "liquidita_auto")]
    tx = aggiungi_acquisto(cliente, pf, reg, k, data, 1.0, 0.0, quantita=importo)
    tx["fonte"] = "liquidita_auto"
    return k


def _primo_anno(attive: list[dict]) -> dict:
    """Pagamenti previsti nei 12 mesi dalla data della strategia (la più recente fra oggi e gli acquisti), da cedola, frequenza ed emissione/acquisto."""
    from core.performance import D, aggiungi_mesi
    if not attive:
        return {"righe": [], "totale": 0.0}
    inizio = max(D(x["data"]) for x in attive) if all(x["data"] > date.today().isoformat() for x in attive) else date.today()
    fine = aggiungi_mesi(inizio, 12)
    righe = []
    for x in attive:
        s_f = x.get("frequenza_cedola")
        if not (x.get("cedola_annua_pct") and s_f):
            continue
        passo = 12 // int(s_f)
        ancora = D(x.get("data_emissione") or x["data"])
        d = ancora
        i = 0
        while d <= inizio or d.isoformat() <= x["data"]:
            i += 1
            d = aggiungi_mesi(ancora, passo * i)
        scad = D(x["scadenza"]) if x.get("scadenza") else fine
        while d <= min(fine, scad):
            if x["categoria"] == "etf_azioni":
                imp = x["importo"] * x["cedola_annua_pct"] / 100 / int(s_f)
            else:
                imp = x["quantita"] * x["cedola_annua_pct"] / 100 / int(s_f)
            righe.append({"data": d.isoformat(), "nome": x["nome"], "importo": imp, "importo_base": imp * x["tasso"]})
            i += 1
            d = aggiungi_mesi(ancora, passo * i)
    righe.sort(key=lambda r: (r["data"], r["nome"]))
    return {"righe": righe, "totale": sum(r["importo_base"] for r in righe), "da": inizio.isoformat(), "a": fine.isoformat()}


def calcola(cliente: dict, pf: dict, reg, cerca=None) -> dict:
    """Riepilogo del portafoglio a costo: una riga per acquisto, pesi, esposizioni, reddito cedolare atteso."""
    from core import dati
    v = dati.vista_portafoglio(cliente, pf["id"])
    base = pf["valuta"]
    from core.scadenze import rimborsi_automatici
    auto, _ = rimborsi_automatici(v["transazioni"], reg.strumenti, date.today().isoformat())
    netto: dict[str, float] = {}
    for t in v["transazioni"] + auto:
        if t["tipo"] in ("acquisto", "vendita", "rimborso") and t.get("strumento"):
            seg = 1 if t["tipo"] == "acquisto" else -1
            netto[t["strumento"]] = netto.get(t["strumento"], 0.0) + seg * (t.get("quantita") or 0.0)
    righe, avvisi = [], []
    for t in sorted(v["transazioni"], key=lambda x: x["data"]):
        s = reg.strumenti.get(t.get("strumento"))
        if t["tipo"] != "acquisto" or not s:
            continue
        comm = (t.get("commissione") or 0.0) + (t.get("tasse") or 0.0)
        pagato = t.get("importo_lordo") if t.get("importo_lordo") is not None else -t["importo_cassa"] - comm
        inv = allocazione(t.get("quantita") or 0.0, t.get("prezzo") or 0.0, bool(s.get("prezzo_in_percento"))) if t.get("prezzo") else pagato
        tasso, ok = cambio(pf, s.get("valuta", base), base, cerca)
        if not ok:
            m = f"Cambio {s.get('valuta')}→{base} non disponibile: importi non convertiti. Inseriscilo a mano."
            if m not in avvisi:
                avvisi.append(m)
        righe.append({"id": t["id"], "strumento": t["strumento"], "nome": s["nome"], "isin": s.get("isin", ""), "ticker": s.get("ticker_mercato") or s.get("ticker") or "", "categoria": s.get("categoria"), "sottocategoria": s.get("sottocategoria", ""),
                      "valuta": s.get("valuta", base), "data": t["data"], "quantita": t.get("quantita") or 0.0, "prezzo": t.get("prezzo"), "commissioni": comm, "importo": inv, "pagato": pagato,
                      "importo_base": inv * tasso, "tasso": tasso, "attivo": netto.get(t["strumento"], 0.0) > 1e-9, "fonte": t.get("fonte", ""),
                      "cedola_annua_pct": s.get("cedola_annua_pct"), "scadenza": s.get("scadenza", ""), "barriera_pct": s.get("barriera_pct"), "protezione_pct": s.get("protezione_pct"),
                      "frequenza_cedola": s.get("frequenza_cedola"), "data_emissione": s.get("data_emissione", ""), "sottostanti": s.get("sottostanti", []), "settori": s.get("settori") or {}, "aree": s.get("aree") or {}, "prezzo_in_percento": bool(s.get("prezzo_in_percento"))})
    attive = [x for x in righe if x["attivo"]]
    tot = sum(x["importo_base"] for x in attive)
    for x in righe:
        x["peso_eff_pct"] = 100.0 * x["importo_base"] / tot if (tot and x["attivo"]) else 0.0
    alloc, valute, settori, aree = {}, {}, {}, {}
    reddito = 0.0
    for x in attive:
        alloc[x["categoria"]] = alloc.get(x["categoria"], 0.0) + x["importo_base"]
        valute[x["valuta"]] = valute.get(x["valuta"], 0.0) + x["importo_base"]
        for dest, pesi in ((settori, x["settori"]), (aree, x["aree"])):
            if pesi:
                for k, w in pesi.items():
                    dest[k] = dest.get(k, 0.0) + x["importo_base"] * w
            else:
                dest["Non classificato"] = dest.get("Non classificato", 0.0) + x["importo_base"]
        if x["cedola_annua_pct"]:
            reddito += x["importo"] * x["tasso"] * x["cedola_annua_pct"] / 100.0
    comm = sum(x["commissioni"] * x["tasso"] for x in attive)
    primo_anno = _primo_anno(attive)
    investito_titoli = sum(x["importo_base"] for x in attive if x["categoria"] != "liquidita")
    cap = pf.get("capitale", 0.0)
    return {"righe": righe, "attive": attive, "totale": tot, "commissioni": comm, "allocazione": alloc, "valute": valute, "settori": settori, "aree": aree,
            "primo_anno": primo_anno, "reddito_annuo": reddito, "rendimento_cedolare": reddito / tot if tot else None, "avvisi": avvisi,
            "capitale": cap, "investito_titoli": investito_titoli, "liquidita_residua": (cap - investito_titoli) if cap else None}


# ───────────────────────── analisi con Claude ─────────────────────────
PUNTI_ANALISI = [
    "Rating e target price degli analisti sui singoli titoli/emittenti e sui sottostanti",
    "Conti economici e bilanci aziendali (ricavi, margini, utile, indebitamento, flussi di cassa)",
    "Struttura e qualità del management",
    "Value proposition e posizionamento rispetto ai concorrenti",
    "Previsioni a 12, 24 e 36 mesi (scenari base, positivo, negativo)",
]


def testo_analisi(cliente: dict, pf: dict, calc: dict) -> str:
    e = lambda x: f"{x:,.0f}".replace(",", "’")
    righe = []
    for x in calc["attive"]:
        extra = []
        if x.get("cedola_annua_pct"): extra.append(f"cedola {x['cedola_annua_pct']:g}% annua")
        if x.get("scadenza"): extra.append(f"scadenza {x['scadenza']}")
        if x.get("barriera_pct"): extra.append(f"barriera {x['barriera_pct']:g}%")
        if x.get("protezione_pct"): extra.append(f"protezione capitale {x['protezione_pct']:g}%")
        if x.get("sottostanti"): extra.append("sottostanti: " + ", ".join(f"{u.get('nome') or u.get('ticker')}" for u in x["sottostanti"]))
        righe.append(f"- {x['nome']} [{x['isin'] or 'ISIN n.d.'}] · {CATEGORIE.get(x['categoria'], x['categoria'])}{' / ' + x['sottocategoria'] if x['sottocategoria'] else ''} · "
                     f"peso {x['peso_eff_pct']:.1f}% · {x['valuta']} {e(x['importo'])}" + (" · " + "; ".join(extra) if extra else ""))
    sett = ", ".join(f"{k} {100 * v / calc['totale']:.0f}%" for k, v in sorted(calc["settori"].items(), key=lambda kv: -kv[1])) if calc["totale"] else "n.d."
    aree = ", ".join(f"{k} {100 * v / calc['totale']:.0f}%" for k, v in sorted(calc["aree"].items(), key=lambda kv: -kv[1])) if calc["totale"] else "n.d."
    punti = "\n".join(f"{i}. {p}" for i, p in enumerate(PUNTI_ANALISI, 1))
    return (
        f"Sei un analista finanziario senior. Analizza la strategia di investimento qui sotto (profilo di rischio {cliente.get('rischio', '-')}/5, valuta {pf['valuta']}, "
        f"capitale {pf['valuta']} {e(pf['capitale'])}, data {date.today().strftime('%d.%m.%Y')}). Usa la ricerca web per i dati e le notizie più recenti.\n\n"
        f"STRATEGIA «{pf['nome']}»\n" + "\n".join(righe) + f"\n\nEsposizione settoriale: {sett}\nEsposizione geografica: {aree}\n\n"
        f"Per ogni prodotto/emittente/sottostante valuta:\n{punti}\n\n"
        "Conclusione: dai un voto complessivo alla strategia da 0 a 100 (100 = strategia perfetta rispetto al momento macroeconomico e alle ultime notizie), "
        "motivalo, e se non è 100 indica i consigli concreti: nuovi acquisti da valutare e modifiche al portafoglio attuale (cosa ridurre, sostituire o aggiungere, con motivazione e rischi). "
        "Distingui fatti verificati da tue valutazioni e cita le fonti."
    )


def link_claude(testo: str) -> str:
    return "https://claude.ai/new?q=" + urllib.parse.quote(testo[:6000])
