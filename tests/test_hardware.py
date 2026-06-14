from pathlib import Path
from app.hardware import HardwareInfo, scan_hardware

def test_scan_returns_sane_values(tmp_path: Path):
    hw = scan_hardware(tmp_path)
    assert isinstance(hw, HardwareInfo)
    assert hw.ram_mb > 0
    assert hw.cpu_cores >= 1
    assert hw.free_disk_mb > 0
    assert hw.vram_mb >= 0
    if hw.has_cuda:
        assert hw.vram_mb > 0 and hw.gpu_name
