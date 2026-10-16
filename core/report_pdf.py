"""Generazione del PDF del report (sfondo chiaro, stile del report di allocazione Athena)."""

from __future__ import annotations

import io
from datetime import date, timedelta

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (BaseDocTemplate, CondPageBreak, Frame, Image, KeepTogether, PageBreak, PageTemplate, Paragraph, Spacer, Table, TableStyle)

from core.config import ASSET, CATEGORIE, DISCLAIMER, NOME_STUDIO

NERO, GRIGIO, GRIGIO_CHIARO = colors.HexColor("#111111"), colors.HexColor("#666666"), colors.HexColor("#F1F1F1")
VERDE_CELLA, ROSSO_CELLA, GIALLO_CELLA = colors.HexColor("#D5ECDB"), colors.HexColor("#F6D6D3"), colors.HexColor("#FBEFC5")
PALETTE = ["#2F5BD8", "#14B8A6", "#F59E0B", "#34A853", "#8B5CF6", "#6B7280", "#24C1E0", "#A3A3A3", "#84CC16", "#0EA5E9"]

ST = {
    "titolo": ParagraphStyle("titolo", fontName="Helvetica-Bold", fontSize=10, leading=13, spaceBefore=16, spaceAfter=6, textColor=NERO),
    "sotto": ParagraphStyle("sotto", fontName="Helvetica-Bold", fontSize=7, leading=9, textColor=NERO, spaceAfter=3),
    "testo": ParagraphStyle("testo", fontName="Helvetica", fontSize=8.2, leading=11, textColor=NERO),
    "piccolo": ParagraphStyle("piccolo", fontName="Helvetica", fontSize=6.8, leading=9, textColor=GRIGIO, spaceBefore=3),
    "cella": ParagraphStyle("cella", fontName="Helvetica", fontSize=7.4, leading=9),
    "cella_b": ParagraphStyle("cella_b", fontName="Helvetica-Bold", fontSize=7.4, leading=9),
    "kpi_v": ParagraphStyle("kpi_v", fontName="Helvetica-Bold", fontSize=13, leading=16, textColor=NERO),
    "kpi_e": ParagraphStyle("kpi_e", fontName="Helvetica", fontSize=6.8, leading=8.5, textColor=GRIGIO),
    "commento": ParagraphStyle("commento", fontName="Helvetica", fontSize=9, leading=13, textColor=NERO),
}


# ───────────────────────── formati (stile italiano, come nel report di allocazione) ─────────────────────────
def n(x, dec=2) -> str:
    if x is None:
        return "–"
    s = f"{abs(x):,.{dec}f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return ("-" if x < 0 and round(abs(x), dec) != 0 else "") + s


def pct(x, dec=2, segno=False) -> str:
    if x is None:
        return "n.d."
    s = f"{x * 100:+.{dec}f}%" if segno else f"{x * 100:.{dec}f}%"
    return s.replace(".", ",")


def dt(iso: str) -> str:
    if not iso:
        return "–"
    a, m, g = iso.split("-")
    return f"{g}.{m}.{a}"


def P(testo, stile="cella"):
    return Paragraph(str(testo), ST[stile])


# ───────────────────────── grafici ─────────────────────────
# Tutti i grafici usano lo stesso carattere e la stessa dimensione del testo del documento (Helvetica ≈ Liberation Sans, 7,4 pt).
# Le immagini hanno la larghezza reale con cui compaiono (nessuna scala): quindi i numeri nei grafici hanno la stessa grandezza di quelli nelle tabelle.
FS = 7.4
DPI = 220
plt.rcParams.update({"font.family": ["Liberation Sans", "Arial", "Helvetica", "DejaVu Sans"], "font.size": FS, "axes.labelsize": FS, "xtick.labelsize": FS, "ytick.labelsize": FS,
                     "legend.fontsize": FS, "text.color": "#111111", "axes.edgecolor": "#BBBBBB"})


def _fig(larg_mm: float, alt_mm: float):
    return plt.subplots(figsize=(larg_mm / 25.4, alt_mm / 25.4), layout="constrained")


def _png(fig) -> io.BytesIO:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=DPI, transparent=False, facecolor="white")
    plt.close(fig)
    buf.seek(0)
    return buf


def _pulisci_assi(ax, sinistra=True):
    for lato in ("top", "right"):
        ax.spines[lato].set_visible(False)
    ax.spines["left"].set_visible(sinistra)
    ax.spines["left"].set_color("#BBBBBB")
    ax.spines["bottom"].set_color("#BBBBBB")
    ax.tick_params(length=0, labelsize=FS)


def torta(valori: dict, etichette: dict, mm: float = 88) -> io.BytesIO | None:
    voci = [(etichette.get(k, k), v) for k, v in valori.items() if v > 0]
    if not voci:
        return None
    fig, ax = _fig(mm, 46)
    tot = sum(v for _, v in voci)
    wedges, _ = ax.pie([v for _, v in voci], colors=PALETTE[: len(voci)], startangle=90, counterclock=False, wedgeprops={"linewidth": 1, "edgecolor": "white"})
    fig.legend(wedges, [f"{e}  {v / tot * 100:.1f}%".replace(".", ",") for e, v in voci], loc="outside right center", frameon=False, fontsize=FS)
    ax.set_aspect("equal")
    return _png(fig)


def barre(valori: dict, titolo_asse="", mm: float = 84) -> io.BytesIO | None:
    voci = sorted([(k, v) for k, v in valori.items() if v > 0], key=lambda kv: kv[1])
    if not voci:
        return None
    tot = sum(v for _, v in voci)
    fig, ax = _fig(mm, max(26, 7.2 * len(voci) + 6))
    ax.barh([k for k, _ in voci], [v / tot * 100 for _, v in voci], color="#4285F4", height=0.62)
    for i, (_, v) in enumerate(voci):
        ax.text(v / tot * 100 + 0.8, i, f"{v / tot * 100:.1f}%".replace(".", ","), va="center", fontsize=FS)
    ax.set_xlim(0, max(v / tot * 100 for _, v in voci) * 1.22)
    for lato in ("top", "right", "bottom"):
        ax.spines[lato].set_visible(False)
    ax.tick_params(axis="y", labelsize=FS, length=0)
    ax.set_xticks([])
    ax.spines["left"].set_color("#BBBBBB")
    return _png(fig)


