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


# ── Kommandoraden har ett tak (Etapp 3) ────────────────────────────────────
# Fyndet: `claude` installeras på Windows som claude.CMD, och cmd.exe:s
# kommandorad tar slut vid 8191 tecken (CreateProcess vid 32767). Tavelschemat
# är 34 kB och provschemat 24 kB — skickade som --json-schema startade
# processen inte ens. Tavlan och provet gick alltså inte att generera på
# lärarens maskin, och ingen svit såg det: alla stubbar satt INNANFÖR den här
# sömmen.

def _fanga_argv(monkeypatch):
    sett = {}

    def fejk(argv, **kw):
        sett["argv"] = argv
        return _FejkProc(_strom("{}"))
    monkeypatch.setattr(claude_code.subprocess, "Popen", fejk)
    return sett


def test_ett_litet_schema_gar_pa_kommandoraden(monkeypatch):
    _inloggad(monkeypatch)
    sett = _fanga_argv(monkeypatch)
    litet = {"type": "object", "properties": {"a": {"type": "string"}}}
    claude_code.generate("fråga", schema=litet)
    assert "--json-schema" in sett["argv"]


def test_ett_stort_schema_flyttas_till_prompten(monkeypatch):
    """Det som inte får plats går på stdin i stället — prompten har inget tak."""
    _inloggad(monkeypatch)
    sett = _fanga_argv(monkeypatch)
    # Tyngden måste ligga i sådant som TVINGAR (pattern), inte i beskrivningar —
    # de strippas numera bort innan taket mäts.
    stort = {"type": "object", "properties": {
        f"f{i}": {"type": "string", "pattern": "x" * 40} for i in range(600)}}
    matat = {}
    monkeypatch.setattr(claude_code, "_neutral_cwd", lambda: ".")
    proc = _FejkProc(_strom("{}"))

    class _Stdin:
        def write(self, s): matat["prompt"] = s
        def close(self): pass
    proc.stdin = _Stdin()
    monkeypatch.setattr(claude_code.subprocess, "Popen",
                        lambda argv, **kw: (sett.update(argv=argv), proc)[1])
    claude_code.generate("fråga", schema=stort)

    assert "--json-schema" not in sett["argv"]
    assert sum(len(a) for a in sett["argv"]) < claude_code.SCHEMA_TAK + 2000
    assert "JSON-schema" in matat["prompt"] and '"f199"' in matat["prompt"]


def test_appens_egna_scheman_far_plats_i_ett_anrop(monkeypatch):
    """Regressionsvakten för .CMD-vägen: när claude bara går att nå genom
    cmd.exe ska tavlans och provets scheman ALDRIG hamna på kommandoraden, hur
    de än växer."""
    from app import exam_spec, whiteboard_spec
    _inloggad(monkeypatch)
    # Just .CMD-vägen: en suffixlös «claude» är Mac/Linux och får det stora
    # taket — det snåla gäller bara genom cmd.exe.
    monkeypatch.setattr(claude_code, "binar", lambda: "C:/npm/claude.CMD")
    sett = _fanga_argv(monkeypatch)
    for schema in (whiteboard_spec.to_response_format()["json_schema"]["schema"],
                   exam_spec.to_response_format(
                       7, exam_spec.balanced_skeleton(7))["json_schema"]["schema"]):
        claude_code.generate("fråga", schema=schema)
        rad = " ".join(sett["argv"])
        # Windows: cmd.exe 8191, CreateProcess 32767. Med marginal för sökvägar.
        assert len(rad) < 8000, f"kommandoraden är {len(rad)} tecken"


# ── Grammatiktvånget tillbaka (minifiering + claude.exe) ───────────────────
# Metadatan i schemat tvingar ingenting — Pydantics `title` säger bara
# fältnamnet en gång till. Strippad krymper tavlans schema från 35 kB till
# 24 kB, och startas claude.exe direkt (förbi cmd.exe:s 8191) ryms det som
# --json-schema igen. Skarpt verifierat: 23 914 tecken schema, argv 24 134,
# returncode 0.

def _fanga_prompt(monkeypatch, sett=None):
    sett = sett if sett is not None else {}

    def fejk(argv, **kw):
        sett["argv"] = argv
        proc = _FejkProc(_strom("{}"))
        delar = []
        proc.stdin = type("S", (), {"write": delar.append,
                                    "close": lambda self=None: None})()
        sett["delar"] = delar
        return proc
    monkeypatch.setattr(claude_code.subprocess, "Popen", fejk)
    return sett


def test_minifieringen_tar_metadatan_men_ror_inte_tvanget():
    schema = {"type": "object", "title": "Tavla", "description": "Toppnivån",
              "additionalProperties": False, "required": ["sort"],
              "properties": {
                  "sort": {"type": "string", "enum": ["figur", "text"],
                           "title": "Sort", "description": "Vilken sorts ruta"},
                  "n": {"type": "integer", "minimum": 1, "maximum": 9,
                        "default": 3, "title": "N"}}}
    m = claude_code._minifiera(schema)
    assert m["required"] == ["sort"] and m["additionalProperties"] is False
    assert m["properties"]["sort"]["enum"] == ["figur", "text"]
    assert m["properties"]["n"]["minimum"] == 1 and m["properties"]["n"]["maximum"] == 9
    assert "title" not in m and "description" not in m
    assert "default" not in m["properties"]["n"]


