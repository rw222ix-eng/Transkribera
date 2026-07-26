<script>
  // Redigering av en lektions uppgifter. Speglar renameOpen-modalen i gamla
  // appen (app/web/static/app.js:5475-5498) funktionellt, men INGENTING av dess
  // form följer med: den är ren inline-CSS med 9-14px hörn och 11,5-18px
  // teckenstorlekar. Här gäller designsystemet — hörn 4px, typrampen, och bara
  // var(--…)-tokens.
  //
  // VIKTIGT om vad sparandet faktiskt gör: PATCH /api/lessons/{id} skickar
  // group_name/course_name genom db.get_or_create_group/get_or_create_course
  // (server.py:972-979), så fritext i Klass- och Kursfälten SKAPAR klassen
  // eller kursen. Datalisterna är därför förslag, inte ett val ur en sluten
  // mängd — och det är just därför sparaLektion() hämtar om
  // organisationslistorna, så en nyskapad klass syns i filtret direkt.
  import { insp } from './stores.svelte.js';
  import { avbrytRedigering, sparaLektion } from './actions.js';
  import { nav } from '../shell/nav.svelte.js';

  let dialog = $state(null);

  // Vilken lektion det gäller. startaRedigering sparar MEDVETET inte namnet i
  // insp.edits — det skickas aldrig till servern — men läraren behöver ändå se
  // vilket kort hon öppnade när flera ser lika ut.
  //
  // FRYST vid öppning, inte $derived ur insp.editId: härleds det reaktivt byter
  // rubriken till "(namnlös)" i samma flush som stängningen, alltså medan
  // dialogen fortfarande är öppen.
  let namn = $state('(namnlös)');

  // showModal()/close() speglar insp.editId.
  //
  // Ett NATIVE <dialog> valdes framför en egen fälla i tangent(): webbläsaren
  // ger då fokusfälla, Escape, backdrop och top-layer — allt det som annars är
  // egen kod som kan glida isär. Bakgrunden blir dessutom inert, vilket är den
  // konkreta buggen som fanns här: Tab kunde vandra ut ur rutan och landa på
  // ett korts Radera-knapp, som skärmläsaren påstår inte finns (aria-modal),
  // och Enter monterade bekräftelseblocket BAKOM skärmen — dit
  // InspelningarViews $effect sedan flyttade fokus.
  //
  // Effekten kräver att komponenten är monterad även när editId är null; se
  // kommentaren vid <RedigeraLektion /> i InspelningarView.svelte.
  //
  // nav.tab ÄR MED I VILLKORET, inte bara insp.editId. App.svelte göms per flik
  // med hidden (.pane[hidden] { display: none }), och en förfader med
  // display:none gör att dialogen inte RITAS — men den förblir `open`, och
  // showModal() håller då fortfarande hela dokumentet inert. Läraren får en app
  // som inte svarar på någonting, utan något på skärmen som förklarar varför.
  // Det går inte att nå via UI:t idag (flikknapparna är inerta medan dialogen
  // är öppen), men ett programmatiskt nav.tab-byte gör det — och mönstret ärvs
  // av B2-B5. Enda säkra invarianten är därför: dialogen är öppen ENBART när
  // Inspelningar-fliken är den synliga.
  //
  // close() ger onclose -> avbrytRedigering, så storen nollställs och oskrivna
  // ändringar förkastas vid flikbytet. Det är avsiktligt: en osynlig dialog som
  // ligger kvar och blockerar dokumentet är värre än en förlorad halvskriven
  // klassbeteckning, och läraren bläddrade själv bort.
  $effect(() => {
    if (!dialog) return;
    if (insp.editId !== null && nav.tab === 'inspelningar') {
      namn = insp.lessons.find((l) => l.id === insp.editId)?.name || '(namnlös)';
      if (!dialog.open) {
        dialog.showModal();
        // Rutan själv, inte första fältet: då läser skärmläsaren aria-label
        // ("Redigera lektionsuppgifter") innan fälten, och första Tab landar
        // på Klass. showModal() hade annars fokuserat Klass direkt.
        dialog.focus();
      }
    } else if (dialog.open) {
      dialog.close();
    }
  });
</script>

