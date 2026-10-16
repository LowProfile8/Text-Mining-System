"""Costanti dell'applicazione."""

from pathlib import Path

NOME_STUDIO = "Athena Advisory Group"
TITOLO_PAGINA = "Athena — report finanziari"
RADICE = Path(__file__).resolve().parent.parent
ASSET = RADICE / "assets"
DATI_LOCALI = RADICE / "dati_locali"          # usata solo se Supabase non è collegato
CACHE_PREZZI = DATI_LOCALI / "cache_prezzi.json"

VALUTE_BASE = ["CHF", "EUR", "USD"]
PERIODI = {"Trimestrale": 3, "Semestrale": 6, "Annuale": 12}

# Categorie di strumento (macro) e relative sotto-categorie
CATEGORIE = {
    "liquidita": "Liquidità",
    "deposito": "Depositi a termine",
    "obbligazione": "Obbligazioni",
    "etf_azioni": "Azioni / ETF",
    "opzione": "Opzioni",
    "strutturato": "Prodotti strutturati",
    "alternativo": "Investimenti alternativi",
}
SOTTOCATEGORIE_STRUTTURATI = [
    "Barrier Reverse Convertible", "Capital Protection Note", "Bullish Shark Note",
    "Bearish Shark Note", "Airbag Certificate", "Altro strutturato",
]
SOTTOCATEGORIE_ALTERNATIVI = ["Fondo immobiliare", "Private equity", "Hedge fund", "Criptovaluta", "Altro alternativo"]
SOTTOCATEGORIE_STRUTTURATI += ["Autocallable", "Bonus Certificate", "Discount Certificate", "Tracker / Participation", "Shark Note con rebate (knock-out)"]
OSSERVAZIONI = {"europea": "Europea (A scadenza)", "americana": "Americana (Continua)"}

# Scelta guidata alla creazione di un prodotto: prima il tipo, poi il menu a tendina dei soli sottotipi pertinenti.
# etichetta -> (categoria interna, sottotipi)
TIPI_PRODOTTO = {
    "Azione": ("etf_azioni", ["Azione ordinaria", "Azione estera / ADR"]),
    "ETF": ("etf_azioni", ["ETF azionario", "ETF obbligazionario", "ETF materie prime", "ETF multi-asset", "ETF tematico"]),
    "Obbligazione": ("obbligazione", ["Governativa", "Corporate", "Convertibile", "Subordinata", "Altra obbligazione"]),
    "Deposito a termine": ("deposito", ["Deposito a termine"]),
    "Liquidità": ("liquidita", ["Conto / liquidità"]),
    "Opzione": ("opzione", ["Call acquistata", "Put acquistata", "Call venduta (covered call)", "Put venduta (cash secured)", "Altra opzione"]),
    "Prodotto strutturato": ("strutturato", [x for x in SOTTOCATEGORIE_STRUTTURATI]),
    "Alternativo": ("alternativo", ["Fondo immobiliare", "Private equity", "Hedge fund", "Criptovaluta", "Altro alternativo"]),
}
SETTORI = [
    "Tecnologia", "Software e cloud", "Semiconduttori", "Intelligenza artificiale", "Calcolo quantistico", "Cybersecurity", "Robotica e automazione",
    "Difesa", "Spazio e aerospaziale", "Healthcare", "Biotecnologie", "Finanziario", "Banche", "Assicurazioni", "Industriale", "Consumi discrezionali",
    "Beni di lusso", "Consumi di base", "Alimentare e bevande", "Automotive e veicoli elettrici", "Energia", "Energie rinnovabili", "Nucleare e uranio",
    "Servizi di pubblica utilità", "Acqua", "Materie prime", "Oro e metalli preziosi", "Metalli industriali", "Agricoltura", "Immobiliare",
    "Comunicazione e media", "Telecomunicazioni", "Logistica e trasporti", "Turismo e tempo libero", "Cripto e blockchain",
    "Governativo", "Obbligazionario corporate", "Liquidità", "Diversificato", "Altri settori",
]
AREE_GEO = [
    "Mondo", "Stati Uniti", "Nord America", "Europa", "Italia", "Germania", "Francia", "Regno Unito", "Spagna", "Paesi Bassi", "Belgio", "Austria",
    "Portogallo", "Irlanda", "Paesi nordici", "Svizzera", "Asia", "Giappone", "Cina", "India", "Asia-Pacifico", "Mercati emergenti", "America Latina",
    "Medio Oriente e Africa", "Altro",
]
# Aree che fanno parte dell'Europa (per aggregare nei grafici se serve)
AREE_EUROPA = {"Europa", "Italia", "Germania", "Francia", "Regno Unito", "Spagna", "Paesi Bassi", "Belgio", "Austria", "Portogallo", "Irlanda", "Paesi nordici", "Svizzera"}

