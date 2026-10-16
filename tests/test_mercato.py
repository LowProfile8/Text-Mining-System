import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.anagrafica import Registro
from core.classificatore import applica, area_da_isin, aree_da_nome_indice, classifica
from core.mercato import Mercato


class Finta:
    """Fonte finta con prezzi fissi: (ticker, data) -> (data_effettiva, prezzo)."""

    def __init__(self, nome, px=None, fx=None, rng=None):
        self.nome, self.px, self.fx_, self.rng, self.chiamate = nome, px or {}, fx or {}, rng or {}, 0

    def chiusura(self, ticker, data):
        self.chiamate += 1
        return self.px.get((ticker, data))

    def cambio(self, da, a, data):
        self.chiamate += 1
        return self.fx_.get((da, a, data))

    def intervallo(self, ticker, data):
        return self.rng.get((ticker, data))


def _strum(t1="CS1.PA", t2="cs1.fr"):
    reg = Registro()
    k = reg.assicura(isin="FR0010655746", simbolo="CS1", nome="AMND IBEX 35 UCI ETF", valuta="EUR")
    reg.strumenti[k]["ticker_mercato"], reg.strumenti[k]["ticker_controllo"] = t1, t2
    return reg, k


def test_due_fonti_concordi():
    reg, k = _strum()
    m = Mercato(Finta("A", px={("CS1.PA", "2026-09-30"): ("2026-09-30", 500.0)}), Finta("B", px={("cs1.fr", "2026-09-30"): ("2026-09-30", 500.8)}))
    r = m.prezzo(reg.strumenti[k], "2026-09-30")
    assert r["stato"] == "ok" and r["prezzo"] == 500.0
    assert m.problemi() == []


def test_due_fonti_discordi_bloccano():
    reg, k = _strum()
    m = Mercato(Finta("A", px={("CS1.PA", "2026-09-30"): ("2026-09-30", 500.0)}), Finta("B", px={("cs1.fr", "2026-09-30"): ("2026-09-30", 470.0)}))
    r = m.prezzo(reg.strumenti[k], "2026-09-30")
    assert r["stato"] == "discrepanza"
    assert len(m.problemi()) == 1


def test_correzione_manuale_risolve():
    reg, k = _strum()
    m = Mercato(Finta("A", px={("CS1.PA", "2026-09-30"): ("2026-09-30", 500.0)}), Finta("B", px={("cs1.fr", "2026-09-30"): ("2026-09-30", 470.0)}),
                manuali={f"{k}@2026-09-30": 498.0})
    r = m.prezzo(reg.strumenti[k], "2026-09-30")
    assert r["stato"] == "manuale" and r["prezzo"] == 498.0
    assert m.problemi() == []


def test_fonte_non_trovata_e_segnalata():
    reg, k = _strum()
    m = Mercato(Finta("A"), Finta("B"))
    assert m.prezzo(reg.strumenti[k], "2026-09-30")["stato"] == "non_trovato"
    assert len(m.problemi()) == 1


def test_senza_ticker_di_controllo_e_dichiarato():
    reg, k = _strum(t2="")
    m = Mercato(Finta("A", px={("CS1.PA", "2026-09-30"): ("2026-09-30", 500.0)}), Finta("B"))
    assert m.prezzo(reg.strumenti[k], "2026-09-30")["stato"] == "unica_fonte"


def test_snapshot_ha_la_precedenza_sulla_rete():
    reg, k = _strum()
    rete = Finta("A", px={("CS1.PA", "2026-09-30"): ("2026-09-30", 999.0)})
    m = Mercato(rete, snapshot={f"{k}@2026-09-30": {"prezzo": 500.0, "fonte": "congelato", "stato": "ok"}})
    assert m.prezzo(reg.strumenti[k], "2026-09-30")["prezzo"] == 500.0
    assert rete.chiamate == 0


def test_cache_evita_richieste_ripetute():
    reg, k = _strum()
    a = Finta("A", px={("CS1.PA", "2026-09-30"): ("2026-09-30", 500.0)})
    m = Mercato(a)
    m.prezzo(reg.strumenti[k], "2026-09-30"); m.prezzo(reg.strumenti[k], "2026-09-30")
    assert a.chiamate == 1


