import sys
from datetime import date
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.anagrafica import Registro, cedola_da_nome, classifica_da_nome, inferisci_frequenza
from core.performance import Contesto, DatoMancante, calcola, modified_dietz, rendimento_atteso, rischio_barriera, xirr


# ───────────────────────── helper ─────────────────────────
def ctx_semplice(base="EUR", fx=None, prezzi=None, spot=None):
    fx = fx or {}
    prezzi = prezzi or {}

    def f_fx(da, a, data):
        if da == a:
            return 1.0
        return fx.get((da, a))

    def f_prezzo(s, data):
        # prezzo = ultimo prezzo noto alla data
        serie = sorted([(d, p) for (k, d), p in prezzi.items() if k == s["chiave"] and d <= data])
        if not serie:
            return {"prezzo": None, "fonte": "", "stato": "mancante"}
        return {"prezzo": serie[-1][1], "fonte": "test", "stato": "ok"}

    return Contesto(base=base, fx=f_fx, prezzo=f_prezzo, spot=(lambda t, d: (spot or {}).get(t)))


def tx(data, tipo, cassa, chiave, valuta="EUR", quantita=None, **extra):
    d = {"data": data, "tipo": tipo, "importo_cassa": cassa, "strumento": chiave, "valuta": valuta, "quantita": quantita,
         "titolo": tipo, "rif": extra.pop("rif", f"{data}{tipo}{chiave}")}
    d.update(extra)
    return d


# ───────────────────────── matematica di base ─────────────────────────
def test_xirr_un_anno():
    r = xirr([(date(2025, 1, 1), -100.0), (date(2026, 1, 1), 110.0)])
    assert r == pytest.approx(0.10, abs=1e-4)


def test_xirr_senza_cambio_di_segno():
    assert xirr([(date(2025, 1, 1), -100.0), (date(2026, 1, 1), -10.0)]) is None


def test_dietz_senza_flussi():
    assert modified_dietz(100, 110, [], date(2026, 7, 1), date(2026, 9, 30)) == pytest.approx(0.10)


def test_dietz_con_acquisto_a_meta_periodo():
    # 100 a inizio, +100 versati esattamente a metà periodo, 220 a fine: P/L = 20 su capitale medio 150
    da, a = date(2026, 1, 1), date(2026, 1, 11)
    r = modified_dietz(100, 220, [(date(2026, 1, 6), -100.0)], da, a)
    assert r == pytest.approx(20 / 150, abs=1e-3)


# ───────────────────────── anagrafica ─────────────────────────
def test_classificazione_automatica_dai_nomi_reali():
    assert classifica_da_nome("6.93% p.a. Multi Barrier Reverse Co")[0:2] == ("strutturato", "Barrier Reverse Convertible")
    assert classifica_da_nome("AMND IBEX 35 UCI ETF")[0] == "etf_azioni"
    assert classifica_da_nome("VANGUARD WRLD HI DIV YLD UCITS ETF")[0] == "etf_azioni"
    assert classifica_da_nome("BTP 2.1% 26/08/2027")[0] == "obbligazione"


def test_cedola_dal_nome():
    assert cedola_da_nome("6.93% p.a. Multi Barrier Reverse Co") == 6.93
    assert cedola_da_nome("AMND IBEX 35 UCI ETF") is None


def test_collegamento_simbolo_isin():
    reg = Registro()
    k1 = reg.assicura(simbolo="CS1", nome="AMND IBEX 35 UCI ETF", valuta="EUR")      # solo simbolo
    assert k1 == "SYM:CS1"
    k2 = reg.assicura(isin="FR0010655746", simbolo="CS1", nome="AMND IBEX 35 UCI ETF", valuta="EUR")
    assert k2 == "FR0010655746"
    assert reg.trova(simbolo="CS1") == "FR0010655746"
    assert len(reg.strumenti) == 1


