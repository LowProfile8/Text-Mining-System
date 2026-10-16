import pandas as pd
import streamlit as st
from datetime import date

from core import dati
from core.config import VALUTE_BASE
from core.nav import vai
from core.importatore import leggi_documento
from core.live import serie_cliente as live_serie
from core.stile import bottone, intestazione, riquadro

VALUTE = ["CHF", "EUR", "USD", "GBP", "JPY", "CAD", "AUD", "SEK", "NOK", "DKK"]


def _stato_prodotto(v, k):
    tx = [t for t in v["transazioni"] if t.get("strumento") == k]
    qta = sum((t.get("quantita") or 0) * (1 if t["tipo"] == "acquisto" else -1) for t in tx if t["tipo"] in ("acquisto", "vendita", "rimborso"))
    return "attivo" if qta > 1e-9 else "chiuso"


def _prodotti(c, reg, pf):
    from core.completezza import problemi_strumento, prodotti_del_cliente
    from modules import scheda_prodotto as sp
    v = dati.vista_portafoglio(c, pf["id"])
    L = pf.get("live") or {}
    perf = L.get("prodotti") or {}
    chiusi = {r["chiave"]: r for r in (L.get("chiusi") or [])}
    with riquadro("blu", f"prodotti_{pf['id']}"):
        st.markdown("#### Condizioni dei prodotti")
        st.caption("Qui completi le condizioni dei prodotti già acquistati (scadenza, cedola, barriera, sottostanti). Poi il programma legge solo i dati reali.")
        prod = prodotti_del_cliente(v, reg)
        if not prod:
            st.info("Nessun prodotto acquistato in questo portafoglio.")
        for k, s in sorted(prod.items(), key=lambda x: (_stato_prodotto(v, x[0]), x[1].get("nome", ""))):
            pr = problemi_strumento(s)
            bl = sum(1 for g, _ in pr if g == "bloccante")
            badge = "🔴 da completare" if bl else "✓ completo"
            r_ = (perf.get(k) or {}).get("rend")
            if r_ is None:
                r_ = (chiusi.get(k) or {}).get("rendimento")
            tit_perf = f" · performance {100 * r_:+.2f}%" if r_ is not None else ""
            with st.expander(f"{s.get('nome') or k} · {_stato_prodotto(v, k)}{tit_perf} · {badge}", expanded=bool(bl) and len(prod) <= 3):
                sp.scheda(reg, k, v, 'p' + pf['id'], cliente=c, pid=pf['id'])


def _revisione_movimenti(nome, est, c, reg):
    from core import revisione
    d = est.a_dict()
    st.markdown(f"**{nome}** · {est.banca} · dal {est.periodo_da} al {est.periodo_a} · {len(est.movimenti)} righe")
    (st.success if est.quadra else st.error)("Saldi quadrati con i movimenti." if est.quadra else "I saldi NON quadrano: controlla bene prima di importare.")
    for a in est.avvisi:
        st.warning(a)
    righe = revisione.prepara_revisione(d, c, reg)
    tipi = list(dati.ETICHETTE_TIPO)
    ed = st.data_editor(pd.DataFrame(righe), hide_index=True, width="stretch", key=f"cli_rev_{nome}",
                        disabled=["Controllo", "Dettaglio", "ISIN", "Prodotto", "Valuta"],
                        column_config={"_i": None, "Tipo": st.column_config.SelectboxColumn(options=tipi, required=True),
                                       "Controllo": st.column_config.TextColumn(width="small"), "Dettaglio": st.column_config.TextColumn(width="large")})
    n_ko = sum(1 for r in righe if r["Controllo"] == "⚠" and r["Importa"])
    if n_ko:
        st.warning(f"{n_ko} operazioni con ⚠: quantità × prezzo + commissioni non torna con l'importo. Correggi nella tabella o togli la spunta.")
    return nome, d, ed.to_dict("records")


def _revisione_posizioni(nome, doc):
    from core import revisione
    st.markdown(f"**{nome}** · {doc['banca']} · posizioni al {doc['data']} · {len(doc['posizioni'])} strumenti")
    for k in doc["controlli"]:
        (st.success if k["ok"] else st.error)(k["testo"])
    for a in doc["avvisi"]:
        st.warning(a)
    ed = st.data_editor(pd.DataFrame(revisione.prepara_revisione_posizioni(doc)), hide_index=True, width="stretch", key=f"cli_revp_{nome}",
                        disabled=["Prodotto", "ISIN", "Valuta"], column_config={"_i": None})
    st.caption("Qui verifica quantità, prezzo d'acquisto e data per ogni prodotto: sono i valori di partenza del report. "
               "Non importare anche gli estratti conto con gli stessi acquisti.")
    return nome, doc, ed.to_dict("records")


