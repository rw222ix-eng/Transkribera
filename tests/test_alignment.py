"""Tidsättningen: textnormalisering, meningsgränser och luckor.

Ingen GPU och ingen modell laddas — det som testas är kringlogiken som avgör
VAD som alignas och hur ordtiderna blir segment. Själva Viterbi-sökningen är
torchaudios och testas inte om här.
"""
from app import alignment
from app.transcriber import MAX_CAPTION_CHARS


VOKAB = {c: i for i, c in enumerate("|ABCDEFGHIJKLMNOPQRSTUVWXYZÅÄÖ")}


# ---- Normalisering ---------------------------------------------------------

def test_ordet_versaliseras_mot_en_versal_vokabular():
    assert alignment._normalisera("derivatan", VOKAB, True) == "DERIVATAN"


def test_siffror_och_tecken_faller_bort():
    # En CTC-vokabulär har inga siffror; "2026" krymper till ingenting och får
    # sin tid interpolerad i stället.
    assert alignment._normalisera("2026!", VOKAB, True) == ""
    assert alignment._normalisera("h(x)", VOKAB, True) == "HX"


def test_svenska_tecken_overlever():
    assert alignment._normalisera("förändring", VOKAB, True) == "FÖRÄNDRING"


# ---- Luckor ----------------------------------------------------------------

def test_ord_utan_tid_hamnar_mellan_grannarna():
    ord_ = [{"text": "år", "start": 1.0, "end": 2.0},
            {"text": "2026", "start": None, "end": None},
            {"text": "kom", "start": 3.0, "end": 4.0}]
    alignment._fyll_luckor(ord_, 10.0)
    assert ord_[1]["start"] == 2.0 and ord_[1]["end"] == 3.0


def test_lucka_forst_och_sist_klamms_mot_bitens_kanter():
    ord_ = [{"text": "§", "start": None, "end": None},
            {"text": "ord", "start": 2.0, "end": 3.0},
            {"text": "77", "start": None, "end": None}]
    alignment._fyll_luckor(ord_, 9.0)
    assert ord_[0]["start"] == 0.0 and ord_[0]["end"] == 2.0
    assert ord_[2]["start"] == 3.0 and ord_[2]["end"] == 9.0


# ---- Meningar --------------------------------------------------------------

def _ord(text, start, langd=0.4):
    return {"text": text, "start": start, "end": start + langd}


def test_punkt_avslutar_meningen_och_tiderna_ar_ordens():
    ord_ = [_ord("Vi", 1.0), _ord("räknade.", 1.5), _ord("Sedan", 3.0), _ord("gick", 3.5)]
    seg = alignment._meningar(ord_, forskjutning=0.0)
    assert [s["text"] for s in seg] == ["Vi räknade.", "Sedan gick"]
    assert seg[0]["start"] == 1.0 and seg[0]["end"] == 1.9


def test_forskjutningen_lagger_bitens_starttid_pa_allt():
    seg = alignment._meningar([_ord("Hej.", 2.0)], forskjutning=300.0)
    assert seg[0]["start"] == 302.0
    assert seg[0]["words"][0]["start"] == 302.0


def test_text_utan_skiljetecken_bryts_anda():
    # Sångtext och uppläsning i ett svep saknar punkter. Utan tak blev hela
    # biten ETT segment — oanvändbart som undertext och som källmarkör.
    ord_ = [_ord(f"ord{i}", i * 0.5) for i in range(60)]
    seg = alignment._meningar(ord_, forskjutning=0.0)
    assert len(seg) > 1
    assert all(len(s["text"]) <= MAX_CAPTION_CHARS for s in seg)


def test_orden_bevaras_i_ordning_over_brytningen():
    ord_ = [_ord(f"ord{i}", i * 0.5) for i in range(60)]
    seg = alignment._meningar(ord_, forskjutning=0.0)
    tillbaka = [w["text"] for s in seg for w in s["words"]]
    assert tillbaka == [o["text"] for o in ord_]


def test_langa_tysta_stracker_bryts_pa_tid():
    # Ett ord var tjugonde sekund ska inte bli en enda cue som spänner minuter.
    ord_ = [_ord("a", 0.0), _ord("b", 20.0), _ord("c", 40.0), _ord("d", 60.0)]
    seg = alignment._meningar(ord_, forskjutning=0.0)
    assert len(seg) > 1


# ---- Modellens plats -------------------------------------------------------

def test_modellmappen_ligger_under_modellroten(tmp_path):
    d = alignment.modell_dir(tmp_path)
    assert d.parent == tmp_path
    assert "/" not in d.name and "\\" not in d.name


def test_ofullstandig_nedladdning_raknas_inte_som_installerad(tmp_path):
    d = alignment.modell_dir(tmp_path)
    d.mkdir(parents=True)
    (d / "vocab.json").write_text("{}", encoding="utf-8")
    assert alignment.ar_installerad(tmp_path) is False      # vikterna saknas
    (d / "model.safetensors").write_bytes(b"x")
    assert alignment.ar_installerad(tmp_path) is True


def test_radera_vagrar_utanfor_modellroten(tmp_path):
    assert alignment.radera(tmp_path) is False              # finns inte → inget raderas
