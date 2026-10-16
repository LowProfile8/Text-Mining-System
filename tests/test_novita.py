from core import movimenti
from core.cedole_suggerite import suggerisci


def test_cedole_suggerite_saltano_incassate_e_prima_acquisto():
    s = {"k": {"nome": "BRC", "categoria": "strutturato", "sottocategoria": "Barrier Reverse Convertible", "cedola_annua_pct": 8, "frequenza_cedola": 4,
               "data_emissione": "2026-01-15", "scadenza": "2027-01-15", "valuta": "EUR"}}
    tx = [{"strumento": "k", "data": "2026-02-20", "tipo": "acquisto", "quantita": 10000}, {"strumento": "k", "data": "2026-04-16", "tipo": "cedola", "quantita": None}]
    r = suggerisci(tx, s, "2026-10-16")
    assert [x["data"] for x in r] == ["2026-07-15", "2026-10-15"]
    assert r[0]["importo"] == 200.0 and not r[0]["condizionata"]


def test_movimenti_duplicato_e_riconciliazione():
    t = {"data": "2026-03-10", "tipo": "costo", "importo_cassa": -50.0, "valuta": "CHF", "banca": "PF", "conto": "1"}
    assert movimenti.e_duplicato([t], dict(t))
    assert not movimenti.e_duplicato([t], {**t, "importo_cassa": -51.0})
    saldi = [{"banca": "PF", "conto": "1", "valuta": "CHF", "data": "2026-02-28", "saldo": 1000.0}, {"banca": "PF", "conto": "1", "valuta": "CHF", "data": "2026-03-31", "saldo": 950.0}]
    r = movimenti.riconcilia([t], saldi)
    assert r[0]["esito"] == "punto di partenza" and r[1]["esito"] == "ok"
    r = movimenti.riconcilia([], saldi)
    assert r[1]["esito"] == "errore" and abs(r[1]["differenza"] + 50) < 1e-9


def test_stato_riga():
    assert movimenti.stato_riga({"tipo": "cedola", "importo_cassa": 10, "strumento": ""}) == "da completare"
    assert movimenti.stato_riga({"tipo": "costo", "importo_cassa": -5, "fonte": "strategia"}) == "previsto"


def test_archivio_veloce_scrive_in_background_e_legge_dalla_cache():
    import time
    from core.db import ArchivioVeloce

    class Lento:
        nome = "lento"
        def __init__(self): self.d = {}
        def leggi(self, c, i): return self.d.get((c, i))
        def scrivi(self, c, i, x): time.sleep(0.2); self.d[(c, i)] = x
        def elenca(self, c): return [v for (cc, _), v in self.d.items() if cc == c]
        def elimina(self, c, i): self.d.pop((c, i), None)
        def verifica(self): return "attivo", ""

    base = Lento(); a = ArchivioVeloce(base)
    t0 = time.time()
    a.scrivi("clienti", "1", {"n": 1}); a.scrivi("clienti", "2", {"n": 2})
    assert time.time() - t0 < 0.1                       # non aspetta la rete
    assert a.leggi("clienti", "1") == {"n": 1} and len(a.elenca("clienti")) == 2
    x = a.leggi("clienti", "1"); x["n"] = 99
    assert a.leggi("clienti", "1") == {"n": 1}          # copie: modificare non sporca la cache
    a.attendi()
    assert base.d[("clienti", "2")] == {"n": 2}


def test_fonti_di_riserva_parser_e_catena():
    from core import fonti_extra as fe
    assert fe.tv_parse_scanner({"data": [{"s": "AMEX:DFND", "d": [41.25, "USD"]}]}) == (41.25, "USD")
    assert fe.tv_parse_scanner({"data": []}) is None
    assert fe.tv_parse_ricerca([{"symbol": "<em>DFND</em>", "exchange": "AMEX", "currency_code": "USD"}])[0]["simbolo"] == "DFND"
    assert fe.google_parse('<div data-last-price="1,234.50" data-currency-code="USD">') == (1234.5, "USD")
    assert fe.justetf_parse('<div class="val"><span>EUR</span> <span>123,45</span>') == (123.45, "EUR")

    class A:
        nome = "A"
        def ultimo(self, t, i, v): return None
    class B:
        nome = "B"
        def ultimo(self, t, i, v): return (10.0, "EUR", "B")
    stat = {}
    cat = fe.CatenaRiserva([A(), B()], stat)
    assert cat.ultimo("X", "", "EUR")[2] == "B"
    assert cat.ordinate()[0].nome == "A"                  # ordine fisso: la prima fonte resta la prima


def test_scadenza_automatica_chiude_il_prodotto():
    from core.scadenze import con_scadenze
    s = {"k": {"nome": "BRC", "categoria": "strutturato", "scadenza": "2026-06-01", "valuta": "EUR", "prezzo_in_percento": True}}
    tx = [{"id": "a", "strumento": "k", "data": "2025-06-01", "tipo": "acquisto", "quantita": 10000.0, "importo_cassa": -10000.0, "valuta": "EUR"}]
    nuovo, av = con_scadenze(tx, s, "2026-10-16")
    assert nuovo[-1]["tipo"] == "rimborso" and nuovo[-1]["importo_cassa"] == 10000.0 and av
    assert con_scadenze(tx, s, "2026-05-01")[0] == tx
    tx2 = tx + [{"id": "b", "strumento": "k", "data": "2026-06-01", "tipo": "rimborso", "quantita": 10000.0, "importo_cassa": 10000.0, "valuta": "EUR"}]
    assert con_scadenze(tx2, s, "2026-10-16")[0] == tx2
