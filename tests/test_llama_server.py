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

def test_stop_is_safe_when_never_started():
    srv = ls.LlamaServer("m.gguf", port=8170)
    srv.stop()                      # must not raise
    assert srv.proc is None

def test_start_times_out_and_stops(monkeypatch):
    monkeypatch.setattr(ls, "is_healthy", lambda *a, **k: False)
    class LiveProc:
        def __init__(self, *a, **k): self.stdout = _Reader("")
        def poll(self): return None             # running, but never becomes healthy
        def terminate(self): pass
        def wait(self, timeout=None): return 0
        def kill(self): pass
    monkeypatch.setattr(ls.subprocess, "Popen", LiveProc)
    srv = ls.LlamaServer("m.gguf", port=8170)
    try:
        srv.start(timeout=1)
        assert False, "expected RuntimeError"
    except RuntimeError as e:
        assert "tidsgränsen" in str(e)
    assert srv.proc is None                     # stop() ran on timeout

def test_build_args_uses_default_binary_when_none():
    args = ls.build_args("m.gguf")
    assert args[0].endswith("llama-server.exe")

def test_default_models_root_source_is_repo_root_models():
    root = ls.default_models_root()
    assert root.name == "models"

def test_autostart_returns_none_when_not_installed(monkeypatch, tmp_path):
    from app import llm_manager
    monkeypatch.setattr(llm_manager, "is_installed", lambda *a, **k: False)
    assert ls.autostart(models_root=tmp_path) is None

def test_autostart_sets_base_url_and_returns_server(monkeypatch, tmp_path):
    from app import llm_manager, llm_client
    monkeypatch.setattr(llm_manager, "is_installed", lambda *a, **k: True)
    monkeypatch.setattr(ls, "find_free_port", lambda *a, **k: 8200)
    class FakeSrv:
        def __init__(self, *a, **k): self.started = False
        def start(self, *a, **k): self.started = True
        def stop(self): pass
    monkeypatch.setattr(ls, "LlamaServer", FakeSrv)
    # run the daemon thread's target synchronously for determinism
    monkeypatch.setattr(ls.threading, "Thread",
                        lambda target=None, **k: type("T", (), {"start": lambda self: target()})())
    srv = ls.autostart(models_root=tmp_path)
    assert isinstance(srv, FakeSrv)
    assert srv.started is True
    assert llm_client.BASE_URL == "http://127.0.0.1:8200"


def test_build_args_includes_mmproj_when_given():
    args = ls.build_args("m.gguf", mmproj="proj.gguf", binary="b")
    assert args[args.index("--mmproj") + 1] == "proj.gguf"


def test_build_args_omits_mmproj_by_default():
    assert "--mmproj" not in ls.build_args("m.gguf", binary="b")


def test_vision_ctx_is_smaller_than_default():
    assert ls.VISION_CTX < ls.DEFAULT_CTX


# ---- stdout-dränering (QA 2026-07-03) ---------------------------------------
# llama-server loggar varje förfrågan till stdout. Med subprocess.PIPE som
# ingen läser fylls OS-rörbufferten efter ett antal förfrågningar och server-
# processen BLOCKERAR mitt i en generering — appen fryser för evigt.

def _fake_popen_factory(lines, exits_immediately=False):
    import io

    class FakeProc:
        def __init__(self, *a, **k):
            self.stdout = io.StringIO("".join(l + "\n" for l in lines))
            self._exited = exits_immediately
        def poll(self):
            return 1 if self._exited else None
        def terminate(self): self._exited = True
        def kill(self): self._exited = True
        def wait(self, timeout=None): return 0
    return FakeProc


def test_start_dranerar_serverns_stdout(monkeypatch):
    import time as _t
    rader = [f"loggrad {i}" for i in range(50)]
    monkeypatch.setattr(ls.subprocess, "Popen", _fake_popen_factory(rader))
    # Första anropet är "körs redan"-checken — den måste vara False så att
    # servern faktiskt spawna(fejka)s; därefter frisk.
    anrop = {"n": 0}
    def fake_healthy(port):
        anrop["n"] += 1
        return anrop["n"] > 1
    monkeypatch.setattr(ls, "is_healthy", fake_healthy)
    srv = ls.LlamaServer("m.gguf", port=8199)
    srv.start(timeout=5)
    # Dräneringstråden ska konsumera stdout så att röret aldrig fylls.
    deadline = _t.time() + 5
    while _t.time() < deadline and len(srv._log_tail) < len(rader):
        _t.sleep(0.05)
    assert list(srv._log_tail)[-1] == "loggrad 49"


def test_start_fel_visar_loggsvansen(monkeypatch):
    import pytest
    monkeypatch.setattr(ls.subprocess, "Popen",
                        _fake_popen_factory(["boom: modellen kunde inte laddas"],
                                            exits_immediately=True))
    monkeypatch.setattr(ls, "is_healthy", lambda port: False)
    srv = ls.LlamaServer("m.gguf", port=8199)
    with pytest.raises(RuntimeError) as e:
        srv.start(timeout=2)
    assert "kunde inte laddas" in str(e.value)
