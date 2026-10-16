"""Revisione prima del salvataggio: ogni movimento letto da un estratto viene mostrato in una tabella modificabile, con il controllo
«quantità × prezzo + commissioni = importo addebitato». Nulla entra nel cliente finché l'utente non conferma."""

from __future__ import annotations

import copy

TOLL_ASSOLUTA = 0.05
TOLL_RELATIVA = 0.0005


def controlla_operazione(m: dict) -> tuple[str, str]:
    """('ok'|'differenza'|'incompleto'|'na', testo). Verifica solo acquisti e vendite di titoli."""
    if m.get("tipo") not in ("acquisto", "vendita"):
        return "na", ""
    q, p = m.get("quantita"), m.get("prezzo")
    if not q or p is None:
        return "incompleto", "quantità o prezzo mancanti"
    lordo = q * p / 100 if m.get("prezzo_in_percento") else q * p
    comm, tasse = float(m.get("commissione") or 0), float(m.get("tasse") or 0)
    atteso = -(lordo + comm + tasse) if m["tipo"] == "acquisto" else (lordo - comm - tasse)
    diff = float(m["importo_cassa"]) - atteso
    if abs(diff) <= max(TOLL_ASSOLUTA, TOLL_RELATIVA * abs(atteso)):
        return "ok", f"{q:,.0f} × {p:g}{'%' if m.get('prezzo_in_percento') else ''} + commissioni {comm + tasse:,.2f} = {abs(atteso):,.2f}".replace(",", "’")
    return "differenza", f"atteso {abs(atteso):,.2f}, addebitato {abs(float(m['importo_cassa'])):,.2f} (differenza {diff:+,.2f})".replace(",", "’")


def _id(m: dict, banca: str) -> str:
    from core.dati import _tx_da_movimento
    return _tx_da_movimento(m, banca, "", "")["id"]


def prepara_revisione(estratto: dict, cliente: dict, reg) -> list[dict]:
    """Righe per la tabella di revisione, una per movimento."""
    esistenti = {t["id"] for t in cliente["transazioni"]}
    righe = []
    for i, m in enumerate(estratto["movimenti"]):
        stato, nota = controlla_operazione(m)
        k = reg.trova(m.get("isin", ""), m.get("simbolo", "")) if m.get("isin") or m.get("simbolo") else None
        gia = _id(m, estratto["banca"]) in esistenti
        righe.append({
            "_i": i, "Importa": not gia, "Data": m["data"], "Tipo": m["tipo"], "Prodotto": (reg.strumenti[k]["nome"] if k else m.get("nome") or m.get("titolo", ""))[:60],
            "ISIN": m.get("isin", ""), "Valuta": m["valuta"], "Quantità": m.get("quantita"), "Prezzo": m.get("prezzo"), "Prezzo in %": bool(m.get("prezzo_in_percento")),
            "Commissioni": float(m.get("commissione") or 0) + float(m.get("tasse") or 0), "Importo": float(m["importo_cassa"]),
            "Controllo": {"ok": "✓", "differenza": "⚠", "incompleto": "⚠", "na": ""}[stato], "Dettaglio": ("già presente" if gia else nota),
        })
    return righe


def applica_modifiche(estratto: dict, righe_modificate: list[dict]) -> dict:
    """Copia dell'estratto con i soli movimenti spuntati e i valori corretti dall'utente."""
    out = copy.deepcopy(estratto)
    nuovi = []
    for r in righe_modificate:
        if not r.get("Importa"):
            continue
        m = copy.deepcopy(estratto["movimenti"][int(r["_i"])])
        m["data"] = str(r["Data"])
        m["tipo"] = r["Tipo"]
        m["quantita"] = r.get("Quantità") if r.get("Quantità") == r.get("Quantità") else None   # NaN -> None
        m["prezzo"] = r.get("Prezzo") if r.get("Prezzo") == r.get("Prezzo") else None
        m["prezzo_in_percento"] = bool(r.get("Prezzo in %"))
        m["importo_cassa"] = float(r["Importo"])
        comm_orig = float(m.get("commissione") or 0) + float(m.get("tasse") or 0)
        if abs(float(r.get("Commissioni") or 0) - comm_orig) > 1e-9:      # l'utente ha corretto le commissioni
            m["commissione"], m["tasse"] = float(r["Commissioni"]), 0.0
        nuovi.append(m)
    out["movimenti"] = nuovi
    return out


# ───────────────────────── documenti di posizioni (valori e quantità iniziali) ─────────────────────────
def prepara_revisione_posizioni(doc: dict) -> list[dict]:
    return [{"_i": i, "Importa": True, "Prodotto": p["nome"][:60], "ISIN": p.get("isin", ""), "Valuta": p["valuta"], "Quantità": p["quantita"],
             "Prezzo acquisto %": p.get("prezzo_acquisto_pct"), "Data acquisto": p.get("data_acquisto") or doc["data"],
             "Scadenza": p.get("scadenza", ""), "Cedola %": p.get("cedola_annua_pct"), "Barriera %": p.get("barriera_pct")}
            for i, p in enumerate(doc["posizioni"])]


def applica_modifiche_posizioni(doc: dict, righe: list[dict]) -> dict:
    out = copy.deepcopy(doc)
    pos = []
    for r in righe:
        if not r.get("Importa"):
            continue
        p = copy.deepcopy(doc["posizioni"][int(r["_i"])])
        p["quantita"] = float(r["Quantità"])
        if r.get("Prezzo acquisto %") == r.get("Prezzo acquisto %") and r.get("Prezzo acquisto %") is not None:
            p["prezzo_acquisto_pct"] = float(r["Prezzo acquisto %"])
        p["data_acquisto"] = str(r["Data acquisto"])
        for k_ui, k in (("Scadenza", "scadenza"), ("Cedola %", "cedola_annua_pct"), ("Barriera %", "barriera_pct")):
            v = r.get(k_ui)
            if v is not None and v == v and v != "":
                p[k] = v
        pos.append(p)
    out["posizioni"] = pos
    return out
