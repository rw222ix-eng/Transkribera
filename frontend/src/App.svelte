<script>
  import AppShell from './lib/shell/AppShell.svelte';
  import { nav } from './lib/shell/nav.svelte.js';
  import TranskriberaView from './lib/transkribera/TranskriberaView.svelte';
  import InspelningarView from './lib/inspelningar/InspelningarView.svelte';
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
  <InspelningarView />
</div>

<div class="pane" hidden={nav.tab !== 'planering'}>
  <PlaneringView />
  <ArkivView />
</div>

<style>
  /* Explicit — så att ingen framtida display-regel på div råkar besegra
     webbläsarens hidden. */
  .pane[hidden] { display: none; }
</style>