def test_frequenza_inferita_dai_pagamenti():
    reg = Registro()
    k = reg.assicura(simbolo="AGARTQ", nome="6.93% p.a. Multi Barrier Reverse Co", valuta="EUR")
    t = [tx("2026-07-06", "cedola", 64.98, k, quantita=10000), tx("2026-07-06", "premio_opzione", 108.22, k, quantita=10000)]
    assert inferisci_frequenza(reg.strumenti[k], t) == 4


# ───────────────────────── blocco a mercato ─────────────────────────
def _etf():
    reg = Registro()
    k = reg.assicura(isin="FR0010655746", simbolo="CS1", nome="AMND IBEX 35 UCI ETF", valuta="EUR")
    return reg, k


def test_etf_a_mercato_rendimento_del_trimestre():
    reg, k = _etf()
    prezzi = {(k, "2026-04-22"): 460.0, (k, "2026-06-30"): 480.0, (k, "2026-09-30"): 500.0}
    t = [tx("2026-04-22", "acquisto", -1853.15, k, quantita=4)]
    r = calcola(t, reg.strumenti, "2026-06-30", "2026-09-30", ctx_semplice(prezzi=prezzi))
    b = r["blocchi"]["mercato"]
    assert b["valore_inizio"] == pytest.approx(1920.0)
    assert b["valore_fine"] == pytest.approx(2000.0)
    assert b["rendimento_periodo"] == pytest.approx(80 / 1920, abs=1e-6)
    assert r["valore_titoli"] == pytest.approx(2000.0)


def test_etf_con_dividendo_in_altra_valuta():
    reg, k = _etf()
    prezzi = {(k, "2026-06-30"): 480.0, (k, "2026-09-30"): 480.0}
    fx = {("USD", "EUR"): 0.9}
    t = [tx("2026-04-22", "acquisto", -1853.15, k, quantita=4),
         tx("2026-07-01", "dividendo", 12.04, k, valuta="USD", quantita=4)]
    r = calcola(t, reg.strumenti, "2026-06-30", "2026-09-30", ctx_semplice(fx=fx, prezzi=prezzi))
    assert r["blocchi"]["mercato"]["pl"] == pytest.approx(12.04 * 0.9)
    assert r["posizioni"][0]["reddito_periodo"] == pytest.approx(10.836)


def test_prezzo_mancante_valuta_al_costo_e_avvisa():
    reg, k = _etf()
    t = [tx("2026-04-22", "acquisto", -1853.15, k, quantita=4)]
    r = calcola(t, reg.strumenti, "2026-06-30", "2026-09-30", ctx_semplice(prezzi={}))
    assert r["posizioni"][0]["stato_prezzo"] == "prezzo_mancante"
    assert r["posizioni"][0]["valore"] == pytest.approx(1853.15)
    assert any("prezzo di mercato non disponibile" in a for a in r["avvisi"])


def test_cambio_mancante_blocca_il_calcolo():
    reg, k = _etf()
    t = [tx("2026-04-22", "acquisto", -2000.0, k, valuta="USD", quantita=4)]
    with pytest.raises(DatoMancante):
        calcola(t, reg.strumenti, "2026-06-30", "2026-09-30", ctx_semplice())


def test_vendita_con_costo_medio():
    reg, k = _etf()
    prezzi = {(k, "2026-09-30"): 500.0}
    t = [tx("2026-04-22", "acquisto", -1000.0, k, quantita=2), tx("2026-05-22", "acquisto", -1200.0, k, quantita=2),
         tx("2026-08-01", "vendita", 1300.0, k, quantita=2)]
    r = calcola(t, reg.strumenti, "2026-06-30", "2026-09-30", ctx_semplice(prezzi=prezzi))
    p = r["posizioni"][0]
    assert p["quantita"] == pytest.approx(2)
    assert p["costo"] == pytest.approx(1100.0)          # costo medio 2200/4 = 550 per quota
    assert p["realizzato"] == pytest.approx(200.0)      # 1300 − 1100
    assert p["valore"] == pytest.approx(1000.0)


