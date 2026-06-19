from app import llama_server as ls

def test_build_args_balanced_profile():
    args = ls.build_args("C:/m/model.gguf", port=8170, ctx=40960,
                         profile="balanced", binary="C:/bin/llama-server.exe")
    assert args[0] == "C:/bin/llama-server.exe"
    assert "-m" in args and "C:/m/model.gguf" in args
    assert args[args.index("-c") + 1] == "40960"
    assert args[args.index("-fa") + 1] == "on"
    assert args[args.index("--cache-type-k") + 1] == "q8_0"
    assert args[args.index("--cache-type-v") + 1] == "q8_0"
    assert args[args.index("--parallel") + 1] == "1"   # full -c as ONE contiguous context
    assert args[args.index("--port") + 1] == "8170"
    assert "--jinja" in args

def test_build_args_quality_profile_is_f16():
    args = ls.build_args("m.gguf", profile="quality", binary="b")
    assert args[args.index("--cache-type-k") + 1] == "f16"
    assert args[args.index("--cache-type-v") + 1] == "f16"

def test_cache_profiles_never_quant_v_below_k():
    # V-cache is 3–4x more sensitive than K — never q4 on V.
    for k, v in ls.CACHE_PROFILES.values():
        assert v in ("f16", "q8_0")

def test_default_port_outside_windows_reserved_range():
    assert not (8048 <= ls.DEFAULT_PORT <= 8147)

def test_default_ctx_is_trained_length():
    assert ls.DEFAULT_CTX == 40960

def test_find_free_port_returns_int():
    p = ls.find_free_port(candidates=(0,))
    assert isinstance(p, int) and p > 0

def test_is_healthy_true(monkeypatch):
    class R:
        status_code = 200
    monkeypatch.setattr(ls.requests, "get", lambda *a, **k: R())
    assert ls.is_healthy(port=8170) is True

def test_is_healthy_false_on_error(monkeypatch):
    def boom(*a, **k): raise OSError("refused")
    monkeypatch.setattr(ls.requests, "get", boom)
    assert ls.is_healthy(port=8170) is False

def test_start_reuses_already_running_server(monkeypatch):
    monkeypatch.setattr(ls, "is_healthy", lambda *a, **k: True)
    called = {"popen": False}
    def fake_popen(*a, **k):
        called["popen"] = True
    monkeypatch.setattr(ls.subprocess, "Popen", fake_popen)
    srv = ls.LlamaServer("m.gguf", port=8170)
    srv.start(timeout=1)                 # already healthy -> must NOT spawn
    assert called["popen"] is False

def test_start_raises_if_process_dies(monkeypatch):
    monkeypatch.setattr(ls, "is_healthy", lambda *a, **k: False)
    class DeadProc:
        def __init__(self, *a, **k):
            self.stdout = _Reader("CUDA error: out of memory")
        def poll(self):
            return 1                      # exited immediately
    monkeypatch.setattr(ls.subprocess, "Popen", DeadProc)
    srv = ls.LlamaServer("m.gguf", port=8170)
    try:
        srv.start(timeout=2)
        assert False, "expected RuntimeError"
    except RuntimeError as e:
        assert "out of memory" in str(e)

class _Reader:
    def __init__(self, text): self._text = text
    def read(self): return self._text
