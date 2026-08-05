"""Bryggan till Claude Code: argumenten, strömmen och de två felen.

Ingen riktig CLI startas — subprocess fejkas. Det som testas är kontraktet:
att prompten går via stdin (ett transkript ryms inte i en kommandorad), att
lärarens egna CLAUDE.md/hooks inte kan påverka svaret, att verktygen är
avstängda, och att «inte inloggad» blir ett eget fel i stället för tyst tomhet.
"""
import json

import pytest

from app import claude_code


@pytest.fixture(autouse=True)
def _tom_cache():
    claude_code._STATUS_CACHE.update(tid=0.0, varde=None)
    yield
    claude_code._STATUS_CACHE.update(tid=0.0, varde=None)


class _FejkProc:
    def __init__(self, rader, returncode=0):
        self.stdout = iter(rader)
        self.stderr = _Tom()
        self.stdin = _Tom()
        self.returncode = returncode
        self.dodad = False

    def wait(self, timeout=None):
        return self.returncode

    def kill(self):
        self.dodad = True


class _Tom:
    def write(self, *a):
        pass

    def close(self):
        pass

    def read(self):
        return ""


def _strom(*texter, kostnad=0.01):
    rader = ['{"type":"system","subtype":"init"}']
    for t in texter:
        rader.append(json.dumps({"type": "stream_event", "event": {
            "type": "content_block_delta", "delta": {"type": "text_delta", "text": t}}}))
    rader.append(json.dumps({"type": "result", "is_error": False,
                             "result": "".join(texter), "total_cost_usd": kostnad,
                             "duration_ms": 1200,
                             "modelUsage": {"claude-haiku-4-5": {"outputTokens": 3},
                                            "claude-opus-5": {"outputTokens": 99}}}))
    return rader


def _inloggad(monkeypatch, ja=True, finns=True):
    monkeypatch.setattr(claude_code, "binar", lambda: "claude" if finns else None)
    monkeypatch.setattr(claude_code.subprocess, "run", lambda *a, **k: type(
        "R", (), {"stdout": json.dumps({"loggedIn": ja, "email": "l@skola.se",
                                        "subscriptionType": "max"})})())


# ---- Status ---------------------------------------------------------------

def test_status_laser_inloggning_epost_och_plan(monkeypatch):
    _inloggad(monkeypatch)
    s = claude_code.status()
    assert s == {"finns": True, "inloggad": True, "epost": "l@skola.se",
                 "plan": "max", "fel": ""}


def test_status_utan_installation_sager_det(monkeypatch):
    _inloggad(monkeypatch, finns=False)
    s = claude_code.status()
    assert s["finns"] is False and "inte installerat" in s["fel"]


def test_utloggad_ger_ett_besked_som_gar_att_visa(monkeypatch):
    _inloggad(monkeypatch, ja=False)
    s = claude_code.status()
    assert s["inloggad"] is False and "inte inloggat" in s["fel"]


def test_statusen_cachas_men_force_gar_forbi(monkeypatch):
    antal = {"n": 0}

    def rakna(*a, **k):
        antal["n"] += 1
        return type("R", (), {"stdout": json.dumps({"loggedIn": True})})()
    monkeypatch.setattr(claude_code, "binar", lambda: "claude")
    monkeypatch.setattr(claude_code.subprocess, "run", rakna)
    claude_code.status()
    claude_code.status()
    assert antal["n"] == 1                      # andra frågan kom ur minnet
    claude_code.status(force=True)
    assert antal["n"] == 2                      # «Kontrollera igen» frågar på riktigt


# ---- Generering -----------------------------------------------------------

def test_deltan_strommas_och_svaret_sys_ihop(monkeypatch):
    _inloggad(monkeypatch)
    monkeypatch.setattr(claude_code.subprocess, "Popen",
                        lambda *a, **k: _FejkProc(_strom("Hej ", "världen")))
    bitar = []
    svar = claude_code.generate("fråga", token_cb=bitar.append)
    assert svar == "Hej världen"
    assert bitar == ["Hej ", "världen"]


def test_kostnaden_och_modellen_som_skrev_sparas(monkeypatch):
    _inloggad(monkeypatch)
    monkeypatch.setattr(claude_code.subprocess, "Popen",
                        lambda *a, **k: _FejkProc(_strom("x", kostnad=0.042)))
    claude_code.generate("fråga")
    assert claude_code.SENASTE["kostnad"] == 0.042
    # modelUsage rymmer även Claude Codes egna småanrop — modellen som SKREV
    # svaret är den med flest utskrivna tokens.
    assert claude_code.SENASTE["modell"] == "claude-opus-5"


