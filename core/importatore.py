"""Riconosce il tipo di PDF caricato e lo legge con il parser giusto."""

from __future__ import annotations

import io

from core import parser_postfinance, parser_posizioni, parser_ubs


def leggi_documento(file) -> tuple[str, object]:
    """Ritorna ('movimenti', Estratto) oppure ('posizioni', dict). Solleva ValueError se il formato non è noto."""
    dati = file.read() if hasattr(file, "read") else open(file, "rb").read()
    if hasattr(file, "seek"):
        file.seek(0)
    def nuovo():
        return io.BytesIO(dati)
    errori = []
    try:
        righe = parser_posizioni._righe(nuovo(), x_tolerance=1)
    except Exception as e:
        raise ValueError(f"PDF non leggibile ({e}). Se è una scansione/immagine, usa l'inserimento manuale.")
    if not righe:
        raise ValueError("Il PDF non contiene testo (è una scansione). Per i depositi a termine usa «Deposito a termine» in Movimenti.")
    if parser_posizioni.riconosci_performance(righe) or parser_posizioni.riconosci_ubs_patrimoniale(righe):
        return "posizioni", parser_posizioni.leggi_posizioni(nuovo())
    if parser_ubs.riconosci(righe):
        return "movimenti", parser_ubs.parse(nuovo())
    for p in (parser_postfinance,):
        try:
            return "movimenti", p.parse(nuovo())
        except ValueError as e:
            errori.append(str(e))
    raise ValueError("Formato non riconosciuto. Supportati: PostFinance, Swissquote e UBS (estratti conto, performance del portafoglio, estratto patrimoniale).")
