<script>
  import { chatt } from './stores.svelte.js';
  import { skicka, vaxlaTank } from './actions.js';

  const kanSkicka = $derived(chatt.utkast.trim().length > 0 && !chatt.skickar);

  // Enter skickar, Shift+Enter ger radbrytning. Gamla appen har en <input>
  // och `if (e.key === 'Enter') sendLessonChat();` utan preventDefault
  // (app.js:2463) — alltså ingen flerradig fråga alls.
  function paTangent(e) {
    if (e.key !== 'Enter' || e.shiftKey) return;
    e.preventDefault();
    if (kanSkicka) skicka();
  }
</script>

<div class="skrivrad">
  <textarea
    class="falt"
    rows="2"
    aria-label="Skriv en fråga till lektionen"
    placeholder="Fråga om lektionen — t.ex. vad sa jag om bråk?"
    bind:value={chatt.utkast}
    onkeydown={paTangent}
  ></textarea>
  <div class="knappar">
    <button
      type="button"
      class="ghost"
      aria-pressed={chatt.tank}
      onclick={vaxlaTank}
    >Tänk djupare</button>
    <button
      type="button"
      class="primar"
      disabled={!kanSkicka}
      onclick={skicka}
    >{chatt.skickar ? 'Svarar …' : 'Skicka'}</button>
  </div>
</div>

<style>
  .skrivrad {
    flex: 0 0 auto;
    display: flex;
    align-items: flex-end;
    gap: 10px;
    margin-top: 12px;
    padding-top: 12px;
    border-top: 1px solid var(--line);
  }
  /* Receptet är RedigeraLektion.svelte:242-254:s, med textarea-tilläggen. */
  .falt {
    flex: 1 1 auto;
    min-width: 0;
    background: var(--surface);
    color: var(--ink);
    border: 1px solid var(--line-2);
    border-radius: 3px;
    padding: 8px 10px;
    font-family: inherit;
    font-size: 1.03rem;
    line-height: 1.45;
    resize: vertical;
  }
  .falt:focus-visible { border-color: var(--accent); }
  .knappar {
    flex: 0 0 auto;
    display: flex;
    align-items: center;
    gap: 8px;
  }
  /* Identisk med .ghost i frontend/src/lib/transkribera/Korning.svelte:284-293. */
  .ghost {
    background: transparent;
    color: var(--ink);
    border: 1px solid var(--line-2);
    border-radius: 4px;
    padding: 9px 18px;
    font-family: inherit;
    font-size: inherit;
    cursor: pointer;
  }
  .ghost[aria-pressed='true'] {
    background: var(--accent-weak);
    color: var(--accent);
    border-color: var(--accent);
  }
  /* Identisk med .primar i frontend/src/lib/transkribera/Korning.svelte:273-283. */
  .primar {
    background: var(--btn-bg);
    color: var(--btn-fg);
    border: none;
    border-radius: 4px;
    padding: 10px 20px;
    font-family: inherit;
    font-size: inherit;
    font-weight: 500;
    cursor: pointer;
  }
  /* Identisk med .ghost:disabled i frontend/src/lib/inspelningar/InspelningarView.svelte:425. */
  .primar:disabled { opacity: 0.55; cursor: default; }
</style>
