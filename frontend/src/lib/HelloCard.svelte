<script>
  let count = $state(0);
</script>

<!-- Accepterad via Impeccable live-läge (variant 2 — asymmetrisk rad: text till
     vänster, handlingen avskild till höger). Luft-ratten bakad till 32px. -->
<section class="row">
  <div class="lead">
    <p class="eyebrow">EXEMPEL</p>
    <h2 class="title">En liten ruta</h2>
    <p class="meta">Klickad {count} gånger.</p>
  </div>
  <button class="act" onclick={() => count++}>Klicka</button>
</section>

<style>
  .row {
    max-width: 360px;
    padding: 32px;
    background: var(--surface);
    border: 1px solid var(--line);
    border-radius: 4px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 18px;
  }
  .lead {
    min-width: 0;
  }
  .eyebrow {
    font-family: var(--mono);
    font-size: 0.72rem;
    letter-spacing: 0.08em;
    color: var(--ink-3);
    margin: 0 0 7px;
  }
  .title {
    font-family: var(--sans);
    font-weight: 600;
    font-size: 1.125rem;
    letter-spacing: -0.011em;
    color: var(--ink);
    margin: 0 0 4px;
  }
  .meta {
    margin: 0;
    font-size: 1.03rem;
    color: var(--ink-2);
    font-variant-numeric: tabular-nums;
  }
  .act {
    flex: none;
    background: var(--btn-bg);
    color: var(--btn-fg);
    border: none;
    border-radius: 4px;
    padding: 10px 18px;
    font-family: inherit;
    font-size: inherit;
    cursor: pointer;
  }
</style>
