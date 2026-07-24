<script>
  import { plan } from './stores.svelte.js';
  import { parsePartialBoard, countSections } from './boardStream.js';
  import { onToken } from './actions.js';

  let frame = $state(null);
  let ready = $state(false);
  let warnings = $state([]);
  let frameHeight = $state(420);
  let liveBuffer = '';
  let liveTimer = null;
  let liveBusy = false;
  let liveChain = Promise.resolve();

  const title = $derived(plan.board?.title || 'Lektionstavla');

  let zoomed = $state(false);

  function print() {
    frame?.contentWindow?.WBHost?.print();
  }

  function setPanZoom(on) {
    try {
      frame?.contentWindow?.WBHost?.setPanZoom?.(on);
    } catch {
      /* motorn saknar panorering — förstoringen fungerar ändå */
    }
  }

  function toggleZoom() {
    zoomed = !zoomed;
    setPanZoom(zoomed);
  }

  $effect(() => {
    if (!zoomed) return;
    function onKey(e) {
      if (e.key === 'Escape') toggleZoom();
    }
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  });

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

  /** Schemalägger nästa live-ritning så länge körningen pågår. */
  function scheduleLiveTick(delay = 450) {
    if (!liveTimer && plan.phase === 'running') liveTimer = setTimeout(liveTick, delay);
  }

  /** Ritar den halvfärdiga tavlan när tillräckligt många sektioner finns. */
  function liveTick() {
    liveTimer = null;
    if (plan.phase !== 'running') return;
    const win = frame?.contentWindow;
    // Motorn kan vara oladdad (iframen monterades nyss) eller upptagen med
    // föregående ritning. Båda är övergående — försök igen i stället för att
    // ge upp, annars ritas ingenting alls under den första genereringen.
    if (!win?.WBHost || liveBusy) {
      scheduleLiveTick(150);
      return;
    }
    const board = parsePartialBoard(liveBuffer);
    const n = board?.boards?.length ? countSections(board) : 0;
    if (!n || n <= plan.liveSections) {
      // Texten räcker ännu inte till en ny sektion — vänta in mer.
      scheduleLiveTick();
      return;
    }
    plan.liveSections = n;
    liveBusy = true;
    liveChain = liveChain
      .then(() => win.WBHost.render({ boards: board.boards }))
      .catch(() => {})
      .then(() => { liveBusy = false; });
  }

  $effect(() => {
    function onMessage(e) {
      // Bara meddelanden från samma ursprung — iframen serveras från samma
      // origin som sidan (i dev via Vite-proxyn).
      if (e.origin !== window.location.origin) return;
      if (e.data?.type === 'wb-height') frameHeight = +e.data.px || 420;
    }
    window.addEventListener('message', onMessage);
    return () => window.removeEventListener('message', onMessage);
  });

  $effect(() => {
    // null = ny körning; annars text att lägga på bufferten.
    return onToken((text) => {
      if (text === null) {
        liveBuffer = '';
        if (liveTimer) { clearTimeout(liveTimer); liveTimer = null; }
        return;
      }
      liveBuffer += text;
      // Första sektionen ritas snabbt så läraren ser att något händer; därefter
      // lugnare takt så motorn slipper rita om vid varje token.
      scheduleLiveTick(plan.liveSections === 0 ? 120 : 450);
    });
  });
</script>

<!-- Ramen ligger alltid i DOM:en och göms bara visuellt när det inte finns något
     att visa. Skälet är live-uppbyggnaden: tavelmotorn (KaTeX + handstilsfonter)
     tar ett par sekunder att ladda, så monteras iframen först när körningen
     startar hinner WBHost aldrig bli redo innan modellen är klar — och då ritas
     ingenting live vid den FÖRSTA genereringen. Nu är motorn varm när det smäller.
     Iframen får aldrig villkoras bort: att återskapa den laddar om dokumentet
     och tömmer tavlan. -->
<figure class="preview" class:zoomed class:idle={!plan.board && plan.phase !== 'running'}>
    <figcaption class="cap">
      <span class="label">Förhandsvisning</span>
      <span class="title">{title}</span>
      <span class="spacer"></span>
      <button class="ghost" onclick={print}>Skriv ut</button>
      <button class="ghost" onclick={toggleZoom}>
        {zoomed ? 'Stäng' : 'Förstora'}
      </button>
    </figcaption>
    <iframe
      bind:this={frame}
      onload={onLoad}
      src="/static/whiteboard/board.html"
      title={'Lektionstavla — ' + title}
      style="height: {frameHeight}px"
    ></iframe>
    {#if warnings.length}
      <ul class="warnings">
        {#each warnings as w}<li>{w}</li>{/each}
      </ul>
    {/if}
</figure>

<style>
  .preview { margin: 32px 0 0; }
  /* Göms visuellt men lämnas i DOM:en så tavelmotorn hinner ladda i förväg.
     display:none skulle spara mer, men iframen laddar sitt dokument ändå och
     vi behöver inte layouten förrän den visas. */
  .preview.idle {
    display: none;
  }
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
  .spacer { flex: 1; }
  .ghost {
    background: transparent;
    color: var(--ink);
    border: 1px solid var(--line-2);
    border-radius: 4px;
    padding: 6px 12px;
    font-family: inherit;
    font-size: inherit;
    cursor: pointer;
  }
  iframe {
    width: 100%;
    border: 1px solid var(--line);
    border-radius: 5px;
    display: block;
    background: var(--sunken);
  }
  /* Förstoringen växer kortet PÅ PLATS — iframen får aldrig flyttas i DOM:en,
     då laddas dokumentet om och tavlan töms. */
  .preview.zoomed {
    position: fixed;
    inset: 24px;
    z-index: 60;
    margin: 0;
    background: var(--canvas);
    border: 1px solid var(--line);
    border-radius: 5px;
    padding: 20px;
    overflow: auto;
    box-shadow: var(--shadow);
    transition: inset 0.28s cubic-bezier(0.2, 0.8, 0.2, 1);
  }
  .preview.zoomed iframe {
    height: calc(100vh - 136px) !important;
  }
  @media (prefers-reduced-motion: reduce) {
    .preview.zoomed { transition: none; }
  }
  /* Varningarna är hela meningar från motorn — sans, inte mono
     (DESIGN.md: mono är reserverad för små versala etiketter). */
  .warnings {
    margin: 10px 0 0;
    padding-left: 18px;
    color: var(--warn);
  }
</style>