MESI = ["gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio", "agosto", "settembre", "ottobre", "novembre", "dicembre"]


def _filtro_periodo(chiave: str, anni: list[int]):
    """Menu Anno / Mese: restituisce (anno o None, mese o None)."""
    a, b, _ = st.columns([1, 1, 3])
    anno = a.selectbox("Anno", ["Tutti"] + sorted(anni, reverse=True), key=f"{chiave}_anno")
    mese = b.selectbox("Mese", ["Tutti"] + MESI, key=f"{chiave}_mese")
    return (None if anno == "Tutti" else int(anno)), (None if mese == "Tutti" else MESI.index(mese) + 1)


def _nel_periodo(iso: str, anno, mese) -> bool:
    try:
        y, m = int(iso[:4]), int(iso[5:7])
    except ValueError:
        return True
    return (anno is None or y == anno) and (mese is None or m == mese)


def _carica_estratti(c, reg, pf):
    st.caption("Carica i PDF (estratti conto PostFinance, Swissquote, UBS; «Performance del portafoglio»; «Estratto patrimoniale» UBS). "
               "Vedrai ogni riga in una tabella modificabile con il controllo ✓/⚠. **Nulla viene salvato finché non confermi.**")
    files = st.file_uploader("Documenti (PDF)", type="pdf", accept_multiple_files=True, key="cli_upload")
    pronti, byte = [], {}
    for f in files or []:
        try:
            tipo, doc = leggi_documento(f)
        except Exception as e:
            st.error(f"{f.name}: {e}")
            continue
        f.seek(0)
        byte[f.name] = f.read()
        with st.container(border=True):
            pronti.append((tipo,) + (_revisione_movimenti(f.name, doc, c, reg) if tipo == "movimenti" else _revisione_posizioni(f.name, doc)))
    if pronti and bottone("Conferma e importa le righe selezionate", "verde", "cli_importa"):
        from core import db, revisione
        n = d = 0
        avvisi, prima = [], set(reg.strumenti)
        for tipo, nome, doc, righe in pronti:
            n_prima = len(c["estratti"])
            if tipo == "movimenti":
                r = dati.importa_in_portafoglio(c, pf["id"], dati.importa_estratto, revisione.applica_modifiche(doc, righe), reg)
            else:
                r = dati.importa_in_portafoglio(c, pf["id"], dati.importa_posizioni, revisione.applica_modifiche_posizioni(doc, righe), reg)
            n += r["nuovi"]; d += r["duplicati"]; avvisi += r.get("avvisi", [])
            if len(c["estratti"]) > n_prima and nome in byte:           # conserva il PDF e collega il documento importato
                fid = f"est_{c['id']}_{db.nuovo_id()[:8]}"
                try:
                    db.archivio().salva_file(fid, byte[nome])
                    c["estratti"][-1].update(file_id=fid, nome_file=nome)
                except Exception:
                    pass
        pf["stato"] = "attivo"
        dati.salva_cliente(c)
        dati.salva_registro(reg)
        st.session_state.pop("cli_upload", None)
        nuovi = sorted(set(reg.strumenti) - prima)
        st.session_state["cli_msg"] = (f"Importati {n} elementi ({d} già presenti). " + (f"{len(nuovi)} prodotti nuovi: completa le condizioni in «Prodotti»." if nuovi else ""), avvisi)
        st.rerun()