def barra_ripartita(valori: dict, mm: float = 174, sottile: bool = False) -> io.BytesIO | None:
    """Una sola barra orizzontale divisa in segmenti con le percentuali; legenda sotto."""
    voci = sorted([(k, v) for k, v in valori.items() if v > 0], key=lambda kv: -kv[1])
    if not voci:
        return None
    tot = sum(v for _, v in voci)
    righe_leg = (len(voci) + 2) // 3
    spessore = 5.0 if sottile else 11.0
    fig, ax = _fig(mm, spessore + 4.2 * righe_leg + 3)
    sx = 0.0
    for i, (k, v) in enumerate(voci):
        w = v / tot * 100
        ax.barh(0, w, left=sx, height=0.9, color=PALETTE[i % len(PALETTE)], edgecolor="white", linewidth=1.0)
        if w >= 8 and not sottile:
            ax.text(sx + w / 2, 0, f"{w:.0f}%".replace(".", ","), ha="center", va="center", fontsize=FS, color="white", fontweight="bold")
        sx += w
    ax.set_xlim(0, 100)
    ax.set_ylim(-0.5, 0.5)
    ax.axis("off")
    from matplotlib.patches import Patch
    fig.legend(handles=[Patch(color=PALETTE[i % len(PALETTE)], label=f"{k}  {v / tot * 100:.1f}%".replace(".", ",")) for i, (k, v) in enumerate(voci)],
               loc="outside lower center", ncol=3, frameon=False, fontsize=FS)
    return _png(fig)


def _img(buf, larghezza_mm):
    """Immagine alla sua larghezza reale (così il testo dei grafici resta della stessa grandezza del documento); si riduce solo se non entra."""
    if buf is None:
        return Spacer(1, 1)
    from PIL import Image as PILImage
    w, h = PILImage.open(buf).size
    buf.seek(0)
    naturale = w / DPI * 25.4
    larg = min(naturale, larghezza_mm) * mm
    return Image(buf, width=larg, height=larg * h / w)


def _stile_tabella(extra=None, intest_righe=1):
    base = [
        ("FONTNAME", (0, 0), (-1, intest_righe - 1), "Helvetica-Bold"), ("FONTSIZE", (0, 0), (-1, -1), 7.4),
        ("LINEBELOW", (0, intest_righe - 1), (-1, intest_righe - 1), 0.6, NERO), ("LINEBELOW", (0, -1), (-1, -1), 0.6, NERO),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("TOPPADDING", (0, 0), (-1, -1), 2.6), ("BOTTOMPADDING", (0, 0), (-1, -1), 2.6),
        ("LEFTPADDING", (0, 0), (-1, -1), 3), ("RIGHTPADDING", (0, 0), (-1, -1), 3),
    ]
    return TableStyle(base + (extra or []))


_HDR = ParagraphStyle("hdr", fontName="Helvetica-Bold", fontSize=7.2, leading=8.6, textColor=NERO)
_HDR_R = ParagraphStyle("hdr_r", parent=_HDR, alignment=TA_RIGHT)
LARGHEZZA_UTILE_MM = 174


def tabella(intest: list, righe: list, larghezze_mm: list, allinea_destra_da=1, extra=None):
    """Intestazioni a capo automatico (niente sovrapposizioni) e larghezze ridotte per stare nei margini."""
    scala = min(1.0, LARGHEZZA_UTILE_MM / sum(larghezze_mm))
    hdr = [Paragraph(h, _HDR_R if i >= allinea_destra_da else _HDR) if isinstance(h, str) and h else h for i, h in enumerate(intest)]
    t = Table([hdr] + righe, colWidths=[w * scala * mm for w in larghezze_mm], repeatRows=1, hAlign="LEFT")
    st = [("ALIGN", (allinea_destra_da, 0), (-1, -1), "RIGHT")]
    t.setStyle(_stile_tabella(st + (extra or [])))
    return t


def _colore_rend(x):
    if x is None:
        return None
    return VERDE_CELLA if x > 0.0005 else ROSSO_CELLA if x < -0.0005 else None


# ───────────────────────── grafici aggiuntivi ─────────────────────────
MESI_IT = ["gen", "feb", "mar", "apr", "mag", "giu", "lug", "ago", "set", "ott", "nov", "dic"]
COL_TIPO = {"cedola": "#4285F4", "premio_opzione": "#24C1E0", "dividendo": "#34A853", "interesse": "#FBBC04"}
NOME_TIPO = {"cedola": "Cedole", "premio_opzione": "Premi di opzione", "dividendo": "Dividendi", "interesse": "Interessi"}


