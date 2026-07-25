<script>
  // Guidens steg 2 — inställningar. Speglar viewTranscribe:s stepConfig-gren
  // (app/web/static/app.js:4472-4578), omstylad till designsystemet.
  import { tr, extOf } from './stores.svelte.js';
  import { removeFromQueue, goSource } from './actions.js';
  import Sprakval from './Sprakval.svelte';
  import Formatval from './Formatval.svelte';
  import Undertextval from './Undertextval.svelte';
</script>

<p class="eyebrow">STEG 2 — INSTÄLLNINGAR</p>
<h1 class="display">Så ska det <span class="ser">låta</span></h1>
<p class="lede">
  Välj språk och format — rätt modell väljs automatiskt, allt körs lokalt på din dator.
</p>

<div class="ko-huvud">
  <span class="label">Filer i kö</span>
  <span class="antal">{tr.queue.length}</span>
  <span class="spacer"></span>
  <button type="button" class="ghost" onclick={goSource}>Lägg till fler</button>
</div>

<ul class="ko">
  {#each tr.queue as q (q.id)}
    <li>
      <span class="ext">{(/^https?:/i).test(q.path || '') ? 'URL' : (extOf(q.name) || 'fil')}</span>
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

<Sprakval />
<Formatval />
<Undertextval />

<style>
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
  .lede { max-width: 62ch; color: var(--ink-2); margin: 0 0 28px; }
  .ko-huvud {
    display: flex;
    align-items: baseline;
    gap: 12px;
    flex-wrap: wrap;
    margin-bottom: 4px;
  }
  .label {
    font-family: var(--mono);
    font-size: 0.72rem;
    font-weight: 500;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: var(--ink-3);
  }
  .antal { color: var(--ink); font-variant-numeric: tabular-nums; }
  .spacer { flex: 1; }
  .ghost {
    background: transparent;
    color: var(--ink);
    border: 1px solid var(--line-2);
    border-radius: 4px;
    padding: 7px 14px;
    font-family: inherit;
    font-size: inherit;
    cursor: pointer;
  }
  .ko { list-style: none; margin: 0; padding: 0; }
  .ko li {
    display: flex;
    align-items: center;
    gap: 12px;
    border-top: 1px solid var(--line);
    padding: 12px 0;
  }
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
</style>