def _estratti(c, reg, pf):
    """Movimenti come appaiono nell'estratto, con saldo; caricamento e inserimento a mano stanno in sezioni apribili."""
    tx = dati.transazioni_ordinate(dati.vista_portafoglio(c, pf["id"]))
    docs = c.get("estratti") or []
    anni = sorted({int(t["data"][:4]) for t in tx} | {int(x["a"][:4]) for x in docs if x.get("a")})
    with st.expander("Carica un estratto conto", expanded=bool(st.session_state.get("cli_upload"))):
        _carica_estratti(c, reg, pf)
    with st.expander("Inserisci un movimento a mano"):
        st.caption("Per ciò che non è (ancora) in un estratto: se il movimento esiste già lo salto. Quando carichi l'estratto, le righe già presenti vengono saltate e i saldi di fine mese vengono confrontati.")
        _form_movimento(c, reg, pf)
    with riquadro("blu", f"est_mov_{pf['id']}"):
        st.markdown("#### Tutti i movimenti in ordine cronologico")
        anno, mese = _filtro_periodo(f"est_{pf['id']}", anni)
        st.markdown("**Controllo dei saldi di fine mese**")
        _controllo_saldi(c, pf, anno, mese)
        st.markdown("**Movimenti**")
        dd = [x for x in docs if _nel_periodo(x.get("a", ""), anno, mese)]
        if dd:
            with st.expander(f"Documenti importati ({len(dd)})"):
                for i, x in enumerate(sorted(dd, key=lambda z: z.get("a", ""), reverse=True)):
                    a_, b_ = st.columns([4, 1], vertical_alignment="center")
                    a_.caption(f"{x.get('banca', '')} · dal {_gma(x.get('da', ''))} al {_gma(x.get('a', ''))} · {x.get('movimenti', 0)} movimenti" + (f" · {x['nome_file']}" if x.get("nome_file") else ""))
                    if x.get("file_id"):
                        from core import db
                        pdf = db.archivio().leggi_file(x["file_id"])
                        if pdf:
                            b_.download_button("PDF", pdf, file_name=x.get("nome_file") or "estratto.pdf", mime="application/pdf", key=f"est_dl_{pf['id']}_{i}")
        _movimenti(c, reg, pf, anno, mese)


def _gma(iso: str) -> str:
    """2026-03-31 → 31.03.2026"""
    return f"{iso[8:10]}.{iso[5:7]}.{iso[:4]}" if iso and len(iso) >= 10 and iso[4] == "-" else (iso or "")


def _form_movimento(c, reg, pf):
    """Inserimento manuale di un movimento (stesso risultato dell'estratto conto, senza doppioni)."""
    from core import movimenti
    v = dati.vista_portafoglio(c, pf["id"])
    prodotti = {k: x["nome"] for k, x in reg.strumenti.items() if any(t.get("strumento") == k for t in v["transazioni"])}
    gen = st.session_state.get(f"mv_gen_{pf['id']}", 0)
    tipi = [k for k in dati.ETICHETTE_TIPO]
    with st.form(f"mv_form_{pf['id']}_{gen}", border=False):
        a, b, d = st.columns(3)
        data = a.date_input("Data", format="DD.MM.YYYY")
        tipo = b.selectbox("Tipo di movimento", tipi, format_func=lambda k: dati.ETICHETTE_TIPO[k], index=tipi.index("costo_custodia"))
        val = d.selectbox("Valuta", VALUTE, index=VALUTE.index(pf["valuta"]) if pf["valuta"] in VALUTE else 0)
        a, b = st.columns(2)
        importo = a.number_input("Prezzo / importo (negativo = uscita)", value=0.0, step=100.0, format="%.2f")
        prodotto = b.selectbox("Prodotto collegato (facoltativo)", [""] + list(prodotti), format_func=lambda k: prodotti.get(k, "—"))
        a, b = st.columns([1, 2])
        imp_prev = a.checkbox("Soggetto a imposta preventiva (35%)", value=False)
        desc = b.text_input("Descrizione")
        if st.form_submit_button("Aggiungi movimento"):
            if importo == 0.0:
                st.error("Inserisci un importo diverso da zero.")
                return
            segno = -1 if tipo in ("acquisto", "costo", "costo_custodia", "imposta", "prelievo") and importo > 0 else 1
            tx = {"data": data.isoformat(), "tipo": tipo, "valuta": val, "importo_cassa": segno * importo, "banca": "", "conto": "", "strumento": prodotto,
                  "titolo": desc or dati.ETICHETTE_TIPO[tipo], "quantita": None, "portafoglio": pf["id"]}
            if movimenti.e_duplicato(c["transazioni"], tx):
                st.warning("Esiste già un movimento identico (stessa data, tipo e importo): non l'ho aggiunto.")
                return
            dati.aggiungi_movimento_manuale(c, **tx)
            if imp_prev and segno * importo > 0:
                dati.aggiungi_movimento_manuale(c, **{**tx, "tipo": "imposta", "importo_cassa": -round(0.35 * segno * importo, 2), "strumento": prodotto,
                                                      "titolo": "Imposta preventiva 35%" + (f" · {desc}" if desc else "")})
            dati.salva_cliente(c)
            st.session_state[f"mv_gen_{pf['id']}"] = gen + 1
            st.session_state["cli_msg"] = ("Movimento aggiunto" + (" con l'imposta preventiva." if imp_prev and segno * importo > 0 else "."), [])
            st.rerun()