def _mesi_tra(da_iso: str, a_iso: str) -> list[tuple[int, int]]:
    d, a = date.fromisoformat(da_iso), date.fromisoformat(a_iso)
    out, y, m = [], d.year, d.month
    while (y, m) <= (a.year, a.month):
        out.append((y, m))
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def grafico_mensile(voci: list[dict], mesi: list[tuple[int, int]], per_tipo: bool = True, mm: float = 160):
    """Barre mensili (impilate per tipo di provento)."""
    if not voci or not mesi:
        return None
    fig, ax = _fig(mm, 44)
    bottom = [0.0] * len(mesi)
    tipi = [t for t in COL_TIPO if any(v["tipo"] == t for v in voci)] if per_tipo else [None]
    for tipo in tipi:
        vals = []
        for (y, m) in mesi:
            vals.append(sum(v["importo_base"] for v in voci if (tipo is None or v["tipo"] == tipo) and v["data"][:7] == f"{y}-{m:02d}"))
        ax.bar(range(len(mesi)), vals, bottom=bottom, color=COL_TIPO.get(tipo, "#4285F4"), width=0.62, label=NOME_TIPO.get(tipo, ""))
        bottom = [b + v for b, v in zip(bottom, vals)]
    for i, tot in enumerate(bottom):
        if tot > 0:
            ax.text(i, tot, n(tot, 0), ha="center", va="bottom", fontsize=FS)
    ax.set_xticks(range(len(mesi)))
    passo = 1 if len(mesi) * 7.5 <= mm else 2                      # se i mesi sono troppi per la larghezza, un'etichetta ogni due
    ax.set_xticklabels([(f"{MESI_IT[m - 1]}\n{str(y)[2:]}" if (i == 0 or m == 1) else MESI_IT[m - 1]) if i % passo == 0 else "" for i, (y, m) in enumerate(mesi)], fontsize=FS)
    ax.set_ylim(0, max(bottom) * 1.25 if max(bottom) > 0 else 1)
    ax.yaxis.set_visible(False)
    _pulisci_assi(ax, sinistra=False)
    if per_tipo and len(tipi) > 1:
        ax.legend(frameon=False, fontsize=FS, ncol=len(tipi), loc="upper left")
    return _png(fig)


def grafico_risultato(voci: list[tuple[str, float]], mm: float = 150):
    voci = [(k, v) for k, v in voci if abs(v) > 0.5]
    if not voci:
        return None
    fig, ax = _fig(mm, 10.5 * len(voci) + 8)
    nomi = [k for k, _ in voci][::-1]
    vals = [v for _, v in voci][::-1]
    ax.barh(nomi, vals, color=["#34A853" if v >= 0 else "#EA4335" for v in vals], height=0.6)
    m = max(abs(v) for v in vals)
    for i, v in enumerate(vals):
        ax.text(v + (m * 0.02 if v >= 0 else -m * 0.02), i, n(v, 0), va="center", ha="left" if v >= 0 else "right", fontsize=FS)
    ax.axvline(0, color="#999999", linewidth=0.6)
    ax.set_xlim(min(0, min(vals)) - m * 0.15, max(0, max(vals)) + m * 0.15)
    ax.set_xticks([])
    _pulisci_assi(ax)
    return _png(fig)


def grafico_scadenze(attivi: list[dict], mm: float = 150):
    cand = [a for a in attivi if a.get("scadenza")]
    if not cand:
        return None
    per: dict[str, float] = {}
    for a in cand:
        d = date.fromisoformat(a["scadenza"])
        k = f"{d.year}-T{(d.month - 1) // 3 + 1}"
        per[k] = per.get(k, 0.0) + a["investito"]
    chiavi = sorted(per)
    fig, ax = _fig(mm, 40)
    ax.bar(range(len(chiavi)), [per[k] for k in chiavi], color="#4285F4", width=0.55)
    for i, k in enumerate(chiavi):
        ax.text(i, per[k], n(per[k], 0), ha="center", va="bottom", fontsize=FS)
    ax.set_xticks(range(len(chiavi)))
    ax.set_xticklabels([k.replace("-T", " · trim. ") for k in chiavi], fontsize=FS)
    ax.set_ylim(0, max(per.values()) * 1.25)
    ax.yaxis.set_visible(False)
    _pulisci_assi(ax, sinistra=False)
    return _png(fig)


# ───────────────────────── contenuto ─────────────────────────
from reportlab.platypus import Flowable


class _RigaCerchi(Flowable):
    """Grado di rischio su 5 con cinque piccoli cerchi, sempre verdi (pieni fino al livello, vuoti oltre)."""

    def __init__(self, r: int):
        super().__init__()
        self.r, self.width, self.height = r, 100 * mm, 6 * mm

    def draw(self):
        c = self.canv
        c.setFont("Helvetica-Bold", 7.4)
        c.setFillColor(NERO)
        c.drawString(0, 1.9 * mm, "Grado di rischio")
        x0 = 34 * mm
        for i in range(5):
            cx = x0 + i * 6 * mm + 1.8 * mm
            c.setLineWidth(0.8)
            c.setStrokeColor(colors.HexColor("#34A853"))
            if i < self.r:
                c.setFillColor(colors.HexColor("#34A853"))
                c.circle(cx, 3 * mm, 1.8 * mm, stroke=1, fill=1)
            else:
                c.setFillColor(colors.white)
                c.circle(cx, 3 * mm, 1.8 * mm, stroke=1, fill=1)
        c.setFillColor(NERO)
        c.setFont("Helvetica-Bold", 7.4)
        c.drawString(x0 + 5 * 6 * mm + 2 * mm, 1.9 * mm, f"{self.r} su 5")


def riga_rischio(rischio, stile: str = "quadrati"):
    """Grado di rischio su 5: cinque caselle, quelle fino al livello sono piene."""
    try:
        r = max(1, min(5, int(rischio)))
    except (TypeError, ValueError):
        return Spacer(1, 1)
    if stile == "cerchi":
        return _RigaCerchi(r)
    cols = {1: "#34A853", 2: "#84CC16", 3: "#F59E0B", 4: "#F97316", 5: "#DC2626"}
    celle = [[P("<b>Grado di rischio</b>", "cella")] + [""] * 5 + [P(f"<b>{r} su 5</b>", "cella")]]
    t = Table(celle, colWidths=[34 * mm] + [8 * mm] * 5 + [26 * mm], rowHeights=[6 * mm], hAlign="LEFT")
    st_ = [("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("LEFTPADDING", (0, 0), (0, 0), 0), ("LEFTPADDING", (1, 0), (5, 0), 0), ("RIGHTPADDING", (1, 0), (5, 0), 0),
           ("LEFTPADDING", (6, 0), (6, 0), 8), ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 0)]
    for i in range(5):
        st_ += [("BACKGROUND", (1 + i, 0), (1 + i, 0), colors.HexColor(cols[r]) if i < r else colors.HexColor("#E3E3E3")), ("LINEAFTER", (1 + i, 0), (1 + i, 0), 1.5, colors.white)]
    t.setStyle(TableStyle(st_))
    return t


