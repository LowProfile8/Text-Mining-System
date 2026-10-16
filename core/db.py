"""Archivio dei dati: Supabase se collegato, altrimenti file locali (solo per prove: si azzerano su Streamlit Cloud).

Due tabelle in Supabase (vedi supabase_schema.sql):
  documenti(collezione, id, dati jsonb, aggiornato)   -> clienti, strumenti, report, prezzi manuali
  file(id, b64)                                       -> i PDF dei report
"""

from __future__ import annotations

import base64
import json
import re
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

from core.config import DATI_LOCALI


def _secret(nome: str) -> Optional[str]:
    try:
        import streamlit as st
        v = st.secrets.get(nome)
        return str(v) if v else None
    except Exception:
        return None


def nuovo_id() -> str:
    return uuid.uuid4().hex[:12]


def _sicuro(nome: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]", "_", nome)


class ArchivioLocale:
    nome = "locale"

    def __init__(self, radice: Path = DATI_LOCALI):
        self.radice = radice

    def _p(self, coll, id_):
        return self.radice / _sicuro(coll) / f"{_sicuro(id_)}.json"

    def leggi(self, coll, id_):
        p = self._p(coll, id_)
        return json.loads(p.read_text()) if p.exists() else None

    def scrivi(self, coll, id_, dati):
        p = self._p(coll, id_)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(dati, ensure_ascii=False))

    def elenca(self, coll):
        cartella = self.radice / _sicuro(coll)
        if not cartella.exists():
            return []
        return [json.loads(p.read_text()) for p in sorted(cartella.glob("*.json"))]

    def elimina(self, coll, id_):
        p = self._p(coll, id_)
        if p.exists():
            p.unlink()

    def salva_file(self, id_, dati: bytes):
        p = self.radice / "file" / _sicuro(id_)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(dati)

    def leggi_file(self, id_) -> Optional[bytes]:
        p = self.radice / "file" / _sicuro(id_)
        return p.read_bytes() if p.exists() else None

    def elimina_file(self, id_):
        p = self.radice / "file" / _sicuro(id_)
        if p.exists():
            p.unlink()

    def verifica(self):
        return "locale", "dati salvati solo su questo computer"


class ArchivioSupabase:
    nome = "supabase"

    def __init__(self, url: str, chiave: str):
        from supabase import create_client
        self.c = create_client(url, chiave)

    def leggi(self, coll, id_):
        r = self.c.table("documenti").select("dati").eq("collezione", coll).eq("id", id_).limit(1).execute()
        return r.data[0]["dati"] if r.data else None

    def scrivi(self, coll, id_, dati):
        self.c.table("documenti").upsert({"collezione": coll, "id": id_, "dati": dati, "aggiornato": datetime.utcnow().isoformat()}).execute()

    def elenca(self, coll):
        r = self.c.table("documenti").select("dati").eq("collezione", coll).execute()
        return [x["dati"] for x in r.data]

    def elimina(self, coll, id_):
        self.c.table("documenti").delete().eq("collezione", coll).eq("id", id_).execute()

    def salva_file(self, id_, dati: bytes):
        self.c.table("file").upsert({"id": id_, "b64": base64.b64encode(dati).decode()}).execute()

    def leggi_file(self, id_):
        r = self.c.table("file").select("b64").eq("id", id_).limit(1).execute()
        return base64.b64decode(r.data[0]["b64"]) if r.data else None

    def elimina_file(self, id_):
        self.c.table("file").delete().eq("id", id_).execute()

    def verifica(self):
        self.c.table("documenti").select("id").limit(1).execute()
        return "attivo", "Supabase risponde"


