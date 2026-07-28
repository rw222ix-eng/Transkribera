<script>
  import { arkiv } from './stores.svelte.js';
  import { runAsk, runSearch, clearSearch } from './actions.js';
  import Segment from '../Segment.svelte';
</script>

<div class="sok">
  <!-- Enval — plattan. Samma kontroll och samma form som Sokfalt.svelte:s
       lägesväxel; de två var tidigare olika utan att beteendet skilde sig. -->
  <Segment
    alternativ={[['ask', 'Fråga AI'], ['word', 'Sök ord']]}
    etikett="Sökläge"
    arVald={(m) => arkiv.mode === m}
    valj={(m) => (arkiv.mode = m)}
  />
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
  /* Lägesväxelns form bor i Segment.svelte. */
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
