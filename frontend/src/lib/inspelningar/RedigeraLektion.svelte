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

  let ruta = $state(null);

  // Fokus in i dialogen när den öppnas. Rutan själv, inte första fältet — då
  // läser skärmläsaren aria-label ("Redigera lektionsuppgifter") innan
  // fälten, och första Tab landar på Klass.
  $effect(() => {
    ruta?.focus();
  });

  // Vilken lektion det gäller. startaRedigering sparar MEDVETET inte namnet i
  // insp.edits — det skickas aldrig till servern — men läraren behöver ändå se
  // vilket kort hon öppnade när flera ser lika ut.
  const namn = $derived(
    insp.lessons.find((l) => l.id === insp.editId)?.name || '(namnlös)',
  );

  function tangent(e) {
    if (e.key === 'Escape') {
      e.preventDefault();
      avbrytRedigering();
    }
  }
</script>

<svelte:window onkeydown={tangent} />

<!-- Bakgrunden är MEDVETET inte klickbar. Ett onclick på en <div> utan roll
     ger både a11y-varningar och en destruktiv genväg (allt oskrivet försvinner
     vid en felklick). Escape och Avbryt är vägarna ut. -->
<div class="bakgrund">
  <div
    class="ruta"
    role="dialog"
    aria-modal="true"
    aria-label="Redigera lektionsuppgifter"
    tabindex="-1"
    bind:this={ruta}
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
         sparandet går via fetch, inte via en riktig formulärpost. -->
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

      <div class="knappar">
        <button type="button" class="ghost" onclick={avbrytRedigering}>Avbryt</button>
        <button type="submit" class="primar">Spara</button>
      </div>
    </form>
  </div>
</div>

<style>
  .bakgrund {
    position: fixed;
    inset: 0;
    z-index: 130;
    background: color-mix(in srgb, var(--ink) 42%, transparent);
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 24px;
  }
  .ruta {
    width: min(94vw, 460px);
    max-height: 90vh;
    overflow: auto;
    background: var(--canvas);
    border: 1px solid var(--line);
    border-radius: 4px;
    box-shadow: var(--shadow);
    padding: 20px 22px;
  }
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

  /* En smal ruta får inte tvinga två kolumner. */
  @media (max-width: 420px) {
    .falt { grid-template-columns: 1fr; }
  }
</style>