def test_prompten_gar_via_stdin_inte_som_argument(monkeypatch):
    _inloggad(monkeypatch)
    fangat = {}

    def fejk_popen(argv, **k):
        fangat["argv"] = argv
        proc = _FejkProc(_strom("ok"))
        skrivet = []
        proc.stdin = type("S", (), {"write": skrivet.append, "close": lambda self=None: None})()
        fangat["skrivet"] = skrivet
        return proc
    monkeypatch.setattr(claude_code.subprocess, "Popen", fejk_popen)
    lang_text = "TRANSKRIPT " * 5000
    claude_code.generate(lang_text, system="Du är svensk.")
    assert lang_text not in " ".join(fangat["argv"])


def test_argumenten_stanger_av_verktyg_och_larararens_egna_installningar(monkeypatch):
    _inloggad(monkeypatch)
    fangat = {}

    def fejk_popen(argv, **k):
        fangat["argv"], fangat["cwd"] = argv, k.get("cwd")
        return _FejkProc(_strom("ok"))
    monkeypatch.setattr(claude_code.subprocess, "Popen", fejk_popen)
    claude_code.generate("fråga", system="Systemtext")
    argv = fangat["argv"]
    assert "-p" in argv and "--safe-mode" in argv
    assert argv[argv.index("--tools") + 1] == ""          # ingen agent, bara text
    assert argv[argv.index("--system-prompt") + 1] == "Systemtext"
    assert "--no-session-persistence" in argv
    # Arbetskatalogen avgör vilka CLAUDE.md som dras in — aldrig projektmappen.
    assert fangat["cwd"] and "Transkribera" not in fangat["cwd"]


def test_schema_skickas_med_som_json_schema(monkeypatch):
    _inloggad(monkeypatch)
    fangat = {}

    def fejk_popen(argv, **k):
        fangat["argv"] = argv
        return _FejkProc(_strom('{"a":1}'))
    monkeypatch.setattr(claude_code.subprocess, "Popen", fejk_popen)
    claude_code.generate("fråga", schema={"type": "object"})
    argv = fangat["argv"]
    assert json.loads(argv[argv.index("--json-schema") + 1]) == {"type": "object"}


def test_svar_utan_deltan_tas_ur_resultatfaltet(monkeypatch):
    _inloggad(monkeypatch)
    rader = [json.dumps({"type": "result", "is_error": False,
                         "result": '{"titel":"Bråk"}', "total_cost_usd": 0.001})]
    monkeypatch.setattr(claude_code.subprocess, "Popen", lambda *a, **k: _FejkProc(rader))
    assert claude_code.generate("fråga") == '{"titel":"Bråk"}'


def test_fel_fran_claude_code_reses_som_fel(monkeypatch):
    _inloggad(monkeypatch)
    rader = [json.dumps({"type": "result", "is_error": True,
                         "result": "Kontexten tog slut"})]
    monkeypatch.setattr(claude_code.subprocess, "Popen", lambda *a, **k: _FejkProc(rader))
    with pytest.raises(RuntimeError, match="Kontexten"):
        claude_code.generate("fråga")


def test_utloggad_reser_inte_inloggad_utan_att_starta_nagot(monkeypatch):
    _inloggad(monkeypatch, ja=False)

    def _forbjuden(*a, **k):
        raise AssertionError("inget får skickas när Claude Code är utloggat")
    monkeypatch.setattr(claude_code.subprocess, "Popen", _forbjuden)
    with pytest.raises(claude_code.InteInloggad):
        claude_code.generate("fråga")


def test_saknad_installation_reser_eget_fel(monkeypatch):
    _inloggad(monkeypatch, finns=False)
    with pytest.raises(claude_code.SaknasClaudeCode):
        claude_code.generate("fråga")


# ---- Samtal ---------------------------------------------------------------

def test_chatten_vaver_in_historiken_i_prompten(monkeypatch):
    _inloggad(monkeypatch)
    fangat = {}

    def fejk_popen(argv, **k):
        proc = _FejkProc(_strom("svar"))
        skrivet = []
        proc.stdin = type("S", (), {"write": skrivet.append, "close": lambda self=None: None})()
        fangat["skrivet"] = skrivet
        return proc
    monkeypatch.setattr(claude_code.subprocess, "Popen", fejk_popen)
    claude_code.chat([{"role": "user", "content": "Vad sa jag om bråk?"},
                      {"role": "assistant", "content": "Du tog det på slutet."},
                      {"role": "user", "content": "Och procent?"}])
    prompt = "".join(fangat["skrivet"])
    assert "Vad sa jag om bråk?" in prompt
    assert "Du tog det på slutet." in prompt
    assert prompt.rstrip().endswith("Och procent?")
