<script>
  // Kölistan, delad mellan guidens steg 1 och steg 2 (plan A2-fixrunda,
  // punkt 3). Låg tidigare duplicerad ordagrant i TranskriberaView.svelte
  // och Installningar.svelte, och hade redan glidit isär: bara den förra
  // hade `li:first-child { border-top: none }`, så steg 2 ritade en
  // överflödig hårlinje ovanför sin första rad. Nu finns bara en definition.
  // Mellanrummet OVANFÖR listan är fortsatt varje anropares eget val (steg 1
  // vill ha 20px luft efter "prova"-raden, steg 2 vill ha noll efter
  // ko-huvud), så den styrs inte här.
  import { tr, extOf } from './stores.svelte.js';
  import { removeFromQueue } from './actions.js';
</script>

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

<style>
  .ko { list-style: none; margin: 0; padding: 0; }
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
</style>
