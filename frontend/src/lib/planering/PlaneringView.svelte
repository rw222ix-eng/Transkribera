<script>
  // Planering — tavelflödet. Delkomponenter kopplas in i senare steg.
  import BuildPanel from './BuildPanel.svelte';
  import BoardPreview from './BoardPreview.svelte';
  import { plan } from './stores.svelte.js';
  import { generateBoard } from './actions.js';
</script>

<section class="view">
  <p class="eyebrow">PLANERING</p>
  <h1 class="display">Dagens <em>tavla</em></h1>
  <p class="lede">
    Beskriv momentet — och välj kurs om du vill — så skrivs tavlan som du annars
    hade skrivit för hand.
  </p>

  <BuildPanel onGenerate={generateBoard} />
  <BoardPreview />

  {#if plan.log.length}
    <ol class="log" aria-live="polite">
      {#each plan.log as line}
        <li class:failed={line.startsWith('Fel:')}>{line}</li>
      {/each}
    </ol>
  {/if}

  {#if plan.errors.length}
    <ul class="errors">
      {#each plan.errors as err}<li>{err}</li>{/each}
    </ul>
  {/if}
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
  /* Loggraderna är hela meningar, inte mikroetiketter — därför sans, inte mono
     (DESIGN.md: mono är reserverad för små versala etiketter). */
  .log {
    margin: 24px 0 0;
    padding-left: 20px;
    color: var(--ink-3);
  }
  /* En körning som havererar ska synas, inte drunkna bland framstegsraderna. */
  .log .failed {
    color: var(--bad);
  }
  .errors {
    margin: 16px 0 0;
    padding-left: 20px;
    color: var(--bad);
  }
</style>