def _kpi(valori: list[tuple[str, str, str]]):
    celle = [[[P(v, "kpi_v"), P(e, "kpi_e"), P(s, "kpi_e")] for e, v, s in valori]]
    t = Table(celle, colWidths=[(174 / len(valori)) * mm] * len(valori))
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), GRIGIO_CHIARO), ("BOX", (0, 0), (-1, -1), 0, GRIGIO_CHIARO),
                           ("LINEAFTER", (0, 0), (-2, -1), 3, colors.white), ("LEFTPADDING", (0, 0), (-1, -1), 7), ("TOPPADDING", (0, 0), (-1, -1), 7),
                           ("BOTTOMPADDING", (0, 0), (-1, -1), 7), ("VALIGN", (0, 0), (-1, -1), "TOP")]))
    return t


def _flusso_riga(grafico, larghezza=174):
    return _img(grafico, larghezza)


def _sezione_per_asset(ris, base):
    pa = ris.get("per_asset") or {}
    if not pa:
        return []
    righe, extra = [], []
    ordine = sorted(pa.items(), key=lambda kv: (kv[0] == "costi", -(kv[1].get("valore_fine") or 0)))
    for i, (k, m) in enumerate(ordine, start=1):
        nome = "Costi del periodo" if k == "costi" else CATEGORIE.get(k, k)
        rp = m.get("rendimento_periodo")
        righe.append([nome, n(m.get("valore_fine") or 0, 0) if k != "costi" else "–", pct(rp, segno=True) if rp is not None else "–",
                      f"{'+' if m['pl'] >= 0 else '−'}{n(abs(m['pl']), 0)}", pct(m["contributo"], segno=True) if m.get("contributo") is not None else "–"])
        c = _colore_rend(rp) if rp is not None else None
        if c:
            extra.append(("BACKGROUND", (2, i), (2, i), c))
    tot = ris["totale"]
    righe.append(["Totale portafoglio", n(ris["valore_titoli"], 0), pct(tot.get("rendimento_periodo"), segno=True) if tot.get("rendimento_periodo") is not None else "–",
                  f"{'+' if tot.get('pl', 0) >= 0 else '−'}{n(abs(tot.get('pl', 0)), 0)}", pct(tot.get("rendimento_periodo"), segno=True) if tot.get("rendimento_periodo") is not None else "–"])
    extra += [("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"), ("LINEABOVE", (0, -1), (-1, -1), 0.6, NERO)]
    return [P("PERFORMANCE PER TIPO DI INVESTIMENTO", "titolo"),
            tabella(["Tipo di investimento", f"Valore ({base})", "Performance del periodo", f"Risultato nominale ({base})", "Contributo alla performance totale"], righe, [46, 28, 30, 36, 34], extra=extra),
            P("Il contributo è la parte della performance complessiva del periodo dovuta a ciascun tipo di investimento: la somma dei contributi (costi compresi) dà la performance totale. "
              "Il valore esclude la liquidità del conto.", "piccolo")]


def _sezione_sintesi(ris, cliente, base):
    el = []
    tot = ris["totale"]
    inizio = tot.get("rendimento_dall_inizio")
    giorni = (date.fromisoformat(ris["periodo"]["a"]) - date.fromisoformat(tot["data_inizio"])).days if tot.get("data_inizio") else 0
    sub_inizio = f"annualizzata {pct(tot['xirr'])}" if tot.get("xirr") is not None and giorni >= 365 else f"dal {dt(tot.get('data_inizio', ''))}"
    proventi = sum(p["importo_base"] for p in ris["proventi"])
    el.append(_kpi([
        ("Valore del portafoglio", f"{base} {n(ris['valore_portafoglio'], 0)}", f"di cui liquidità {base} {n(ris['liquidita']['totale'], 0)}"),
        ("Proventi del periodo", f"{base} {n(proventi, 0)}", "cedole, dividendi e premi incassati"),
        ("Performance del periodo", pct(tot.get("rendimento_periodo"), segno=True), f"nominale {'+' if tot.get('pl', 0) >= 0 else '−'}{base} {n(abs(tot.get('pl', 0)), 0)}"),
        ("Performance dall'inizio", pct(inizio, segno=True), f"nominale {'+' if (tot.get('pl_dall_inizio') or 0) >= 0 else '−'}{base} {n(abs(tot.get('pl_dall_inizio') or 0), 0)} · {sub_inizio}"),
    ]))
    el.append(Spacer(1, 6))
    el.append(riga_rischio(cliente.get("rischio")))
    el.append(Spacer(1, 4))
    el.append(P(f"COME È INVESTITO IL PATRIMONIO (in {base})", "titolo"))
    for titolo, dati_, etich in (("Per tipo di investimento", ris["allocazione"], CATEGORIE), ("Per valuta", ris["valute"], {})):
        tot_a = sum(v for v in dati_.values() if v > 0) or 1
        righe = [[etich.get(k, k), pct(v / tot_a), n(v)] for k, v in sorted(dati_.items(), key=lambda kv: -kv[1]) if v > 0]
        righe.append(["Totale", "100,00%", n(tot_a)])
        t = tabella([titolo, "%", "Valore"], righe, [38, 16, 24], extra=[("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"), ("LINEABOVE", (0, -1), (-1, -1), 0.6, NERO)])
        riga = Table([[t, _img(torta(dati_, etich, 88), 90)]], colWidths=[84 * mm, 90 * mm])
        riga.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("LEFTPADDING", (0, 0), (-1, -1), 0), ("TOPPADDING", (0, 0), (-1, -1), 6)]))
        el.append(riga)
    el += _sezione_per_asset(ris, base)
    el.append(Spacer(1, 10))
    el.append(KeepTogether([P("COME LEGGIAMO LA PERFORMANCE", "titolo"), P(
        "<b>Prodotti strutturati</b>: li teniamo fino al rimborso, quindi li valutiamo sempre al 100% del nominale; le cedole e i premi incassati si sommano alla performance, "
        "e quelli ancora da ricevere sono indicati nei prossimi passi.<br/>"
        "<b>Obbligazioni, azioni, ETF e opzioni</b>: valutati al prezzo di mercato alla data del report (per le obbligazioni, in % del nominale).", "testo")]))
    return el


