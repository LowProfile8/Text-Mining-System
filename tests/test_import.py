import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import dati, db
from core.anagrafica import Registro
from core.parser_postfinance import parse

PDF_LUG = "/mnt/user-data/uploads/Estrattoconto.pdf"
PDF_APR = "/mnt/user-data/uploads/Estrattoconto_2.pdf"


@pytest.fixture(autouse=True)
def archivio_temporaneo(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "_archivio", db.ArchivioLocale(tmp_path))


def test_import_due_estratti_in_ordine_inverso_collega_simbolo_e_isin():
    cli = dati.nuovo_cliente("Luigi Longobardi", "CHF")
    reg = Registro()
    # prima luglio (dividendo VHYL, cedola AGARTQ: solo simboli), poi aprile (acquisto con ISIN di CS1)
    r1 = dati.importa_estratto(cli, parse(PDF_LUG).a_dict(), reg)
    r2 = dati.importa_estratto(cli, parse(PDF_APR).a_dict(), reg)
    assert r1["nuovi"] == 6 and r2["nuovi"] == 4 and r2["duplicati"] == 0
    chiavi = set(reg.strumenti)
    assert "FR0010655746" in chiavi and "SYM:VHYL" in chiavi and "SYM:AGARTQ" in chiavi
    assert reg.strumenti["SYM:AGARTQ"]["categoria"] == "strutturato"
    assert reg.strumenti["SYM:AGARTQ"]["cedola_annua_pct"] == 6.93
    assert reg.strumenti["SYM:AGARTQ"]["frequenza_cedola"] == 4          # dedotta da 173.20 / (10000 × 6.93%)
    assert reg.strumenti["SYM:VHYL"]["categoria"] == "etf_azioni"


def test_reimportare_lo_stesso_estratto_non_duplica():
    cli = dati.nuovo_cliente("Luigi Longobardi", "CHF")
    reg = Registro()
    dati.importa_estratto(cli, parse(PDF_LUG).a_dict(), reg)
    n = len(cli["transazioni"])
    r = dati.importa_estratto(cli, parse(PDF_LUG).a_dict(), reg)
    assert r["nuovi"] == 0 and r["duplicati"] == n and len(cli["transazioni"]) == n


def test_saldi_liquidita_e_persistenza():
    cli = dati.nuovo_cliente("Luigi Longobardi", "CHF")
    reg = Registro()
    dati.importa_estratto(cli, parse(PDF_LUG).a_dict(), reg)
    dati.salva_cliente(cli); dati.salva_registro(reg)
    ricaricato = dati.carica_cliente(cli["id"])
    assert dati.saldi_a_data(ricaricato, "2026-07-31") == {"CHF": 0.0, "USD": 12.04, "EUR": 11085.75}
    assert dati.saldi_a_data(ricaricato, "2026-06-30") == {}
    assert "SYM:AGARTQ" in dati.carica_registro().strumenti


def test_acquisto_con_isin_promuove_il_simbolo_gia_noto():
    cli = dati.nuovo_cliente("X", "EUR")
    reg = Registro()
    reg.assicura(simbolo="CS1", nome="AMND IBEX 35 UCI ETF", valuta="EUR")
    cli["transazioni"].append({"id": "a", "data": "2026-01-01", "tipo": "dividendo", "valuta": "EUR", "importo_cassa": 5.0, "strumento": "SYM:CS1", "quantita": 4})
    dati.importa_estratto(cli, parse(PDF_APR).a_dict(), reg)
    assert cli["transazioni"][0]["strumento"] == "FR0010655746"
    assert "SYM:CS1" not in reg.strumenti
