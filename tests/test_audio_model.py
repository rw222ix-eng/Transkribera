from app import audio_model as am


def test_model_id_is_open_gemma4():
    # The audio-correction engine is the OPEN (non-gated) Gemma 4 E4B — the best
    # model we settled on. The gated gemma-3n-E4B-it cannot download without a token.
    assert am.AUDIO_MODEL_ID == "google/gemma-4-E4B-it"


def test_audio_model_dir(tmp_path):
    assert am.audio_model_dir(tmp_path) == tmp_path / "google__gemma-4-E4B-it"


def test_is_installed_requires_weights_and_config(tmp_path):
    d = am.audio_model_dir(tmp_path)
    d.mkdir(parents=True)
    assert am.is_audio_model_installed(tmp_path) is False
    (d / "config.json").write_text("{}", encoding="utf-8")
    assert am.is_audio_model_installed(tmp_path) is False     # weights missing
    (d / "model.safetensors").write_bytes(b"x")
    assert am.is_audio_model_installed(tmp_path) is True


def test_is_installed_accepts_sharded_index(tmp_path):
    d = am.audio_model_dir(tmp_path)
    d.mkdir(parents=True)
    (d / "config.json").write_text("{}", encoding="utf-8")
    (d / "model.safetensors.index.json").write_text("{}", encoding="utf-8")
    assert am.is_audio_model_installed(tmp_path) is True
