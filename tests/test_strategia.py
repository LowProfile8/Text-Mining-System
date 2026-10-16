import sys, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from core import dati, db, live, strategia as stg
from core.anagrafica import Registro
from core.mercato import Mercato
from core.strategia_pdf import genera_pdf_strategia


def _setup():
    db._archivio = db.ArchivioLocale(Path(tempfile.mkdtemp()))
    c = dati.nuovo_cliente("Mario", "CHF", 3, cognome="Rossi")
    reg = Registro()
    k1 = reg.assicura(isin="CH0000000001", nome="6.93% BRC Multi", valuta="EUR", pct=True)
    reg.strumenti[k1].update(categoria="strutturato", sottocategoria="Barrier Reverse Convertible", valutazione="nominale", cedola_annua_pct=6.93, frequenza_cedola=4,
                             data_emissione="2026-01-06", scadenza="2028-01-06", barriera_pct=60.0, settori={"Diversificato": 1.0}, aree={"Europa": 0.5, "Stati Uniti": 0.5})
    k2 = reg.assicura(isin="IE00B8GKDB10", nome="Vanguard High Div ETF", valuta="USD")
    reg.strumenti[k2].update(categoria="etf_azioni", sottocategoria="ETF azionario", valutazione="mercato", ticker_mercato="VHYL.L", settori={"Finanziario": 0.5, "Tecnologia": 0.5}, aree={"Stati Uniti": 1.0})
    pf = dati.nuovo_portafoglio(c, "Strategia 1", 100000, "CHF")
    pf["cambi"] = {"USD": 0.8, "EUR": 0.93}
    return c, reg, pf, k1, k2


def test_acquisto_da_importo_investito_e_da_quantita():
    c, reg, pf, k1, k2 = _setup()
    t = stg.aggiungi_acquisto(c, pf, reg, k1, "2026-01-06", 99.5, 25.0, investito=20000.0)          # 20'000 di nominale investiti, pagati al 99.5%
    assert t["quantita"] == pytest.approx(20000.0) and t["importo_lordo"] == pytest.approx(20000 * 0.995)
    assert t["importo_cassa"] == pytest.approx(-(19900.0 + 25.0)) and t["portafoglio"] == pf["id"]
    t2 = stg.aggiungi_acquisto(c, pf, reg, k2, "2026-01-07", 55.0, 2.0, quantita=100)
    assert t2["importo_lordo"] == pytest.approx(5500.0) and t2["importo_cassa"] == pytest.approx(-5502.0)
    calc = stg.calcola(c, pf, reg)
    assert calc["totale"] == pytest.approx(20000 * 0.93 + 5500 * 0.8)             # capitale investito ora è sempre calcolato
    assert abs(sum(x["peso_eff_pct"] for x in calc["attive"]) - 100) < 1e-6
    assert calc["reddito_annuo"] == pytest.approx(20000 * 0.93 * 0.0693)
    assert genera_pdf_strategia(c, pf, calc)[:4] == b"%PDF"
    assert "BRC" in stg.testo_analisi(c, pf, calc)


def test_modifica_acquisto_ricalcola():
    c, reg, pf, k1, k2 = _setup()
    t = stg.aggiungi_acquisto(c, pf, reg, k1, "2026-01-06", 100.0, 0.0, investito=10000.0)
    stg.modifica_acquisto(t, reg.strumenti[k1], investito=15000.0)                   # cambia l'importo: la quantità segue
    assert t["quantita"] == pytest.approx(15000.0) and t["importo_cassa"] == pytest.approx(-15000.0)
    stg.modifica_acquisto(t, reg.strumenti[k1], prezzo=98.0)                         # cambia il prezzo: l'importo segue
    assert t["importo_lordo"] == pytest.approx(15000 * 0.98)


def test_incassi_e_costi_entrano_nella_performance():
    from core.performance import Contesto, calcola
    c, reg, pf, k1, k2 = _setup()
    stg.aggiungi_acquisto(c, pf, reg, k1, "2026-01-06", 100.0, 0.0, investito=10000.0)
    stg.registra_incasso(c, pf, reg, k1, "cedola", "2026-04-06", 173.25, imposta=0.0, nota="1° trimestre")
    stg.registra_incasso(c, pf, reg, k1, "premio_opzione", "2026-04-06", 100.0)
    stg.registra_costo(c, pf, "costo_custodia", "2026-06-30", 20.0, "CHF", "Custodia")
    v = dati.vista_portafoglio(c, pf["id"])
    ctx = Contesto(base="CHF", fx=lambda d, a, dt: 1.0 if d == a else 0.93, prezzo=lambda s, d: {"prezzo": None}, spot=lambda t, d: None)
    r = calcola(dati.transazioni_ordinate(v), reg.strumenti, "2026-01-05", "2026-06-30", ctx)
    assert r["posizioni"][0]["reddito_totale"] == pytest.approx((173.25 + 100.0) * 0.93)
    assert r["costi_dettaglio"]["custodia"] == pytest.approx(-20.0) or r["costi_dettaglio"]["custodia"] == pytest.approx(20.0)


