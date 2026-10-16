from datetime import date

import pandas as pd
import streamlit as st

from core import cambi_report, cedole_suggerite, commento as cmt, dati, db, strategia as stg
from core.calcolo import calcola_portafoglio
from core.config import PERIODI
from core.performance import DatoMancante
from core.report_pdf import genera_pdf
from core.stile import bottone, bottone_link, intestazione, riquadro

PERSONALIZZATO = "Personalizzato (date a scelta)"


def _da(a: date, mesi: int) -> date:
    return (pd.Timestamp(a) - pd.DateOffset(months=mesi)).date()


def _calcola(c, pid, reg, tipo, da, a):
    r = calcola_portafoglio(c, pid, reg, da, a)
    r["tipo"] = tipo
    return r


def render():
    intestazione("Crea report", "Scegli cliente, strategia e periodo: i prezzi di mercato vengono controllati su due fonti.")
    clienti = dati.elenco_clienti()
    if not clienti:
        st.info("Crea prima un cliente.")
        return
    reg = dati.carica_registro()
    ids = [c["id"] for c in clienti]
    pre = st.session_state.get("cli_id")
    c_id = st.selectbox("Cliente", ids, index=ids.index(pre) if pre in ids else 0, format_func=lambda i: next(c["nome"] for c in clienti if c["id"] == i), key="rep_cliente")
    c = dati.carica_cliente(c_id)
    if reg.allinea(c):
        dati.salva_cliente(c)
    pfs = dati.assicura_portafogli(c)
    if not pfs:
        st.warning("Questo cliente non ha ancora una strategia: creane una dalla scheda del cliente.")
        return
    pid = st.selectbox("Strategia", [p["id"] for p in pfs], format_func=lambda i: next(p["nome"] for p in pfs if p["id"] == i), key="rep_pf")
    pannello(c, reg, dati.portafoglio(c, pid))
    if st.session_state.get(f"rep_pdf_{pid}"):
        pdf, nome = st.session_state[f"rep_pdf_{pid}"]
        st.success("Report generato e archiviato.")
        st.download_button("Scarica il report", pdf, file_name=nome, mime="application/pdf", key=f"rep_dl_pag_{pid}")


def _cambi(c, reg, pf, v, a: date) -> bool:
    """Tassi di cambio da confermare (valuta ≠ valuta della strategia, alla data di fine report). True se confermati o non servono."""
    pid, base = pf["id"], pf["valuta"]
    tx = dati.transazioni_ordinate(v)
    valute = cambi_report.valute_da_convertire(tx, reg, base, a.isoformat())
    if not valute:
        return True
    chiave = f"rep_fx_{pid}_{a.isoformat()}"
    ok_key = f"rep_fxok_{pid}_{a.isoformat()}"
    with riquadro("blu", f"rep_fx_{pid}"):
        st.markdown(f"**Tassi di cambio al {a.strftime('%d.%m.%Y')}** per esprimere tutto in {base}")
        if chiave not in st.session_state:
            with st.spinner("Cerco i tassi (ICTax / BCE)…"):
                st.session_state[chiave] = cambi_report.suggerisci(valute, base, a.isoformat())
        sug = st.session_state[chiave]
        df = pd.DataFrame([{"Valuta": x, f"1 unità in {base}": sug[x]["tasso"], "Fonte del suggerimento": sug[x]["fonte"]} for x in valute])
        ed = st.data_editor(df, hide_index=True, width="stretch", key=f"{chiave}_ed", disabled=["Valuta", "Fonte del suggerimento"],
                            column_config={f"1 unità in {base}": st.column_config.NumberColumn(format="%.6f")})
        st.caption("Ti suggerisco i tassi (ICTax dell'Amministrazione federale delle contribuzioni se raggiungibile, altrimenti BCE): controllali, correggili se serve e conferma. "
                   f"Riferimento: [ICTax]({cambi_report.URL_ICTAX.format(anno=a.year)}).")
        if bottone("Conferma i tassi", "verde", f"{chiave}_ok"):
            man = dati.carica_manuali()
            for r in ed.to_dict("records"):
                t = r[f"1 unità in {base}"]
                if t and t == t and float(t) > 0:
                    man[cambi_report.chiave(r["Valuta"], base, a.isoformat())] = float(t)
            dati.salva_manuali(man)
            st.session_state[ok_key] = True
            st.rerun()
        if not st.session_state.get(ok_key):
            st.warning("Conferma i tassi per poter calcolare il report.")
    return bool(st.session_state.get(ok_key))


