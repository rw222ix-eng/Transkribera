<script>
  import { plan } from './stores.svelte.js';

  let frame = $state(null);
  let ready = $state(false);
  let warnings = $state([]);

  const title = $derived(plan.board?.title || 'Lektionstavla');

  /** Ritar aktuell tavla i iframen. Tyst när motorn inte är laddad än. */
  async function renderBoard() {
    const win = frame?.contentWindow;
    if (!win?.WBHost || !plan.board) return;
    try {
      const res = await win.WBHost.render(plan.board);
      warnings = res?.warnings ?? [];
    } catch (e) {
      warnings = ['Kunde inte rita tavlan: ' + (e?.message || e)];
    }
  }

  function onLoad() {
    ready = true;
    renderBoard();
  }

  // Rita om när en ny tavla kommer in (och iframen redan är laddad).
  $effect(() => {
    void plan.board;
    if (ready) renderBoard();
  });
</script>

{#if plan.board}
  <figure class="preview">
    <figcaption class="cap">
      <span class="label">Förhandsvisning</span>
      <span class="title">{title}</span>
    </figcaption>
    <iframe
      bind:this={frame}
      onload={onLoad}
      src="/static/whiteboard/board.html"
      title={'Lektionstavla — ' + title}
    ></iframe>
    {#if warnings.length}
      <ul class="warnings">
        {#each warnings as w}<li>{w}</li>{/each}
      </ul>
    {/if}
  </figure>
{/if}

<style>
  .preview { margin: 32px 0 0; }
  .cap {
    display: flex;
    align-items: baseline;
    gap: 12px;
    margin-bottom: 10px;
  }
  .label {
    font-family: var(--mono);
    font-size: 0.72rem;
    font-weight: 500;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: var(--ink-3);
  }
  .title { color: var(--ink-2); }
  iframe {
    width: 100%;
    height: 420px;
    border: 1px solid var(--line);
    border-radius: 5px;
    display: block;
    background: var(--sunken);
  }
  .warnings {
    margin: 10px 0 0;
    padding-left: 18px;
    color: var(--warn);
    font-size: 0.72rem;
    font-family: var(--mono);
    letter-spacing: 0.08em;
  }
</style>
