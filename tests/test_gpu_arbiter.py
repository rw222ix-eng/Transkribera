from app import gpu_arbiter as ga
from app import llm_client


def _arb(tmp_path):
    return ga.GpuArbiter(models_root=tmp_path)


def test_gpu_lock_is_exclusive_and_releasable(tmp_path):
    arb = _arb(tmp_path)
    assert arb.try_acquire_gpu() is True
    assert arb.try_acquire_gpu() is False     # busy
    arb.release_gpu()
    assert arb.try_acquire_gpu() is True       # free again
    arb.release_gpu()


def test_release_gpu_is_safe_when_not_held(tmp_path):
    arb = _arb(tmp_path)
    arb.release_gpu()                          # must not raise


def test_ensure_llm_returns_none_when_not_installed(tmp_path, monkeypatch):
    arb = _arb(tmp_path)
    monkeypatch.setattr(ga.llm_manager, "is_installed", lambda *a, **k: False)
    assert arb.ensure_llm() is None


def test_ensure_llm_starts_server_and_sets_base_url(tmp_path, monkeypatch):
    arb = _arb(tmp_path)
    monkeypatch.setattr(ga.llm_manager, "is_installed", lambda *a, **k: True)
    monkeypatch.setattr(ga, "find_free_port", lambda *a, **k: 8200)
    monkeypatch.setattr(ga, "is_healthy", lambda *a, **k: False)

    class FakeSrv:
        def __init__(self, *a, **k):
            self.port = 8200
            self.started = False

        @property
        def base_url(self):
            return "http://127.0.0.1:8200"

        def start(self, *a, **k):
            self.started = True

        def stop(self):
            pass

    monkeypatch.setattr(ga, "LlamaServer", FakeSrv)
    url = arb.ensure_llm()
    assert url == "http://127.0.0.1:8200"
    assert llm_client.BASE_URL == "http://127.0.0.1:8200"
    assert isinstance(arb._server, FakeSrv) and arb._server.started is True


def test_ensure_llm_reuses_healthy_server(tmp_path, monkeypatch):
    arb = _arb(tmp_path)
    monkeypatch.setattr(ga.llm_manager, "is_installed", lambda *a, **k: True)
    starts = {"n": 0}

    class FakeSrv:
        def __init__(self, *a, **k):
            self.port = 8201

        @property
        def base_url(self):
            return "http://127.0.0.1:8201"

        def start(self, *a, **k):
            starts["n"] += 1

        def stop(self):
            pass

    monkeypatch.setattr(ga, "LlamaServer", FakeSrv)
    monkeypatch.setattr(ga, "find_free_port", lambda *a, **k: 8201)
    monkeypatch.setattr(ga, "is_healthy", lambda *a, **k: False)
    arb.ensure_llm()                           # cold start -> 1
    monkeypatch.setattr(ga, "is_healthy", lambda *a, **k: True)
    arb.ensure_llm()                           # healthy -> reused, no new start
    assert starts["n"] == 1


def test_stop_llm_stops_and_clears(tmp_path, monkeypatch):
    arb = _arb(tmp_path)
    stopped = {"n": 0}

    class FakeSrv:
        port = 8202

        def stop(self):
            stopped["n"] += 1

    arb._server = FakeSrv()
    assert arb.stop_llm() is True
    assert arb._server is None
    assert stopped["n"] == 1
    assert arb.stop_llm() is False             # idempotent, nothing to stop


def test_prewarm_async_skips_when_not_installed(tmp_path, monkeypatch):
    arb = _arb(tmp_path)
    monkeypatch.setattr(ga.llm_manager, "is_installed", lambda *a, **k: False)
    called = {"thread": False}
    monkeypatch.setattr(ga.threading, "Thread",
                        lambda *a, **k: called.__setitem__("thread", True))
    arb.prewarm_async()
    assert called["thread"] is False           # no thread spawned


def test_prewarm_async_swallows_start_failure(tmp_path, monkeypatch):
    arb = _arb(tmp_path)
    monkeypatch.setattr(ga.llm_manager, "is_installed", lambda *a, **k: True)
    monkeypatch.setattr(arb, "ensure_llm",
                        lambda: (_ for _ in ()).throw(RuntimeError("oom")))
    # Run the daemon thread's target synchronously; must not raise.
    monkeypatch.setattr(ga.threading, "Thread",
                        lambda target=None, **k: type("T", (), {"start": lambda self: target()})())
    arb.prewarm_async()                         # best effort — no exception escapes
