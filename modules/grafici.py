"""Grafici dell'interfaccia (Altair, tema scuro, niente rosa)."""

from __future__ import annotations

import altair as alt
import pandas as pd
import streamlit as st

from core.stile import PALETTE

TESTO = "#F4EFE6"


def _df(valori: dict, etichette: dict | None = None) -> pd.DataFrame | None:
    voci = {(etichette or {}).get(k, k): v for k, v in valori.items() if v and v > 0}
    if not voci:
        return None
    df = pd.DataFrame({"Voce": list(voci), "Valore": list(voci.values())})
    df["Quota"] = df["Valore"] / df["Valore"].sum()
    return df


def _scala(df: pd.DataFrame):
    return alt.Scale(domain=list(df["Voce"]), range=[PALETTE[i % len(PALETTE)] for i in range(len(df))])


def torta(valori: dict, etichette: dict | None = None, interno: int = 0, altezza: int = 240):
    """Torta (interno=0) o ciambella (interno>0)."""
    df = _df(valori, etichette)
    if df is None:
        st.caption("Nessun dato.")
        return
    ch = alt.Chart(df).mark_arc(innerRadius=interno, stroke="#000000").encode(
        theta="Valore:Q", color=alt.Color("Voce:N", scale=_scala(df), legend=alt.Legend(orient="right", labelColor=TESTO, title=None)),
        tooltip=["Voce", alt.Tooltip("Valore:Q", format=",.0f"), alt.Tooltip("Quota:Q", format=".1%")]).properties(height=altezza)
    st.altair_chart(ch, width="stretch")


def barre_orizzontali(valori: dict, etichette: dict | None = None, altezza: int | None = None):
    df = _df(valori, etichette)
    if df is None:
        st.caption("Nessun dato.")
        return
    df = df.sort_values("Valore", ascending=False)
    ch = alt.Chart(df).mark_bar(cornerRadiusEnd=4).encode(
        x=alt.X("Quota:Q", axis=alt.Axis(format="%", labelColor=TESTO, title=None, grid=False)),
        y=alt.Y("Voce:N", sort="-x", axis=alt.Axis(labelColor=TESTO, title=None, labelLimit=180)),
        color=alt.Color("Voce:N", scale=_scala(df), legend=None),
        tooltip=["Voce", alt.Tooltip("Valore:Q", format=",.0f"), alt.Tooltip("Quota:Q", format=".1%")]).properties(height=altezza or max(120, 28 * len(df)))
    st.altair_chart(ch, width="stretch")


def barra_unica(valori: dict, etichette: dict | None = None):
    """Una sola barra orizzontale divisa in segmenti (quote %)."""
    df = _df(valori, etichette)
    if df is None:
        st.caption("Nessun dato.")
        return
    df["Tutto"] = "Valuta"
    ch = alt.Chart(df).mark_bar(stroke="#000000", strokeWidth=1).encode(
        x=alt.X("Valore:Q", stack="normalize", axis=alt.Axis(format="%", labelColor=TESTO, title=None)), y=alt.Y("Tutto:N", axis=None),
        color=alt.Color("Voce:N", scale=_scala(df), legend=alt.Legend(orient="bottom", labelColor=TESTO, title=None)),
        tooltip=["Voce", alt.Tooltip("Valore:Q", format=",.0f"), alt.Tooltip("Quota:Q", format=".1%")]).properties(height=70)
    st.altair_chart(ch, width="stretch")


def linea(serie, titolo="Performance dall'inizio (%)", altezza: int = 240):
    if len(serie) < 2:
        st.caption("Il grafico compare quando ci sono almeno due date di calcolo (dopo il primo mese).")
        return
    df = pd.DataFrame(serie, columns=["Data", titolo])
    df["Data"] = pd.to_datetime(df["Data"])
    base = alt.Chart(df).encode(x=alt.X("Data:T", axis=alt.Axis(labelColor=TESTO, title=None, format="%b %y")), y=alt.Y(f"{titolo}:Q", axis=alt.Axis(labelColor=TESTO, title=None)))
    ch = (base.mark_area(opacity=0.18, color="#3B82F6", line={"color": "#3B82F6"}) + base.mark_point(color="#3B82F6", filled=True, size=36)).properties(height=altezza)
    st.altair_chart(ch, width="stretch")


def barre_verticali(serie: dict, titolo: str = "", colore: str = "#14B8A6", altezza: int = 220):
    if not serie:
        st.caption("Nessun dato.")
        return
    df = pd.DataFrame({"Periodo": list(serie), "Valore": list(serie.values())})
    ch = alt.Chart(df).mark_bar(color=colore, cornerRadiusEnd=3).encode(x=alt.X("Periodo:N", axis=alt.Axis(labelColor=TESTO, title=None, labelAngle=-45)),
                                                                        y=alt.Y("Valore:Q", axis=alt.Axis(labelColor=TESTO, title=titolo or None)),
                                                                        tooltip=["Periodo", alt.Tooltip("Valore:Q", format=",.0f")]).properties(height=altezza)
    st.altair_chart(ch, width="stretch")
