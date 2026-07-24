<script>
  import { arkiv, resetSearch } from './stores.svelte.js';
  import { getJSON, streamPost } from '../api.js';

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

  async function runAsk() {
    const q = arkiv.query.trim();
    if (!q || arkiv.asking) return;
    resetSearch();
    arkiv.asking = true;
    arkiv.askedFor = q;
    try {
      await streamPost('/api/planning/ask', { q }, (ev) => {
        if (ev.type === 'scan_plan') {
          arkiv.scan = (ev.items ?? []).map((i) => ({ ...i, hits: null }));
        } else if (ev.type === 'scan_result') {
          arkiv.scan = arkiv.scan.map((s) => (s.key === ev.key ? { ...s, ...ev } : s));
        } else if (ev.type === 'deep_read') {
          // deep_read anländer INNAN genereringen startar (se
          // routes_planning.py) — källorna sätts därför inte här, utan vid
          // done. Annars visar "Bygger på: …" som om svaret lyckats även när
          // ett fel inträffar mitt i strömmen.
        } else if (ev.type === 'token') {
          arkiv.answer += ev.text ?? '';
        } else if (ev.type === 'done') {
          arkiv.sources = ev.result?.sources ?? [];
        } else if (ev.type === 'error') {
          // Samma tre fall som den gamla appen (app.js: runArkivAsk) — ett
          // tomt arkiv ska kännas som ett ärligt svar, inte ett fel.
          arkiv.askError = /matchar sökningen/i.test(ev.message || '')
            ? 'Ingen tavla och inget prov i arkivet verkar nämna det du frågar om. Prova att formulera om frågan.'
            : /network|failed to fetch|load failed/i.test(ev.message || '')
            ? 'Anslutningen till appen bröts mitt i sökningen. Ställ frågan igen så görs ett nytt försök.'
            : 'Kunde inte svara: ' + (ev.message || 'okänt fel');
        }
      });
    } finally {
      arkiv.asking = false;
    }
  }

  function clearSearch() {
    arkiv.query = '';
    resetSearch();
    arkiv.error = '';
  }
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
