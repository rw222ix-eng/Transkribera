<script>
  import AppShell from './lib/shell/AppShell.svelte';
  import { nav } from './lib/shell/nav.svelte.js';
  import TranskriberaView from './lib/transkribera/TranskriberaView.svelte';
  import PlaneringView from './lib/planering/PlaneringView.svelte';
  import ArkivView from './lib/arkiv/ArkivView.svelte';
</script>

<AppShell />

<!-- Vyerna monteras alltid och göms med hidden — de villkoras aldrig bort.
     Tavelns iframe (BoardPreview.svelte:168) måste stå monterad hela tiden;
     avmonteras den tappar en ritad tavla sitt innehåll och motorn får laddas
     om. Samma skäl som iframens egen .idle-regel. -->
<div class="pane" hidden={nav.tab !== 'transkribera'}>
  <TranskriberaView />
</div>

<div class="pane" hidden={nav.tab !== 'inspelningar'}>
  <section class="kommer">
    <p class="eyebrow">INSPELNINGAR</p>
    <p>Den här vyn migreras just nu. Tills den är klar finns den i den gamla appen.</p>
  </section>
</div>

<div class="pane" hidden={nav.tab !== 'planering'}>
  <PlaneringView />
  <ArkivView />
</div>

<style>
  /* Explicit — så att ingen framtida display-regel på div råkar besegra
     webbläsarens hidden. */
  .pane[hidden] { display: none; }
  .kommer {
    max-width: 860px;
    margin: 0 auto;
    padding: 56px 24px 96px;
    color: var(--ink-2);
  }
  .eyebrow {
    font-family: var(--mono);
    font-size: 0.72rem;
    font-weight: 500;
    letter-spacing: 0.08em;
    color: var(--ink-3);
    margin: 0 0 14px;
  }
</style>