def _cedole(c, reg, pf, v, a: date):
    """Cedole teoriche (da emissione e frequenza) senza incasso registrato: precompilate, da correggere e confermare."""
    pid = pf["id"]
    sug = cedole_suggerite.suggerisci(dati.transazioni_ordinate(v), reg.strumenti, a.isoformat())
    if not sug:
        return
    gen = st.session_state.get(f"rep_ced_gen_{pid}", 0)
    with riquadro("giallo", f"rep_ced_{pid}"):
        st.markdown("#### Cedole che sembrano mancanti")
        st.caption("Dalla data di emissione e dalla frequenza risulta che questi pagamenti dovrebbero essere già avvenuti, ma non trovo l'incasso. "
                   "Importi e date sono precompilati: correggili (per esempio le imposte trattenute) e spunta quelli da registrare. Le cedole condizionali dei prodotti strutturati dipendono dai sottostanti: controlla che siano state pagate.")
        df = pd.DataFrame([{"Registra": not x["condizionata"], "Prodotto": x["nome"], "Data": date.fromisoformat(x["data"]), "Importo": x["importo"], "Valuta": x["valuta"],
                            "Nota": "condizionata: verifica" if x["condizionata"] else "", "_k": x["chiave"], "_t": x["tipo"]} for x in sug])
        ed = st.data_editor(df, hide_index=True, width="stretch", key=f"rep_ced_ed_{pid}_{gen}", disabled=["Prodotto", "Valuta", "Nota"],
                            column_config={"_k": None, "_t": None, "Data": st.column_config.DateColumn(format="DD.MM.YYYY"), "Importo": st.column_config.NumberColumn(format="%.2f")})
        if bottone("Registra le cedole spuntate", "bianco", f"rep_ced_ok_{pid}"):
            n_ = 0
            for r in ed.to_dict("records"):
                if r["Registra"] and r["Importo"] and r["Importo"] > 0:
                    stg.registra_incasso(c, pf, reg, r["_k"], r["_t"], r["Data"].isoformat(), float(r["Importo"]), nota="suggerita dal programma")
                    n_ += 1
            if n_:
                dati.salva_cliente(c)
                st.session_state[f"rep_ced_gen_{pid}"] = gen + 1
                st.session_state.pop(f"rep_stato_{pid}", None)
            st.rerun()


