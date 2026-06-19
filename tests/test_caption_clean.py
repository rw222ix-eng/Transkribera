from app.transcriber import (
    Segment, group_into_sentences, polish_captions,
    clean_caption_segments, clean_caption_dicts,
)


# ---- group_into_sentences ----

def test_group_merges_fragments_into_one_sentence():
    out = group_into_sentences([Segment(0, 1, "Hej och"), Segment(1, 2, "välkommen.")])
    assert len(out) == 1
    assert (out[0].start, out[0].end, out[0].text) == (0, 2, "Hej och välkommen.")


def test_group_keeps_two_sentences_separate():
    out = group_into_sentences([Segment(0, 1, "Hej."), Segment(1, 2, "Då kör vi.")])
    assert [s.text for s in out] == ["Hej.", "Då kör vi."]


def test_group_caps_length_at_segment_boundary():
    a, b = "x" * 50, "y" * 50  # 101 tillsammans > 84, inget skiljetecken
    out = group_into_sentences([Segment(0, 1, a), Segment(1, 2, b)])
    assert len(out) == 2
    assert out[0].text == a and (out[0].start, out[0].end) == (0, 1)
    assert out[1].text == b


def test_group_safety_brake_after_30s():
    out = group_into_sentences([Segment(0, 15, "aa"), Segment(15, 32, "bb"), Segment(32, 40, "cc")])
    assert len(out) == 2
    assert (out[0].start, out[0].end) == (0, 32)
    assert out[1].text == "cc"


def test_group_splits_single_oversized_segment():
    text = " ".join(["word"] * 30)  # 149 tecken
    out = group_into_sentences([Segment(0, 10, text)])
    assert len(out) >= 2
    assert out[0].start == 0 and out[-1].end == 10
    assert all(len(s.text) <= 84 for s in out)


# ---- polish_captions ----

def test_polish_moves_leading_punct_to_previous():
    out = polish_captions([Segment(0, 1, "Hej"), Segment(1, 2, ". Då")])
    assert [s.text for s in out] == ["Hej.", "Då"]


def test_polish_drops_punctuation_only_cue():
    out = polish_captions([Segment(0, 1, "Hej"), Segment(1, 2, ".")])
    assert [s.text for s in out] == ["Hej."]


def test_polish_strips_leading_punct_on_first_cue():
    out = polish_captions([Segment(0, 1, ". Hej")])
    assert [s.text for s in out] == ["Hej"]


def test_polish_keeps_normal_cue():
    out = polish_captions([Segment(0, 1, "Hej då.")])
    assert [s.text for s in out] == ["Hej då."]


# ---- clean_caption_segments / clean_caption_dicts ----

def test_clean_segments_groups_then_polishes():
    out = clean_caption_segments([Segment(0, 1, "Hej och"), Segment(1, 2, "välkommen.")])
    assert [s.text for s in out] == ["Hej och välkommen."]


def test_clean_dicts_group_false_only_polishes():
    segs = [{"start": 0, "end": 1, "text": "Hej"}, {"start": 1, "end": 2, "text": ". Då."}]
    out = clean_caption_dicts(segs, group=False)
    assert [s["text"] for s in out] == ["Hej.", "Då."]
