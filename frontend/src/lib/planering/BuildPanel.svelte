<script>
  import { plan } from './stores.svelte.js';
  import { prov } from '../prov/stores.svelte.js';
  import { getJSON } from '../api.js';
  import Segment from '../Segment.svelte';

  let { onGenerate = () => {} } = $props();

  let courses = $state([]);
  let groups = $state([]);
  let loadError = $state('');

  // Tavlan och prov/arbetsblad kör var sin SSE-ström (plan.phase resp.
  // prov.phase) — "running" måste läsa rätt store beroende på typ, annars
  // visar CTA:n aldrig "Skriver …" under en provgenerering.
  const running = $derived(plan.typ === 'tavla' ? plan.phase === 'running' : prov.phase === 'running');
  // Innehållsvalet är valfritt för prov/arbetsblad, precis som i gamla appen
  // (exCanStart: !!st.byggCourseId, app.js:3605) — utan val väljer modellen
  // fritt ur kursens innehåll (se ContentPickers "Inget valt"-text). Att
  // skriva ett prov över en hel kurs utan att peka ut enskilda punkter är
  // ett riktigt arbetsflöde, inte ett ofullständigt formulär.
  const canGenerate = $derived(
    !running &&
      (plan.typ === 'tavla' ? plan.moment.trim().length > 0 : plan.courseId !== ''),
  );
  const typLabel = $derived(
    plan.typ === 'tavla' ? 'tavlan' : plan.typ === 'arbetsblad' ? 'arbetsbladet' : 'provet',
  );

  $effect(() => {
    // allSettled, inte all: faller en av endpointerna ska den andra ändå fylla
    // sitt fält — annars försvinner kurschipsen för att klasslistan strular.
    Promise.allSettled([getJSON('/api/courses'), getJSON('/api/groups')]).then(([c, g]) => {
      if (c.status === 'fulfilled') courses = c.value?.courses ?? c.value ?? [];
      if (g.status === 'fulfilled') groups = g.value?.groups ?? g.value ?? [];
      const failed = [];
      if (c.status === 'rejected') failed.push('kurser');
      if (g.status === 'rejected') failed.push('klasser');
      loadError = failed.length ? 'Kunde inte hämta ' + failed.join(' och ') + '.' : '';
    });
  });

  // pickCourse() är borta med chipsen. En <select> med bind:value skriver
  // plan.courseId direkt, och "Ingen kurs" bär tomvalet som chipsens
  // toggla-av-gren stod för.
</script>

<div class="panel">
  <div class="row">
    <span class="label">Skriv</span>
    <Segment
      alternativ={[['tavla', 'Tavla'], ['prov', 'Prov'], ['arbetsblad', 'Arbetsblad']]}
      etikett="Dokumenttyp"
      arVald={(v) => plan.typ === v}
      valj={(v) => (plan.typ = v)}
    />
  </div>

  {#if plan.typ === 'tavla'}
    <div class="row">
      <span class="label">Moment</span>
      <input
        class="field"
        aria-label="Moment"
        placeholder="Moment — t.ex. derivatans definition"
        bind:value={plan.moment}
        onkeydown={(e) => { if (e.key === 'Enter' && canGenerate) onGenerate(); }}
      />
    </div>
  {/if}

  {#if groups.length}
    <div class="row">
      <span class="label">Klass</span>
      <select class="field" aria-label="Klass" bind:value={plan.groupId}>
        <option value="">Ingen klass</option>
        {#each groups as g (g.id)}
          <option value={String(g.id)}>{g.namn ?? g.name}</option>
        {/each}
      </select>
    </div>
  {/if}

  {#if courses.length}
    <div class="row">
      <span class="label">Kurs</span>
      <!--
        <select>, inte chips. Kurslistan är lärarens EGNA kurser och växer med
        tjänsten — på den här maskinen ritade den tio chips över tre rader,
        alltså tio synliga val vid ETT beslut. Arbetsminnet rymmer fyra.

        Valet av kontroll är inte uppfunnet för tillfället: Klass-raden tre
        rader ovanför är redan en <select class="field">, och Inspelningars
        Filterrad.svelte väljer klass, kurs och månad på exakt samma sätt. Ett
        chipsfält bredvid en select för samma sorts val var inkonsekvensen,
        inte antalet i sig.

        Tomvalet ersätter chipsens toggla-av-beteende (pickCourse nollställde
        vid klick på det redan valda). En select kan inte "klickas av", så
        vägen tillbaka till inget kursval måste finnas som ett alternativ.
      -->
      <select class="field" aria-label="Kurs" bind:value={plan.courseId}>
        <option value="">Ingen kurs</option>
        {#each courses as c (c.id)}
          <option value={String(c.id)}>{c.namn ?? c.name}</option>
        {/each}
      </select>
    </div>
  {/if}

  <div class="row">
    <span class="label">När</span>
    <input class="field narrow" type="date" aria-label="Datum" bind:value={plan.datum} />
    {#if plan.typ === 'tavla'}
      <!-- Starttid ingår aldrig i prov-/arbetsbladspayloaden (prov/actions.js:
           generateExam) — gamla appen döljer fältet av samma skäl, app.js:5853-5858. -->
      <input class="field narrow" type="time" aria-label="Starttid" bind:value={plan.starttid} />
    {/if}
  </div>

  {#if loadError}
    <p class="note error">{loadError}</p>
  {/if}

  <div class="cta">
    <span class="note">
      {#if canGenerate}
        Klart att skriva.
      {:else if plan.typ === 'tavla'}
        Beskriv momentet ovan så kan tavlan skrivas.
      {:else if !plan.courseId}
        Välj kurs ovan så kan {typLabel} skrivas.
      {/if}
    </span>
    <button class="primary" disabled={!canGenerate} onclick={() => onGenerate()}>
      {#if running}
        Skriver …
      {:else if plan.typ === 'tavla'}
        Skriv tavlan
      {:else if plan.typ === 'arbetsblad'}
        Skriv arbetsbladet
      {:else}
        Skriv provet
      {/if}
    </button>
  </div>
</div>

<style>
  .panel {
    display: flex;
    flex-direction: column;
    gap: 14px;
    margin-top: 32px;
  }
  .row {
    display: flex;
    align-items: center;
    gap: 14px;
    flex-wrap: wrap;
  }
  /* Typväljarens form bor i Segment.svelte, kursens i den vanliga .field. */
  .label {
    flex: 0 0 74px;
    font-family: var(--mono);
    font-size: 0.72rem;
    font-weight: 500;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: var(--ink-3);
  }
  .field {
    flex: 1;
    min-width: 240px;
    background: var(--surface);
    border: 1px solid var(--line);
    border-radius: 4px;
    padding: 12px 14px;
    font-family: inherit;
    font-size: inherit;
    color: var(--ink);
  }
  .field.narrow { flex: 0 0 auto; min-width: 0; padding: 8px 10px; }
  .field:focus-visible { border-color: var(--accent); }
  .cta {
    display: flex;
    align-items: center;
    gap: 14px;
    flex-wrap: wrap;
    padding-top: 14px;
    border-top: 1px solid var(--line);
  }
  .note { flex: 1; color: var(--ink-3); margin: 0; }
  .note.error { color: var(--bad); flex: none; }
  .primary {
    background: var(--btn-bg);
    color: var(--btn-fg);
    border: none;
    border-radius: 4px;
    padding: 12px 22px;
    font-family: inherit;
    font-size: inherit;
    font-weight: 500;
    cursor: pointer;
  }
  .primary:disabled { opacity: 0.55; cursor: default; }
</style>