# ───────────────────────── blocco a scadenza ─────────────────────────
def _brc():
    reg = Registro()
    k = reg.assicura(simbolo="AGARTQ", nome="6.93% p.a. Multi Barrier Reverse Co", valuta="EUR")
    s = reg.strumenti[k]
    s.update(valutazione="scadenza", frequenza_cedola=4, scadenza="2027-01-06", barriera_pct=60.0,
             sottostanti=[{"ticker": "SPX", "nome": "S&P 500", "livello_iniziale": 5000.0},
                          {"ticker": "SX5E", "nome": "Euro Stoxx 50", "livello_iniziale": 4000.0}])
    t = [tx("2026-01-06", "acquisto", -10000.0, k, quantita=10000),
         tx("2026-04-06", "cedola", 64.98, k, quantita=10000), tx("2026-04-06", "premio_opzione", 108.27, k, quantita=10000),
         tx("2026-07-06", "cedola", 64.98, k, quantita=10000), tx("2026-07-06", "premio_opzione", 108.22, k, quantita=10000)]
    return reg, k, t


def test_brc_non_dipende_dal_prezzo_di_mercato():
    reg, k, t = _brc()
    # prezzo di mercato in forte calo: NON deve cambiare il risultato
    r1 = calcola(t, reg.strumenti, "2026-06-30", "2026-09-30", ctx_semplice(prezzi={(k, "2026-09-30"): 80.0}))
    r2 = calcola(t, reg.strumenti, "2026-06-30", "2026-09-30", ctx_semplice(prezzi={(k, "2026-09-30"): 105.0}))
    assert r1["blocchi"]["scadenza"]["rendimento_periodo"] == pytest.approx(r2["blocchi"]["scadenza"]["rendimento_periodo"])
    assert r1["posizioni"][0]["stato_prezzo"] == "al_costo"


def test_brc_rendimento_trimestrale_circa_una_cedola():
    reg, k, t = _brc()
    r = calcola(t, reg.strumenti, "2026-06-30", "2026-09-30", ctx_semplice())
    rend = r["blocchi"]["scadenza"]["rendimento_periodo"]
    assert rend == pytest.approx(0.0173, abs=0.0005)     # 6.93%/4 ≈ 1.73%
    assert r["blocchi"]["scadenza"]["incassi"] == pytest.approx(173.20)


def test_cedola_maturata_prorata():
    reg, k, t = _brc()
    r = calcola(t, reg.strumenti, "2026-06-30", "2026-09-30", ctx_semplice())
    atteso = 10000 * 0.0693 / 4 * 86 / 92                  # 06.07 → 30.09 su un trimestre di 92 giorni
    assert r["posizioni"][0]["maturato"] == pytest.approx(atteso, rel=1e-6)


def test_rendimento_atteso_a_scadenza():
    reg, k, t = _brc()
    ctx = ctx_semplice()
    from core.performance import _replay
    pos = _replay(t, reg.strumenti, "2026-09-30", ctx)[k]
    att = rendimento_atteso(reg.strumenti[k], pos, t, "2026-09-30", ctx)
    assert att["completo"]
    # 4 cedole trimestrali (2 incassate + 2 future) su 10'000 ≈ 6.93% in un anno
    assert att["rendimento_totale_atteso"] == pytest.approx(0.0693, abs=0.0005)
    assert att["rimborso_atteso"] == pytest.approx(10000.0)
    assert att["rendimento_annuo_atteso"] > 0.06


def test_rendimento_atteso_senza_scadenza_non_inventa_nulla():
    reg, k, t = _brc()
    reg.strumenti[k]["scadenza"] = ""
    ctx = ctx_semplice()
    from core.performance import _replay
    pos = _replay(t, reg.strumenti, "2026-09-30", ctx)[k]
    assert rendimento_atteso(reg.strumenti[k], pos, t, "2026-09-30", ctx)["completo"] is False