# Borse di riferimento: etichetta -> (suffisso Yahoo, suffisso Stooq o None). Il ticker si scrive UNA volta; il suffisso lo aggiunge il programma.
BORSE = {
    "USA · NYSE / Nasdaq / AMEX": ("", ".us"),
    "Borsa Italiana (Milano)": (".MI", None),
    "Xetra (Germania)": (".DE", ".de"),
    "Francoforte": (".F", None),
    "Euronext Parigi": (".PA", None),
    "Euronext Amsterdam": (".AS", None),
    "Euronext Bruxelles": (".BR", None),
    "Euronext Lisbona": (".LS", None),
    "Londra (LSE)": (".L", ".uk"),
    "SIX Swiss Exchange": (".SW", None),
    "Madrid": (".MC", None),
    "Vienna": (".VI", None),
    "Stoccolma": (".ST", None),
    "Copenaghen": (".CO", None),
    "Helsinki": (".HE", None),
    "Oslo": (".OL", None),
    "Toronto": (".TO", None),
    "Tokyo": (".T", ".jp"),
    "Hong Kong": (".HK", ".hk"),
    "Sydney (ASX)": (".AX", None),
    "Indice / criptovaluta / altro (ticker completo)": ("", None),
}
BORSA_DEFAULT = "USA · NYSE / Nasdaq / AMEX"

# Come si valuta uno strumento nel report
#   mercato  -> quantità x prezzo di mercato
#   scadenza -> al costo (+ cedole): si porta a scadenza, le oscillazioni non contano
#   manuale  -> ultimo NAV inserito a mano (fondi non quotati)
VALUTAZIONI = {"mercato": "A mercato (prezzo da Yahoo)", "manuale": "Prezzo / NAV inserito a mano", "nominale": "Al 100% del nominale (strutturati)", "scadenza": "Al costo + cedola maturata (depositi)"}
VALUTAZIONE_DEFAULT = {
    "obbligazione": "manuale", "strutturato": "nominale", "etf_azioni": "mercato",
    "opzione": "mercato", "alternativo": "manuale", "liquidita": "scadenza", "deposito": "scadenza",
}

# Soglie del semaforo «distanza dalla barriera» (calo ancora possibile del sottostante peggiore)
SOGLIA_VERDE = 0.20     # oltre il 20% di distanza: tutto ordinario
SOGLIA_GIALLO = 0.10    # 20% → 10%: da seguire
SOGLIA_ARANCIO = 0.05   # 10% → 5%: attenzione; sotto il 5%: critico

# Tolleranza del doppio controllo fra le due fonti di prezzo
TOLLERANZA_PREZZI = 0.015

DISCLAIMER = (
    "Il presente documento ha scopo puramente informativo e non costituisce offerta, raccomandazione "
    "o consulenza legale o fiscale. I dati provengono dagli estratti conto delle banche depositarie e da fonti di mercato "
    "pubbliche; i rendimenti passati non sono indicativi di quelli futuri. Per i prodotti portati a scadenza la valutazione "
    "al costo non riflette il prezzo di mercato attuale, che può essere inferiore o superiore."
)
