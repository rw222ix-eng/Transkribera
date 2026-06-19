# Historik: radera transkribering även från disk — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** När en transkribering raderas från historiken ska dess resultatmapp raderas permanent från disken, säkert och med tydlig varning.

**Architecture:** En ny validerande hjälpfunktion `delete_result_folder` i `app/output_store.py` (som redan äger mapp-livscykeln) raderar mappen, men bara om den ligger strikt under `base_dir/Transkriberingar`. `DELETE /api/history/{id}` i `app/web/server.py` anropar den före JSON-borttagningen; vid låst fil (OSError) behålls posten och 409 returneras. Frontend (`app.js`) varnar tydligt, stoppar uppspelning före radering, och visar en notis om mappen inte kunde tas bort.

**Tech Stack:** Python 3.12, FastAPI, pytest (backend); vanilla JS + morphdom (frontend). Spec: [docs/superpowers/specs/2026-06-19-historik-radera-fran-disk-design.md](../specs/2026-06-19-historik-radera-fran-disk-design.md).

---

## File Structure

- **`app/output_store.py`** (modify) — lägg till `delete_result_folder(base_dir, folder) -> bool`. Äger redan `create_result_folder`; radering hör hemma här.
- **`app/web/server.py`** (modify) — `DELETE /api/history/{entry_id}` slår upp posten, raderar mappen (validerat), returnerar `{ok, folder_removed}`; 409 vid OSError. `output_store` är redan importerad (rad 18-området; används av `/api/transcribe`).
- **`app/web/static/app.js`** (modify) — ny varningstext i `askDeleteHistory`; `stopAudio()` + felhantering i `confirmYes`; nytt `histNotice`-state + banner i historik-vyn.
- **`tests/test_output_store.py`** (modify) — enhetstester för `delete_result_folder`.
- **`tests/test_web_server.py`** (modify) — uppdatera `test_history_delete_ok`; nya endpoint-tester (mapp borttagen, utanför base, låst fil).

---

## Task 1: `delete_result_folder` i output_store

**Files:**
- Modify: `app/output_store.py`
- Test: `tests/test_output_store.py`

- [ ] **Step 1: Write the failing tests**

Lägg till sist i `tests/test_output_store.py`:

```python
# ---- delete_result_folder ----

def test_delete_result_folder_removes_valid(tmp_path):
    folder = tmp_path / "Transkriberingar" / "2026-06-19 · klipp"
    folder.mkdir(parents=True)
    (folder / "klipp.mp4").write_text("v", encoding="utf-8")
    (folder / "klipp.srt").write_text("1\n", encoding="utf-8")
    assert output_store.delete_result_folder(tmp_path, folder) is True
    assert not folder.exists()


def test_delete_result_folder_refuses_outside_root(tmp_path):
    outside = tmp_path / "inte_transkriberingar"
    outside.mkdir()
    (outside / "f.txt").write_text("x", encoding="utf-8")
    assert output_store.delete_result_folder(tmp_path, outside) is False
    assert outside.exists()


def test_delete_result_folder_refuses_the_root_itself(tmp_path):
    root = tmp_path / "Transkriberingar"
    root.mkdir()
    assert output_store.delete_result_folder(tmp_path, root) is False
    assert root.exists()


def test_delete_result_folder_missing_is_ok(tmp_path):
    folder = tmp_path / "Transkriberingar" / "saknas"
    assert output_store.delete_result_folder(tmp_path, folder) is True


def test_delete_result_folder_empty_returns_false(tmp_path):
    assert output_store.delete_result_folder(tmp_path, None) is False
    assert output_store.delete_result_folder(tmp_path, "") is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_output_store.py -q -k delete_result_folder`
Expected: FAIL — `AttributeError: module 'app.output_store' has no attribute 'delete_result_folder'`.

- [ ] **Step 3: Implement `delete_result_folder`**

Lägg till i `app/output_store.py` direkt efter `create_result_folder` (efter rad 41):

```python
def delete_result_folder(base_dir: Path, folder: str | Path | None) -> bool:
    """Radera en resultatmapp permanent. Returnerar True om mappen togs bort (eller
    redan saknades), False om sökvägen är tom eller inte ligger strikt under
    base_dir/Transkriberingar (säkerhetsvägran — ingen radering). Kastar OSError
    vidare vid t.ex. låst fil så anroparen kan hantera det."""
    if not folder:
        return False
    root = (Path(base_dir) / "Transkriberingar").resolve()
    target = Path(folder).resolve()
    if root not in target.parents:   # refuses outside-root AND the root itself
        return False
    if not target.exists():
        return True
    shutil.rmtree(target)
    return True
```

