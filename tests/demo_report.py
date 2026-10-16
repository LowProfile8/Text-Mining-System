"""Report di prova: i due estratti PostFinance veri + dati di fantasia (acquisto BRC, BTP, prezzi e cambi simulati).
Serve solo a controllare layout e calcoli. Uso:  python3 tests/demo_report.py  ->  dati_prova/demo_report.pdf"""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import dati, db
from core.anagrafica import Registro
from core.mercato import Mercato
from core.parser_postfinance import parse
from core.performance import Contesto, calcola
from core.report_pdf import genera_pdf

db._archivio = db.ArchivioLocale(Path(tempfile.mkdtemp()))
cli = dati.nuovo_cliente("Luigi Longobardi", "CHF", rischio=2)
reg = Registro()
for f in ("/mnt/user-data/uploads/Estrattoconto_2.pdf", "/mnt/user-data/uploads/Estrattoconto.pdf"):
    dati.importa_estratto(cli, parse(f).a_dict(), reg)

# ── dati di fantasia (NON reali) ──
brc = reg.strumenti["SYM:AGARTQ"]
brc.update(scadenza="2028-01-06", barriera_pct=60.0, confermato=True, isin="CH0000000001",
           sottostanti=[{"ticker": "^GSPC", "nome": "S&P 500", "livello_iniziale": 5000.0}, {"ticker": "^STOXX50E", "nome": "Euro Stoxx 50", "livello_iniziale": 4800.0},
                        {"ticker": "^SSMI", "nome": "SMI", "livello_iniziale": 12000.0}])
dati.aggiungi_movimento_manuale(cli, data="2026-01-06", tipo="acquisto", valuta="EUR", importo_cassa=-10000.0, quantita=10000, strumento="SYM:AGARTQ", titolo="Acquisto BRC (dato di prova)")
vh = reg.strumenti["SYM:VHYL"]; vh.update(valuta="USD", ticker_mercato="VHYL.L")
dati.aggiungi_movimento_manuale(cli, data="2026-03-10", tipo="acquisto", valuta="USD", importo_cassa=-805.0, quantita=13, strumento="SYM:VHYL", titolo="Acquisto VHYL (dato di prova)")
k_btp = reg.assicura(isin="IT0005657330", nome="BTP 2,1% 26/08/2027", valuta="EUR", pct=True)
reg.strumenti[k_btp].update(categoria="obbligazione", valutazione="scadenza", cedola_annua_pct=2.1, frequenza_cedola=2, scadenza="2027-08-26", data_emissione="2026-02-26", confermato=True)
dati.aggiungi_movimento_manuale(cli, data="2026-02-03", tipo="acquisto", valuta="EUR", importo_cassa=-5997.6, quantita=6000, strumento=k_btp, titolo="Acquisto BTP (dato di prova)")
cs1 = reg.strumenti["FR0010655746"]; cs1.update(ticker_mercato="CS1.PA")
dati.completa_strumenti(cli, reg)
reg.strumenti["FR0010655746"]["aree"] = {"Europa": 1.0}
reg.strumenti["SYM:AGARTQ"]["aree"] = {"Stati Uniti": 1 / 3, "Europa": 1 / 3, "Svizzera": 1 / 3}

PX = {("CS1.PA", "2026-06-30"): 471.0, ("CS1.PA", "2026-09-30"): 506.0, ("VHYL.L", "2026-06-30"): 63.0, ("VHYL.L", "2026-09-30"): 66.4,
      ("^GSPC", "2026-09-30"): 5400.0, ("^STOXX50E", "2026-09-30"): 4500.0, ("^SSMI", "2026-09-30"): 11200.0}
FX = {("EUR", "CHF"): 0.93, ("USD", "CHF"): 0.80, ("CHF", "EUR"): 1 / 0.93, ("USD", "EUR"): 0.86, ("EUR", "USD"): 1.16}


class Finta:
    nome = "dati simulati"
    def chiusura(self, t, d): return (d, PX.get((t, d))) if PX.get((t, d)) else None
    def cambio(self, da, a, d): return (d, FX[(da, a)]) if (da, a) in FX else None


m = Mercato(Finta())
ctx = Contesto(base="CHF", fx=m.fx, prezzo=m.prezzo, spot=m.spot)
ris = calcola(dati.transazioni_ordinate(cli), reg.strumenti, "2026-06-30", "2026-09-30", ctx, saldi_liquidita=dati.saldi_a_data(cli, "2026-09-30"))
commento = "Nel terzo trimestre il portafoglio ha incassato la cedola trimestrale del BRC e il dividendo dell'ETF VHYL.\nLa strategia resta invariata: manteniamo i prodotti strutturati fino a scadenza."
pdf = genera_pdf(ris, cli, "Trimestrale", commento)
out = Path(__file__).resolve().parent.parent / "dati_prova"
out.mkdir(exist_ok=True)
(out / "demo_report.pdf").write_bytes(pdf)
print("PDF", len(pdf), "byte | avvisi:", ris["avvisi"])
print("totale", {k: (round(v, 4) if isinstance(v, float) else v) for k, v in ris["totale"].items()})
for k, b in ris["blocchi"].items():
    print(k, {a: (round(v, 4) if isinstance(v, float) else v) for a, v in b.items()})