def _controllo_saldi(c, pf, anno, mese):
    """Saldo di fine mese dell'estratto contro saldo precedente + movimenti: segnala le differenze."""
    from core import movimenti
    v = dati.vista_portafoglio(c, pf["id"])
    righe = movimenti.riconcilia(v["transazioni"], v["saldi"])
    righe = [r for r in righe if _nel_periodo(r["data"], anno, mese)]
    if not righe:
        st.caption("Nessun saldo di estratto conto nel periodo: i saldi si leggono dagli estratti caricati o si inseriscono qui sotto.")
    else:
        err = [r for r in righe if r["esito"] == "errore"]
        if err:
            st.error(f"{len(err)} saldi non tornano: manca o è errato qualche movimento, oppure c'è un doppione. Controlla la lista qui sotto.")
        elif any(r["esito"] == "ok" for r in righe):
            st.success("Tutti i saldi di fine periodo tornano con i movimenti inseriti.")
        df = pd.DataFrame([{"Esito": {"ok": "✓", "errore": "⚠", "punto di partenza": "·"}[r["esito"]], "Data": date.fromisoformat(r["data"]), "Banca · conto": f"{r['banca']} · {r['conto']}", "Valuta": r["valuta"],
                            "Saldo estratto": r["saldo_estratto"], "Saldo calcolato": r["saldo_calcolato"], "Differenza": r["differenza"]} for r in righe])
        st.dataframe(df, hide_index=True, width="stretch", column_config={"Data": st.column_config.DateColumn(format="DD.MM.YYYY")} | {x: st.column_config.NumberColumn(format="%.2f") for x in ("Saldo estratto", "Saldo calcolato", "Differenza")})
        st.caption("«Saldo calcolato» = saldo dell'estratto precedente + movimenti del conto fino alla data. · = primo saldo, usato come punto di partenza.")
    with st.expander("Inserisci un saldo di fine mese (se non hai l'estratto)"):
        a, b, d, e = st.columns(4)
        conti = sorted({(s["banca"], s["conto"]) for s in v["saldi"]} | {(t.get("banca") or "", t.get("conto") or "") for t in v["transazioni"] if t.get("banca")})
        sc = a.selectbox("Conto", [f"{x} · {y}" for x, y in conti] or ["(nessun conto)"], key=f"sd_c_{pf['id']}")
        dd = b.date_input("Alla data", format="DD.MM.YYYY", key=f"sd_d_{pf['id']}")
        vv = d.selectbox("Valuta", VALUTE, index=VALUTE.index(pf["valuta"]) if pf["valuta"] in VALUTE else 0, key=f"sd_v_{pf['id']}")
        sv = e.number_input("Saldo", value=0.0, step=100.0, format="%.2f", key=f"sd_s_{pf['id']}")
        if bottone("Salva il saldo", "verde", f"sd_ok_{pf['id']}") and conti:
            banca, _, cc = (x.strip() for x in sc.partition("·"))
            c["saldi"] = [x for x in c["saldi"] if not (x["banca"] == banca and x["conto"] == cc and x["valuta"] == vv and x["data"] == dd.isoformat() and x.get("portafoglio", pf["id"]) == pf["id"])]
            c["saldi"].append({"banca": banca, "conto": cc, "valuta": vv, "data": dd.isoformat(), "saldo": sv, "portafoglio": pf["id"]})
            dati.salva_cliente(c)
            st.rerun()


def _saldi_progressivi(tx_tutte: list[dict], saldi: list[dict]) -> dict[str, float]:
    """Saldo dopo ogni movimento, per valuta: somma progressiva ancorata all'ultimo saldo di estratto noto (se c'è)."""
    cum, per_id = {}, {}
    for t in tx_tutte:
        cum[t["valuta"]] = cum.get(t["valuta"], 0.0) + (t.get("importo_cassa") or 0.0)
        per_id[t["id"]] = (t["valuta"], cum[t["valuta"]], t["data"])
    scarto = {}
    for val in cum:
        ss = sorted([s for s in saldi if s["valuta"] == val], key=lambda s: s["data"])
        if ss:
            ultimo = ss[-1]
            fino = sum((t.get("importo_cassa") or 0.0) for t in tx_tutte if t["valuta"] == val and t["data"] <= ultimo["data"])
            scarto[val] = ultimo["saldo"] - fino
    return {i: v_ + scarto.get(val, 0.0) for i, (val, v_, _) in per_id.items()}