(`shutil` är redan importerad högst upp i filen.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_output_store.py -q`
Expected: PASS — alla tester (de gamla 18 + de 5 nya).

- [ ] **Step 5: Commit**

```bash
git add app/output_store.py tests/test_output_store.py
git commit -m "$(printf 'Lägg till delete_result_folder (validerad mapp-radering)\n\nCo-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>')"
```

---

## Task 2: Koppla `DELETE /api/history/{id}` till mapp-radering

**Files:**
- Modify: `app/web/server.py` (`api_history_delete`, ~rad 382-385)
- Test: `tests/test_web_server.py`

- [ ] **Step 1: Update the existing test + write the new failing tests**

I `tests/test_web_server.py`, **ersätt** det befintliga `test_history_delete_ok` (svaret har nu ett extra fält):

```python
def test_history_delete_ok(client):
    r = client.delete("/api/history/nope")
    assert r.status_code == 200
    assert r.json() == {"ok": True, "folder_removed": False}
```

Lägg sedan till nya tester sist i filen:

```python
def test_history_delete_removes_folder(client, tmp_path):
    import json
    folder = tmp_path / "Transkriberingar" / "2026-06-19 · klipp"
    folder.mkdir(parents=True)
    (folder / "klipp.mp4").write_text("v", encoding="utf-8")
    (tmp_path / "history.json").write_text(
        json.dumps([{"id": "h1", "name": "klipp.mp4", "folder": str(folder)}]),
        encoding="utf-8")
    r = client.delete("/api/history/h1")
    assert r.status_code == 200
    assert r.json() == {"ok": True, "folder_removed": True}
    assert not folder.exists()
    assert client.get("/api/history").json() == []


def test_history_delete_refuses_folder_outside_root(client, tmp_path):
    import json
    outside = tmp_path / "inte_transkriberingar"
    outside.mkdir()
    (outside / "f.txt").write_text("x", encoding="utf-8")
    (tmp_path / "history.json").write_text(
        json.dumps([{"id": "h2", "name": "x", "folder": str(outside)}]),
        encoding="utf-8")
    r = client.delete("/api/history/h2")
    assert r.status_code == 200
    assert r.json() == {"ok": True, "folder_removed": False}
    assert outside.exists()                       # disk untouched
    assert client.get("/api/history").json() == []  # entry still removed


def test_history_delete_locked_folder_keeps_entry(client, tmp_path, monkeypatch):
    import json
    folder = tmp_path / "Transkriberingar" / "2026-06-19 · last"
    folder.mkdir(parents=True)
    (tmp_path / "history.json").write_text(
        json.dumps([{"id": "h3", "name": "x", "folder": str(folder)}]),
        encoding="utf-8")

    def boom(*a, **k):
        raise OSError("locked")
    monkeypatch.setattr(server.output_store, "delete_result_folder", boom)

    r = client.delete("/api/history/h3")
    assert r.status_code == 409
    assert [e["id"] for e in client.get("/api/history").json()] == ["h3"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_web_server.py -q -k history_delete`
Expected: FAIL — `test_history_delete_ok` fails (svaret saknar `folder_removed`); `removes_folder`/`refuses_*` fail (mappen finns kvar / fel svar); `locked` fails (200 i stället för 409).

- [ ] **Step 3: Implement the endpoint change**

I `app/web/server.py`, **ersätt** hela `api_history_delete`:

```python
    @app.delete("/api/history/{entry_id}")
    def api_history_delete(entry_id: str):
        items = history_store.load_history(history_file)
        entry = next((e for e in items if e.get("id") == entry_id), None)
        folder_removed = False
        if entry and entry.get("folder"):
            try:
                folder_removed = output_store.delete_result_folder(base, entry["folder"])
            except OSError:
                return JSONResponse(
                    {"error": "kunde inte radera mappen — en fil kan vara öppen"},
                    status_code=409)
        history_store.delete_history(history_file, entry_id)
        return {"ok": True, "folder_removed": folder_removed}
```

(`base`, `history_file`, `history_store`, `output_store` och `JSONResponse` är alla redan i scope i `create_app`.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_web_server.py -q`
Expected: PASS — alla web-server-tester.

- [ ] **Step 5: Commit**

```bash
git add app/web/server.py tests/test_web_server.py
git commit -m "$(printf 'DELETE /api/history raderar resultatmappen (validerat, 409 vid låst fil)\n\nCo-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>')"
```

---

## Task 3: Frontend — varning, stopp av uppspelning, felnotis

Ingen JS-testharness finns i repot; denna task verifieras i live-preview. Gör alla redigeringar, ladda om preview, och kör verifieringsstegen.

**Files:**
- Modify: `app/web/static/app.js`

- [ ] **Step 1: Add `histNotice` to state**

I `app/web/static/app.js`, i `S`-objektet (nära `toast: null`, rad ~73), lägg till på egen rad:

```javascript
    histNotice: null,
```

- [ ] **Step 2: Update the delete-confirmation wording**

Ersätt hela `askDeleteHistory` (rad ~345):

```javascript
  function askDeleteHistory(id, name) { setState({ confirm: { kind: 'history', id: id, title: 'Ta bort transkriberingen?', body: '"' + name + '" och hela dess mapp (video/ljud + undertexter) raderas permanent från disken. Det går inte att ångra.', label: 'Ta bort', danger: true } }); }
```

- [ ] **Step 3: Add the `histNotice` helper**

Direkt efter `confirmNo` (rad ~360) lägg till:

```javascript
  var _histNoticeT;
  function showHistNotice(msg) { clearTimeout(_histNoticeT); setState({ histNotice: msg }); _histNoticeT = setTimeout(function () { setState({ histNotice: null }); }, 6000); }
```

- [ ] **Step 4: Stop playback + handle failure in `confirmYes`**

Ersätt history-grenen i `confirmYes` (rad ~351-353):

```javascript
    } else if (c.kind === 'history') {
      setState({ confirm: null });
      stopAudio();
      fetch('/api/history/' + encodeURIComponent(c.id), { method: 'DELETE' }).then(function (r) {
        if (!r.ok) { r.json().then(function (b) { showHistNotice((b && b.error) || 'Kunde inte radera mappen.'); }).catch(function () { showHistNotice('Kunde inte radera mappen.'); }); }
        loadHistory();
      }).catch(function () { loadHistory(); });
```

(Behåll den efterföljande `} else if (c.kind === 'rerun') {`-grenen oförändrad.)

- [ ] **Step 5: Expose `histNotice` in the view-model**

I `vm()`-returobjektet, nära `confirmOpen:` (rad ~1051), lägg till:

```javascript
      histNotice: st.histNotice,
```

- [ ] **Step 6: Render the notice banner in the history view**

I historik-sektionen, direkt efter `historyEmpty`-blocket (efter rad ~1813, före `<div style="display:flex;flex-direction:column;gap:10px">`), lägg till:

```javascript
      ${ v.histNotice ? `
        <div style="display:flex;align-items:center;gap:10px;margin-bottom:12px;background:color-mix(in srgb,var(--bad) 7%,var(--surface));border:1px solid color-mix(in srgb,var(--bad) 30%,transparent);border-radius:12px;padding:12px 15px">
          <span style="width:20px;height:20px;border-radius:50%;flex:0 0 auto;background:color-mix(in srgb,var(--bad) 16%,transparent);color:var(--bad);display:flex;align-items:center;justify-content:center;font-size:13px;font-weight:700">!</span>
          <span style="font-size:14.5px;color:var(--ink)">${esc(v.histNotice)}</span>
        </div>
      ` : '' }
```

- [ ] **Step 7: Verify in live-preview**

Servern kör redan på 127.0.0.1:8750 (preview). Ladda om sidan med cache-bust (`location.replace('/?cb='+Date.now())` via preview_eval, eller ta en ny skärmbild).

Verifiera:
1. Gå till Historik-fliken. Om tom: transkribera först en kort lokal fil så en post med mapp skapas.
2. Klicka soptunne-ikonen på en post → bekräfta att dialogtexten nu nämner att hela mappen raderas permanent.
3. Bekräfta "Ta bort" → posten försvinner ur listan, och mappen under `Transkriberingar/{datum · namn}/` är borta på disk (`ls`/Utforskaren).
4. Negativ kontroll (låst fil): öppna posten i spelaren och spela, gå tillbaka, radera — `stopAudio()` ska släppa filen så raderingen lyckas. (Om en fil mot förmodan är låst visas den röda notisen i stället, och posten ligger kvar.)

- [ ] **Step 8: Commit**

```bash
git add app/web/static/app.js
git commit -m "$(printf 'Historik: varna + radera mappen, stoppa uppspelning, visa felnotis\n\nCo-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>')"
```

---

## Self-Review

**Spec coverage:**
- Mål 1 (mapp raderas permanent) → Task 1 (`delete_result_folder` + rmtree) + Task 2 (endpoint anropar den). ✓
- Mål 2 (bara under `Transkriberingar/`) → Task 1 (`root not in target.parents`) + test `refuses_outside_root` / `refuses_the_root_itself`. ✓
- Mål 3 (tydlig varning) → Task 3 Step 2 (ny dialogtext). ✓
- Beslut "permanent" → `shutil.rmtree`. ✓
- Beslut "allt-eller-inget vid låst fil" → Task 2 (OSError → 409, posten behålls) + Task 3 (stopAudio före DELETE, notis vid fel). ✓
- Beslut "poster utan folder" → Task 2 (`if entry and entry.get("folder")`) → annars bara JSON bort; täcks av `test_history_delete_ok`. ✓
- Verifiering (pytest + live-preview) → Task 1/2 enhetstester, Task 3 Step 7. ✓

**Placeholder scan:** Inga TBD/TODO; all kod är fullständig och konkret. ✓

**Type/namn-konsistens:** `delete_result_folder(base_dir, folder)` används identiskt i Task 1 (def), Task 2 (anrop) och Task 2-testet (monkeypatch på `server.output_store.delete_result_folder`). Svarsformen `{"ok": True, "folder_removed": bool}` är konsekvent mellan endpoint och alla tre endpoint-testerna. `showHistNotice` definieras (Step 3) före användning (Step 4). `histNotice` är konsekvent i state (Step 1), vm (Step 5) och render (Step 6). ✓