def _sezione_risultato(ris, base):
    el = [P("IL RISULTATO DEL PERIODO", "titolo")]
    bl, tot = ris["blocchi"], ris["totale"]
    prov = {}
    for p in ris["proventi"]:
        prov[p["tipo"]] = prov.get(p["tipo"], 0.0) + p["importo_base"]
    # tabella semplice: due tipi di titoli + totale
    nomi = {"scadenza": "Prodotti strutturati (al 100%)", "mercato": "Obbligazioni, azioni ed ETF (a mercato)"}
    righe, extra = [], []
    for i, k in enumerate(("scadenza", "mercato"), start=1):
        b = bl[k]
        righe.append([nomi[k], n(b["valore_inizio"], 0), n(b["valore_fine"], 0), pct(b["rendimento_periodo"], segno=True)])
        c = _colore_rend(b["rendimento_periodo"])
        if c:
            extra.append(("BACKGROUND", (3, i), (3, i), c))
    righe.append(["Totale titoli", n(tot["valore_inizio"], 0), n(tot["valore_fine"], 0), pct(tot["rendimento_periodo"], segno=True)])
    c = _colore_rend(tot["rendimento_periodo"])
    if c:
        extra.append(("BACKGROUND", (3, 3), (3, 3), c))
    extra += [("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"), ("LINEABOVE", (0, -1), (-1, -1), 0.6, NERO)]
    el.append(tabella(["", f"Valore iniziale ({base})", f"Valore finale ({base})", "Rendimento"], righe, [62, 36, 36, 28], extra=extra))
    el.append(P("Il valore iniziale e finale comprendono la cedola già maturata e non ancora incassata. Il rendimento tiene conto del momento in cui sono avvenuti acquisti e incassi.", "piccolo"))
    # da dove arriva il risultato
    cedole_mat = (bl["scadenza"]["maturato"] - bl["scadenza"].get("maturato0", 0.0)) + (bl["mercato"]["maturato"] - bl["mercato"].get("maturato0", 0.0))
    redditi = sum(prov.values())
    costi = tot["costi_periodo"]
    variazione = tot["pl"] - redditi - costi - cedole_mat
    voci = [("Cedole incassate", prov.get("cedola", 0.0)), ("Premi di opzione", prov.get("premio_opzione", 0.0)), ("Dividendi", prov.get("dividendo", 0.0)),
            ("Interessi", prov.get("interesse", 0.0)), ("Cedole maturate, da incassare", cedole_mat), ("Variazione di valore dei titoli", variazione),
            ("Costi (custodia, spese, imposte)", costi)]
    graf = grafico_risultato(voci)
    if graf:
        el.append(KeepTogether([P("DA DOVE ARRIVA IL RISULTATO", "titolo"), _img(graf, 150),
                                P(f"Risultato complessivo del periodo sui titoli: {base} {n(tot['pl'], 0)}. Importi in {base}.", "piccolo")]))
    return el


def _nota_cedole(fut, base) -> str:
    tot = n(sum(f["importo_base"] for f in fut), 0)
    if all(f.get("incondizionata") for f in fut):
        return (f"Cedole attese nei prossimi 12 mesi: {base} {tot}. Le cedole di obbligazioni, depositi e prodotti a cedola fissa (come i Barrier Reverse Convertible) "
                "sono dovute anche se la barriera viene toccata: la barriera riguarda solo il rimborso del capitale. Il pagamento dipende dalla solvibilità dell'emittente.")
    return (f"Cedole attese nei prossimi 12 mesi: {base} {tot}. Le cedole dei prodotti a cedola fissa sono dovute anche se la barriera viene toccata (la barriera riguarda solo il rimborso del capitale); "
            "i dividendi e le distribuzioni di azioni ed ETF sono stime.")


def _sezione_cedole(ris, base, da, a):
    el = [P("LE CEDOLE E I PROVENTI INCASSATI", "titolo")]
    prov = ris["proventi"]
    if not prov:
        el.append(P("Nel periodo non sono stati incassati proventi.", "testo"))
    else:
        el.append(_img(grafico_mensile(prov, _mesi_tra(da, a), mm=160), 160))
        righe = [[dt(p["data"]), P(p["nome"]), NOME_TIPO.get(p["tipo"], p["tipo"]), p["valuta"], n(p["importo"]), n(p["importo_base"])] for p in prov]
        righe.append(["", P("<b>Totale</b>"), "", "", "", n(sum(p["importo_base"] for p in prov))])
        el.append(Spacer(1, 4))
        el.append(tabella(["Data", "Prodotto", "Tipo", "Val.", "Importo", f"In {base}"], righe, [18, 64, 26, 10, 24, 26], allinea_destra_da=3,
                          extra=[("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"), ("LINEABOVE", (0, -1), (-1, -1), 0.6, NERO)]))
    fut = ris["cedole_future"]
    if fut:
        mesi = _mesi_tra(ris["periodo"]["a"], max(f["data"] for f in fut))[1:13] or _mesi_tra(ris["periodo"]["a"], ris["periodo"]["a"])
        el.append(KeepTogether([P("CEDOLE ATTESE NEI PROSSIMI 12 MESI", "titolo"), _img(grafico_mensile(fut, mesi, per_tipo=False, mm=160), 160),
                                P(_nota_cedole(fut, base), "piccolo")]))
    if ris["cedole_future_non_calcolabili"]:
        el.append(P("Cedole future non calcolabili per: " + ", ".join(ris["cedole_future_non_calcolabili"]) + " (manca la data dell'ultima cedola o di emissione).", "piccolo"))
    return el


