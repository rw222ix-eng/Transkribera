"""Nedladdningen i skrivbordsappen: filen ska heta .pdf och ligga i Hämtat.

Lärarens fynd 2026-09-12: «Ladda ner PDF» på en godkänd tavla gav
«Tavla — 1.3 Andelar och förhållanden bygg tisdag» — utan ändelse, med
generisk ikon, och den öppnades inte som PDF. Mätningen samma dag visade att
WebView2 lämnar över rätt sökväg med .pdf och MimeType application/pdf; det var
pywebviews SaveFileDialog som gav tillbaka namnet utan ändelse (HideFileExt),
och .NET kunde inte lägga på den igen — punkten i «1.3» såg ut som en ändelse
för Path.GetExtension.

Testerna här vaktar det som går att pröva utan fönster: att «1.3» inte
misstas för en ändelse, att MIME-typen fyller i den som saknas, och att två
nedladdningar av samma tavla inte skriver över varandra.
"""
from __future__ import annotations

from pathlib import Path

from app.web import desktop


# ── ändelsen ur MIME-typen ──────────────────────────────────────────────────
def test_mime_ger_andelse():
    assert desktop._andelse_ur_mime("application/pdf") == ".pdf"
    # Huvudet får bära teckenuppsättning — servern skickar det ibland.
    assert desktop._andelse_ur_mime("application/pdf; charset=utf-8") == ".pdf"
    assert desktop._andelse_ur_mime("APPLICATION/PDF") == ".pdf"
    assert desktop._andelse_ur_mime("image/png") == ".png"
    assert desktop._andelse_ur_mime("") == ""


def test_punkt_i_kapitelnummer_ar_ingen_andelse():
    """Kärnan i buggen: «1.3» får inte räknas som en filändelse."""
    assert not desktop._ser_ut_som_andelse("3 Andelar och förhållanden bygg tisdag")
    assert not desktop._ser_ut_som_andelse("")
    # Ett namn som slutar på kapitelnummer: «Prov kap 2.3» har ingen ändelse.
    assert not desktop._ser_ut_som_andelse("3")
    # Inga ändelser heter «höst» — ett svenskt ord efter punkten är text.
    assert not desktop._ser_ut_som_andelse("höst")
    assert desktop._ser_ut_som_andelse("pdf")
    assert desktop._ser_ut_som_andelse("PDF")
    assert desktop._ser_ut_som_andelse("mp3")


def test_namn_som_slutar_pa_kapitelnummer_far_andelse():
    assert desktop._filnamn("Prov kap 2.3", "application/pdf") == "Prov kap 2.3.pdf"


# ── filnamnet ───────────────────────────────────────────────────────────────
LARARENS = "Tavla — 1.3 Andelar och förhållanden bygg tisdag"


def test_lararens_tavla_far_sin_andelse():
    assert desktop._filnamn(LARARENS, "application/pdf") == LARARENS + ".pdf"


def test_namn_som_redan_har_andelsen_far_ingen_till():
    assert desktop._filnamn(LARARENS + ".pdf", "application/pdf") == LARARENS + ".pdf"


def test_egen_andelse_behalls():
    """En fil som redan heter rätt ska inte bli «bok.zip.pdf»."""
    assert desktop._filnamn("bok.zip", "application/pdf") == "bok.zip"


def test_forbjudna_tecken_stadas_bort():
    ut = desktop._filnamn('Prov: kap 2/3 "höst"?', "application/pdf")
    assert not set(ut) & set('\\/:*?"<>|')
    assert ut.endswith(".pdf")


def test_tomt_namn_blir_nagot():
    assert desktop._filnamn("", "application/pdf") == "Hamtad fil.pdf"
    # Windows tål inte avslutande punkt eller mellanslag.
    assert desktop._filnamn("Tavla. ", "application/pdf") == "Tavla.pdf"


def test_okand_mime_ger_namnet_orort():
    assert desktop._filnamn(LARARENS, "") == LARARENS


# ── mappen och kollisionerna ────────────────────────────────────────────────
def test_hamtat_kan_pekas_om(monkeypatch, tmp_path):
    monkeypatch.setenv("TRANSKRIBERA_HAMTAT", str(tmp_path / "Hamtat"))
    assert desktop._hamtat_mapp() == tmp_path / "Hamtat"


