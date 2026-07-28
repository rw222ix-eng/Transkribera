<script>
  import { tk } from './stores.svelte.js';
  import { fmtTid } from './tid.js';
  import { spolaTill, taBortMarkor } from './actions.js';
</script>

{#if tk.markorer.length}
  <ul class="markorer">
    {#each tk.markorer as m (m.id)}
      <li class="markor">
        <button type="button" class="hoppa" onclick={() => spolaTill(m.t)}>{fmtTid(m.t)}</button>
        <button
          type="button"
          class="ta-bort"
          aria-label="Ta bort markören {fmtTid(m.t)}"
          onclick={() => taBortMarkor(m.id)}
        >×</button>
      </li>
    {/each}
  </ul>
{/if}

<style>
  .markorer {
    list-style: none;
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
    margin: 10px 0 0;
    padding: 0;
  }
  .markor {
    display: flex;
    align-items: stretch;
    border: 1px solid var(--line-2);
    border-radius: 3px;
    overflow: hidden;
  }
  .hoppa,
  .ta-bort {
    background: transparent;
    color: var(--ink-2);
    border: none;
    font-family: inherit;
    font-size: 0.72rem;
    font-variant-numeric: tabular-nums;
    padding: 4px 8px;
    cursor: pointer;
  }
  .hoppa:hover { background: var(--sunken); }
  .ta-bort {
    border-left: 1px solid var(--line);
    color: var(--ink-3);
  }
  .ta-bort:hover { color: var(--bad); }
</style>
