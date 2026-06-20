# Verifiering: "Tänk djupare"-toggle i chatten (Qwen3 thinking on/off)

**Datum:** 2026-06-20
**Branch:** `claude/transcription-correction-workflow-yx2zz2`
**Kräver:** Windows-burken med RTX 4090 (24 GB), installerad GGUF (Qwen3-14B-Q8_0).

## Vad som ändrades

- **Korrigering/sammanfattning (`postprocess.run` → `llm_client.generate`)** är *oförändrat OFF*
  för thinking. Mekanisk uppgift — thinking är ren latens-overhead utan kvalitetsvinst.
- **Chatten** kan nu slå PÅ Qwen3 thinking per förfrågan via en "Tänk djupare"-knapp.
  Default är AV (snabbt, inget engelskt resonemang).
- Oavsett på/av separeras allt resonemang från svaret (`reasoning_content`-fältet
  **och** inline `<think>…</think>`) och visas i en egen, dämpad "Resonemang"-bubbla i
  stället för att läcka in i det svenska svaret.

## Avvägningen vi verifierar (varför man oftast vinner på OFF)

| | Thinking AV (default) | Thinking PÅ |
|---|---|---|
| Tid till första ord | direkt | flera sek (resonemang genereras först) |
| Kontext-/KV-budget | allt går till transkript | resonemang konkurrerar om fönstret |
| Språkläckage | inget | hanterat (separeras), men finns |
| Svåra flerstegsfrågor | ok | bättre |

## Förberedelse

```powershell
git fetch origin claude/transcription-correction-workflow-yx2zz2
git checkout claude/transcription-correction-workflow-yx2zz2
python -m pytest tests/test_llm_client.py tests/test_web_server.py -q   # ska vara grönt
python -m app.web
```

Öppna appen, transkribera en **lång** källa (helst en ~1 h föreläsning så kontexten
verkligen testas), välj **Chatta**, öppna chatten. Ha `nvidia-smi -l 1` igång i en
andra terminal.

## Testfall (bocka av + klistra in bevis)

### 1. Default är AV — snabbt svar, inget resonemang
- [ ] "Tänk djupare"-knappen är **av** (grå) när chatten öppnas.
- [ ] Ställ en enkel fråga ("Vad handlade det om?"). Svaret börjar strömma **direkt**.
- [ ] Ingen "Resonemang"-bubbla visas. Inga engelska/kinesiska ord i svaret.
- [ ] (DevTools → Network → `/api/chat`) request-body innehåller `"think": false`.

### 2. PÅ — resonemang separeras, läcker inte in i svaret
- [ ] Klicka "Tänk djupare" (blir markerad/accent). Ställ en **svår flerstegsfråga**,
      t.ex. "Jämför vad föreläsaren sa i början mot slutet och peka ut motsägelser."
- [ ] En dämpad **"Resonemang"-bubbla** dyker upp först, sedan det svenska svaret i en
      separat bubbla.
- [ ] **Inget** `<think>`/`</think>` och **ingen** engelsk text i själva svarsbubblan.
- [ ] Request-body innehåller `"think": true`.
- [ ] Mät grovt: PÅ ger märkbart längre tid till första *svars*-token än AV.

### 3. Kvalitetsjämförelse (är PÅ värt latensen här?)
- [ ] Ställ samma svåra fråga en gång med AV och en gång med PÅ. Notera om PÅ ger ett
      mätbart bättre/mer korrekt svar (flerstegsslutledning) — det är den enda vinsten
      som motiverar extratiden.
- [ ] Ställ en *enkel* uppslagsfråga med båda. Bekräfta att AV är lika bra men snabbare
      (→ default AV är rätt).

### 4. Korrigering påverkas inte
- [ ] Kör **Korrekturläs** på samma transkript. `/api/postprocess`-anropet ska ha
      `enable_thinking:false` (serverstyrt) och svaret ska vara rent svenskt, snabbt,
      utan resonemangsbubbla. (Toggeln finns bara i chatten.)

### 5. VRAM/GPU — ingen OOM, ingen regression
- [ ] `nvidia-smi` under PÅ-chatt: VRAM stannar inom ~22 GB (samma KV-profil, q8_0).
      Thinking ska **inte** spränga 24 GB-taket på en lång kontext.
- [ ] Lång kontext + PÅ: bekräfta att svaret fortfarande grundas i **hela** transkriptet
      (fråga om något som bara nämns tidigt) — kontexten får inte trängas undan av
      resonemanget.

## Resultat

> Fyll i datum, drivrutin, observerad tid-till-första-token (AV vs PÅ), VRAM-topp, och
> en mening om huruvida PÅ gav bättre svar på de svåra frågorna. Klistra in `nvidia-smi`.