def test_cambio_bce_con_controllo_su_yahoo():
    bce = Finta("BCE", fx={("EUR", "CHF", "2026-09-30"): ("2026-09-30", 0.9300)})
    yh = Finta("Y", fx={("EUR", "CHF", "2026-09-30"): ("2026-09-30", 0.9310)})
    m = Mercato(yh, controllo_cambi=bce)
    assert m.fx("EUR", "CHF", "2026-09-30") == 0.9300 and m.fx("EUR", "EUR", "2026-09-30") == 1.0
    assert m.problemi() == []
    yh.fx_[("EUR", "CHF", "2026-09-30")] = ("2026-09-30", 0.90)
    m2 = Mercato(yh, controllo_cambi=bce)
    m2.fx("EUR", "CHF", "2026-09-30")
    assert m2.problemi()[0]["tipo"] == "cambio"


def test_controllo_interno_sul_prezzo_di_acquisto():
    reg, k = _strum()
    rete = Finta("A", rng={("CS1.PA", "2026-04-22"): (455.0, 465.0)})
    m = Mercato(rete)
    ok = {"tipo": "acquisto", "strumento": k, "data": "2026-04-22", "prezzo": 460.0}
    assert m.controllo_acquisti([ok], reg.strumenti)[0]["stato"] == "ok"
    sbagliato = dict(ok, prezzo=380.0)          # ticker sbagliato o prezzo mal letto
    assert m.controllo_acquisti([sbagliato], reg.strumenti)[0]["stato"] == "incoerente"


# ───────────────────────── classificazione ─────────────────────────
def test_obbligazione_area_da_isin():
    assert area_da_isin("IT0005657330") == "Europa" and area_da_isin("US912828") == "Stati Uniti"
    s = {"categoria": "obbligazione", "isin": "IT0005657330", "nome": "BTP"}
    r = classifica(s)
    assert r["settori"] == {"Governativo": 1.0} and r["aree"] == {"Italia": 1.0}


def test_etf_su_indice_regole_del_nome():
    assert aree_da_nome_indice("AMND IBEX 35 UCI ETF")[0] == {"Europa": 1.0}
    assert aree_da_nome_indice("ISHARES S&P 500 UCITS ETF")[0] == {"Stati Uniti": 1.0}
    mondo, _ = aree_da_nome_indice("VANGUARD WRLD HI DIV YLD UCITS ETF")
    assert sum(mondo.values()) == pytest.approx(1.0)


def test_etf_con_dati_yahoo():
    s = {"categoria": "etf_azioni", "nome": "ISHARES CORE MSCI WORLD", "isin": "IE00B4L5Y983"}
    r = classifica(s, {"settori_fondo": {"technology": 0.25, "healthcare": 0.12, "financial_services": 0.15, "energy": 0.08, "utilities": 0.04}})
    assert sum(r["settori"].values()) == pytest.approx(1.0)
    assert r["settori"]["Tecnologia"] > r["settori"]["Healthcare"]


def test_strutturato_media_dei_sottostanti():
    s = {"categoria": "strutturato", "sottostanti": [{"ticker": "^GSPC"}, {"ticker": "^STOXX50E"}, {"ticker": "^SSMI"}]}
    r = classifica(s)
    assert r["aree"] == pytest.approx({"Stati Uniti": 1 / 3, "Europa": 1 / 3, "Svizzera": 1 / 3})


def test_non_classificabile_resta_vuoto_e_non_inventa():
    s = {"categoria": "etf_azioni", "nome": "XYZ FONDO ZETA"}
    r = classifica(s)
    assert r["settori"] == {} and r["aree"] == {}


def test_classificazione_manuale_non_viene_sovrascritta():
    s = {"categoria": "obbligazione", "isin": "IT0005657330", "nome": "BTP", "settori": {"Governativo": 1.0}, "aree": {"Svizzera": 1.0}, "classificazione_manuale": True}
    assert applica(s)["aree"] == {"Svizzera": 1.0}
