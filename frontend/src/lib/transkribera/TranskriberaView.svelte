<script>
  // Transkriberingsguiden, steg 1 — Källa. Speglar viewTranscribe:s
  // stepSource-gren (app/web/static/app.js:4383-4470), omstylad till
  // designsystemet. Steg 2 och 3 kommer i plan A2 och A3.
  import { tr, extOf } from './stores.svelte.js';
  import { removeFromQueue, addSample, addSampleCorrupt } from './actions.js';
  import Stegindikator from './Stegindikator.svelte';
  import Dropzone from './Dropzone.svelte';
  import LankFalt from './LankFalt.svelte';
</script>

<section class="view">
  <Stegindikator />

  <p class="eyebrow">STEG 1 — KÄLLA</p>
  <h1 class="display">Vad vill du <span class="ser">transkribera?</span></h1>
  <p class="lede">
    Dra in en eller flera filer, eller välj från datorn — allt körs på din egen dator.
  </p>

  <Dropzone />
  <LankFalt />

  <p class="prova">
    Eller prova med
    <button type="button" class="lank" onclick={addSample}>ett exempel</button>
    <button type="button" class="lank" onclick={addSampleCorrupt}>skadad_inspelning.m4a</button>
  </p>

  {#if tr.fileError}
    <p class="fel" role="status">{tr.fileError}</p>
  {/if}

  {#if tr.queue.length}
    <ul class="ko">
      {#each tr.queue as q (q.id)}
        <li>
          <span class="ext">{extOf(q.name) || '?'}</span>
          <span class="namn">{q.name}</span>
          <button
            type="button"
            class="bort"
            aria-label={'Ta bort ' + q.name + ' ur kön'}
            onclick={() => removeFromQueue(q.id)}
          >✕</button>
        </li>
      {/each}
    </ul>
    <p class="antal">{tr.queue.length} {tr.queue.length === 1 ? 'fil' : 'filer'} i kön.</p>
  {/if}
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
  .lede { max-width: 62ch; color: var(--ink-2); margin: 0; }
  .prova { color: var(--ink-3); margin: 20px 0 0; display: flex; gap: 12px; flex-wrap: wrap; }
  .lank {
    border: none;
    background: transparent;
    color: var(--ink-2);
    font-family: inherit;
    font-size: inherit;
    padding: 0;
    cursor: pointer;
    text-decoration: underline;
    text-underline-offset: 3px;
  }
  .lank:hover { color: var(--ink); }
  .fel { color: var(--bad); margin: 14px 0 0; }
  .ko { list-style: none; margin: 20px 0 0; padding: 0; }
  .ko li {
    display: flex;
    align-items: center;
    gap: 12px;
    border-top: 1px solid var(--line);
    padding: 12px 0;
  }
  .ko li:first-child { border-top: none; }
  .ext {
    font-family: var(--mono);
    font-size: 0.72rem;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    color: var(--ink-3);
    flex: 0 0 auto;
  }
  .namn {
    flex: 1;
    min-width: 0;
    color: var(--ink);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .bort {
    flex: 0 0 auto;
    border: 1px solid var(--line);
    background: transparent;
    color: var(--ink-3);
    border-radius: 3px;
    padding: 5px 10px;
    font-family: inherit;
    font-size: inherit;
    cursor: pointer;
  }
  .bort:hover { border-color: var(--bad); color: var(--bad); }
  .antal { color: var(--ink-3); margin: 10px 0 0; }
</style>
