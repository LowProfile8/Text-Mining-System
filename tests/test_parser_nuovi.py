"""Parser UBS, Swissquote, posizioni (Performance del portafoglio, Estratto patrimoniale). Si saltano se i PDF di esempio non ci sono."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core.importatore import leggi_documento

U = Path("/root/.claude/uploads/1f95d8fd-ed72-5ab0-9b6a-a36fe1f388a9")
F = {
    "ubs_conto": U / "1aacb115-0247000016613661E0000_Estratto_del_conto_20261001173014598930.pdf",
    "ubs_patr": U / "6c4f23a8-0247000016613601null_Estrattopatrimonialeal31122025_20260106143019265796_copy.pdf",
    "sq_conto": U / "74a93918-Estrattoconto_8.pdf",
    "pf_perf": U / "bb745b71-Performance_del_portafoglio_2930204_20260106_copy.pdf",
    "sq_perf": U / "07054197-Performancedelportafoglio.pdf",
    "pf_conto": U / "aa585c10-Estrattoconto_8_copy.pdf",
}
pytestmark = pytest.mark.skipif(not all(p.exists() for p in F.values()), reason="PDF di esempio non disponibili")


def test_ubs_conto():
    t, e = leggi_documento(F["ubs_conto"])
    assert t == "movimenti" and e.banca == "UBS" and e.quadra and len(e.movimenti) == 8
    assert sum(1 for m in e.movimenti if m["tipo"] == "dividendo") == 4


def test_swissquote_conto():
    t, e = leggi_documento(F["sq_conto"])
    assert t == "movimenti" and e.banca == "Swissquote" and e.quadra and not e.avvisi
    assert {m["tipo"] for m in e.movimenti} >= {"deposito", "acquisto", "costo_custodia"}


def test_postfinance_trasferimenti_interni():
    t, e = leggi_documento(F["pf_conto"])
    assert e.quadra and sum(1 for m in e.movimenti if m["tipo"] == "trasferimento") == 5


def test_performance_portafoglio_quadra():
    for k, n_pos in (("pf_perf", 11), ("sq_perf", 2)):
        t, d = leggi_documento(F[k])
        assert t == "posizioni" and d["quadra"] and len(d["posizioni"]) == n_pos


def test_ubs_patrimoniale():
    t, d = leggi_documento(F["ubs_patr"])
    assert t == "posizioni" and d["quadra"]
    assert len(d["posizioni"]) == 6                       # deposito a termine + 5 prodotti strutturati
    brc = [p for p in d["posizioni"] if p.get("barriera_pct")]
    assert {p["barriera_pct"] for p in brc} == {58.5, 53.75}
