<script>
  // Appens topbar: ordmärke, de tre flikarna och temaväxlaren. Speglar
  // gamla appens header (app/web/static/app.js:4341-4366), omstylad till
  // designsystemet — originalets 15,5px text och 9-12px hörn ligger utanför
  // rampen.
  import { nav, setTab, toggleTheme } from './nav.svelte.js';
  // Skalet känner till transkriberingsvyn, inte tvärtom — samma riktning som
  // App.svelte redan monterar vyerna i. Brickan måste bo HÄR: den ska synas
  // även när Transkribera-panelen är hidden (App.svelte), och topbaren är den
  // enda nod som alltid ligger framme.
  import InspelningBricka from '../transkribera/InspelningBricka.svelte';

  const FLIKAR = [
    ['transkribera', 'Transkribera'],
    ['inspelningar', 'Inspelningar'],
    ['planering', 'Planering'],
  ];

  // MANUELL AKTIVERING. ARIA:s flikmönster tillåter både automatisk (pilen
  // byter flik direkt) och manuell (pilen flyttar fokus, Enter/Mellanslag
  // byter). Här måste det vara manuell: ett flikbyte kör monteringseffekter
  // som hämtar från servern (kollaHistorik i InspelningarView, katalogen i
  // Transkribera). Att svepa förbi Inspelningar på väg till Planering ska
  // inte trigga tre hämtningar.
  //
  // Samma val som Segment.svelte gör, av samma skäl.
  function tangent(e) {
    const steg =
      e.key === 'ArrowRight' ? 1 : e.key === 'ArrowLeft' ? -1 : 0;
    if (!steg && e.key !== 'Home' && e.key !== 'End') return;

    const knappar = [...e.currentTarget.parentElement.querySelectorAll('[role="tab"]')];
    const nu = knappar.indexOf(e.currentTarget);
    if (nu === -1) return;

    e.preventDefault();
    const till =
      e.key === 'Home'
        ? 0
        : e.key === 'End'
          ? knappar.length - 1
          : (nu + steg + knappar.length) % knappar.length;
    knappar[till].focus();
  }

  // Temat sätts på <html> så att app.css [data-theme="dark"] slår igenom.
  $effect(() => {
    document.documentElement.dataset.theme = nav.theme;
  });
</script>

<header class="bar">
  <span class="ordmarke">transkrib<span class="ser">era</span></span>

  <!--
    RIKTIGA FLIKAR, inte växlingsknappar. Tidigare var det här en <nav> med
    <button aria-pressed> — en skärmläsare annonserade "tryckt växlingsknapp"
    i stället för "flik 1 av 3", och gav ingen aning om hur många vyer som
    fanns eller vilken man stod i.

    Panelerna ligger i App.svelte och bär role="tabpanel" + aria-labelledby
    tillbaka hit. Att de alla är monterade samtidigt och göms med hidden är
    precis vad flikmönstret förutsätter.

    ROVING TABINDEX: bara den valda fliken är tabbstopp, resten nås med
    piltangenter. Utan det kostar det tre tabbtryck att ta sig förbi
    flikraden på väg in i innehållet.
  -->
  <div class="flikar" role="tablist" aria-label="Vy">
    {#each FLIKAR as [id, etikett]}
      <button
        type="button"
        class="flik"
        role="tab"
        id={'flik-' + id}
        aria-selected={nav.tab === id}
        aria-controls={'panel-' + id}
        tabindex={nav.tab === id ? 0 : -1}
        onclick={() => setTab(id)}
        onkeydown={tangent}
      >{etikett}</button>
    {/each}
  </div>

  <!-- Brickan bor INUTI .temaruta, inte som en egen kolumn i .bar. Det är
       .ordmarke och .temaruta som centrerar .flikar: båda är flex: 1 1 0, alltså
       två lika breda sidor. En fjärde flex: 0 0 auto-kolumn på ~170 px hade
       flyttat hela flikgruppen ~85 px åt vänster i samma ögonblick inspelningen
       startar — och tillbaka igen när den stoppas. Här växer i stället höger
       kolumn inifrån och flikarna står stilla. Brickan renderar ingenting alls
       när inget spelas in. -->
  <div class="temaruta">
    <InspelningBricka />
    <button
      type="button"
      class="tema"
      aria-label={'Växla tema — ' + (nav.theme === 'light' ? 'Mörkt' : 'Ljust')}
      title="Växla tema"
      onclick={toggleTheme}
    >{nav.theme === 'light' ? 'Mörkt' : 'Ljust'}</button>
  </div>
</header>

<style>
  .bar {
    position: sticky;
    top: 0;
    z-index: 20;
    display: flex;
    align-items: center;
    gap: 16px;
    padding: 14px 24px;
    border-bottom: 1px solid var(--line);
    background: var(--canvas);
  }
  .ordmarke {
    flex: 1 1 0;
    min-width: 0;
    font-size: 1.125rem;
    font-weight: 500;
    letter-spacing: -0.01em;
    color: var(--ink);
  }
  .ordmarke .ser {
    font-family: var(--serif);
    font-style: italic;
    font-weight: 400;
  }
  /*
    INGEN PLATTA. Den här raden var en fylld flik på ett --track-fack med
    egen ram — DESIGN.md säger uttryckligen motsatsen om navigationen:
    "the active section is marked by ink weight and the sky accent, not by a
    filled tab or heavy chrome". Den var dessutom det visuellt tyngsta
    elementet på skärmen i en app vars första designprincip är "recede,
    don't perform": det första ögat landade på var man kunde gå, inte på det
    man kommit för.

    Nu bär bläckvikten och en hårfin accentlinje markeringen. Accenten
    används här för URVAL, vilket är exakt vad One Voice Rule reserverar den
    till (åtgärder, urval, live-tillstånd).
  */
  .flikar {
    flex: 0 1 auto;
    display: inline-flex;
    gap: 26px;
  }
  .flik {
    position: relative;
    border: none;
    padding: 4px 0;
    background: transparent;
    color: var(--ink-3);
    font-family: inherit;
    font-size: inherit;
    font-weight: 500;
    white-space: nowrap;
    cursor: pointer;
  }
  .flik:hover { color: var(--ink-2); }
  .flik[aria-selected='true'] {
    color: var(--ink);
    font-weight: 600;
  }
  /* Linjen ritas med ::after i stället för border-bottom så att den inte
     flyttar baslinjen när fliken byts, och den ligger alltid framme —
     bara transparent — så att vikt- och färgbytet inte samtidigt ändrar
     radens höjd. */
  .flik::after {
    content: '';
    position: absolute;
    left: 0;
    right: 0;
    bottom: -3px;
    height: 2px;
    background: transparent;
  }
  .flik[aria-selected='true']::after { background: var(--accent); }
  .temaruta {
    flex: 1 1 0;
    display: flex;
    align-items: center;
    justify-content: flex-end;
    /* Samma 16px som .bar:s egen gap — brickan och temaväxlaren ska stå isär
       lika mycket som topbarens övriga kolumner. */
    gap: 16px;
  }
  .tema {
    flex: 0 0 auto;
    border: none;
    background: transparent;
    color: var(--ink-3);
    font-family: inherit;
    font-size: 0.72rem;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    cursor: pointer;
  }
  .tema:hover { color: var(--ink-2); }
</style>