def test_samma_tavla_tva_ganger_skriver_inte_over(tmp_path):
    namn = LARARENS + ".pdf"
    forst = desktop._ledig_fil(tmp_path, namn)
    assert forst == tmp_path / namn
    forst.write_bytes(b"%PDF-1.4")

    sedan = desktop._ledig_fil(tmp_path, namn)
    assert sedan.name == LARARENS + " (2).pdf"
    sedan.write_bytes(b"%PDF-1.4")

    assert desktop._ledig_fil(tmp_path, namn).name == LARARENS + " (3).pdf"


def test_ledig_fil_skapar_mappen(tmp_path):
    mapp = tmp_path / "Hamtat" / "djupare"
    assert desktop._ledig_fil(mapp, "Tavla.pdf") == mapp / "Tavla.pdf"
    assert mapp.is_dir()


def test_utan_andelse_numreras_ocksa(tmp_path):
    (tmp_path / "Tavla").write_text("x", encoding="utf-8")
    assert desktop._ledig_fil(tmp_path, "Tavla").name == "Tavla (2)"


# ── hanteraren ──────────────────────────────────────────────────────────────
class _Op:
    """Så mycket av CoreWebView2DownloadOperation som hanteraren rör."""

    def __init__(self, mime):
        self.MimeType = mime
        self.State = "InProgress"
        self.ResultFilePath = ""
        self.StateChanged = self

    def __iadd__(self, hake):        # op.StateChanged += hake
        self.hake = hake
        return self


class _Args:
    def __init__(self, sokvag, mime):
        self.ResultFilePath = sokvag
        self.DownloadOperation = _Op(mime)
        self.Handled = False


def test_hanteraren_styr_om_till_hamtat(monkeypatch, tmp_path):
    """Hela vägen: WebView2:s förslag in, en fil i Hämtat ut.

    Sökvägen in är exakt den som mätningen 2026-09-12 loggade."""
    hamtat = tmp_path / "Hamtat"
    monkeypatch.setenv("TRANSKRIBERA_HAMTAT", str(hamtat))
    args = _Args(str(Path("C:/Users/bolun/Downloads") / (LARARENS + ".pdf")),
                 "application/pdf")

    desktop._pa_nedladdning(None, None, args)

    assert Path(args.ResultFilePath).parent == hamtat
    assert Path(args.ResultFilePath).name == LARARENS + ".pdf"
    # Ingen nedladdningsruta från Edge — appen har sin egen toast.
    assert args.Handled is True


def test_hanteraren_lagger_pa_andelsen_nar_den_saknas(monkeypatch, tmp_path):
    monkeypatch.setenv("TRANSKRIBERA_HAMTAT", str(tmp_path))
    args = _Args("C:/Users/bolun/Downloads/" + LARARENS, "application/pdf")
    desktop._pa_nedladdning(None, None, args)
    assert Path(args.ResultFilePath).name == LARARENS + ".pdf"


def test_hanteraren_visar_filen_nar_den_ar_klar(monkeypatch, tmp_path):
    monkeypatch.setenv("TRANSKRIBERA_HAMTAT", str(tmp_path))
    visade = []
    monkeypatch.setattr(desktop.filhanterare, "markera", visade.append)
    args = _Args("C:/x/" + LARARENS + ".pdf", "application/pdf")
    desktop._pa_nedladdning(None, None, args)

    op = args.DownloadOperation
    op.hake(None, None)              # fortfarande InProgress
    assert visade == []

    op.State = "Completed"
    op.ResultFilePath = args.ResultFilePath
    op.hake(None, None)
    assert visade == [args.ResultFilePath]


def test_avbruten_nedladdning_oppnar_ingen_mapp(monkeypatch, tmp_path):
    monkeypatch.setenv("TRANSKRIBERA_HAMTAT", str(tmp_path))
    visade = []
    monkeypatch.setattr(desktop.filhanterare, "markera", visade.append)
    args = _Args("C:/x/Tavla.pdf", "application/pdf")
    desktop._pa_nedladdning(None, None, args)

    op = args.DownloadOperation
    op.State = "Interrupted"
    op.hake(None, None)
    assert visade == []