def _sezione_scadenza(ris, base):
    el = []
    attese = {a["chiave"]: a for a in ris["attese"] if a.get("completo")}
    barr = {b["chiave"]: b for b in ris["barriere"]}
    attivi = [r for r in ris["attivi"] if r["chiave"] in attese or r["chiave"] in barr]
    if not attivi:
        return el
    el.append(P("I PRODOTTI PORTATI A SCADENZA", "titolo"))
    etich = {"verde": "Ampia", "giallo": "Da seguire", "rosso": "Ridotta"}
    col = {"verde": VERDE_CELLA, "giallo": GIALLO_CELLA, "rosso": ROSSO_CELLA}
    righe, extra = [], []
    for i, r in enumerate(attivi, start=1):
        a = attese.get(r["chiave"])
        b = barr.get(r["chiave"])
        sicurezza = "–"
        if b and b.get("completo"):
            sicurezza = f"{etich[b['semaforo']]} ({pct(b['buffer'], 0)})"
            extra.append(("BACKGROUND", (5, i), (5, i), col[b["semaforo"]]))
        righe.append([P(r["nome"]), dt(r["scadenza"]), n(a["cedole_incassate"], 0) if a else "–", n(a["rimborso_atteso"], 0) if a else "–",
                      pct(a["rendimento_annuo_atteso"]) if a else "n.d.", sicurezza])
    el.append(tabella(["Prodotto", "Scadenza", f"Cedole incassate", f"Rimborso atteso", "Rendimento annuo atteso", "Distanza dalla barriera"], righe, [52, 20, 24, 24, 26, 28], extra=extra))
    el.append(P(f"Importi in {base}. Scenario base: cedole regolari (dovute anche se la barriera viene toccata) e rimborso del nominale a scadenza; non è una garanzia (dipende dalla solvibilità dell'emittente "
                "e, per i prodotti con barriera, dall'andamento dei sottostanti). «Distanza dalla barriera» = di quanto può ancora scendere il sottostante più debole prima di toccare la barriera.", "piccolo"))
    graf = grafico_scadenze(ris["attivi"])
    if graf:
        el.append(KeepTogether([P("QUANDO SCADONO I PRODOTTI", "titolo"), _img(graf, 150), P(f"Capitale investito per trimestre di scadenza, in {base}.", "piccolo")]))
    return el


def _sezione_esposizioni(ris, base):
    el = [P("DOVE È INVESTITO", "titolo")]
    for titolo, dati_ in (("Per settore", ris["settori"]), ("Per area geografica", ris["aree"])):
        tot = sum(v for v in dati_.values() if v > 0)
        if tot <= 0:
            continue
        el.append(P(titolo, "sotto"))
        el.append(_img(barre({k: v for k, v in dati_.items() if v > 0}, mm=120), 120))
    el.append(P("Le esposizioni sono calcolate sul valore dei titoli, liquidità inclusa. Per ETF e indici si usa la composizione di riferimento dell'indice replicato: i valori sono indicativi.", "piccolo"))
    return el


def _sezione_commento(commento):
    if not (commento and commento.strip()):
        return []
    el = [P("IL NOSTRO COMMENTO", "titolo")]
    for par in commento.strip().split("\n"):
        if par.strip():
            el.append(Paragraph(par.strip().replace("&", "&amp;").replace("<", "&lt;"), ST["commento"]))
            el.append(Spacer(1, 4))
    return el


def _sezione_elenco(ris, base):
    el = [P(f"I TUOI INVESTIMENTI ATTIVI al {dt(ris['periodo']['a'])}", "titolo")]
    att = ris["attivi"]
    if att:
        righe, extra = [], []
        for i, r in enumerate(att, start=1):
            nom = f"{r['nome']}<br/><font size=6 color='#666666'>{n(r['quantita'], 0)} {r['valuta']}" + (f" · cedola {pct(r['cedola_annua_pct'] / 100)}" if r["cedola_annua_pct"] else "") + "</font>"
            if r.get("categoria") == "strutturato":
                prz = "100%"
            elif r.get("prezzo") is not None:
                prz = f"{n(r['prezzo'], 2)}%" if r.get("prezzo_pct") else n(r["prezzo"], 2)
            else:
                prz = "–"
            righe.append([P(nom), dt(r["apertura"]), dt(r["scadenza"]) if r["scadenza"] else "–", n(r.get("investito_alloc", r["investito"]), 0), prz, n(r["valore"], 0), n(r["redditi"], 0), pct(r["rendimento"], segno=True)])
            c = _colore_rend(r["rendimento"])
            if c:
                extra.append(("BACKGROUND", (7, i), (7, i), c))
        righe.append([P("<b>Totale</b>"), "", "", n(sum(r.get("investito_alloc", r["investito"]) for r in att), 0), "", n(sum(r["valore"] for r in att), 0), n(sum(r["redditi"] for r in att), 0), ""])
        extra += [("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"), ("LINEABOVE", (0, -1), (-1, -1), 0.6, NERO)]
        el.append(tabella(["Prodotto", "Acquisto", "Scadenza", f"Investito ({base})", "Prezzo", f"Valore ({base})", "Proventi incassati", "Rendimento"], righe, [46, 17, 17, 21, 15, 21, 21, 18], allinea_destra_da=3, extra=extra))
        el.append(P("«Investito» è l'importo realmente allocato (per obbligazioni e strutturati il nominale), senza costi: i costi sono esposti a parte. Rendimento = (valore attuale + proventi incassati − importo pagato, costi inclusi) / importo pagato, dall'acquisto e senza annualizzare. «Prezzo»: obbligazioni in % del nominale; prodotti strutturati sempre al 100%. «Valore»: obbligazioni al prezzo indicato, strutturati al 100% del nominale, azioni ed ETF al prezzo di mercato.", "piccolo"))
    else:
        el.append(P("Nessun investimento attivo.", "testo"))
    el += _sezione_scenari(ris, base)
    el.append(P("INVESTIMENTI CHIUSI", "titolo"))
    chi = ris["chiusi"]
    if chi:
        righe, extra = [], []
        for i, r in enumerate(chi, start=1):
            righe.append([P(r["nome"]), dt(r["apertura"]), dt(r["chiusura"]), n(r["investito"], 0), n(r["incassi"] + r["redditi"], 0), n(r["risultato"], 0), pct(r["rendimento"], segno=True), pct(r["rendimento_annuo"], segno=True) if r["rendimento_annuo"] is not None else "–"])
            c = _colore_rend(r["rendimento"])
            if c:
                extra.append(("BACKGROUND", (6, i), (6, i), c))
        el.append(tabella(["Prodotto", "Acquisto", "Chiusura", f"Investito ({base})", "Incassato", "Risultato", "Rendimento", "Annuo"], righe, [44, 17, 17, 21, 21, 19, 18, 17], allinea_destra_da=3, extra=extra))
        el.append(P("«Incassato» comprende vendita o rimborso e tutti i proventi ricevuti durante la vita dell'investimento, al netto dei costi.", "piccolo"))
    else:
        el.append(P("Nessun investimento chiuso fino a questa data.", "testo"))
    return el


