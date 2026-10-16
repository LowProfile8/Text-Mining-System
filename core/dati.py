"""Logica applicativa sui dati: clienti, transazioni, import degli estratti, registro strumenti, report salvati."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from core import classificatore, db
from core.anagrafica import Registro, inferisci_frequenza
from core.performance import TIPI_ESCLUSI

TIPI_CON_STRUMENTO = ("acquisto", "vendita", "dividendo", "cedola", "premio_opzione", "rimborso")
ETICHETTE_TIPO = {
    "acquisto": "Acquisto", "vendita": "Vendita", "dividendo": "Dividendo", "cedola": "Cedola", "premio_opzione": "Premio opzione",
    "rimborso": "Rimborso a scadenza", "interesse": "Interessi", "costo_custodia": "Diritti di custodia", "costo": "Spese e commissioni", "imposta": "Imposte",
    "cambio": "Cambio valuta", "deposito": "Versamento", "prelievo": "Prelievo", "trasferimento": "Trasferimento tra conti", "altro": "Altro",
}


# ───────────────────────── clienti ─────────────────────────
def elenco_clienti() -> list[dict]:
    return sorted(db.archivio().elenca("clienti"), key=lambda c: c.get("nome", "").lower())


def carica_cliente(id_: str) -> Optional[dict]:
    return db.archivio().leggi("clienti", id_)


def salva_cliente(c: dict) -> dict:
    c.setdefault("id", db.nuovo_id())
    c.setdefault("creato", datetime.now().isoformat(timespec="seconds"))
    c.setdefault("transazioni", [])
    c.setdefault("saldi", [])
    c.setdefault("estratti", [])
    c.setdefault("portafogli", [])
    db.archivio().scrivi("clienti", c["id"], c)
    return c


def nuovo_cliente(nome: str, valuta_base: str = "CHF", rischio: int = 2, note: str = "", cognome: str = "") -> dict:
    return salva_cliente({"nome": f"{nome.strip()} {cognome.strip()}".strip(), "nome_proprio": nome.strip(), "cognome": cognome.strip(),
                          "valuta_base": valuta_base, "rischio": rischio, "note": note})


# ───────────────────────── portafogli (strategia → portafoglio attivo) ─────────────────────────
def nuovo_portafoglio(cliente: dict, nome: str, capitale: float = 0.0, valuta: str | None = None) -> dict:
    pf = {"id": db.nuovo_id()[:10], "nome": nome.strip() or "Portafoglio", "valuta": valuta or cliente["valuta_base"], "stato": "attivo",
          "capitale": float(capitale), "righe": [], "note": "", "creato": datetime.now().isoformat(timespec="seconds")}
    cliente.setdefault("portafogli", []).append(pf)
    return pf


def assicura_portafogli(cliente: dict) -> list[dict]:
    """Migrazione: i clienti con movimenti ma senza portafogli ricevono un «Portafoglio 1» già attivo."""
    if not cliente.get("portafogli") and cliente.get("transazioni"):
        pf = nuovo_portafoglio(cliente, "Portafoglio 1")
        pf["stato"] = "attivo"
    return cliente.setdefault("portafogli", [])


def portafoglio(cliente: dict, pid: str) -> dict | None:
    return next((p for p in cliente.get("portafogli", []) if p["id"] == pid), None)


def _pf_di(cliente: dict, t: dict) -> str:
    return t.get("portafoglio") or (cliente["portafogli"][0]["id"] if cliente.get("portafogli") else "")


def vista_portafoglio(cliente: dict, pid: str) -> dict:
    """Copia leggera del cliente con le sole transazioni e i soli saldi di quel portafoglio (per calcoli e report)."""
    v = dict(cliente)
    v["transazioni"] = [t for t in cliente.get("transazioni", []) if _pf_di(cliente, t) == pid]
    v["saldi"] = [s for s in cliente.get("saldi", []) if _pf_di(cliente, s) == pid]
    v["portafoglio_id"] = pid
    return v


def importa_in_portafoglio(cliente: dict, pid: str, funzione, *args) -> dict:
    """Esegue un import e assegna al portafoglio tutto ciò che è stato aggiunto (transazioni e saldi)."""
    prima_t = {id(t) for t in cliente["transazioni"]}
    prima_s = {id(s) for s in cliente["saldi"]}
    r = funzione(cliente, *args)
    for t in cliente["transazioni"]:
        if id(t) not in prima_t:
            t["portafoglio"] = pid
    for s in cliente["saldi"]:
        if id(s) not in prima_s:
            s["portafoglio"] = pid
    sostituiti = _sostituisci_acquisti_strategia(cliente, pid)
    if sostituiti:
        r.setdefault("avvisi", []).append(f"{sostituiti} acquisto/i inserito/i in fase di strategia sostituito/i dai dati reali dell'estratto conto (prezzo, quantità e commissioni effettivi).")
    return r


def _sostituisci_acquisti_strategia(cliente: dict, pid: str) -> int:
    """Se l'estratto conto contiene un acquisto già inserito alla creazione del portafoglio (stesso prodotto e quantità, date vicine), vince l'estratto."""
    n = 0
    reali = [t for t in cliente["transazioni"] if t.get("portafoglio") == pid and t["tipo"] == "acquisto" and t.get("fonte") == "estratto"]
    for st_ in [t for t in cliente["transazioni"] if t.get("portafoglio") == pid and t.get("fonte") == "strategia"]:
        for r in reali:
            if r.get("strumento") == st_.get("strumento") and abs((r.get("quantita") or 0) - (st_.get("quantita") or 0)) < 1e-6 \
                    and abs((datetime.fromisoformat(r["data"]) - datetime.fromisoformat(st_["data"])).days) <= 10:
                cliente["transazioni"].remove(st_)
                n += 1
                break
    return n


def elimina_cliente(id_: str):
    db.archivio().elimina("clienti", id_)


# ───────────────────────── registro strumenti (comune a tutti i clienti) ─────────────────────────
def carica_registro() -> Registro:
    doc = db.archivio().leggi("strumenti", "registro") or {"strumenti": {}}
    return Registro(doc["strumenti"])


def salva_registro(reg: Registro):
    db.archivio().scrivi("strumenti", "registro", {"strumenti": reg.strumenti})


def carica_manuali() -> dict:
    return (db.archivio().leggi("strumenti", "prezzi_manuali") or {}).get("prezzi", {})


def salva_manuali(prezzi: dict):
    db.archivio().scrivi("strumenti", "prezzi_manuali", {"prezzi": prezzi})


# ───────────────────────── import estratti ─────────────────────────
def _tx_da_movimento(m: dict, banca: str, conto: str, chiave: str) -> dict:
    return {
        "id": f"{banca}:{m['rif']}:{m['valuta']}" if m.get("rif") else f"{banca}:{m['data']}:{m['tipo']}:{m['valuta']}:{m['importo_cassa']}",
        "data": m["data"], "data_valuta": m["data_valuta"], "tipo": m["tipo"], "titolo": m["titolo"], "valuta": m["valuta"],
        "importo_cassa": m["importo_cassa"], "quantita": m.get("quantita"), "prezzo": m.get("prezzo"),
        "prezzo_in_percento": m.get("prezzo_in_percento", False), "importo_lordo": m.get("importo_lordo"),
        "commissione": m.get("commissione", 0.0), "tasse": m.get("tasse", 0.0), "rif": m.get("rif", ""),
        "banca": banca, "conto": conto, "strumento": chiave, "fonte": "estratto",
    }


def importa_estratto(cliente: dict, estratto: dict, reg: Registro) -> dict:
    """Aggiunge al cliente i movimenti nuovi. Ritorna un riepilogo {nuovi, duplicati, strumenti_nuovi}."""
    banca, conto = estratto["banca"], estratto.get("cliente_numero", "")
    esistenti = {t["id"] for t in cliente["transazioni"]}
    prima = set(reg.strumenti)
    nuovi = dup = 0
    for m in estratto["movimenti"]:
        chiave = ""
        if m["tipo"] in TIPI_CON_STRUMENTO:
            chiave = reg.assicura(m.get("isin", ""), m.get("simbolo", ""), m.get("nome", ""), m["valuta"], m.get("prezzo_in_percento", False))
        tx = _tx_da_movimento(m, banca, conto, chiave)
        if tx["id"] in esistenti:
            dup += 1
            continue
        cliente["transazioni"].append(tx)
        esistenti.add(tx["id"])
        nuovi += 1
    # se un simbolo è stato promosso a ISIN, le transazioni già salvate vanno riallineate
    rimappa = reg.mappa_chiavi()
    for t in cliente["transazioni"]:
        if t.get("strumento") in rimappa and rimappa[t["strumento"]] != t["strumento"]:
            t["strumento"] = rimappa[t["strumento"]]
        elif t.get("strumento", "").startswith("SYM:") and t["strumento"] not in reg.strumenti:
            sim = t["strumento"][4:]
            t["strumento"] = reg.trova(simbolo=sim) or t["strumento"]
    # saldi dei conti a fine periodo
    for val, c in estratto["conti"].items():
        cliente["saldi"] = [s for s in cliente["saldi"] if not (s["banca"] == banca and s["conto"] == conto and s["valuta"] == val and s["data"] == estratto["periodo_a"])]
        cliente["saldi"].append({"banca": banca, "conto": conto, "valuta": val, "data": estratto["periodo_a"], "saldo": c["saldo_finale"]})
    cliente["estratti"].append({"banca": banca, "conto": conto, "da": estratto["periodo_da"], "a": estratto["periodo_a"],
                                "importato": datetime.now().isoformat(timespec="seconds"), "movimenti": nuovi})
    completa_strumenti(cliente, reg, nuovi_solo=set(reg.strumenti) - prima)
    return {"nuovi": nuovi, "duplicati": dup, "strumenti_nuovi": sorted(set(reg.strumenti) - prima)}


_CAMPI_TERMINI = ("scadenza", "data_emissione", "cedola_annua_pct", "frequenza_cedola", "barriera_pct", "protezione_pct", "rating", "emittente")


def importa_posizioni(cliente: dict, doc: dict, reg: Registro) -> dict:
    """Importa le posizioni di un documento (valore e quantità iniziali) come acquisti al costo, e i saldi di liquidità."""
    banca, conto, data_doc = doc["banca"], doc["conto"], doc["data"]
    esistenti = {t["id"] for t in cliente["transazioni"]}
    prima = set(reg.strumenti)
    nuovi = dup = 0
    avvisi = []
    for p in doc["posizioni"]:
        dep = p.get("categoria_hint") == "deposito"
        k = reg.assicura(p.get("isin", ""), "" if p.get("isin") else f"DEP{conto}{p['valuta']}{int(p['quantita'])}", p["nome"], p["valuta"], not dep)
        s = reg.strumenti[k]
        if dep:
            s.update(categoria="deposito", sottocategoria="Deposito a termine", valutazione="scadenza", prezzo_in_percento=False)
        for c in _CAMPI_TERMINI:
            if p.get(c) and not s.get(c):
                s[c] = p[c]
        if p.get("sottostanti") and not s.get("sottostanti"):
            s["sottostanti"] = p["sottostanti"]
        if p.get("sottostanti_testo"):
            s["sottostanti_testo"] = p["sottostanti_testo"]
        if p.get("rebate_pct"):
            s["rebate_pct"], s["barriera_superiore_pct"] = p["rebate_pct"], p.get("barriera_superiore_pct")
        if "Reverse" in p["nome"] or "BRC" in p["nome"]:
            s.update(categoria="strutturato", sottocategoria="Barrier Reverse Convertible", valutazione="nominale", prezzo_in_percento=True)
        data = p.get("data_acquisto") or data_doc
        costo = p["quantita"] * (1.0 if dep else p["prezzo_acquisto_pct"] / 100)
        tid = f"posizione:{banca}:{conto}:{k}:{data}"
        if tid in esistenti:
            dup += 1
            continue
        if any(t["strumento"] == k and t["tipo"] == "acquisto" and t["fonte"] == "estratto" and t["data"] <= data_doc for t in cliente["transazioni"]):
            avvisi.append(f"{s['nome']}: esiste già un acquisto da estratto conto per questo strumento; la posizione iniziale può duplicarlo. Controlla.")
        cliente["transazioni"].append({
            "id": tid, "data": data, "data_valuta": data, "tipo": "acquisto", "titolo": f"Posizione iniziale al {data_doc}: {p['nome']}", "valuta": p["valuta"],
            "importo_cassa": -costo, "quantita": p["quantita"], "prezzo": None if dep else p["prezzo_acquisto_pct"], "prezzo_in_percento": not dep,
            "importo_lordo": costo, "commissione": 0.0, "tasse": 0.0, "rif": "", "banca": banca, "conto": conto, "strumento": k, "fonte": "posizione_iniziale"})
        esistenti.add(tid)
        nuovi += 1
    for c in doc.get("liquidita", []):
        cliente["saldi"] = [x for x in cliente["saldi"] if not (x["banca"] == banca and x["conto"] == c["conto"] and x["valuta"] == c["valuta"] and x["data"] == data_doc)]
        cliente["saldi"].append({"banca": banca, "conto": c["conto"], "valuta": c["valuta"], "data": data_doc, "saldo": c["saldo"]})
    cliente["estratti"].append({"banca": banca, "conto": conto, "da": data_doc, "a": data_doc, "importato": datetime.now().isoformat(timespec="seconds"),
                                "movimenti": nuovi, "tipo": "posizioni"})
    completa_strumenti(cliente, reg, nuovi_solo=set(reg.strumenti) - prima)
    return {"nuovi": nuovi, "duplicati": dup, "strumenti_nuovi": sorted(set(reg.strumenti) - prima), "avvisi": avvisi}


def aggiungi_deposito_termine(cliente: dict, reg: Registro, banca: str, numero: str, valuta: str, nominale: float, tasso: float,
                              inizio: str, fine: str, interesse_lordo: float, imposta: float = 0.0) -> str:
    """Deposito vincolato (es. Raiffeisen): acquisto alla data di inizio; a fine: interesse lordo, imposta preventiva, rimborso del nominale."""
    k = reg.assicura("", f"DEP{numero}", f"Deposito a termine {banca} {valuta} {tasso:g}%", valuta, False)
    s = reg.strumenti[k]
    s.update(categoria="deposito", sottocategoria="Deposito a termine", valutazione="scadenza", prezzo_in_percento=False, cedola_annua_pct=tasso,
             frequenza_cedola=1, data_emissione=inizio, scadenza=fine, confermato=True, aree={}, settori={})
    base = dict(valuta=valuta, banca=banca, conto=numero, strumento=k)
    aggiungi_movimento_manuale(cliente, data=inizio, tipo="acquisto", importo_cassa=-nominale, quantita=nominale, titolo=f"Deposito a termine {banca} {numero}", **base)
    if interesse_lordo:
        aggiungi_movimento_manuale(cliente, data=fine, tipo="interesse", importo_cassa=interesse_lordo, titolo="Interesse lordo deposito a termine", **base)
    if imposta:
        aggiungi_movimento_manuale(cliente, data=fine, tipo="imposta", importo_cassa=-imposta, titolo="Imposta preventiva 35% sul deposito", **base)
    aggiungi_movimento_manuale(cliente, data=fine, tipo="rimborso", importo_cassa=nominale, quantita=nominale, titolo="Rimborso del nominale", **base)
    return k


def completa_strumenti(cliente: dict, reg: Registro, nuovi_solo: set | None = None, con_yahoo: bool = False):
    """Deduce automaticamente frequenza cedolare e classificazione per gli strumenti del cliente."""
    for k, s in reg.strumenti.items():
        if nuovi_solo is not None and k not in nuovi_solo and s.get("frequenza_cedola"):
            continue
        if not s.get("frequenza_cedola"):
            f = inferisci_frequenza(s, cliente["transazioni"])
            if f:
                s["frequenza_cedola"] = f
        if not s.get("classificazione_manuale") and not (s.get("settori") and s.get("aree")):
            y = classificatore.dati_yahoo(s["ticker_mercato"]) if (con_yahoo and s.get("ticker_mercato")) else None
            classificatore.applica(s, y)


def saldi_a_data(cliente: dict, data: str) -> dict[str, float]:
    """Saldo di liquidità per valuta all'ultima data disponibile ≤ data (somma dei conti/banche)."""
    ultimo: dict[tuple, dict] = {}
    for s in cliente["saldi"]:
        if s["data"] <= data:
            k = (s["banca"], s["conto"], s["valuta"])
            if k not in ultimo or s["data"] > ultimo[k]["data"]:
                ultimo[k] = s
    out: dict[str, float] = {}
    for s in ultimo.values():
        out[s["valuta"]] = out.get(s["valuta"], 0.0) + s["saldo"]
    return out


