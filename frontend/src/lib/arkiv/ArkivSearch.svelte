<script>
  import { arkiv, resetSearch } from './stores.svelte.js';
  import { getJSON } from '../api.js';

  const canSearch = $derived(arkiv.query.trim().length > 0 && !arkiv.searching);

  async function runSearch() {
    const q = arkiv.query.trim();
    if (!q || arkiv.searching) return;
    resetSearch();
    arkiv.searching = true;
    try {
      const d = await getJSON('/api/planning/archive/search?q=' + encodeURIComponent(q));
      arkiv.hits = d?.hits ?? [];
      arkiv.error = '';
    } catch (e) {
      arkiv.hits = [];
      arkiv.error = 'Sökningen misslyckades: ' + (e?.message || e);
    } finally {
      arkiv.searching = false;
    }
  }

  function clearSearch() {
    arkiv.query = '';
    resetSearch();
    arkiv.error = '';
  }
</script>

<div class="sok">
  <input
    class="field"
    aria-label="Sök i arkivet"
    placeholder="Sök ett ord — t.ex. derivata"
    bind:value={arkiv.query}
    onkeydown={(e) => { if (e.key === 'Enter' && canSearch) runSearch(); }}
  />
  <button class="ghost" disabled={!canSearch} onclick={() => runSearch()}>
    {arkiv.searching ? 'Söker …' : 'Sök ord'}
  </button>
  {#if arkiv.hits}
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