def _movimenti(c, reg, pf, anno=None, mese=None):
    from core import movimenti
    from core.stile import num_ch
    from modules.strategia import _pn
    v = dati.vista_portafoglio(c, pf["id"])
    tutte = dati.transazioni_ordinate(v)
    saldo = _saldi_progressivi(tutte, v["saldi"])
    tx = [t for t in tutte if _nel_periodo(t["data"], anno, mese)]
    if not tx:
        st.info("Nessun movimento nel periodo scelto.")
        return
    n = lambda x, d=2: "" if x is None else num_ch(x, d)
    righe = [{"id": t["id"], "Elimina": False, "Stato": movimenti.stato_riga(t), "Data": date.fromisoformat(t["data"]), "Banca · conto": f"{t.get('banca') or ''} · {t.get('conto') or ''}".strip(" ·"),
              "Tipo": dati.ETICHETTE_TIPO.get(t["tipo"], t["tipo"]), "Strumento / descrizione": (reg.strumenti.get(t.get("strumento")) or {}).get("nome") or t.get("titolo", ""),
              "Quantità": n(t.get("quantita"), 2), "Prezzo": n(t.get("prezzo"), 4), "Valuta": t["valuta"], "Importo": n(t.get("importo_cassa")),
              "Saldo": n(saldo.get(t["id"])), "Origine": t.get("fonte", "")} for t in tx]
    da_fare = sum(1 for r in righe if r["Stato"] != "registrato")
    if da_fare:
        st.warning(f"{da_fare} movimenti sono «previsti» o «da completare»: confermali con l'estratto conto o completali qui sotto.")
    ed = st.data_editor(pd.DataFrame(righe), hide_index=True, width="stretch", key=f"cli_mov_ed_{pf['id']}",
                        column_config={"id": None, "Data": st.column_config.DateColumn(format="DD.MM.YYYY"), "Saldo": st.column_config.TextColumn(help="Saldo del conto dopo il movimento, allineato all'ultimo saldo dell'estratto.")},
                        disabled=["Stato", "Banca · conto", "Tipo", "Strumento / descrizione", "Valuta", "Saldo", "Origine"])
    b1, _ = st.columns([1, 3])
    with b1:
        if bottone("Salva modifiche ai movimenti", "verde", "cli_mov_salva", width="stretch"):
            per_id = {t["id"]: t for t in c["transazioni"]}
            el = 0
            for r in ed.to_dict("records"):
                t = per_id[r["id"]]
                if r["Elimina"]:
                    c["transazioni"].remove(t); el += 1; continue
                t["data"] = r["Data"].isoformat() if hasattr(r["Data"], "isoformat") else str(r["Data"])
                t["quantita"] = _pn(r["Quantità"])
                t["prezzo"] = _pn(r["Prezzo"])
                imp = _pn(r["Importo"])
                if imp is not None:
                    t["importo_cassa"] = imp
            dati.salva_cliente(c)
            st.session_state["cli_msg"] = (f"Salvato ({el} eliminati)." if el else "Salvato.", [])
            st.rerun()


