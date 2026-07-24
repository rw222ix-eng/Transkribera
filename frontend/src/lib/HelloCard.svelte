<script>
  let count = $state(0);
</script>

<section class="card">
  <p class="eyebrow">EXEMPEL</p>
  <h2>En liten ruta</h2>
  <p>Klickad {count} gånger.</p>
  <button onclick={() => count++}>Klicka</button>
</section>

<style>
  .card { border: 1px solid var(--line); border-radius: 4px; padding: 20px;
    background: var(--surface); max-width: 360px; }
  .eyebrow { font-family: var(--mono); font-size: 0.72rem; letter-spacing: 0.08em;
    color: var(--ink-3); margin: 0 0 8px; }
  h2 { font-family: var(--sans); font-weight: 600; font-size: 1.125rem; margin: 0 0 6px; }
  button { background: var(--btn-bg); color: var(--btn-fg); border: none;
    border-radius: 4px; padding: 10px 18px; font-family: inherit; cursor: pointer; }
</style>