def aggiungi_movimento_manuale(cliente: dict, **campi) -> dict:
    tx = {"id": f"manuale:{db.nuovo_id()}", "fonte": "manuale", "banca": "", "conto": "", "rif": "", "titolo": campi.get("titolo", ""),
          "commissione": 0.0, "tasse": 0.0, "data_valuta": campi["data"], "prezzo_in_percento": False, "importo_lordo": None,
          "prezzo": None, "quantita": None, "strumento": ""}
    tx.update(campi)
    cliente["transazioni"].append(tx)
    return tx


def transazioni_ordinate(cliente: dict) -> list[dict]:
    return sorted(cliente["transazioni"], key=lambda t: (t["data"], t.get("rif", "")))


# ───────────────────────── report salvati ─────────────────────────
def salva_report(meta: dict, pdf: bytes) -> dict:
    meta.setdefault("id", db.nuovo_id())
    meta.setdefault("creato", datetime.now().isoformat(timespec="seconds"))
    db.archivio().salva_file(meta["id"], pdf)
    db.archivio().scrivi("report", meta["id"], meta)
    return meta


def elenco_report() -> list[dict]:
    return sorted(db.archivio().elenca("report"), key=lambda r: r.get("creato", ""), reverse=True)


def pdf_report(id_: str) -> Optional[bytes]:
    return db.archivio().leggi_file(id_)


def elimina_report(id_: str):
    db.archivio().elimina("report", id_)
    db.archivio().elimina_file(id_)
