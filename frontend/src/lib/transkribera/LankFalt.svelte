<script>
  // YouTube-/länkfältet. Speglar app.js:4400-4407.
  import { tr } from './stores.svelte.js';
  import { addUrl } from './actions.js';
</script>

<div class="rad">
  <span class="label">Eller länk</span>
  <input
    class="falt"
    aria-label="YouTube-länk"
    placeholder="Klistra in en YouTube-länk …"
    bind:value={tr.urlInput}
    onkeydown={(e) => { if (e.key === 'Enter') addUrl(); }}
  />
  <button type="button" class="lagg" onclick={addUrl}>Lägg till</button>
</div>

<style>
  .rad {
    display: flex;
    align-items: center;
    gap: 14px;
    flex-wrap: wrap;
    margin-top: 16px;
  }
  .label {
    flex: 0 0 74px;
    font-family: var(--mono);
    font-size: 0.72rem;
    font-weight: 500;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: var(--ink-3);
  }
  .falt {
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
  .falt:focus-visible { border-color: var(--accent); }
  .lagg {
    background: transparent;
    color: var(--ink);
    border: 1px solid var(--line-2);
    border-radius: 4px;
    padding: 11px 18px;
    font-family: inherit;
    font-size: inherit;
    cursor: pointer;
  }
</style>