def pannello(c, reg, pf):
    """Scelta del periodo, cambi, calcolo, controlli e generazione del PDF del report di una strategia."""
    pid, c_id = pf["id"], c["id"]
    v = dati.vista_portafoglio(c, pid)
    tipi = list(PERIODI) + [PERSONALIZZATO]
    col1, col2, col3 = st.columns(3)
    tipo = col1.selectbox("Tipo di report", tipi, key=f"rep_tipo_{pid}")
    a = col3.date_input("Fino al (fine periodo)", value=date.today(), format="DD.MM.YYYY", key=f"rep_a_{pid}")
    if tipo == PERSONALIZZATO:
        da = col2.date_input("Dal (inizio periodo)", value=_da(a, 3), format="DD.MM.YYYY", key=f"rep_da_{pid}")
        if da >= a:
            st.error("La data iniziale deve precedere quella finale.")
            return
    else:
        da = _da(a, PERIODI[tipo])
        col2.date_input("Dal (inizio periodo)", value=da, format="DD.MM.YYYY", disabled=True, key=f"rep_da_auto_{pid}_{tipo}")
    if not v.get("transazioni"):
        st.warning("Questa strategia non ha ancora movimenti: aggiungi i prodotti.")
        return
    _cedole(c, reg, pf, v, a)
    if not _cambi(c, reg, pf, v, a):
        return

    if st.button("Calcola", type="primary", key=f"rep_calcola_{pid}"):
        with st.spinner("Recupero prezzi e cambi, doppio controllo…"):
            try:
                st.session_state[f"rep_stato_{pid}"] = _calcola(c, pid, reg, tipo, da, a)
            except DatoMancante as e:
                st.session_state.pop(f"rep_stato_{pid}", None)
                st.error(f"Dato mancante: {e}. Inserisci il valore o correggi il prodotto nella scheda della strategia.")
    S = st.session_state.get(f"rep_stato_{pid}")
    if not S or S["cliente"] != c_id or S.get("portafoglio") != pid:
        return

    ris = S["ris"]
    bloccanti = bool(S["problemi"] or S["incoerenti"])
    from core.completezza import riepilogo_cliente
    schede = riepilogo_cliente(v, reg)
    bl_sch = {k: x for k, x in schede.items() if x["bloccanti"]}

    # ── controlli prima di generare: tutto ciò che serve a te, non al cliente ──
    avvisi = list(ris.get("avvisi", []))
    if schede or avvisi or S["problemi"] or S["incoerenti"]:
        with riquadro("giallo", f"rep_ctrl_{pid}"):
            st.markdown("#### Controlli prima di generare")
            st.caption("Queste note servono a te e non compaiono nel report del cliente.")
            for k, x in schede.items():
                for t_ in x["bloccanti"]:
                    st.warning(f"{x['nome']}: {t_}")
                for t_ in x["consigliati"]:
                    st.caption(f"{x['nome']}: {t_}")
            for av in avvisi:
                st.warning(av)
            if S["problemi"]:
                st.markdown("**Prezzi e cambi da verificare**")
                from modules import strategia
                live_p = [{**p, "nome": reg.strumenti.get(str(p["chiave"]).split("@")[0], {}).get("nome", str(p["chiave"]).split("@")[0]),
                           "isin": reg.strumenti.get(str(p["chiave"]).split("@")[0], {}).get("isin", ""), "ticker": reg.strumenti.get(str(p["chiave"]).split("@")[0], {}).get("ticker_mercato", "")} for p in S["problemi"]]
                strategia.prezzi_da_verificare(c, reg, pf, live_p, f"rep_{pid}", dopo=lambda: st.session_state.update({f"rep_stato_{pid}": _calcola(c, pid, reg, S["tipo"], date.fromisoformat(S["da"]), date.fromisoformat(S["a"]))}))
            if S["incoerenti"]:
                st.markdown("**Acquisti incoerenti con il mercato**")
                st.caption("Il prezzo dell'estratto cade fuori dal range della giornata: controlla ticker, valuta o l'estratto.")
                st.dataframe(pd.DataFrame(S["incoerenti"]), hide_index=True, width="stretch")
                if st.checkbox("Ho verificato: procedi comunque", key=f"rep_forza_{pid}"):
                    bloccanti = bool(S["problemi"])
            if bl_sch:
                if st.checkbox("Genera comunque, anche con schede incomplete", key=f"rep_forza_schede_{pid}"):
                    pass
                else:
                    bloccanti = True

    t = ris["totale"]
    base = ris["periodo"]["base"]
    k = st.columns(4)
    k[0].metric("Valore finale", f"{base} {ris['valore_portafoglio']:,.0f}".replace(",", "’"))
    k[1].metric("Performance del periodo", f"{100 * t['rendimento_periodo']:+.2f}%" if t.get("rendimento_periodo") is not None else "n.d.")
    k[2].metric("Dall'inizio", f"{100 * t['rendimento_dall_inizio']:+.2f}%" if t.get("rendimento_dall_inizio") is not None else "n.d.")
    k[3].metric("Risultato nominale", f"{base} {t.get('pl', 0):,.0f}".replace(",", "’"))
    if ris["periodo"].get("da_effettivo") and ris["periodo"]["da_effettivo"] != ris["periodo"]["da"]:
        st.caption("Il periodo parte prima del primo acquisto: la performance del periodo coincide con quella dall'inizio.")

    # ── commento facoltativo, con aiuto di Claude ──
    ck = f"rep_commento_{pid}"
    prompt = cmt.testo_prompt(ris, c, S["tipo"])
    chiave_api = db._secret("ANTHROPIC_API_KEY")

    def _genera():
        try:
            st.session_state[ck] = cmt.chiedi_claude(prompt, chiave_api, db._secret("ANTHROPIC_MODEL") or "claude-sonnet-5-5")
            st.session_state.pop(f"rep_claude_err_{pid}", None)
        except Exception as e:
            st.session_state[f"rep_claude_err_{pid}"] = str(e)

    a_, b_ = st.columns([4, 1.4], vertical_alignment="bottom")
    a_.markdown("**Commento (facoltativo)** · puoi modificarlo prima di generare il report")
    with b_:
        if chiave_api:
            bottone("Scrivi con Claude", "arancio", f"rep_claude_{pid}", width="stretch", on_click=_genera, icon=":material/auto_awesome:")
        else:
            bottone_link("Scrivi con Claude", "arancio", f"rep_claude_{pid}", cmt.link_claude(prompt), width="stretch", icon=":material/auto_awesome:")
    if st.session_state.get(f"rep_claude_err_{pid}"):
        st.warning(st.session_state[f"rep_claude_err_{pid}"])
    if not chiave_api:
        st.caption("Il pulsante apre Claude con i dati del report già scritti nel messaggio: premi invio lì, copia il commento che ti scrive e incollalo qui sotto. Nessuna chiave e nessun costo oltre al tuo abbonamento Claude.")
        with st.expander("Il link non si apre o il messaggio è troncato? Copia il testo"):
            st.code(prompt, language=None, wrap_lines=True)
    commento = st.text_area("Commento", key=ck, height=110, label_visibility="collapsed", placeholder="2 o 3 righe sul periodo, per il cliente…")

    if st.button("Genera PDF", type="primary", disabled=bloccanti, key=f"rep_genera_{pid}"):
        tipo_pdf = "Periodico" if S["tipo"] == PERSONALIZZATO else S["tipo"]
        pdf = genera_pdf(ris, c, tipo_pdf, commento)
        dati.salva_report({"cliente_id": c["id"], "portafoglio": pid, "cliente": c["nome"], "tipo": tipo_pdf, "da": S["da"], "a": S["a"],
                           "commento": commento, "snapshot": S["snapshot"]}, pdf)
        st.session_state[f"rep_pdf_{pid}"] = (pdf, f"Report_{c['nome'].replace(' ', '_')}_{S['a']}.pdf")
        st.session_state[f"st_repopen_{pid}"] = False              # il riquadro del report si richiude: il PDF si scarica dalla pagina della strategia
        st.rerun()
    if bloccanti:
        st.caption("La generazione è bloccata finché i punti sopra non sono risolti.")
