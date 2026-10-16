"""PDF della proposta di strategia da presentare al cliente (sfondo chiaro, stessa grafica del report)."""

from __future__ import annotations

import io
from datetime import date

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.platypus import BaseDocTemplate, Frame, KeepTogether, PageBreak, PageTemplate, Spacer, Table, TableStyle

from core.config import ASSET, CATEGORIE, NOME_STUDIO
from core.report_pdf import riga_rischio, GRIGIO, NERO, P, _img, _kpi, barra_ripartita, barre, dt, n, pct, tabella, torta, colors

DISCLAIMER_STRATEGIA = (
    "Questa è una proposta di strategia di investimento a scopo informativo, non un'offerta vincolante né una consulenza legale o fiscale. "
    "Prezzi, quantità e importi sono indicativi: all'acquisto possono differire. Le cedole indicate sono quelle previste dalle condizioni dei prodotti "
    "e dipendono, per i prodotti strutturati, dall'andamento dei sottostanti e dalla solvibilità dell'emittente. Il valore degli investimenti può scendere come salire; "
    "i rendimenti passati non sono indicativi di quelli futuri."
)


def _riga2(sx, dx, wx=84, wd=90):
    t = Table([[sx, dx]], colWidths=[wx * mm, wd * mm])
    t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0), ("TOPPADDING", (0, 0), (-1, -1), 4)]))
    return t