def _dati(c):
    with st.container(border=True):
        c1, c2 = st.columns(2)
        nome = c1.text_input("Nome", c.get("nome_proprio", c["nome"]), key="dc_nome")
        cognome = c2.text_input("Cognome", c.get("cognome", ""), key="dc_cogn")
        c1, c2 = st.columns(2)
        valuta = c1.selectbox("Valuta di riferimento (predefinita per le nuove strategie)", VALUTE_BASE, index=VALUTE_BASE.index(c["valuta_base"]) if c["valuta_base"] in VALUTE_BASE else 0, key="dc_val")
        rischio = c2.selectbox("Grado di rischio (1 basso – 5 alto)", [1, 2, 3, 4, 5], index=int(c.get("rischio", 2)) - 1, key="dc_risc")
        note = st.text_area("Note", c.get("note", ""), key="dc_note")
        b1, b2, _ = st.columns([1, 1, 3])
        with b1:
            if bottone("Salva", "verde", "dc_salva", width="stretch"):
                c.update(nome=f"{nome.strip()} {cognome.strip()}".strip() or c["nome"], nome_proprio=nome.strip(), cognome=cognome.strip(), valuta_base=valuta, rischio=rischio, note=note)
                dati.salva_cliente(c)
                st.success("Salvato.")
        with b2:
            if bottone("Elimina cliente", "giallo", "cli_elimina", width="stretch"):
                st.session_state["cli_elimina_chiedi"] = True
    if st.session_state.get("cli_elimina_chiedi"):
        st.warning(f"Eliminare definitivamente {c['nome']} con tutte le strategie e i movimenti? Non si può annullare.")
        y1, y2, _ = st.columns([1, 1, 3])
        with y1:
            if bottone("Sì, elimina", "giallo", "cli_elimina_ok", width="stretch"):
                dati.elimina_cliente(c["id"])
                st.session_state.pop("cli_id", None)
                st.session_state.pop("cli_elimina_chiedi", None)
                vai("clienti")
        with y2:
            if st.button("Annulla", key="cli_elimina_no", width="stretch"):
                st.session_state.pop("cli_elimina_chiedi", None)
                st.rerun()


def _selettore_portafoglio(c):
    """Un solo riquadro blu: scelta della strategia, nuova strategia e modifica dei suoi dati."""
    pfs = dati.assicura_portafogli(c)
    with riquadro("blu", "pf_sel"):
        a, b = st.columns([3, 1], vertical_alignment="bottom")
        if pfs:
            ids = [p["id"] for p in pfs]
            pre = st.session_state.get("cli_pf")
            if pre not in ids:
                pre = ids[0]
            st.session_state["cli_pf"] = a.selectbox("Strategia", ids, index=ids.index(pre), key="cli_pf_sel",
                                                     format_func=lambda i: next(f"{p['nome']} · {p['valuta']}" for p in pfs if p["id"] == i))
        else:
            a.info("Nessuna strategia: creane una per questo cliente.")
        with b.popover("➕ Nuova strategia", width="stretch"):
            nome = st.text_input("Nome", f"Strategia {len(pfs) + 1}", key="npf_nome")
            vv = ["CHF", "EUR", "USD", "GBP", "JPY"]
            val = st.selectbox("Valuta di questa strategia", vv, index=vv.index(c["valuta_base"]) if c["valuta_base"] in vv else 0, key="npf_val")
            cap = st.number_input(f"Capitale da investire ({val}) – facoltativo", min_value=0.0, value=0.0, step=1000.0, key="npf_cap")
            if bottone("Crea", "verde", "npf_crea"):
                pf = dati.nuovo_portafoglio(c, nome, cap, val)
                dati.salva_cliente(c)
                st.session_state["cli_pf"] = pf["id"]
                st.rerun()
        pf = dati.portafoglio(c, st.session_state.get("cli_pf")) if pfs else None
        if pf:
            from modules import strategia
            strategia.testata(c, pf)
    return pf


def render():
    c = dati.carica_cliente(st.session_state.get("cli_id", "")) if st.session_state.get("cli_id") else None
    if not c:
        vai("clienti")
        return
    intestazione(c["nome"], f"{c['valuta_base']} · rischio {c.get('rischio', '-')}")
    reg = dati.carica_registro()
    if reg.allinea(c):                      # prodotti promossi da simbolo a ISIN altrove: le righe non devono sparire
        dati.salva_cliente(c)
    msg = st.session_state.pop("cli_msg", None)
    if msg:
        st.success(msg[0])
        for a in msg[1]:
            st.warning(a)
    pf = _selettore_portafoglio(c)
    if pf is None:
        _dati(c)
        return
    from modules import andamento, strategia
    if len(c.get("portafogli", [])) > 1:
        ser = live_serie(c)
        if len(ser) >= 2:
            with st.expander("Andamento complessivo di tutte le strategie del cliente"):
                strategia.linea(ser)
    t = st.tabs(["Strategia", "Andamento", "Prodotti", "Movimenti", "Cliente"])
    with t[0]:
        strategia.render(c, reg, pf)
    with t[1]:
        andamento.render(c, reg, pf)
    with t[2]:
        _prodotti(c, reg, pf)
    with t[3]:
        _estratti(c, reg, pf)
    with t[4]:
        _dati(c)