<!-- Bakgrunden är MEDVETET inte klickbar. En stängning på backdrop-klick är en
     destruktiv genväg — allt oskrivet försvinner vid en felklick. Escape och
     Avbryt är vägarna ut.

     onclose nollställer storen. Escape stängs av WEBBLÄSAREN, inte av oss, så
     utan den raden vore dialogen stängd medan insp.editId fortfarande pekade på
     lektionen — och en ny öppning av SAMMA kort hade inte ändrat editId och
     alltså inte utlöst effekten ovan. Dialogen hade aldrig gått att öppna igen.

     Varken role="dialog" eller aria-modal="true" står kvar: showModal() ger
     båda från webbläsaren, och en utskriven roll på ett element som redan har
     den fälls av svelte-checks a11y-regler. -->
<dialog
  class="ruta"
  aria-label="Redigera lektionsuppgifter"
  tabindex="-1"
  bind:this={dialog}
  onclose={avbrytRedigering}
>
  <p class="eyebrow">REDIGERA UPPGIFTER</p>
  <h2 class="namn">{namn}</h2>

  <!-- Datalisterna är förslag ur insp.groups/insp.courses. Läraren kan lika
       gärna skriva ett nytt värde — API:et skapar det då. -->
  <datalist id="insp-dl-klass">
    {#each insp.groups as g (g.id)}<option value={g.namn}></option>{/each}
  </datalist>
  <datalist id="insp-dl-kurs">
    {#each insp.courses as c (c.id)}<option value={c.namn}></option>{/each}
  </datalist>

  <!-- <form> så att Enter i ett fält sparar. preventDefault eftersom
       sparandet går via fetch, inte via en riktig formulärpost.

       method="dialog" används MEDVETET inte: det hade stängt dialogen innan
       fetch:en ens skickats, och ett misslyckat sparande hade då försvunnit
       tillsammans med rutan. -->
  <form
    class="falt"
    onsubmit={(e) => {
      e.preventDefault();
      sparaLektion();
    }}
  >
    <label>
      <span class="etikett">Klass</span>
      <!-- bind:value på store-EGENSKAPEN, inte på en lokal kopia. Det är
           mutationen runes-reglerna kräver, och PR 6 bekräftade att den
           skriver igenom. -->
      <input list="insp-dl-klass" bind:value={insp.edits.group} placeholder="t.ex. NA21" />
    </label>
    <label>
      <span class="etikett">Kurs</span>
      <input list="insp-dl-kurs" bind:value={insp.edits.course} placeholder="t.ex. Matematik 2b" />
    </label>
    <label>
      <span class="etikett">Sal</span>
      <input bind:value={insp.edits.sal} placeholder="t.ex. B214" />
    </label>
    <label>
      <span class="etikett">Datum</span>
      <input type="date" bind:value={insp.edits.datum} />
    </label>

    <!--
      SPARFELET, i två noder: en klippt live-region och en synlig kopia.

      EN ANNONSERANDE NOD PER RENDERINGSKONTEXT — principen B2-B5 ärver.
      showModal() gör resten av dokumentet INERT, och inert innehåll är borta ur
      tillgänglighetsträdet. Vyns p.fel-sr[role="status"]
      (InspelningarView.svelte:87) kan alltså inte annonsera medan dialogen är
      öppen, och den synliga kopian här är aria-hidden och finns inte i trädet
      heller. Utan regionen nedan finns INGEN väg fram till texten alls: en <p>
      går inte att tabba till, och aria-hidden gömmer den även för läsmarkören.
      Sparfelet blir då osynligt för en skärmläsaranvändare — precis det svalda
      fel som modalen fick sin felrad för att förhindra.

      De två regionerna kan aldrig konkurrera, och det är villkoret för att den
      här noden inte bryter antalsregeln: är dialogen öppen är vyn inert, är den
      stängd är dialogen display:none och alltså själv borta ur trädet. Antalet
      annonserande noder i den kontext som faktiskt syns är fortfarande ett.

      Regionen får INTE :empty { display: none } — display:none tar bort noden
      ur trädet, och då kan role="status" inte längre annonsera mutationen. Det
      mönstret har underkänts fyra gånger i den här migrationen. Den ligger
      permanent i markupen av samma skäl: en region som monteras in samtidigt
      som sin text annonseras inte pålitligt.

      Den SYNLIGA kopian är aria-hidden och utan egen roll, precis som kopian i
      InspelningarView.svelte. :empty-regeln hör hemma på den — på en kopia,
      aldrig på en live-region.
    -->
    <p class="fel-sr" role="status">{insp.fel}</p>
    <p class="fel" aria-hidden="true">{insp.fel}</p>

    <!-- Spara är avstängd medan PATCH:en är i luften; två klick hade annars
         skickat två PATCH. Avbryt lämnas PÅ med flit — ångrar sig läraren mitt
         i ett långsamt sparande ska hon komma ur rutan, och sparaLektion vaktar
         redan att den inte stänger fel dialog när svaret landar. -->
    <div class="knappar">
      <button type="button" class="ghost" onclick={avbrytRedigering}>Avbryt</button>
      <button type="submit" class="primar" disabled={insp.sparar}>Spara</button>
    </div>
  </form>
</dialog>

<style>
  /* Ingen egen skärm och inget z-index längre: showModal() lyfter dialogen till
     top-layer, som ligger över allt annat oavsett stackningskontext, och
     centreringen kommer ur webbläsarens egna `position: fixed; inset: 0;
     margin: auto` för <dialog>. Kvar här är bara rutans form.

     color sätts uttryckligen — webbläsarens <dialog>-regel sätter
     `color: CanvasText`, som bryter arvet från body. */
  .ruta {
    width: min(94vw, 460px);
    max-height: 90vh;
    overflow: auto;
    background: var(--canvas);
    color: var(--ink);
    border: 1px solid var(--line);
    border-radius: 4px;
    box-shadow: var(--shadow);
    padding: 20px 22px;
  }
  /* Dimmningen, med samma token och samma 42 % som den borttagna .bakgrund. */
  .ruta::backdrop { background: color-mix(in srgb, var(--ink) 42%, transparent); }
  .ruta:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
  /* Kort versal mikroetikett — den enda sorts text som bär var(--mono). */
  .eyebrow {
    font-family: var(--mono);
    font-size: 0.72rem;
    font-weight: 500;
    letter-spacing: 0.08em;
    color: var(--ink-3);
    margin: 0 0 8px;
  }
  .namn {
    font-family: var(--sans);
    font-size: 1.03rem;
    font-weight: 600;
    line-height: 1.3;
    color: var(--ink);
    margin: 0 0 16px;
    overflow-wrap: anywhere;
  }
  .falt {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 10px;
  }
  label {
    display: flex;
    flex-direction: column;
    gap: 5px;
    min-width: 0;
  }
  .etikett {
    font-size: 0.72rem;
    color: var(--ink-3);
  }
  input {
    background: var(--surface);
    border: 1px solid var(--line);
    border-radius: 3px;
    padding: 8px 10px;
    font-family: inherit;
    font-size: 1.03rem;
    color: var(--ink);
    min-width: 0;
    width: 100%;
    box-sizing: border-box;
  }
  input:focus-visible { border-color: var(--accent); }
  /* Klippande teknik, identisk med .fel-sr i InspelningarView.svelte:194 och
     TranskriberaView.svelte:197: noden finns kvar i tillgänglighetsträdet men
     upptar ingen synlig plats. position:absolute tar den dessutom ur
     rutnätsflödet, så den lägger ingen rad i .falt. INGEN :empty-regel — se
     kommentaren vid noden. */
  .fel-sr {
    position: absolute;
    width: 1px;
    height: 1px;
    overflow: hidden;
    clip-path: inset(50%);
    white-space: nowrap;
  }
  /* Identisk med .fel i InspelningarView.svelte:210 så de två kopiorna av
     insp.fel ser likadana ut var läraren än råkar se dem. */
  .fel {
    grid-column: 1 / -1;
    color: var(--bad);
    margin: 8px 0 0;
    overflow-wrap: anywhere;
  }
  .fel:empty { display: none; }
  .knappar {
    grid-column: 1 / -1;
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    justify-content: flex-end;
    margin-top: 6px;
  }
  /* Båda identiska med Korning.svelte:266-293 — samma hörn, samma padding,
     samma font-size: inherit. */
  .ghost {
    background: transparent;
    color: var(--ink);
    border: 1px solid var(--line-2);
    border-radius: 4px;
    padding: 9px 18px;
    font-family: inherit;
    font-size: inherit;
    cursor: pointer;
  }
  .primar {
    background: var(--btn-bg);
    color: var(--btn-fg);
    border: none;
    border-radius: 4px;
    padding: 10px 20px;
    font-family: inherit;
    font-size: inherit;
    font-weight: 500;
    cursor: pointer;
  }
  /* Väntläget ska SYNAS, annars ser en avstängd knapp bara trasig ut. */
  .primar:disabled { opacity: 0.55; cursor: default; }

  /* En smal ruta får inte tvinga två kolumner. */
  @media (max-width: 420px) {
    .falt { grid-template-columns: 1fr; }
  }
</style>
