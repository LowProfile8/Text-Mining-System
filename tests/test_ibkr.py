import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

SHOT = Path(__file__).resolve().parent.parent / "dati_prova" / "ib_screenshot.png"


@pytest.mark.skipif(not SHOT.exists(), reason="screenshot di esempio assente")
def test_lettura_screenshot_ibkr():
    pytest.importorskip("pytesseract")
    from PIL import Image
    from core.parser_ibkr import parse_immagine
    pos = {p.simbolo: p for p in parse_immagine(Image.open(SHOT))}
    assert len(pos) == 13
    assert pos["CAN"].quantita == 1000 and pos["CAN"].costo_totale == 799.06 and pos["CAN"].valuta == "USD"
    assert pos["UEC"].quantita == 360 and pos["UEC"].costo_totale == 4119.18
    assert pos["CEMR"].valuta == "EUR" and pos["IWVL"].valuta == "EUR" and pos["WDEF"].valuta == "EUR" and pos["IWDE"].valuta == "EUR"
    assert pos["IWDE"].quantita == 43 and pos["IWDE"].costo_totale == 4501.3
    assert pos["GDIG"].prezzo_effettivo() == pytest.approx(2874.5 / 45)
    assert "CANAAN" in pos["CAN"].nome
