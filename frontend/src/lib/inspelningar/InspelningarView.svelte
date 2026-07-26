<script>
  // Inspelningar-fliken: kartoteket över transkriberade lektioner. Speglar
  // viewRecordings (app/web/static/app.js:4776-4956), omstylad till
  // designsystemet — gamla vyn är ren inline-CSS med 9-14px hörn.
  //
  // MEDVETET ingen egen statusrad ännu. insp.fel finns i storen (för B2-B5:s
  // fel- och räddningsbesked) men är alltid '' i den här uppgiften — inget
  // körs som skulle sätta den. En permanent role="status" här, byggd exakt
  // som TranskriberaView.svelte:s hoistade .fel-sr, kolliderar med
  // nodidentitetsspärren i e2e/transkribera-kalla.spec.mjs: den räknar
  // section.view [role="status"] över HELA sidan, inte bara den synliga
  // fliken — App.svelte göms med hidden, inte {#if}, så alla flikars paneler
  // ligger kvar i DOM:en samtidigt. Verifierat: en andra permanent
  // status-nod här fick fyra tester i den specen att gå från 1 till 2
  // träffar och falla. Den som först skriver ett riktigt fel till insp.fel
  // (B2 eller senare) måste lösa den kollisionen på riktigt, inte bara
  // upprepa mönstret.
</script>

<section class="view">
  <p class="eyebrow">INSPELNINGAR</p>
  <h1 class="display">Dina <span class="ser">lektioner</span></h1>
  <p class="lede">
    Allt som transkriberats, samlat per vecka. Ljudet och texten ligger kvar på
    din egen dator.
  </p>
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
  .lede {
    font-size: 1.03rem;
    color: var(--ink-2);
    margin: 0 0 26px;
    max-width: 52ch;
  }
</style>