def _sezione_scenari(ris, base):
    """Rendimento a scadenza dei prodotti strutturati e a capitale protetto, con l'eventuale rebate."""
    righe = []
    for a in ris.get("attese", []):
        if not a.get("completo") or not a.get("scenari"):
            continue
        for i, sc in enumerate(a["scenari"]):
            righe.append([P(a["nome"]) if i == 0 else "", dt(a["scadenza"]) if i == 0 else "", P(sc["nome"]), pct(sc["rimborso_pct"] / 100, 0), n(sc["rimborso"], 0),
                          pct(sc["rendimento"], segno=True), pct(sc["rendimento_annuo"], segno=True) if sc.get("rendimento_annuo") is not None else "–"])
    if not righe:
        return []
    el = [P("RENDIMENTO A SCADENZA", "titolo"),
          tabella(["Prodotto", "Scadenza", "Scenario", "Rimborso", f"Importo ({base})", "Rendimento totale", "Annuo"], righe, [36, 15, 50, 14, 20, 22, 17], allinea_destra_da=3)]
    el.append(P("Il rendimento comprende le cedole già incassate, quelle ancora da ricevere e il rimborso dello scenario, rispetto a quanto pagato. Le cedole a tasso fisso sono dovute in ogni scenario. "
                "Il rebate è il rimborso previsto se scatta la barriera superiore (knock-out). Non è una garanzia: dipende dalla solvibilità dell'emittente.", "piccolo"))
    return el


def _sezione_costi(ris, base):
    c = ris["costi_dettaglio"]
    el = [P("COSTI SOSTENUTI NEL PERIODO", "titolo")]
    righe = [["Commissioni e tasse su acquisti e vendite", n(c["commissioni"])], ["Diritti di custodia", n(c["custodia"])], ["Altre spese bancarie", n(c["spese"])],
             ["Imposte", n(c["imposte"])], ["Totale costi", n(c["totale"])]]
    val = ris["valore_portafoglio"]
    righe[-1].append(pct(c["totale"] / val) if val else "")
    for r in righe[:-1]:
        r.append(pct(float(r[1].replace(".", "").replace(",", ".")) / val) if val else "")
    el.append(tabella(["", f"Importo ({base})", "% del patrimonio"], righe, [90, 36, 36],
                      extra=[("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"), ("LINEABOVE", (0, -1), (-1, -1), 0.6, NERO)]))
    rc = ris["riconciliazione"]
    el.append(P("TUTTI I MOVIMENTI DEL PERIODO", "titolo"))
    righe = []
    for k, etich in [(k, e) for k, e in __import__("core.riepiloghi", fromlist=["GRUPPI"]).GRUPPI]:
        r = rc["righe"][k]
        if r["n"]:
            righe.append([etich, str(r["n"]), n(r["base"])])
    righe.append(["Totale movimenti", str(rc["movimenti_totali"]), n(sum(r["base"] for r in rc["righe"].values()))])
    el.append(tabella(["Voce dell'estratto conto", "N.", f"Effetto sul conto ({base})"], righe, [100, 16, 46], extra=[("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"), ("LINEABOVE", (0, -1), (-1, -1), 0.6, NERO)]))
    el.append(P("Ogni movimento degli estratti conto del periodo è compreso in una delle voci sopra. I cambi di valuta sono neutri sul patrimonio (cambia solo la valuta di detenzione). "
                "Versamenti, prelievi e trasferimenti non sono un guadagno né una perdita e non entrano nel rendimento.", "piccolo"))
    return el


def _sezione_note(avvisi):
    el = [Spacer(1, 6), P("NOTE", "titolo")]
    if avvisi:
        el.append(P("<b>Avvertenze di calcolo</b>: " + " ".join(avvisi), "piccolo"))
    el.append(P(DISCLAIMER, "piccolo"))
    return el


