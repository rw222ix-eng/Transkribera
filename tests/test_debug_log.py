import logging

from app import debug_log


def test_setup_writes_log_file(tmp_path, monkeypatch):
    # Force a clean configuration for this test.
    monkeypatch.setattr(debug_log, "_configured", False)
    logger = logging.getLogger(debug_log.LOGGER_NAME)
    for h in list(logger.handlers):
        logger.removeHandler(h)

    log = debug_log.setup(tmp_path, tag="test")
    log.info("hej %s", "varld")
    for h in log.handlers:
        h.flush()

    p = debug_log.log_path(tmp_path)
    assert p.exists()
    text = p.read_text(encoding="utf-8")
    assert "Transkribera start (test)" in text
    assert "hej varld" in text


def test_setup_is_idempotent(tmp_path, monkeypatch):
    monkeypatch.setattr(debug_log, "_configured", False)
    logger = logging.getLogger(debug_log.LOGGER_NAME)
    for h in list(logger.handlers):
        logger.removeHandler(h)
    debug_log.setup(tmp_path)
    n = len(logger.handlers)
    debug_log.setup(tmp_path)
    assert len(logger.handlers) == n  # no duplicate handlers