def test_sostituzione_da_estratto():
    c, reg, pf, k1, k2 = _setup()
    stg.aggiungi_acquisto(c, pf, reg, k1, "2026-01-06", 100.0, 0.0, quantita=64516.0)
    est = {"banca": "PostFinance", "conto": "X", "movimenti": [{"data": "2026-01-07", "data_valuta": "2026-01-07", "tipo": "acquisto", "titolo": "BRC", "valuta": "EUR", "importo_cassa": -64000.0,
           "quantita": 64516.0, "prezzo": 99.2, "prezzo_in_percento": True, "importo_lordo": 64000.0, "commissione": 0.0, "tasse": 0.0, "rif": "R1", "isin": "CH0000000001", "nome": "BRC", "simbolo": ""}],
           "conti": {"EUR": {"saldo_finale": 0.0}}, "controlli": [], "avvisi": [], "quadra": True, "periodo_da": "2026-01-01", "periodo_a": "2026-01-31"}
    dati.importa_in_portafoglio(c, pf["id"], dati.importa_estratto, est, reg)
    brc = [t for t in dati.vista_portafoglio(c, pf["id"])["transazioni"] if t["strumento"] == k1]
    assert len(brc) == 1 and brc[0]["fonte"] == "estratto"


def test_portafogli_separati_con_valuta_propria():
    c, reg, pf, k1, k2 = _setup()
    pf2 = dati.nuovo_portafoglio(c, "Dollari", 0, "USD")
    assert pf2["valuta"] == "USD" and pf["valuta"] == "CHF"
    c["transazioni"].append({"id": "a", "data": "2026-01-01", "tipo": "deposito", "valuta": "CHF", "importo_cassa": 10, "portafoglio": pf2["id"]})
    assert len(dati.vista_portafoglio(c, pf2["id"])["transazioni"]) == 1 and not dati.vista_portafoglio(c, pf["id"])["transazioni"]


class Finta:
    nome = "sim"
    def chiusura(self, t, d): return (d, {"VHYL.L": 60.0}.get(t, 60.0))
    def cambio(self, da, a, d): return (d, {("EUR", "CHF"): 0.93, ("USD", "CHF"): 0.80, ("CHF", "EUR"): 1 / 0.93, ("CHF", "USD"): 1.25}.get((da, a), 1.0))


def test_live_e_aggregazione_tra_clienti():
    c, reg, pf, k1, k2 = _setup()
    stg.aggiungi_acquisto(c, pf, reg, k1, "2026-01-06", 100.0, 0.0, investito=10000.0)
    stg.aggiungi_acquisto(c, pf, reg, k2, "2026-02-03", 50.0, 0.0, quantita=100)
    stg.registra_incasso(c, pf, reg, k1, "cedola", "2026-04-06", 173.25)
    L = live.aggiorna(c, pf, reg, Mercato(Finta()))
    assert L["errore"] is None and L["valore"] > 0 and L["perf"] is not None and len(L["serie"]) >= 3
    assert L["proventi"] == pytest.approx(173.25 * 0.93)
    # strutturato al 100%: il prezzo di mercato non c'entra; ETF a 60 contro 50 pagati => +20%
    c2 = dati.nuovo_cliente("Anna", "CHF", cognome="Verdi")
    pf2 = dati.nuovo_portafoglio(c2, "S", 0, "CHF")
    stg.aggiungi_acquisto(c2, pf2, reg, k2, "2026-02-03", 50.0, 0.0, quantita=100)
    live.aggiorna(c2, pf2, reg, Mercato(Finta()))
    ag = live.aggrega([c, c2])
    assert ag["valore"] > 0 and ag["perf_media"] == pytest.approx((c["portafogli"][0]["live"]["perf"] + pf2["live"]["perf"]) / 2)   # peso uguale per cliente
    assert ag["serie"] and sum(ag["allocazione"].values()) == pytest.approx(ag["valore"])


def test_firma_cambia_con_i_dati():
    c, reg, pf, k1, k2 = _setup()
    f0 = live.firma(c, pf, reg)
    stg.aggiungi_acquisto(c, pf, reg, k1, "2026-01-06", 100.0, 0.0, investito=10000.0)
    assert live.firma(c, pf, reg) != f0


def test_primo_anno_e_pdf_strategia():
    c, reg, pf, k1, k2 = _setup()
    stg.aggiungi_acquisto(c, pf, reg, k1, "2026-01-06", 99.5, 25.0, investito=20000.0)
    calc = stg.calcola(c, pf, reg)
    pa = calc["primo_anno"]
    assert len(pa["righe"]) in (4, 5) and pa["totale"] > 0
    assert all(pa["da"] < r["data"] <= pa["a"] for r in pa["righe"])
    pdf = genera_pdf_strategia(c, pf, calc)
    assert pdf[:4] == b"%PDF"
    open("/tmp/strategia_prova.pdf", "wb").write(pdf)
