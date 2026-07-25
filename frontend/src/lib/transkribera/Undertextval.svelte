<script>
  // Undertext i video. Visas bara när den aktiva källan ÄR en video — samma
  // villkor som gamla appens _activeIsVideo (app.js:3204-3205).
  import { tr } from './stores.svelte.js';

  const VIDEO = /\.(mp4|mkv|mov|webm|avi|m4v)$/i;

  const aktiv = $derived(
    tr.queue.find((q) => q.id === tr.activeId) || tr.queue[0] || null,
  );
  const arVideo = $derived(!!aktiv && VIDEO.test(aktiv.name || ''));

  const LAGE = [['separate', 'Spara separat'], ['embed', 'Bädda in']];
  const SORT = [['soft', 'Mjukt sub-spår'], ['burn', 'Hård inbränning']];
</script>

{#if arVideo}
  <div class="rad">
    <span class="rubrik">Undertext i video</span>
    <div class="seg" role="group" aria-label="Undertext i video">
      {#each LAGE as [kod, etikett]}
        <button
          type="button"
          aria-pressed={tr.subtitleMode === kod}
          onclick={() => (tr.subtitleMode = kod)}
        >{etikett}</button>
      {/each}
    </div>

    {#if tr.subtitleMode === 'embed'}
      <div class="seg" role="group" aria-label="Sorts inbäddning">
        {#each SORT as [kod, etikett]}
          <button
            type="button"
            aria-pressed={tr.embedKind === kod}
            onclick={() => (tr.embedKind = kod)}
          >{etikett}</button>
        {/each}
      </div>
    {/if}
  </div>
{/if}

<style>
  .rad {
    display: flex;
    align-items: center;
    gap: 14px;
    flex-wrap: wrap;
    background: var(--surface);
    border: 1px solid var(--line);
    border-radius: 5px;
    padding: 14px 18px;
    margin-top: 12px;
  }
  .rubrik { color: var(--ink-2); font-weight: 500; }
  .seg {
    display: flex;
    gap: 3px;
    padding: 3px;
    background: var(--track);
    border: 1px solid var(--line);
    border-radius: 5px;
  }
  .seg button {
    border: none;
    border-radius: 3px;
    padding: 7px 13px;
    background: transparent;
    color: var(--ink-2);
    font-family: inherit;
    font-size: inherit;
    font-weight: 500;
    cursor: pointer;
  }
  .seg button[aria-pressed='true'] { background: var(--surface); color: var(--ink); }
</style>
