<script>
  import { arkiv } from './stores.svelte.js';
  import { runAsk, runSearch, clearSearch } from './actions.js';
</script>

<div class="sok">
  <div class="lagen" role="group" aria-label="Sökläge">
    <button
      class="seg"
      aria-pressed={arkiv.mode === 'ask'}
      onclick={() => (arkiv.mode = 'ask')}
    >Fråga AI</button>
    <button
      class="seg"
      aria-pressed={arkiv.mode === 'word'}
      onclick={() => (arkiv.mode = 'word')}
    >Sök ord</button>
  </div>
  <input
    class="field"
    aria-label="Sök i arkivet"
    placeholder={arkiv.mode === 'ask' ? 'Ställ en fråga — t.ex. när gick vi igenom derivata?' : 'Sök ett ord — t.ex. derivata'}
    bind:value={arkiv.query}
    onkeydown={(e) => { if (e.key === 'Enter' && arkiv.query.trim() && !arkiv.asking && !arkiv.searching) { arkiv.mode === 'ask' ? runAsk() : runSearch(); } }}
  />
  <button
    class="ghost"
    disabled={!(arkiv.query.trim() && !arkiv.asking && !arkiv.searching)}
    onclick={() => (arkiv.mode === 'ask' ? runAsk() : runSearch())}
  >
    {arkiv.asking || arkiv.searching ? 'Söker …' : arkiv.mode === 'ask' ? 'Fråga' : 'Sök'}
  </button>
  {#if arkiv.hits || arkiv.askedFor || arkiv.query}
    <button class="ghost" onclick={clearSearch}>Rensa</button>
  {/if}
</div>

<style>
  .sok {
    display: flex;
    align-items: center;
    gap: 12px;
    flex-wrap: wrap;
    margin-top: 16px;
  }
  .lagen {
    display: inline-flex;
    gap: 3px;
    padding: 3px;
    background: var(--track);
    border: 1px solid var(--line);
    border-radius: 4px;
  }
  .seg {
    border: none;
    border-radius: 3px;
    padding: 8px 14px;
    background: transparent;
    color: var(--ink-2);
    font-family: inherit;
    font-size: inherit;
    cursor: pointer;
  }
  .seg[aria-pressed='true'] {
    background: var(--surface);
    color: var(--ink);
  }
  .field {
    flex: 1;
    min-width: 240px;
    background: var(--surface);
    border: 1px solid var(--line);
    border-radius: 4px;
    padding: 12px 14px;
    font-family: inherit;
    font-size: inherit;
    color: var(--ink);
  }
  .ghost {
    background: transparent;
    color: var(--ink);
    border: 1px solid var(--line-2);
    border-radius: 4px;
    padding: 11px 18px;
    font-family: inherit;
    font-size: inherit;
    cursor: pointer;
  }
  .ghost:disabled { opacity: 0.55; cursor: default; }
</style>