class ArchivioVeloce:
    """Davanti a un archivio lento (Supabase): le letture vengono dalla memoria e le scritture partono in background, in ordine.
    L'interfaccia non aspetta più la rete a ogni salvataggio; `attendi()` aspetta che tutto sia scritto e `errore` riporta eventuali guasti."""

    def __init__(self, base):
        import copy, queue, threading
        self._copy = copy.deepcopy
        self.base = base
        self.nome = base.nome
        self._doc: dict = {}
        self._elenchi: dict = {}
        self._coda: "queue.Queue" = queue.Queue()
        self.errore = ""
        self._lock = threading.RLock()
        threading.Thread(target=self._lavora, daemon=True).start()

    def _lavora(self):
        while True:
            fn, args = self._coda.get()
            try:
                fn(*args)
            except Exception as e:             # la scrittura non è riuscita: l'interfaccia lo mostra
                self.errore = f"{type(e).__name__}: {e}"[:200]
            finally:
                self._coda.task_done()

    def attendi(self):
        self._coda.join()

    def leggi(self, coll, id_):
        with self._lock:
            if (coll, id_) in self._doc:
                v = self._doc[(coll, id_)]
                return self._copy(v) if v is not None else None
        v = self.base.leggi(coll, id_)
        with self._lock:
            self._doc[(coll, id_)] = self._copy(v) if v is not None else None
        return v

    def scrivi(self, coll, id_, dati):
        with self._lock:
            self._doc[(coll, id_)] = self._copy(dati)
            self._elenchi.pop(coll, None)
        self._coda.put((self.base.scrivi, (coll, id_, self._copy(dati))))

    def elenca(self, coll):
        with self._lock:
            if coll in self._elenchi:
                return self._copy(self._elenchi[coll])
        self.attendi()                       # prima che le scritture in corso siano arrivate, l'elenco della rete sarebbe vecchio
        v = self.base.elenca(coll)
        with self._lock:
            self._elenchi[coll] = self._copy(v)
        return v

    def elimina(self, coll, id_):
        with self._lock:
            self._doc[(coll, id_)] = None
            self._elenchi.pop(coll, None)
        self._coda.put((self.base.elimina, (coll, id_)))

    def salva_file(self, id_, dati: bytes):
        self._coda.put((self.base.salva_file, (id_, dati)))

    def leggi_file(self, id_):
        self.attendi()
        return self.base.leggi_file(id_)

    def elimina_file(self, id_):
        self._coda.put((self.base.elimina_file, (id_,)))

    def verifica(self):
        return self.base.verifica()


_archivio = None
_errore_cloud = ""
_verifica_ts = 0.0
_verifica_esito = ("", "")


def archivio():
    """Archivio in uso: Supabase se i secrets ci sono e rispondono, altrimenti locale."""
    global _archivio, _errore_cloud
    if _archivio is not None:
        return _archivio
    url, chiave = _secret("SUPABASE_URL"), _secret("SUPABASE_KEY")
    if url and chiave:
        try:
            a = ArchivioSupabase(url, chiave)
            a.verifica()
            _archivio = ArchivioVeloce(a)
            return _archivio
        except Exception as e:      # configurato ma non raggiungibile: NON si ripiega in silenzio sul locale
            _errore_cloud = str(e)[:200]
            raise ConnectionError(_errore_cloud)
    _archivio = ArchivioLocale()
    return _archivio


def stato_cloud() -> tuple[str, str]:
    """('attivo'|'locale'|'errore', dettaglio) — per il pallino in basso a sinistra."""
    url, chiave = _secret("SUPABASE_URL"), _secret("SUPABASE_KEY")
    if not (url and chiave):
        return "locale", "Supabase non configurato"
    global _verifica_ts, _verifica_esito
    import time
    if _verifica_esito and _verifica_esito[0] == "attivo" and time.time() - _verifica_ts < 60:      # un controllo al minuto, non a ogni ricarico
        a = _archivio
        if getattr(a, "errore", ""):
            return "errore", f"ultimo salvataggio non riuscito: {a.errore}"
        return _verifica_esito
    try:
        _verifica_esito = archivio().verifica()
        _verifica_ts = time.time()
        return _verifica_esito
    except Exception as e:
        return "errore", str(e)[:200]


def reimposta():
    global _archivio
    _archivio = None