def genera_pdf_strategia(cliente: dict, pf: dict, calc: dict) -> bytes:
    base = pf["valuta"]
    tot = calc["totale"] or 1.0
    buf = io.BytesIO()
    larg, alt = A4
    logo = ASSET / "logo_pdf.png"
    from PIL import Image as PILImage
    lw0, lh0 = PILImage.open(logo).size
    titolo = "STRATEGIA DI INVESTIMENTO"
    oggi = date.today().strftime("%d.%m.%Y")

    def testata(canvas, doc, grande):
        canvas.saveState()
        lw = 52 * mm if grande else 34 * mm
        canvas.drawImage(str(logo), 18 * mm, alt - (14 * mm if grande else 11 * mm) - lw * lh0 / lw0, width=lw, height=lw * lh0 / lw0, mask="auto")
        canvas.setFillColor(NERO)
        if grande:
            canvas.setFont("Helvetica", 8.5); canvas.drawRightString(larg - 18 * mm, alt - 17 * mm, f"Sig. {cliente['nome']}")
            canvas.setFont("Helvetica-Bold", 11.5); canvas.drawRightString(larg - 18 * mm, alt - 22.5 * mm, titolo)
            canvas.setFont("Helvetica-Bold", 8.5); canvas.drawRightString(larg - 18 * mm, alt - 27.5 * mm, f"{pf['nome']} · {oggi}")
        else:
            canvas.setFont("Helvetica", 7.5); canvas.drawRightString(larg - 18 * mm, alt - 14 * mm, f"Sig. {cliente['nome']} · {titolo.title()} · {oggi}")
        canvas.setStrokeColor(colors.HexColor("#BBBBBB")); canvas.setLineWidth(0.5)
        canvas.line(18 * mm, 15 * mm, larg - 18 * mm, 15 * mm)
        canvas.setFont("Helvetica", 6.5); canvas.setFillColor(GRIGIO)
        canvas.drawString(18 * mm, 11 * mm, f"{NOME_STUDIO} · Bissone (TI)")
        canvas.drawRightString(larg - 18 * mm, 11 * mm, f"Pagina {doc.page}")
        canvas.restoreState()

    doc = BaseDocTemplate(buf, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=36 * mm, bottomMargin=20 * mm,
                          title=f"{titolo} – {cliente['nome']}", author=NOME_STUDIO)
    f1 = Frame(18 * mm, 20 * mm, larg - 36 * mm, alt - 70 * mm, leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0, id="f1")
    doc.addPageTemplates([PageTemplate(id="tutte", frames=[f1], onPage=lambda c, d: testata(c, d, True))])      # stessa intestazione in tutte le pagine

    el = []
    rend = calc["rendimento_cedolare"]
    el.append(_kpi([
        ("Capitale investito", f"{base} {n(calc['totale'], 0)}", "capitale effettivamente allocato"),
        ("Prodotti in portafoglio", str(len(calc["attive"])), "vedi elenco a pagina 3"),
        ("Reddito annuo atteso", f"{base} {n(calc['reddito_annuo'], 0)}", f"{pct(rend, 1)} del capitale investito" if rend else "cedole e proventi previsti"),
        ("Liquidità", f"{base} {n(max(calc['allocazione'].get('liquidita', 0.0), 0), 0)}", "non investita"),
    ]))
    el.append(Spacer(1, 6))
    el.append(riga_rischio(cliente.get("rischio"), "cerchi"))
    el.append(Spacer(1, 4))
    el.append(P("COME PROPONIAMO DI INVESTIRE", "titolo"))
    for titolo_t, dati_, etich in (("Per tipo di investimento", calc["allocazione"], CATEGORIE), ("Per valuta", calc["valute"], {})):
        righe = [[etich.get(k, k), pct(v / tot, 1), n(v, 0)] for k, v in sorted(dati_.items(), key=lambda kv: -kv[1]) if v > 0]
        righe.append(["Totale", "100,0%", n(sum(dati_.values()), 0)])
        t = tabella([titolo_t, "%", f"Importo ({base})"], righe, [38, 14, 26], extra=[("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"), ("LINEABOVE", (0, -1), (-1, -1), 0.6, NERO)])
        el.append(_riga2(t, _img(torta(dati_, etich, 88), 90)))
    el.append(Spacer(1, 6))
    el.append(KeepTogether([P("L'IDEA DELLA STRATEGIA", "titolo"), P(
        "I prodotti sono scelti per bilanciare reddito periodico (cedole, interessi, dividendi) e crescita, in linea con il profilo di rischio del cliente. "
        "Le pagine seguenti mostrano in quali settori e aree geografiche si investe e l'elenco dei prodotti consigliati.", "testo")]))

    el.append(PageBreak())
    el.append(P("DOVE INVESTIAMO", "titolo"))
    sett = {k: v for k, v in calc["settori"].items() if v > 0}
    aree = {k: v for k, v in calc["aree"].items() if v > 0}
    el.append(_riga2([P("Per settore", "sotto"), _img(barre(sett, mm=84), 86)], [P("Per area geografica", "sotto"), _img(barre(aree, mm=84), 86)], 87, 87))
    el.append(P("Le esposizioni sono calcolate sul controvalore dei prodotti. Per ETF e indici si usa la composizione di riferimento: i valori sono indicativi.", "piccolo"))
    pa = calc.get("primo_anno") or {}
    if pa.get("righe"):
        tot_pa = pa["totale"]
        el.append(KeepTogether([P("QUANTO DISTRIBUISCE IL PORTAFOGLIO NEL PRIMO ANNO", "titolo"),
                                _kpi([("Distribuzione prevista nei primi 12 mesi", f"{base} {n(tot_pa, 0)}", f"{pct(tot_pa / tot, 1)} del capitale investito" if tot else ""),
                                      ("Numero di pagamenti", str(len(pa["righe"])), f"dal {dt(pa['da'])} al {dt(pa['a'])}")]),
                                Spacer(1, 4),
                                tabella(["Data", "Prodotto", f"Importo ({base})"], [[dt(r["data"]), P(r["nome"]), n(r["importo_base"], 0)] for r in pa["righe"]] + [["", P("<b>Totale</b>"), n(tot_pa, 0)]],
                                        [24, 110, 40], allinea_destra_da=2, extra=[("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"), ("LINEABOVE", (0, -1), (-1, -1), 0.6, NERO)]),
                                P("Cedole e interessi previsti dalle condizioni dei prodotti, a partire dalla data della strategia. Per i prodotti strutturati con cedola condizionale l'importo dipende dai sottostanti; "
                                  "per azioni ed ETF i dividendi non sono prevedibili e non sono inclusi.", "piccolo")]))
    red = {x["nome"]: x["importo"] * x["tasso"] * (x["cedola_annua_pct"] or 0) / 100 for x in calc["attive"] if x.get("cedola_annua_pct")}
    if red:
        el.append(KeepTogether([P("DA DOVE ARRIVA IL REDDITO ATTESO", "titolo"), _img(barra_ripartita(red, 174, sottile=True), 174),
                                P(f"Ripartizione del reddito annuo atteso di {base} {n(calc['reddito_annuo'], 0)} secondo le cedole previste dai prodotti. "
                                  "Le cedole a tasso fisso sono dovute anche se la barriera viene toccata; il pagamento dipende dalla solvibilità dell'emittente.", "piccolo")]))

    el.append(PageBreak())
    el.append(P("I PRODOTTI DELLA STRATEGIA", "titolo"))
    righe = []
    for x in calc["attive"]:
        det = [CATEGORIE.get(x["categoria"], "")] + ([x["sottocategoria"]] if x["sottocategoria"] else [])
        nome = f"{x['nome']}<br/><font size=6 color='#666666'>{' · '.join(det)}</font>"
        codici = "<br/>".join(c_ for c_ in ((f"Ticker {x['ticker']}" if x.get("ticker") else ""), (f"ISIN {x['isin']}" if x.get("isin") else "")) if c_) or "–"
        cond = []
        if x.get("cedola_annua_pct"): cond.append(f"cedola {n(x['cedola_annua_pct'], 2)}%")
        if x.get("barriera_pct"): cond.append(f"barriera {n(x['barriera_pct'], 0)}%")
        if x.get("protezione_pct"): cond.append(f"protezione {n(x['protezione_pct'], 0)}%")
        prezzo = "–" if x["prezzo"] is None else (f"{n(x['prezzo'], 2)}%" if x["prezzo_in_percento"] else n(x["prezzo"], 2))
        righe.append([P(nome), P(codici), pct(x["peso_eff_pct"] / 100, 1), f"{x['valuta']} {prezzo}", n(x["quantita"], 0), f"{x['valuta']} {n(x['pagato'], 0)}", n(x["importo_base"], 0),
                      P("<br/>".join(cond) or "–"), dt(x["scadenza"]) if x["scadenza"] else "–"])
    righe.append([P("<b>Totale</b>"), "", "100,0%", "", "", "", n(calc["totale"], 0), "", ""])
    el.append(tabella(["Prodotto", "Ticker · ISIN", "Peso", "Prezzo d'acquisto", "Quantità / nominale", "Importo investito", f"Allocato ({base})", "Condizioni", "Scadenza"], righe, [34, 24, 10, 17, 17, 20, 17, 21, 14],
                      allinea_destra_da=2, extra=[("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"), ("LINEABOVE", (0, -1), (-1, -1), 0.6, NERO), ("ALIGN", (7, 0), (7, -1), "LEFT"), ("ALIGN", (1, 0), (1, -1), "LEFT")]))
    el.append(P("«Importo investito» = quantità × prezzo d'acquisto, nella valuta del prodotto; «Allocato» è il controvalore nella valuta della strategia (per obbligazioni e strutturati il nominale). Prezzi e quantità possono variare all'esecuzione. Per obbligazioni e prodotti strutturati il prezzo è espresso in % del nominale.", "piccolo"))
    el.append(Spacer(1, 10))
    el.append(P("NOTE", "titolo"))
    el.append(P(DISCLAIMER_STRATEGIA, "piccolo"))
    doc.build(el)
    return buf.getvalue()
