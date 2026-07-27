<script>
  import AppShell from './lib/shell/AppShell.svelte';
  import { nav } from './lib/shell/nav.svelte.js';
  import TranskriberaView from './lib/transkribera/TranskriberaView.svelte';
  import InspelningarView from './lib/inspelningar/InspelningarView.svelte';
  import PlaneringView from './lib/planering/PlaneringView.svelte';
  import ArkivView from './lib/arkiv/ArkivView.svelte';
  import TranskriptModal from './lib/transkript/TranskriptModal.svelte';
  import LektionschattModal from './lib/lektionschatt/LektionschattModal.svelte';
  import FragekortModal from './lib/kalender/FragekortModal.svelte';
  import AnteckningModal from './lib/kalender/AnteckningModal.svelte';
  import GoogleAnslutModal from './lib/kalender/GoogleAnslutModal.svelte';
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

<!-- Transkriptvyn monteras EN gång, utanför flikpanelerna: den delas av
     Inspelningar och Transkribera, och en <dialog> i en hidden panel ritas
     inte men blockerar dokumentet. Utanför panelerna finns inte problemet. -->
<TranskriptModal />

<!-- Lektionschatten monteras på samma nivå och av samma skäl. Ordningen i
     DOM:en styr ingenting: showModal() lyfter båda till top-layer, som
     staplar dem i ÖPPNINGSORDNING — så transkriptvyn lägger sig ovanpå
     chatten när den öppnas därifrån, och chatten finns kvar under. -->
<LektionschattModal />

<!-- Kalenderns tre modaler (frågekort, anteckning, Google-koppling) hör
     till lektionschatten men monteras på SAMMA nivå som den, inte inuti
     LektionschattModal.svelte: nested <dialog>-element ärver sin förälders
     display — en förälder som är display:none (dialog:not([open])) gör att
     ett barn aldrig ritas ens om barnet själv har showModal() anropat på
     sig. Som toppnivå-syskon lägger showModal() dem i top-layer oberoende
     av lektionschattens DOM-läge, precis som TranskriptModal ovan. -->
<FragekortModal />
<AnteckningModal />
<GoogleAnslutModal />

<style>
  /* Explicit — så att ingen framtida display-regel på div råkar besegra
     webbläsarens hidden. */
  .pane[hidden] { display: none; }
</style>