# ───────────────────────── barriera ─────────────────────────
@pytest.mark.parametrize("spx,sx5e,semaforo,peggiore", [
    (5000, 4000, "verde", None),       # perf 100% -> buffer 40%
    (4500, 3600, "verde", None),       # 90% -> 33%
    (3500, 3600, "giallo", "S&P 500"),  # 70% -> 14%
    (3100, 3600, "rosso", "S&P 500"),   # 62% -> 3%
])
def test_semaforo_barriera(spx, sx5e, semaforo, peggiore):
    reg, k, _ = _brc()
    r = rischio_barriera(reg.strumenti[k], "2026-09-30", ctx_semplice(spot={"SPX": spx, "SX5E": sx5e}))
    assert r["completo"] and r["semaforo"] == semaforo
    if peggiore:
        assert r["peggiore"] == peggiore


def test_barriera_senza_prezzi_non_dichiara_sicurezza():
    reg, k, _ = _brc()
    r = rischio_barriera(reg.strumenti[k], "2026-09-30", ctx_semplice(spot={"SPX": 5000}))   # manca SX5E
    assert r["completo"] is False


# ───────────────────────── report complessivo ─────────────────────────
def test_totale_e_liquidita_in_valuta_base():
    reg, k, t = _brc()
    kk = reg.assicura(isin="FR0010655746", simbolo="CS1", nome="AMND IBEX 35 UCI ETF", valuta="EUR")
    t.append(tx("2026-04-22", "acquisto", -1853.15, kk, quantita=4))
    t.append(tx("2026-07-01", "costo_custodia", -18.0, "", valuta="CHF"))
    fx = {("CHF", "EUR"): 1.05, ("EUR", "CHF"): 0.95}
    prezzi = {(kk, "2026-06-30"): 480.0, (kk, "2026-09-30"): 500.0}
    r = calcola(t, reg.strumenti, "2026-06-30", "2026-09-30", ctx_semplice(fx=fx, prezzi=prezzi), saldi_liquidita={"EUR": 11085.75, "CHF": 0.0})
    assert r["liquidita"]["totale"] == pytest.approx(11085.75)
    assert r["totale"]["costi_periodo"] == pytest.approx(-18.0 * 1.05)
    assert r["valore_portafoglio"] == pytest.approx(r["valore_titoli"] + 11085.75)
    assert r["allocazione"]["strutturato"] >= 10000 and r["allocazione"]["etf_azioni"] == pytest.approx(2000.0)


def test_strutturato_sempre_al_100_per_cento_e_cedole_incassate():
    reg, k, t = _brc()
    reg.strumenti[k]["valutazione"] = "nominale"
    t[0] = tx("2026-01-06", "acquisto", -9950.0, k, quantita=10000)        # comprato al 99.5%
    r = calcola(t, reg.strumenti, "2026-06-30", "2026-09-30", ctx_semplice(prezzi={(k, "2026-09-30"): 70.0}))
    pos = r["posizioni"][0]
    assert pos["valore"] == pytest.approx(10000.0) and pos["maturato"] == 0.0     # il prezzo di mercato non conta, niente cedola maturata
    assert pos["reddito_totale"] == pytest.approx(64.98 * 2 + 108.27 + 108.22)    # le cedole incassate fanno la performance
    assert r["cedole_future"] and r["attese"]                                     # e quelle future restano nell'analisi


def test_obbligazione_prezzo_in_percento_manuale():
    reg = Registro()
    k = reg.assicura(isin="IT0005657330", nome="BTP 2027", valuta="EUR", pct=True)
    reg.strumenti[k].update(categoria="obbligazione", valutazione="manuale", nav_manuale=[{"data": "2026-09-01", "nav": 101.5}])
    t = [tx("2026-02-03", "acquisto", -5997.6, k, quantita=6000)]
    r = calcola(t, reg.strumenti, "2026-06-30", "2026-09-30", ctx_semplice())
    assert r["posizioni"][0]["valore"] == pytest.approx(6000 * 1.015) and r["posizioni"][0]["prezzo"] == 101.5
