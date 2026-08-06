"""Gemensamma fixturer för hela pytest-sviten (Etapp 1).

`client` låg tidigare kopierad i tio filer — samma tjugo rader, med små
skillnader som inte var avsiktliga (någon satte `base_dir` på klienten, någon
inte; några lät arbitern svara, andra inte). Den bor här nu, och skillnaderna
är namngivna i stället för slumpade:

* `client`      — servern mot en TOM `tmp_path`. Maskinprobet och
                  `llm_client.is_running` är stubbade: inga endpoints får röra
                  lärarens riktiga maskin, disk eller modeller.
* `llm_ready`   — samma klient, men arbitern svarar som om Claude Code finns
                  och är inloggad. Allt som genererar (tavla, prov, arkivfråga)
                  behöver den; allt annat ska klara sig utan.

`c.base_dir` finns alltid — nästan varje svit behöver skriva eller läsa en fil
under basen, och att leta upp `tmp_path` en gång till är bara ett sätt att få
dem att glida isär.
"""
from __future__ import annotations

import pytest

from app.web import server


class HW:
    """Maskinen som sviten låtsas köra på. Ett riktigt maskinprobe tar
    sekunder, svarar olika på olika datorer och är dessutom det enda
    `test_hardware.py` testar — här ska det vara samma maskin varje gång."""
    gpu_name = "Test GPU"; vram_mb = 24000; has_cuda = True
    ram_mb = 64000; cpu_cores = 16; free_disk_mb = 500000
    cpu_name = "Test CPU"; vram_free_mb = 20000; ram_free_mb = 40000
    total_disk_mb = 1000000; cuda_version = "12.1"
    compute_capability = "8.9"; gpu_arch = "Ada Lovelace"; disks = []


@pytest.fixture
def client(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    monkeypatch.setattr(server.hardware, "scan_hardware", lambda *_: HW())
    monkeypatch.setattr(server.llm_client, "is_running", lambda *a, **k: False)
    c = TestClient(server.create_app(base_dir=tmp_path))
    c.base_dir = tmp_path
    return c


@pytest.fixture
def llm_ready(client, monkeypatch):
    """Arbitern svarar som om språkmodellen är på plats. Utan den 503:ar varje
    generering — vilket är rätt beteende och testas för sig."""
    monkeypatch.setattr(client.app.state.arbiter, "ensure_llm",
                        lambda: "http://127.0.0.1:8170")
    return client
