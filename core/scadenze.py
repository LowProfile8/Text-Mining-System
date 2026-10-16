"""Prodotti arrivati a scadenza: se la data di scadenza è passata e non c'è un rimborso registrato, si considerano rimborsati al nominale e passano fra i prodotti chiusi."""

from __future__ import annotations

CATEGORIE_A_SCADENZA = ("obbligazione", "strutturato", "deposito")


def rimborsi_automatici(tx: list[dict], strumenti: dict, a: str) -> tuple[list[dict], list[str]]:
    """Movimenti di rimborso sintetici (non salvati) per i prodotti scaduti entro `a` che hanno ancora quantità. Restituisce (movimenti, avvisi)."""
    netto: dict[str, float] = {}
    pf_di: dict[str, str] = {}
    for t in tx:
        k = t.get("strumento")
        if k and t["tipo"] in ("acquisto", "vendita", "rimborso"):
            netto[k] = netto.get(k, 0.0) + (t.get("quantita") or 0.0) * (1 if t["tipo"] == "acquisto" else -1)
            if t.get("portafoglio"):
                pf_di[k] = t["portafoglio"]
    extra, avvisi = [], []
    for k, q in netto.items():
        s = strumenti.get(k)
        if not s or q <= 1e-9 or not s.get("scadenza") or s.get("categoria") not in CATEGORIE_A_SCADENZA or s["scadenza"] > a:
            continue
        importo = q if s.get("prezzo_in_percento") or s.get("categoria") == "deposito" else q * 1.0
        extra.append({"id": f"auto:{k}:{s['scadenza']}", "data": s["scadenza"], "data_valuta": s["scadenza"], "tipo": "rimborso", "valuta": s.get("valuta"),
                      "titolo": f"Rimborso a scadenza {s.get('nome', '')} (automatico)", "importo_cassa": importo, "quantita": q, "prezzo": None,
                      "prezzo_in_percento": bool(s.get("prezzo_in_percento")), "importo_lordo": importo, "commissione": 0.0, "tasse": 0.0, "rif": "", "banca": "", "conto": "",
                      "strumento": k, "fonte": "auto_scadenza", "portafoglio": pf_di.get(k, "")})
        avvisi.append(f"«{s.get('nome', k)}» è scaduto il {s['scadenza'][8:]}.{s['scadenza'][5:7]}.{s['scadenza'][:4]}: lo considero rimborsato al 100% del nominale. "
                      "Se il rimborso reale è diverso (per esempio consegna dei titoli), registralo con «Registra transazione».")
    return extra, avvisi


def con_scadenze(tx: list[dict], strumenti: dict, a: str) -> tuple[list[dict], list[str]]:
    extra, avvisi = rimborsi_automatici(tx, strumenti, a)
    return (sorted(tx + extra, key=lambda t: (t["data"], t.get("rif", ""))) if extra else tx), avvisi
