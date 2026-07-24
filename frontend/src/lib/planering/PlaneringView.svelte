<script>
  // Planering — tavelflödet. Delkomponenter kopplas in i senare steg.
</script>

<section class="view">
  <p class="eyebrow">PLANERING</p>
  <h1 class="display">Dagens <em>tavla</em></h1>
  <p class="lede">
    Beskriv momentet — och välj kurs om du vill — så skrivs tavlan som du annars
    hade skrivit för hand.
  </p>
</section>

<style>
  .view {
    max-width: 860px;
    margin: 0 auto;
    padding: 56px 24px 96px;
  }
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
  .display em {
    font-family: var(--serif);
    font-style: italic;
    font-weight: 400;
    font-size: 2.375rem;
    line-height: 1.05;
    letter-spacing: -0.01em;
  }
  .lede {
    max-width: 62ch;
    color: var(--ink-2);
    margin: 0;
  }
</style>
