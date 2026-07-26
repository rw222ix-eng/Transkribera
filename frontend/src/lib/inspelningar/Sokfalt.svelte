<script>
  // Sökfältet och lägesväxeln. Speglar spotlightPanel
  // (app/web/static/app.js:5138-5162), omstylat till designsystemet — gamla
  // fältet är inline-CSS med 14px hörn, --shadow och en pulserande accentprick.
  import { sok } from './sok.svelte.js';
  import { korSokning, rensaSokning, valjLage } from './sokActions.js';

  const harFraga = $derived(sok.fraga.trim().length > 0);

  // Enter kör sökningen. preventDefault så fältet inte submittar något
  // formulär — det finns inget här, men vyn har dialoger som gör det.
  function taKey(e) {
    if (e.key !== 'Enter') return;
    e.preventDefault();
    if (sok.lage === 'keyword') korSokning();
  }
</script>

<section class="sok">
  <div class="falt">
    <input
      class="input"
      bind:value={sok.fraga}
      onkeydown={taKey}
      aria-label="Sök i arkivet"
      placeholder={sok.lage === 'ask'
        ? 'Ställ en fråga, t.ex. när hade vi prov om derivata?'
        : 'Sök efter vad som sades, t.ex. pythagoras sats'}
    />

    <!--
      ✕ BEHÅLLER ALLTID SIN PLATS. visibility, inte display och inte {#if}:
      annars knuffas Sök-knappen i sidled vid första tecknet. Gamla appen löser
      det likadant och av samma skäl (app.js:5147-5149, style.css:195).
      visibility: hidden tar dessutom bort knappen ur både tabbordningen och
      tillgänglighetsträdet, så den är inte nåbar medan den är dold.
    -->
    <button
      class="rensa"
      onclick={rensaSokning}
      aria-label="Rensa"
      style:visibility={harFraga ? 'visible' : 'hidden'}
    >✕</button>

    <!-- Inaktiv i fråge-läget: det svarar inte förrän B3b. -->
    <button class="kor" onclick={korSokning} disabled={sok.soker || sok.lage === 'ask'}>
      {sok.soker ? 'Söker …' : 'Sök'}
    </button>
  </div>

  <div class="lagen" role="group" aria-label="Sökläge för inspelningar">
    <button class="lage" aria-pressed={sok.lage === 'ask'} onclick={() => valjLage('ask')}>
      Fråga AI
    </button>
    <button class="lage" aria-pressed={sok.lage === 'keyword'} onclick={() => valjLage('keyword')}>
      Sök ord
    </button>
  </div>
</section>

<style>
  .sok { margin: 18px 0 4px; }

  /* Fältet är en rad med hårlinje, inte gamla appens 14px-kort med --shadow.
     Flat-by-Default (DESIGN.md): hårlinjen bär formen. */
  .falt {
    display: flex;
    align-items: center;
    gap: 8px;
    background: var(--surface);
    border: 1px solid var(--line-2);
    border-radius: 4px;
    padding: 4px 4px 4px 12px;
  }
  .falt:focus-within { border-color: var(--accent); }

  .input {
    flex: 1;
    min-width: 0;
    background: transparent;
    border: 0;
    color: var(--ink);
    font-family: inherit;
    font-size: 1.03rem;
    padding: 8px 0;
  }
  .input::placeholder { color: var(--ink-3); }

  .rensa {
    flex: none;
    background: transparent;
    border: 0;
    color: var(--ink-3);
    font-family: inherit;
    font-size: 1.03rem;
    line-height: 1;
    padding: 6px 8px;
    cursor: pointer;
  }
  .rensa:hover { color: var(--ink); }

  /* Primärknapp, samma form som RedigeraLektion.svelte:297-307. */
  .kor {
    flex: none;
    background: var(--btn-bg);
    color: var(--btn-fg);
    border: 1px solid var(--btn-bg);
    border-radius: 4px;
    padding: 8px 18px;
    font-family: inherit;
    font-size: inherit;
    cursor: pointer;
  }
  .kor:disabled { cursor: default; opacity: 0.5; }

  .lagen { display: flex; gap: 6px; margin-top: 10px; }

  /* Mikroetikettens form: kort, versal, mono. Den ENDA platsen i komponenten
     där var(--mono) hör hemma. */
  .lage {
    background: transparent;
    border: 1px solid var(--line);
    border-radius: 3px;
    padding: 5px 11px;
    font-family: var(--mono);
    font-size: 0.72rem;
    font-weight: 500;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: var(--ink-3);
    cursor: pointer;
  }
  .lage:hover { color: var(--ink-2); border-color: var(--line-2); }
  /* Accenten markerar ett VAL — precis vad One Voice reserverar den för. */
  .lage[aria-pressed='true'] {
    background: var(--accent-weak);
    border-color: var(--accent);
    color: var(--accent);
  }
</style>
