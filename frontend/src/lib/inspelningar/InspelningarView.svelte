<script>
  // Inspelningar-fliken: kartoteket över transkriberade lektioner. Speglar
  // viewRecordings (app/web/static/app.js:4776-4956), omstylad till
  // designsystemet — gamla vyn är ren inline-CSS med 9-14px hörn.
  import { insp } from './stores.svelte.js';
</script>

<section class="view">
  <p class="eyebrow">INSPELNINGAR</p>
  <h1 class="display">Dina <span class="ser">lektioner</span></h1>
  <p class="lede">
    Allt som transkriberats, samlat per vecka. Ljudet och texten ligger kvar på
    din egen dator.
  </p>

  <!--
    Vyns egen live-region. Permanent i DOM:en och bara visuellt klippt — aldrig
    {#if}-grindad och aldrig display:none. Det mönstret har underkänts fyra
    gånger i den här migrationen: en region som monteras in samtidigt som sin
    text annonseras inte pålitligt, och display:none tar bort noden ur
    tillgänglighetsträdet så role="status" aldrig kan annonsera mutationen.

    ATT VARJE VY HAR EN EGEN ÄR RÄTT, inte en dubblett. App.svelte göms per
    flik med hidden (.pane[hidden] { display: none }), inte genom att
    avmontera, så alla vyers paneler ligger kvar i DOM:en samtidigt — men en
    dold panel är display:none och alltså borta ur tillgänglighetsträdet, så
    bara den synliga fliken kan annonsera. A4:s nodidentitetsspärr i
    e2e/transkribera-kalla.spec.mjs räknade från början [role="status"] över
    HELA sidan och fällde därför den här noden; den är nu avgränsad till den
    synliga panelen, vilket är vad den hela tiden menade.
  -->
  <p class="fel-sr" role="status">{insp.fel}</p>
</section>

<style>
  .view { max-width: 860px; margin: 0 auto; padding: 56px 24px 96px; }
  .eyebrow {
    font-family: var(--mono);
    font-size: 0.72rem;
    font-weight: 500;
    letter-spacing: 0.08em;
    color: var(--ink-3);
    margin: 0 0 14px;
  }
  .display {
    font-family: var(--sans);
    font-weight: 700;
    font-size: 1.5rem;
    line-height: 1.15;
    letter-spacing: -0.02em;
    color: var(--ink);
    margin: 0 0 10px;
  }
  .display .ser {
    font-family: var(--serif);
    font-style: italic;
    font-weight: 400;
    font-size: 2.375rem;
    line-height: 1.05;
    letter-spacing: -0.01em;
  }
  /* Klippande teknik — noden finns kvar i tillgänglighetsträdet men upptar
     ingen synlig plats, till skillnad från display:none. Identisk med
     TranskriberaView.svelte:197. */
  .fel-sr {
    position: absolute;
    width: 1px;
    height: 1px;
    overflow: hidden;
    clip-path: inset(50%);
    white-space: nowrap;
  }
  .lede {
    font-size: 1.03rem;
    color: var(--ink-2);
    margin: 0 0 26px;
    max-width: 52ch;
  }
</style>
