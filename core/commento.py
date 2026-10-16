"""Commento di 2-3 righe per il report, scritto da Claude sulla base dei numeri del report (modificabile prima di generare il PDF)."""

from __future__ import annotations

import urllib.parse


def _n(x, d=0):
    return f"{x:,.{d}f}".replace(",", "’")


def _p(x):
    return "n.d." if x is None else f"{100 * x:+.2f}%"


def testo_prompt(ris: dict, cliente: dict, tipo: str) -> str:
    base, t = ris["periodo"]["base"], ris["totale"]
    att = ris.get("attivi", [])
    prodotti = "; ".join(f"{r['nome']} ({_p(r.get('rendimento'))})" for r in att[:8])
    return (
        "Scrivi, in italiano, un commento di 2 o 3 righe per il report " + tipo.lower() + " destinato al cliente (tono professionale, sobrio e chiaro). "
        "Usa solo i dati qui sotto, non inventare nulla, non dare consigli di investimento e non fare previsioni.\n\n"
        f"Periodo: {ris['periodo']['da']} → {ris['periodo']['a']} · valuta {base}\n"
        f"Valore del portafoglio: {base} {_n(ris['valore_portafoglio'])}\n"
        f"Performance del periodo: {_p(t.get('rendimento_periodo'))} (risultato nominale {base} {_n(t.get('pl', 0))})\n"
        f"Performance dall'inizio: {_p(t.get('rendimento_dall_inizio'))} (risultato nominale {base} {_n(t.get('pl_dall_inizio') or 0)})\n"
        f"Proventi incassati nel periodo: {base} {_n(sum(p['importo_base'] for p in ris['proventi']))}\n"
        f"Prodotti: {prodotti or 'nessuno'}\n"
        "Rispondi solo con il testo del commento."
    )


def chiedi_claude(prompt: str, chiave: str, modello: str = "claude-sonnet-5-5") -> str:
    """Chiama l'API di Anthropic (serve ANTHROPIC_API_KEY nei Secrets). Solleva un'eccezione leggibile se non riesce."""
    import requests
    r = requests.post("https://api.anthropic.com/v1/messages", timeout=60,
                      headers={"x-api-key": chiave, "anthropic-version": "2023-06-01", "content-type": "application/json"},
                      json={"model": modello, "max_tokens": 400, "messages": [{"role": "user", "content": prompt}]})
    if r.status_code != 200:
        raise RuntimeError(f"Claude ha risposto {r.status_code}: {r.text[:160]}")
    return "".join(b.get("text", "") for b in r.json().get("content", [])).strip()


def link_claude(prompt: str) -> str:
    return "https://claude.ai/new?q=" + urllib.parse.quote(prompt[:5000])
