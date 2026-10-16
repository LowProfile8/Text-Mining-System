import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core.completezza import problemi_strumento
from core.revisione import applica_modifiche, controlla_operazione


def _m(**kw):
    base = {"data": "2026-06-16", "tipo": "acquisto", "valuta": "CHF", "importo_cassa": -20040.0, "quantita": 20000.0, "prezzo": 100.0, "prezzo_in_percento": True,
            "commissione": 40.0, "tasse": 0.0, "titolo": "x"}
    base.update(kw)
    return base


def test_controllo_acquisto_ok_e_differenza():
    assert controlla_operazione(_m())[0] == "ok"
    assert controlla_operazione(_m(importo_cassa=-20000.0))[0] == "differenza"      # manca la commissione
    assert controlla_operazione(_m(prezzo=None))[0] == "incompleto"
    assert controlla_operazione(_m(tipo="dividendo"))[0] == "na"


def test_controllo_vendita():
    assert controlla_operazione(_m(tipo="vendita", importo_cassa=19960.0))[0] == "ok"


def test_applica_modifiche_solo_spuntati_e_corretti():
    est = {"banca": "X", "movimenti": [_m(), _m(data="2026-06-17")]}
    righe = [{"_i": 0, "Importa": True, "Data": "2026-06-16", "Tipo": "acquisto", "Quantità": 10000.0, "Prezzo": 100.0, "Prezzo in %": True, "Commissioni": 40.0, "Importo": -10040.0},
             {"_i": 1, "Importa": False, "Data": "2026-06-17", "Tipo": "acquisto", "Quantità": 1.0, "Prezzo": 1.0, "Prezzo in %": False, "Commissioni": 0.0, "Importo": -1.0}]
    out = applica_modifiche(est, righe)
    assert len(out["movimenti"]) == 1 and out["movimenti"][0]["quantita"] == 10000.0 and out["movimenti"][0]["importo_cassa"] == -10040.0
    assert est["movimenti"][0]["quantita"] == 20000.0          # l'originale non cambia


def test_completezza_brc():
    s = {"valuta": "EUR", "categoria": "strutturato", "valutazione": "scadenza", "scadenza": "2028-01-06", "cedola_annua_pct": 6.9, "frequenza_cedola": 4,
         "barriera_pct": 60.0, "sottostanti": [{"ticker": "^GSPC", "nome": "S&P 500", "livello_iniziale": None}]}
    bl = [t for g, t in problemi_strumento(s) if g == "bloccante"]
    assert any("livello iniziale" in t for t in bl)
    s["sottostanti"][0]["livello_iniziale"] = 5000.0
    assert not [t for g, t in problemi_strumento(s) if g == "bloccante"]
