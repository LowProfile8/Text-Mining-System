"""Flusso completo nell'interfaccia: cliente → strategie (valute diverse) → prodotti → transazioni → portafoglio in diretta → report → home (mercato simulato, archivio temporaneo)."""
import sys, tempfile
from datetime import date
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from streamlit.testing.v1 import AppTest

from core import dati, db
import core.calcolo as cc
from core.mercato import Mercato

APP = str(Path(__file__).resolve().parent.parent / "app.py")


def _at(vista, **st_):
    at = AppTest.from_file(APP, default_timeout=120)
    at.session_state["_autenticato"] = True
    at.session_state["vista"] = vista
    for k, v in st_.items():
        at.session_state[k] = v
    return at


def _bt(at, testo):
    b = [b for b in at.button if b.label == testo] or [b for b in at.button if testo in b.label]
    assert b, (testo, [x.label for x in at.button])
    return b[0]


def _ok(at):
    assert not at.exception, [e.value for e in at.exception]


class Finta:
    nome = "sim"
    def chiusura(self, t, d): return (d, {"VHYL.L": 66.0, "^GSPC": 5400.0, "VHYL": 66.0}.get(t, 66.0))
    def cambio(self, da, a, d): return (d, {("EUR", "CHF"): 0.93, ("USD", "CHF"): 0.80, ("USD", "EUR"): 0.86, ("EUR", "USD"): 1.16}.get((da, a), 1.0))


