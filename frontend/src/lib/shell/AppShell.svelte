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

  // Temat sätts på <html> så att app.css [data-theme="dark"] slår igenom.
  $effect(() => {
    document.documentElement.dataset.theme = nav.theme;
  });
</script>

<header class="bar">
  <span class="ordmarke">transkrib<span class="ser">era</span></span>

  <nav class="flikar" aria-label="Vy">
    {#each FLIKAR as [id, etikett]}
      <button
        type="button"
        class="flik"
        aria-pressed={nav.tab === id}
        onclick={() => setTab(id)}
      >{etikett}</button>
    {/each}
  </nav>

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
  .flikar {
    flex: 0 1 auto;
    display: inline-flex;
    gap: 3px;
    padding: 3px;
    background: var(--track);
    border: 1px solid var(--line);
    border-radius: 5px;
  }
  .flik {
    border: none;
    border-radius: 3px;
    padding: 7px 14px;
    background: transparent;
    color: var(--ink-2);
    font-family: inherit;
    font-size: inherit;
    font-weight: 500;
    white-space: nowrap;
    cursor: pointer;
  }
  .flik[aria-pressed='true'] {
    background: var(--surface);
    color: var(--ink);
  }
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
