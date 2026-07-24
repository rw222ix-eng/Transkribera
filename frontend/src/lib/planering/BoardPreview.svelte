<script>
  import { plan } from './stores.svelte.js';
  import { parsePartialBoard, countSections } from './boardStream.js';
  import { onToken } from './actions.js';

  let frame = $state(null);
  let ready = $state(false);
  let warnings = $state([]);
  let liveBuffer = '';
  let liveTimer = null;
  let liveBusy = false;
  let liveChain = Promise.resolve();

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
    const win = frame?.contentWindow;
    if (!win?.WBHost) {
      warnings = ['Kunde inte ladda tavelmotorn.'];
      return;
    }
    renderBoard();
  }

  // Rita om när en ny tavla kommer in (och iframen redan är laddad).
  $effect(() => {
    void plan.board;
    if (ready) renderBoard();
  });

  /** Ritar den halvfärdiga tavlan när tillräckligt många sektioner finns. */
  function liveTick() {
    liveTimer = null;
    if (plan.phase !== 'running') return;
    const win = frame?.contentWindow;
    if (!win?.WBHost || liveBusy) return;
    const board = parsePartialBoard(liveBuffer);
    if (!board?.boards?.length) return;
    const n = countSections(board);
    if (n <= plan.liveSections) return;
    plan.liveSections = n;
    liveBusy = true;
    liveChain = liveChain
      .then(() => win.WBHost.render({ boards: board.boards }))
      .catch(() => {})
      .then(() => { liveBusy = false; });
  }

  $effect(() => {
    // null = ny körning; annars text att lägga på bufferten.
    return onToken((text) => {
      if (text === null) {
        liveBuffer = '';
        if (liveTimer) { clearTimeout(liveTimer); liveTimer = null; }
        return;
      }
      liveBuffer += text;
      if (!liveTimer) liveTimer = setTimeout(liveTick, 450);
    });
  });
</script>

{#if plan.board || plan.liveSections > 0}
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
  /* Varningarna är hela meningar från motorn — sans, inte mono
     (DESIGN.md: mono är reserverad för små versala etiketter). */
  .warnings {
    margin: 10px 0 0;
    padding-left: 18px;
    color: var(--warn);
  }
</style>