def _sezione_pagina2(ris, base, da, a):
    """Pagina 2: esposizioni, cedole e interessi incassati, prossimi passi, costi."""
    el = [P("DOVE È INVESTITO", "titolo")]
    sx = [P("Per settore", "sotto"), _img(barre({k: v for k, v in ris["settori"].items() if v > 0}, mm=84), 86)]
    dx = [P("Per area geografica", "sotto"), _img(barre({k: v for k, v in ris["aree"].items() if v > 0}, mm=84), 86)]
    t = Table([[sx, dx]], colWidths=[87 * mm, 87 * mm])
    t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0), ("TOPPADDING", (0, 0), (-1, -1), 2)]))
    el.append(t)
    el.append(P("CEDOLE E INTERESSI INCASSATI", "titolo"))
    prov = ris["proventi"]
    if not prov:
        el.append(P("Nel periodo non sono stati incassati proventi.", "testo"))
    else:
        per_tipo = {}
        for p in prov:
            r = per_tipo.setdefault(p["tipo"], [0, 0.0])
            r[0] += 1
            r[1] += p["importo_base"]
        righe = [[NOME_TIPO.get(k, k), str(v[0]), n(v[1])] for k, v in per_tipo.items()]
        righe.append(["Totale", str(sum(v[0] for v in per_tipo.values())), n(sum(v[1] for v in per_tipo.values()))])
        tb = tabella(["Tipo", "N.", f"Importo ({base})"], righe, [36, 10, 28], extra=[("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"), ("LINEABOVE", (0, -1), (-1, -1), 0.6, NERO)])
        g = _img(grafico_mensile(prov, _mesi_tra(da, a), mm=92), 92)
        rr = Table([[tb, g]], colWidths=[80 * mm, 94 * mm])
        rr.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("LEFTPADDING", (0, 0), (-1, -1), 0)]))
        el.append(rr)
    el.append(P("I PROSSIMI PASSI", "titolo"))
    eventi = [(f["data"], "Cedola attesa", f["nome"], f["importo_base"]) for f in ris["cedole_future"]]
    eventi += [(r["scadenza"], "Scadenza / rimborso", r["nome"], r["investito"]) for r in ris["attivi"] if r.get("scadenza") and r["scadenza"] >= ris["periodo"]["a"]]
    eventi = sorted(eventi)[:7]
    if eventi:
        el.append(tabella(["Data", "Cosa succede", "Prodotto", f"Importo ({base})"], [[dt(d), e, P(nm), n(i, 0)] for d, e, nm, i in eventi], [20, 34, 80, 26], allinea_destra_da=3))
        fut = ris["cedole_future"]
        if fut:
            mesi = _mesi_tra(ris["periodo"]["a"], max(f["data"] for f in fut))[1:13] or _mesi_tra(ris["periodo"]["a"], ris["periodo"]["a"])
            el.append(Spacer(1, 4))
            el.append(_img(grafico_mensile(fut, mesi, per_tipo=False, mm=92), 92))
            el.append(P(_nota_cedole(fut, base), "piccolo"))
    else:
        el.append(P("Nessuna cedola o scadenza prevista nel prossimo periodo.", "testo"))
    c = ris["costi_dettaglio"]
    el.append(P("COSTI SOSTENUTI NEL PERIODO", "titolo"))
    voci = [("Commissioni e tasse su acquisti e vendite", c["commissioni"]), ("Diritti di custodia", c["custodia"]), ("Altre spese bancarie", c["spese"]), ("Imposte", c["imposte"])]
    righe = [[k, n(v)] for k, v in voci if abs(v) > 0.004] + [["Totale costi", n(c["totale"])]]
    el.append(tabella(["", f"Importo ({base})"], righe, [90, 36], extra=[("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"), ("LINEABOVE", (0, -1), (-1, -1), 0.6, NERO)]))
    return el


# ───────────────────────── documento ─────────────────────────
def genera_pdf(ris: dict, cliente: dict, tipo_periodo: str, commento: str = "") -> bytes:
    base = ris["periodo"]["base"]
    da = (date.fromisoformat(ris["periodo"]["da"]) + timedelta(days=1)).isoformat()    # il periodo mostrato parte dal giorno dopo il valore iniziale
    a = ris["periodo"]["a"]
    titolo = f"REPORT {tipo_periodo.upper()}"
    buf = io.BytesIO()
    larg, alt = A4
    logo = ASSET / "logo_pdf.png"
    from PIL import Image as PILImage
    lw0, lh0 = PILImage.open(logo).size

    def testata(canvas, doc, grande):
        canvas.saveState()
        lw = 52 * mm if grande else 34 * mm
        canvas.drawImage(str(logo), 18 * mm, alt - (14 * mm if grande else 11 * mm) - lw * lh0 / lw0, width=lw, height=lw * lh0 / lw0, mask="auto")
        canvas.setFillColor(NERO)
        if grande:
            canvas.setFont("Helvetica", 8.5); canvas.drawRightString(larg - 18 * mm, alt - 17 * mm, f"Sig. {cliente['nome']}")
            canvas.setFont("Helvetica-Bold", 11.5); canvas.drawRightString(larg - 18 * mm, alt - 22.5 * mm, titolo)
            canvas.setFont("Helvetica-Bold", 8.5); canvas.drawRightString(larg - 18 * mm, alt - 27.5 * mm, f"{dt(da)} – {dt(a)}")
        else:
            canvas.setFont("Helvetica", 7.5); canvas.drawRightString(larg - 18 * mm, alt - 14 * mm, f"Sig. {cliente['nome']} · {titolo.title()} · {dt(da)} – {dt(a)}")
        canvas.setStrokeColor(colors.HexColor("#BBBBBB")); canvas.setLineWidth(0.5)
        canvas.line(18 * mm, 15 * mm, larg - 18 * mm, 15 * mm)
        canvas.setFont("Helvetica", 6.5); canvas.setFillColor(GRIGIO)
        canvas.drawString(18 * mm, 11 * mm, f"{NOME_STUDIO} · Bissone (TI)")
        canvas.drawRightString(larg - 18 * mm, 11 * mm, f"Pagina {doc.page}")
        canvas.restoreState()

    doc = BaseDocTemplate(buf, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=36 * mm, bottomMargin=20 * mm,
                          title=f"{titolo} – {cliente['nome']} – {dt(a)}", author=NOME_STUDIO)
    # prima pagina: più aria fra logo/titolo e contenuto; pagine successive: testata ridotta
    f1 = Frame(18 * mm, 20 * mm, larg - 36 * mm, alt - 20 * mm - 50 * mm, leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0, id="f1")
    doc.addPageTemplates([PageTemplate(id="tutte", frames=[f1], onPage=lambda c, d: testata(c, d, True))])      # stessa intestazione in tutte le pagine

    el = []
    el += _sezione_sintesi(ris, cliente, base)
    el += [PageBreak()] + _sezione_pagina2(ris, base, da, a) + ([KeepTogether(_sezione_commento(commento))] if commento and commento.strip() else [])
    el += [PageBreak()] + _sezione_elenco(ris, base) + _sezione_note([])      # le avvertenze di calcolo si leggono nell'app prima di generare, non nel PDF del cliente
    doc.build(el)
    return buf.getvalue()
