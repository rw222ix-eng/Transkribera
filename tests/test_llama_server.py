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


def test_switch_to_starts_requested_model_and_passes_mmproj(monkeypatch, tmp_path):
    from app import llm_manager, llm_client
    monkeypatch.setattr(llm_manager, "is_installed", lambda *a, **k: True)
    monkeypatch.setattr(ls, "is_healthy", lambda *a, **k: False)
    captured = {}
    class FakeSrv:
        def __init__(self, *a, **k): captured["kw"] = k; self.started = False
        def start(self, *a, **k): self.started = True
        def stop(self): captured["stopped"] = True
    monkeypatch.setattr(ls, "LlamaServer", FakeSrv)
    ls._ACTIVE.update(srv=None, spec=None, root=None, port=8200)
    srv = ls.switch_to(llm_manager.VISION_LLM, models_root=tmp_path)
    assert isinstance(srv, FakeSrv) and srv.started is True
    assert ls._ACTIVE["spec"] is llm_manager.VISION_LLM
    assert captured["kw"].get("mmproj") is not None         # vision -> projector passed
    assert captured["kw"].get("ctx") == ls.VISION_CTX
    assert llm_client.BASE_URL.endswith(":8200")


def test_switch_to_is_noop_when_already_serving(monkeypatch, tmp_path):
    from app import llm_manager
    monkeypatch.setattr(llm_manager, "is_installed", lambda *a, **k: True)
    monkeypatch.setattr(ls, "is_healthy", lambda *a, **k: True)
    sentinel = object()
    ls._ACTIVE.update(srv=sentinel, spec=llm_manager.ACTIVE_LLM, root=tmp_path, port=8200)
    def boom(*a, **k): raise AssertionError("must not build a new server")
    monkeypatch.setattr(ls, "LlamaServer", boom)
    assert ls.switch_to(llm_manager.ACTIVE_LLM, models_root=tmp_path) is sentinel


def test_switch_to_raises_friendly_when_not_installed(monkeypatch, tmp_path):
    from app import llm_manager
    monkeypatch.setattr(llm_manager, "is_installed", lambda *a, **k: False)
    ls._ACTIVE.update(srv=None, spec=None, root=None, port=8200)
    try:
        ls.switch_to(llm_manager.VISION_LLM, models_root=tmp_path)
        assert False, "expected RuntimeError"
    except RuntimeError as e:
        assert "inte installerad" in str(e)


def test_shutdown_stops_active_and_clears(monkeypatch):
    stopped = {"v": False}
    class S:
        def stop(self): stopped["v"] = True
    ls._ACTIVE.update(srv=S(), spec=object())
    ls.shutdown()
    assert stopped["v"] is True and ls._ACTIVE["srv"] is None
