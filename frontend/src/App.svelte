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
  import { chatt } from './lib/lektionschatt/stores.svelte.js';
  import { skickaFraga } from './lib/lektionschatt/actions.js';
  import { sok } from './lib/inspelningar/sok.svelte.js';
  import { skickaKalenderSvar } from './lib/inspelningar/sokActions.js';
</script>

<AppShell />

<!-- Vyerna monteras alltid och göms med hidden — de villkoras aldrig bort.
     Tavelns iframe (BoardPreview.svelte:168) måste stå monterad hela tiden;
     avmonteras den tappar en ritad tavla sitt innehåll och motorn får laddas
     om. Samma skäl som iframens egen .idle-regel.

     role="tabpanel" + aria-labelledby knyter panelen till sin flik i
     AppShell.svelte, som sedan flikraden blev en riktig tablist. id:na måste
     matcha AppShell:s aria-controls respektive id på formen panel-<tab> /
     flik-<tab> — ändras den ena måste den andra följa med.

     Att alla tre paneler ligger monterade och göms med hidden är inte en
     avvikelse från flikmönstret utan precis vad det förutsätter: en dold
     tabpanel ska vara hidden, inte avmonterad. -->
<div
  class="pane"
  id="panel-transkribera"
  role="tabpanel"
  aria-labelledby="flik-transkribera"
  hidden={nav.tab !== 'transkribera'}
>
  <TranskriberaView />
</div>

<div
  class="pane"
  id="panel-inspelningar"
  role="tabpanel"
  aria-labelledby="flik-inspelningar"
  hidden={nav.tab !== 'inspelningar'}
>
  <InspelningarView />
</div>

<div
  class="pane"
  id="panel-planering"
  role="tabpanel"
  aria-labelledby="flik-planering"
  hidden={nav.tab !== 'planering'}
>
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

<!-- Kalenderns tre modaler (frågekort, anteckning, Google-koppling) hör till
     BÅDA värdarna (lektionschatten och arkivsvaret i Inspelningar-fliken),
     inte inuti LektionschattModal.svelte eller InspelningarView.svelte:
     nested <dialog>-element ärver sin förälders display — en förälder som
     är display:none (dialog:not([open])) eller [hidden] gör att ett barn
     aldrig ritas ens om barnet själv har showModal() anropat på sig. Som
     toppnivå-syskon lägger showModal() dem i top-layer oberoende av vilken
     flik eller modal som råkar vara öppen, precis som TranskriptModal ovan
     — därför behövs ingen flikgrind (jfr nav.tab-kollen B:s motsvarande
     dialoger hade).

     FragekortModal MONTERAS TVÅ GÅNGER, en per värdnyckel: kal.fragor är
     ETT delat fält (se kalender/stores.svelte.js) med bara EN ägare åt
     gången, så de två instanserna konkurrerar aldrig om samma dialog.
     AnteckningModal och GoogleAnslutModal tar inga värd-props — den förra
     läser värden ur kal.anteckningOppen själv, den senare är inte
     värdbunden alls (ett Google-konto delas av båda). -->
<FragekortModal vardnyckel="lektion" onSkicka={skickaFraga} skickar={chatt.skickar} />
<FragekortModal vardnyckel="arkiv" onSkicka={skickaKalenderSvar} skickar={sok.fragar || sok.foljdSkriver} />
<AnteckningModal />
<GoogleAnslutModal />

<style>
  /* Explicit — så att ingen framtida display-regel på div råkar besegra
     webbläsarens hidden. */
  .pane[hidden] { display: none; }
</style>
