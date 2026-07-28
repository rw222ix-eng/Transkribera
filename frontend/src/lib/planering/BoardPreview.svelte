<script>
  import { plan } from './stores.svelte.js';
  import { parsePartialBoard, countSections } from './boardStream.js';
  import { onToken } from './actions.js';
  import { postJSON } from '../api.js';

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

  // PNG-exportens eget kvittotillstånd. INTE i plan (stores.svelte.js) — det
  // gäller bara den här komponenten, precis som warnings/frameHeight ovan.
  let exporting = $state(false);
  let exportMsg = $state('');
  let exportFailed = $state(false);

  function print() {
    frame?.contentWindow?.WBHost?.print();
  }

  /**
   * "Spara som PNG". Speglar wbExportPng, app.js:819-868, i samma ordning:
   * File System Access-dialogen FÖRST (om webbläsaren har den), servern som
   * fallback. Dialogen öppnas SYNKRONT i klickgesten, innan den långsamma
   * WBHost.exportPng(2) — annars nekar webbläsaren den (samma skäl som
   * gamla appens kommentar, app.js:823-824).
   *
   * Motorn kan skriva DIREKT till disk via File System Access — servern
   * (POST /api/planning/export) behövs bara som fallback för webbläsare utan
   * den API:n, och sparar då under Transkriberingar/<lektion>/planering/
   * (routes_planning.py).
   */
  async function exportPng() {
    const win = frame?.contentWindow;
    if (!win?.WBHost || exporting) return;

    // File System Access API — inte i TypeScripts DOM-lib än. Samma
    // /** @type {any} */-mönster som window.pywebview i
    // frontend/src/lib/transkribera/actions.js (openPicker).
    const picker = /** @type {any} */ (window).showSaveFilePicker;
    if (picker) {
      const namn = (title || 'tavla').replace(/[\\/:*?"<>|]/g, '-') + '.png';
      let handle;
      try {
        handle = await picker({
          suggestedName: namn,
          types: [{ description: 'PNG-bild', accept: { 'image/png': ['.png'] } }],
        });
      } catch (e) {
        if (e?.name === 'AbortError') return; // läraren avbröt dialogen — inget fel
        exportFailed = true;
        exportMsg = 'Kunde inte spara PNG: ' + (e?.message || e);
        return;
      }
      exporting = true;
      exportMsg = '';
      exportFailed = false;
      try {
        const dataUrl = await win.WBHost.exportPng(2);
        const blob = await (await fetch(dataUrl)).blob();
        const writable = await handle.createWritable();
        await writable.write(blob);
        await writable.close();
        exportMsg = 'PNG sparad: ' + handle.name;
      } catch (e) {
        exportFailed = true;
        exportMsg = 'Kunde inte spara PNG: ' + (e?.message || e);
      } finally {
        exporting = false;
      }
      return;
    }

    // Serverfallbacken (äldre motor utan File System Access API).
    exporting = true;
    exportMsg = '';
    exportFailed = false;
    try {
      const dataUrl = await win.WBHost.exportPng(2);
      const res = await postJSON('/api/planning/export', { title, png: dataUrl });
      exportMsg = 'PNG sparad: ' + res.path;
    } catch (e) {
      exportFailed = true;
      exportMsg = 'Kunde inte spara PNG: ' + (e?.message || e);
    } finally {
      exporting = false;
    }
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
<figure class={['preview', { zoomed, idle: plan.typ !== 'tavla' || (!plan.board && plan.phase !== 'running') }]}>
    <figcaption class="cap">
      <span class="label">Förhandsvisning</span>
      <span class="title">{title}</span>
      <span class="spacer"></span>
      <button class="ghost" onclick={print}>Skriv ut</button>
      <button class="ghost" onclick={toggleZoom}>
        {zoomed ? 'Stäng' : 'Förstora'}
      </button>
      <button class="ghost" onclick={exportPng} disabled={exporting}>
        {exporting ? 'Sparar …' : 'Spara som PNG'}
      </button>
    </figcaption>
    <!--
      Exportens live-region. PERMANENT och bara visuellt klippt — aldrig
      {#if}-grindad och aldrig display:none (CLAUDE.md: en {#if}-grindad
      role="status" annonseras inte pålitligt eftersom noden monteras in
      samtidigt som sin text). Klipptekniken är identisk med .fel-sr i
      InspelningarView.svelte/TranskriberaView.svelte — samma teknik, ny plats.
      Den delar figurens .idle-gömning med resten av verktygsraden, vilket är
      rätt: finns ingen tavla finns inget att exportera och inget att annonsera,
      exakt som en dold flik inte annonserar (App.svelte).
    -->
    <p class="exportmsg-sr" role="status">{exportMsg}</p>
    <iframe
      bind:this={frame}
      onload={onLoad}
      src="/static/whiteboard/board.html"
      title={'Lektionstavla — ' + title}
      style="height: {frameHeight}px"
    ></iframe>
    <!-- SYNLIG kopia av live-regionen ovan, aria-hidden och utan egen roll —
         bara live-regionen ska annonseras. :empty döljer den utan att
         villkora bort monteringen (samma :empty-mönster som .fel i
         InspelningarView.svelte). -->
    <p class={['exportmsg', { fel: exportFailed }]} aria-hidden="true">{exportMsg}</p>
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
  /* Väntläget ska SYNAS, annars ser en avstängd knapp bara trasig ut. Samma
     regel som InspelningarView.svelte:585 (Radera under en pågående DELETE). */
  .ghost:disabled { opacity: 0.55; cursor: default; }
  /* Klippande teknik — noden finns kvar i tillgänglighetsträdet men upptar
     ingen synlig plats, till skillnad från display:none. Duplicerad från
     InspelningarView.svelte (.fel-sr) och TranskriberaView.svelte, källan
     till mönstret. */
  .exportmsg-sr {
    position: absolute;
    width: 1px;
    height: 1px;
    overflow: hidden;
    clip-path: inset(50%);
    white-space: nowrap;
  }
  /* Kvittotext, inte en mikroetikett — 0.72rem/--mono är reserverat för korta
     versala etiketter (DESIGN.md), och den här raden är en hel mening.
     font-size: inherit håller den i den slutna typrampen. */
  .exportmsg { margin: 8px 0 0; color: var(--ink-3); }
  .exportmsg:empty { display: none; }
  .exportmsg.fel { color: var(--bad); }
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