def test_flusso_completo():
    db._archivio = db.ArchivioLocale(Path(tempfile.mkdtemp()))
    cc.mercato_reale = lambda manuali=None, snapshot=None: Mercato(Finta(), manuali=manuali)

    # 1 cliente
    at = _at("clienti"); at.run()
    at.button(key="nc_apri").click().run()
    at.text_input(key="nc_nome").set_value("Mario"); at.text_input(key="nc_cogn").set_value("Rossi")
    _bt(at, "Crea cliente").click().run(); _ok(at)
    cid = at.session_state["cli_id"]

    # 2 due strategie con valute diverse
    at = _at("cliente", cli_id=cid); at.run()
    at.selectbox(key="npf_val").set_value("EUR")
    _bt(at, "Crea").click().run(); _ok(at)
    at = _at("cliente", cli_id=cid); at.run()
    at.selectbox(key="npf_val").set_value("USD")
    _bt(at, "Crea").click().run(); _ok(at)
    pfs = dati.carica_cliente(cid)["portafogli"]
    assert [p["valuta"] for p in pfs] == ["EUR", "USD"]
    pid = pfs[0]["id"]

    def pannello(a, nome):
        a.session_state[f"pan_{pid}"] = nome

    # 3 aggiungo un BRC (importo = nominale) e un ETF (ticker + borsa)
    a = _at("cliente", cli_id=cid, cli_pf=pid); pannello(a, "add"); a.run(); _ok(a)
    pre = f"np_{pid}_0"
    a.radio(key=f"{pre}_tipo").set_value("Prodotto strutturato").run()
    a.selectbox(key=f"{pre}_sub_Prodotto strutturato").set_value("Barrier Reverse Convertible")
    a.text_input(key=f"{pre}_nome").set_value("6.93% BRC Multi")
    a.selectbox(key=f"{pre}_val").set_value("EUR")
    a.number_input(key=f"{pre}_ced").set_value(6.93); a.number_input(key=f"{pre}_bar").set_value(60.0); a.selectbox(key=f"{pre}_fr").set_value(4)
    a.selectbox(key=f"{pre}_osv").set_value("americana")
    a.number_input(key=f"{pre}_strutturato_1_inv").set_value(20000.0); a.number_input(key=f"{pre}_strutturato_1_p").set_value(99.0)
    a.date_input(key=f"{pre}_data").set_value(date(2026, 1, 6))
    _bt(a, "Aggiungi il prodotto").click().run(); _ok(a)
    c = dati.carica_cliente(cid)
    t = [x for x in c["transazioni"] if x["tipo"] == "acquisto"][0]
    assert t["quantita"] == 20000.0 and t["importo_lordo"] == pytest.approx(19800.0) and t["prezzo_in_percento"]
    assert a.session_state[f"np_gen_{pid}"] == 1                                   # i campi ripartono vuoti

    a = _at("cliente", cli_id=cid, cli_pf=pid); pannello(a, "add"); a.run()
    pre = f"np_{pid}_0"
    a.radio(key=f"{pre}_tipo").set_value("ETF").run()
    a.text_input(key=f"{pre}_nome").set_value("Vanguard High Div"); a.selectbox(key=f"{pre}_val").set_value("USD")
    a.text_input(key=f"{pre}_tick").set_value("vhyl"); a.selectbox(key=f"{pre}_borsa").set_value("Londra (LSE)")
    a.multiselect(key=f"{pre}_set_sel").set_value(["Finanziario", "Tecnologia"])
    a.multiselect(key=f"{pre}_are_sel").set_value(["Mondo", "Stati Uniti"])
    a.radio(key=f"{pre}_modo_etf_azioni").set_value("Quantità").run()
    a.number_input(key=f"{pre}_etf_azioni_0_p").set_value(55.0); a.number_input(key=f"{pre}_etf_azioni_0_q").set_value(100.0)
    a.date_input(key=f"{pre}_data").set_value(date(2026, 2, 3))
    _bt(a, "Aggiungi il prodotto").click().run(); _ok(a)
    reg = dati.carica_registro()
    etf = next(s for s in reg.strumenti.values() if s["categoria"] == "etf_azioni")
    brc = next(s for s in reg.strumenti.values() if s["categoria"] == "strutturato")
    assert etf["ticker"] == "VHYL" and etf["ticker_mercato"] == "VHYL.L" and etf["ticker_controllo"] == "vhyl.uk"
    assert etf["settori"] == {"Finanziario": 0.5, "Tecnologia": 0.5} and etf["aree"] == {"Mondo": 0.5, "Stati Uniti": 0.5}
    assert brc["valutazione"] == "nominale" and brc["osservazione"] == "americana"

    # 4 deposito a termine: chiede se aggiornare il capitale
    a = _at("cliente", cli_id=cid, cli_pf=pid); pannello(a, "add"); a.run()
    pre = f"np_{pid}_0"
    a.radio(key=f"{pre}_tipo").set_value("Deposito a termine").run()
    a.number_input(key=f"{pre}_deposito_0_inv").set_value(5000.0)
    _bt(a, "Aggiungi il prodotto").click().run(); _ok(a)
    assert a.session_state[f"cap_chiedi_{pid}"][0] == 5000.0
    assert next(s for s in dati.carica_registro().strumenti.values() if s["categoria"] == "deposito")

    # 5 incasso di una cedola con «Registra transazione», e una spesa di deposito
    a = _at("cliente", cli_id=cid, cli_pf=pid); pannello(a, "tx"); a.run(); _ok(a)
    pre = f"tx_{pid}_0"
    a.selectbox(key=f"{pre}_tipo").set_value("cedola")
    a.date_input(key=f"{pre}_d").set_value(date(2026, 4, 6)); a.number_input(key=f"{pre}_i").set_value(173.25)
    _bt(a, "Registra").click().run(); _ok(a)
    a = _at("cliente", cli_id=cid, cli_pf=pid); pannello(a, "tx"); a.run()
    a.selectbox(key=f"{pre}_tipo").set_value("costo_custodia").run()
    a.number_input(key=f"{pre}_i").set_value(25.0)
    _bt(a, "Registra").click().run(); _ok(a)
    tx = dati.carica_cliente(cid)["transazioni"]
    assert any(t["tipo"] == "cedola" and t["importo_cassa"] == 173.25 for t in tx) and any(t["tipo"] == "costo_custodia" and t["importo_cassa"] == -25.0 for t in tx)

    # 6 capitale e liquidità per differenza
    c = dati.carica_cliente(cid); c["portafogli"][0]["capitale"] = 50000.0; dati.salva_cliente(c)
    a = _at("cliente", cli_id=cid, cli_pf=pid); a.run(); _ok(a)
    _bt(a, "Calcola la liquidità").click().run(); _ok(a)
    liq = next(s for s in dati.carica_registro().strumenti.values() if s["categoria"] == "liquidita")
    assert any(t["strumento"] == liq["chiave"] and t["quantita"] > 0 for t in dati.carica_cliente(cid)["transazioni"])

    # 6b stato «live» vecchio con stringhe nei problemi di prezzo: non deve più andare in errore
    c = dati.carica_cliente(cid); c["portafogli"][0].setdefault("live", {})["problemi_prezzi"] = ["vecchio formato"]; dati.salva_cliente(c)
    a = _at("cliente", cli_id=cid, cli_pf=pid); a.run(); _ok(a)

    # 6c vendita di un prodotto: passa fra i venduti
    a = _at("cliente", cli_id=cid, cli_pf=pid); pannello(a, "sell"); a.run(); _ok(a)
    pre = f"sell_{pid}_0"
    chiavi_attive = a.selectbox(key=f"{pre}_k").options
    a.selectbox(key=f"{pre}_tipo").set_value("vendita")
    a.number_input(key=f"{pre}_i").set_value(1000.0)
    _bt(a, "Registra").click().run(); _ok(a)
    assert any(t["tipo"] == "vendita" and t["importo_cassa"] == 1000.0 for t in dati.carica_cliente(cid)["transazioni"])

    # 7 panoramica in diretta
    a = _at("cliente", cli_id=cid, cli_pf=pid); a.run(); _ok(a)
    L = dati.carica_cliente(cid)["portafogli"][0]["live"]
    assert L["errore"] is None and L["valore"] > 0 and L["proventi"] == pytest.approx(173.25) and "liquidita" in L["allocazione"]
    assert any("Performance" == m.label for m in a.metric)

    # 8 report: periodo libero, cambi da confermare, PDF, riquadro che si richiude
    a = _at("cliente", cli_id=cid, cli_pf=pid); a.session_state[f"st_repopen_{pid}"] = True; a.run(); _ok(a)
    a.selectbox(key=f"rep_tipo_{pid}").set_value("Personalizzato (date a scelta)").run()
    a.date_input(key=f"rep_da_{pid}").set_value(date(2026, 1, 1)); a.date_input(key=f"rep_a_{pid}").set_value(date(2026, 10, 15))
    a.run()
    assert f"rep_fxok_{pid}_2026-10-15" in a.session_state or any("Conferma i tassi" in b.label for b in a.button), "i cambi vanno confermati prima del calcolo"
    _bt(a, "Conferma i tassi").click().run(); _ok(a)
    _bt(a, "Calcola").click().run(); _ok(a)
    g = [b for b in a.button if "Genera PDF" in b.label][0]
    if g.proto.disabled:                                                           # il BRC non ha sottostanti: lo si può forzare, ma il programma lo segnala
        a.checkbox(key=f"rep_forza_schede_{pid}").check().run(); _ok(a)
        g = [b for b in a.button if "Genera PDF" in b.label][0]
    assert not g.proto.disabled
    g.click().run(); _ok(a)
    assert a.session_state[f"rep_pdf_{pid}"][0][:4] == b"%PDF"
    open("/tmp/report_prova.pdf", "wb").write(a.session_state[f"rep_pdf_{pid}"][0])
    assert not a.session_state[f"st_repopen_{pid}"]
    assert dati.elenco_report()

    # 9 home e altre viste
    h = _at("home"); h.run(); _ok(h)
    assert any(m.label == "Clienti" for m in h.metric)
    for v in ("clienti", "report", "archivio_report"):
        x = _at(v, cli_id=cid); x.run(); _ok(x)
    for tab_cli in range(1):
        x = _at("cliente", cli_id=cid, cli_pf=pfs[1]["id"]); x.run(); _ok(x)               # la seconda strategia (vuota) si apre senza errori

    # 10 elimina cliente
    a = _at("cliente", cli_id=cid, cli_pf=pid); a.run()
    _bt(a, "Elimina cliente").click().run()
    _bt(a, "Sì, elimina").click().run()
    assert dati.carica_cliente(cid) is None