def test_ett_falt_som_HETER_title_overlever_minifieringen():
    """Nycklarna under `properties` är fältnamn, inte schemanyckelord."""
    schema = {"type": "object", "required": ["title"], "properties": {
        "title": {"type": "string", "title": "Rubrik"},
        "description": {"type": "string"}}}
    m = claude_code._minifiera(schema)
    assert set(m["properties"]) == {"title", "description"}
    assert m["properties"]["title"] == {"type": "string"}


def test_direkt_mot_exe_far_tavlan_plats_som_json_schema(monkeypatch):
    """Det som var poängen: grammatiktvånget tillbaka för tavlan och provet."""
    from app import exam_spec, whiteboard_spec
    _inloggad(monkeypatch)
    monkeypatch.setattr(claude_code, "binar", lambda: r"C:\npm\bin\claude.exe")
    sett = _fanga_prompt(monkeypatch)
    for schema in (whiteboard_spec.to_response_format()["json_schema"]["schema"],
                   exam_spec.to_response_format(
                       7, exam_spec.balanced_skeleton(7))["json_schema"]["schema"]):
        claude_code.generate("fråga", schema=schema)
        argv = sett["argv"]
        assert "--json-schema" in argv
        skickat = json.loads(argv[argv.index("--json-schema") + 1])
        assert skickat["required"] == schema["required"]
        assert claude_code._radlangd(argv) <= claude_code.SCHEMA_TAK_EXE
        assert "JSON-schema" not in "".join(sett["delar"])   # inte i prompten


def test_ett_schema_som_inte_ryms_ens_forbi_cmd_gar_i_prompten(monkeypatch):
    _inloggad(monkeypatch)
    monkeypatch.setattr(claude_code, "binar", lambda: r"C:\npm\bin\claude.exe")
    sett = _fanga_prompt(monkeypatch)
    stort = {"type": "object", "properties": {
        f"f{i}": {"type": "string", "pattern": "x" * 60} for i in range(600)}}
    claude_code.generate("fråga", schema=stort)
    assert "--json-schema" not in sett["argv"]
    prompt = "".join(sett["delar"])
    assert "JSON-schema" in prompt and '"f599"' in prompt


def test_beskrivningarna_foljer_med_i_prompten_nar_schemat_minifieras(monkeypatch):
    """Metadatan får kosta tokens bara där den vägleder — i prompten, en gång."""
    _inloggad(monkeypatch)
    monkeypatch.setattr(claude_code, "binar", lambda: r"C:\npm\bin\claude.exe")
    sett = _fanga_prompt(monkeypatch)
    claude_code.generate("fråga", schema={"type": "object", "properties": {
        "kant": {"type": "string", "description": "Alltid vänsterkant"}}})
    prompt = "".join(sett["delar"])
    assert "kant: Alltid vänsterkant" in prompt
    assert "Alltid vänsterkant" not in " ".join(sett["argv"])


def test_forbi_cmd_valjer_exe_bredvid_men_bara_om_den_finns(tmp_path):
    cmd = tmp_path / "claude.CMD"
    cmd.write_text("")
    assert claude_code._forbi_cmd(str(cmd)) == str(cmd)     # ingen exe bredvid
    exe = tmp_path / "node_modules" / "@anthropic-ai" / "claude-code" / "bin" / "claude.exe"
    exe.parent.mkdir(parents=True)
    exe.write_text("")
    assert claude_code._forbi_cmd(str(cmd)) == str(exe)
    # En sökväg som redan är binären lämnas orörd (native build, Mac).
    assert claude_code._forbi_cmd("/usr/local/bin/claude") == "/usr/local/bin/claude"


# ── Modellen ───────────────────────────────────────────────────────────────

def test_tom_modell_pinnas_till_opus_5(monkeypatch):
    """Förvalet löste ut till claude-opus-5[1m] — samma modell, men den långa
    kontextvägen som appens ~25k-prompter aldrig behöver."""
    _inloggad(monkeypatch)
    sett = _fanga_argv(monkeypatch)
    claude_code.generate("fråga")
    argv = sett["argv"]
    assert argv[argv.index("--model") + 1] == claude_code.MODELL == "claude-opus-5"


def test_en_utpekad_modell_far_gå_före(monkeypatch):
    _inloggad(monkeypatch)
    sett = _fanga_argv(monkeypatch)
    claude_code.generate("fråga", modell="claude-haiku-4-5")
    argv = sett["argv"]
    assert argv[argv.index("--model") + 1] == "claude-haiku-4-5"
