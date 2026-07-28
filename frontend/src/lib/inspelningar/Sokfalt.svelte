<script>
  // Sökfältet och lägesväxeln. Speglar spotlightPanel
  // (app/web/static/app.js:5138-5162), omstylat till designsystemet — gamla
  // fältet är inline-CSS med 14px hörn, --shadow och en pulserande accentprick.
  import { sok } from './sok.svelte.js';
  import { korSokning, rensaSokning, valjLage, stallFraga } from './sokActions.js';
  import Segment from '../Segment.svelte';

  const harFraga = $derived(sok.fraga.trim().length > 0);

  // "/" FOKUSERAR SÖKET. Appen hade inga kortkommandon alls; en lärare med
  // ett läsår i arkivet når annars fältet bara genom att tabba förbi
  // filterraden och säkerhetskopieringen. "/" är webbens etablerade
  // sökgenväg och kostar inget att lära sig.
  //
  // GRINDARNA. Genvägen får inte kapa ett tecken läraren skriver någon
  // annanstans:
  //   · redigerbara fält (input, textarea, contenteditable) äger sitt "/",
  //   · modifierade tryck (Ctrl+/, Cmd+/) är webbläsarens eller OS:ets,
  //   · en öppen <dialog> gör resten av dokumentet inert — men lyssnaren
  //     sitter på window och nås ändå, så flikgrinden nedan räcker inte.
  //
  // Lyssnaren är knuten till komponentens livstid via <svelte:window>, inte
  // till en $effect med manuell add/removeEventListener: komponenten är
  // monterad hela sessionen (App.svelte göms med hidden), och attributformen
  // kan inte läcka en lyssnare.
  let falt = $state(null);

  function globalTangent(e) {
    if (e.key !== '/' || e.ctrlKey || e.metaKey || e.altKey) return;
    const m = e.target;
    if (m instanceof HTMLElement && (m.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(m.tagName))) return;
    // Panelen är dold vid flikbyte; en genväg som fokuserar ett osynligt fält
    // flyttar fokus ut ur det läraren tittar på. offsetParent är null för allt
    // under en [hidden]-förälder.
    if (!falt || !falt.offsetParent) return;
    e.preventDefault();
    falt.focus();
    falt.select();
  }

  // Enter kör lägets aktion. preventDefault så fältet inte submittar något
  // formulär — det finns inget här, men vyn har dialoger som gör det.
  function taKey(e) {
    if (e.key !== 'Enter') return;
    e.preventDefault();
    if (sok.lage === 'ask') stallFraga();
    else korSokning();
  }
</script>

<svelte:window onkeydown={globalTangent} />

<section class="sok">
  <div class="falt">
    <input
      class="input"
      bind:this={falt}
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

    <button
      class="kor"
      onclick={sok.lage === 'ask' ? stallFraga : korSokning}
      disabled={sok.soker || sok.fragar}
    >
      {sok.soker || sok.fragar ? 'Söker …' : sok.lage === 'ask' ? 'Fråga' : 'Sök'}
    </button>
  </div>

  <!--
    AVVIKELSEN ÄR BORTA. Den här lägesväxeln bar tidigare fristående
    mikroetiketter (var(--line)-ram var, var(--accent-weak) på det aktiva
    valet) medan ArkivSearch och BuildPanel ritade samma sorts kontroll som en
    segmentplatta. Den gamla kommentaren här sköt upp valet till "en separat
    visuell genomgång av alla tre" — det här ÄR den genomgången.

    Formen som vann är plattan, och skälet är inte estetiskt: chipsformen var
    identisk med Formatval.svelte:s FLERVALS-chips (SRT *och* TXT), medan den
    här kontrollen är ENVAL (Fråga AI *eller* Sök ord). Två motsatta kontrakt
    med ett utseende. Regeln står överst i Segment.svelte.
  -->
  <Segment
    alternativ={[['ask', 'Fråga AI'], ['keyword', 'Sök ord']]}
    etikett="Sökläge för inspelningar"
    arVald={(l) => sok.lage === l}
    valj={valjLage}
  />
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

  /* Lägesväxelns egen form bor numera i Segment.svelte. Kvar här är bara
     placeringen i sökfältet. Med den gick också var(--mono) ur komponenten:
     mono är reserverat för korta versala MIKROETIKETTER, och en kontroll som
     läraren trycker på är inte en etikett (DESIGN.md, Mono-Is-Labels-Only). */
  .sok :global(.seg) { margin-top: 10px; }
</style>
