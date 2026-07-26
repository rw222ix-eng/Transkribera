<script>
  // "Inför nästa lektion". Speglar prepPanel (app/web/static/app.js:5186-5223).
  //
  // Gamla panelen är fylld med --accent-weak och inramad i --accent. Det följer
  // INTE med: DESIGN.md:s One Voice reserverar accenten för handlingar, val och
  // live-tillstånd — inte för att måla ett helt kort. Panelen får samma form som
  // de två andra, och accenten sparas till mikroetiketterna.
  import { insp } from './stores.svelte.js';
  import { markeraKlar } from './actions.js';
  import { datumEtikett } from '../week.js';

  const atgarder = $derived(insp.nastaLektion?.open_actions || []);
  const svarigheter = $derived(insp.nastaLektion?.difficulties || []);
  const klass = $derived(insp.nastaLektion?.group || '');
  const forraDatum = $derived(insp.nastaLektion?.last_lesson?.datum || '');
  const tomt = $derived(!atgarder.length && !svarigheter.length);

  // Samma karta som gamla appens TYP_LABEL (app.js:2098).
  const TYP = {
    kalender: 'Kalender',
    svårighet: 'Svårighet',
    åtgärd: 'Åtgärd',
    grupprum: 'Grupprum',
    material: 'Material',
    övrigt: 'Övrigt',
  };

  // typ · ref · datum, delarna som finns. Datumet är lektionens, inte
  // förfallodatumet — open_actions bär lesson_datum, inte due_date.
  const rad = (a) =>
    [TYP[a.typ] || a.typ, a.ref, datumEtikett(a.lesson_datum)].filter(Boolean).join(' · ');
</script>

<!-- null = ingen klass vald, eller hämtningen föll → ingen panel. -->
{#if insp.nastaLektion}
  <section class="panel">
    <h2 class="rubrik">
      Inför nästa lektion{#if klass}<span class="klass"> · {klass}</span>{/if}
    </h2>

    {#if tomt}
      <p class="tomt">
        Inget att bära med sig ännu — öppna åtgärder och förra lektionens
        svårigheter dyker upp här när du analyserat lektioner för den här
        klassen.
      </p>
    {/if}

    {#if atgarder.length}
      <p class="etikett">Att göra (öppna)</p>
      <ul class="lista">
        {#each atgarder as a (a.id)}
          <li class="rad">
            <button
              class="ruta"
              onclick={() => markeraKlar(a.id)}
              disabled={insp.markerar === a.id}
              aria-label="Markera klar"
              title="Markera klar"
            ></button>
            <div class="text">
              <p class="titel">{a.text || ''}</p>
              {#if rad(a)}<p class="meta">{rad(a)}</p>{/if}
            </div>
          </li>
        {/each}
      </ul>
    {/if}

    {#if svarigheter.length}
      <p class="etikett" class:avstand={atgarder.length}>
        Repetera — förra lektionens svårigheter{#if forraDatum}
          ({datumEtikett(forraDatum)}){/if}
      </p>
      <ul class="punkter">
        {#each svarigheter as d (d.id)}
          <li>
            {d.text || ''}{#if d.ref}<span class="ref"> ({d.ref})</span>{/if}
          </li>
        {/each}
      </ul>
    {/if}
  </section>
{/if}

<style>
  /* Identisk panelform som Agenda.svelte — samma tokens, samma 4px. */
  .panel {
    background: var(--surface);
    border: 1px solid var(--line);
    border-radius: 4px;
    padding: 16px 18px;
    margin-bottom: 14px;
  }
  .rubrik {
    font-size: 1.125rem;
    font-weight: 600;
    color: var(--ink);
    margin: 0;
  }
  .klass { font-weight: 400; color: var(--ink-3); }

  .tomt {
    font-size: 1.03rem;
    color: var(--ink-2);
    max-width: 52ch;
    margin: 10px 0 0;
  }

  /* Mikroetikett: den ENDA platsen i panelen där var(--mono) hör hemma. Kort,
     versal, och en etikett — inte löpande text. Accenten markerar att det är
     panelens handlingsbara sektion. */
  .etikett {
    font-family: var(--mono);
    font-size: 0.72rem;
    font-weight: 500;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: var(--accent);
    margin: 16px 0 6px;
  }
  .etikett.avstand { margin-top: 20px; }

  .lista { list-style: none; margin: 0; padding: 0; }
  .rad {
    display: flex;
    align-items: flex-start;
    gap: 10px;
    padding: 8px 0;
    border-top: 1px solid var(--line);
  }
  .rad:first-child { border-top: 0; }

  .ruta {
    flex: none;
    width: 17px;
    height: 17px;
    margin-top: 2px;
    border: 1.5px solid var(--line-2);
    border-radius: 3px;
    background: transparent;
    cursor: pointer;
    padding: 0;
  }
  .ruta:hover:not(:disabled) {
    border-color: var(--ok);
    background: color-mix(in srgb, var(--ok) 18%, transparent);
  }
  .ruta:disabled { cursor: default; opacity: 0.5; }

  .text { flex: 1; min-width: 0; }
  .titel {
    font-size: 1.03rem;
    color: var(--ink);
    margin: 0;
    overflow-wrap: anywhere;
  }
  .meta { font-size: 0.72rem; color: var(--ink-3); margin: 2px 0 0; }

  .punkter {
    list-style: disc;
    margin: 0;
    padding-left: 18px;
    font-size: 1.03rem;
    color: var(--ink);
  }
  .punkter li { margin: 3px 0; overflow-wrap: anywhere; }
  .ref { color: var(--ink-3); font-size: 0.72rem; }
</style>
