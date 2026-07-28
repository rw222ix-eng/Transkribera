<script>
  // Agendan: daterade insikter tvärs alla klasser. Speglar agendaPanel
  // (app/web/static/app.js:5000-5030), omstylad till designsystemet — gamla
  // panelen är inline-CSS med 16px hörn, --shadow-sm och en 📅 i rubriken.
  import { insp } from './stores.svelte.js';
  import { vaxlaAgenda, markeraKlar, exporteraIcs } from './actions.js';
  import { datumEtikett } from '../week.js';

  const poster = $derived(insp.agenda || []);

  // RÄKNAREN filtrerar, LISTAN gör det inte. Gamla appens beteende, behållet:
  // "3 öppna" räknar status !== 'klar', men listan visar även klarmarkerade
  // poster överstrukna, så läraren får kvittens på vad hon just bockat av.
  const oppna = $derived(poster.filter((a) => a.status !== 'klar'));
  const forsenade = $derived(oppna.filter((a) => a.overdue).length);

  const meta = (a) => [a.group, a.course, a.lesson_name].filter(Boolean).join(' · ');
</script>

<!--
  null = okänt (inte hämtat, eller hämtningen föll) → ingen panel alls. En tom
  ARRAY är känt tomt och renderar tomtexten nedan. Regeln står i specens
  avsnitt 4.
-->
{#if insp.agenda}
  <!--
    TOM PANEL FÅR INGEN LÅDA. Tomläget ritade tidigare samma ramade,
    ytfärgade .panel som den fyllda: en låda i full bredd, ovanför
    lektionerna, som tog plats för att säga att den inte hade något att säga.
    Den lärare som öppnar Inspelningar för att hitta måndagens genomgång fick
    den i vägen varje gång.

    RUBRIKEN ÄR KVAR, och det är avsiktligt: utan "Kommande" står raden
    "Inga daterade insikter ännu …" fritt under sökfältet utan att säga vad
    det är som är tomt. Det är ramen och ytan som försvinner, inte
    innebörden — och tomtillståndet SYNS fortfarande, vilket är hela poängen
    med panelen (se inspelningar-paneler.spec.mjs: den försvinner inte, till
    skillnad från i gamla appen).

    Den fyllda panelen är orörd — där bär lådan faktiskt något.
  -->
  {#if !poster.length}
    <section class="tompanel">
      <h2 class="rubrik">Kommande</h2>
      <p class="tomrad">
        Inga daterade insikter ännu — sätt ett datum på en åtgärd eller en
        kalenderpost så dyker den upp här.
      </p>
    </section>
  {:else}
    <section class="panel">
      <!--
        Knappen ligger INUTI <h2> och inte tvärtom: ett <button> får bara
        innehålla frasinnehåll, och en rubrik är flödesinnehåll. Så här blir
        rubriken dessutom nåbar med getByRole("heading") och knappen med
        getByRole("button").
      -->
      <h2 class="rubrik">
        <button class="huvud" onclick={vaxlaAgenda} aria-expanded={insp.agendaOppen}>
          <span>Kommande</span>
          <span class="antal">
            {oppna.length}
            {oppna.length === 1 ? 'öppen' : 'öppna'}
            {#if forsenade}
              <span class="sen">
                · {forsenade} {forsenade === 1 ? 'försenad' : 'försenade'}
              </span>
            {/if}
          </span>
          <span class={['chevron', { upp: insp.agendaOppen }]} aria-hidden="true">▾</span>
        </button>
      </h2>

      {#if insp.agendaOppen}
        <ul class="lista">
          {#each poster as a (a.id)}
            <li class={['rad', { forsenad: a.overdue }]}>
              <!--
                SAMMA <button> i BÅDA lägena — öppen och klar. Gamla appen
                (och en tidigare version här) bytte till <span> när posten
                blev klar: en no-op-knapp PATCH:ade om samma status, så bytet
                stängde det. Men #each är nyckelad på a.id, och ett bytt
                elementnamn river Sveltes DOM-nod för just den raden — läraren
                bockar av, PATCH:en lyckas, laddaPaneler() hämtar om, och
                precis den rad hon höll tangentbordsfokus på försvinner under
                fingret. En klar post ska ändå inte gå att aktivera: det löser
                aria-disabled plus den tidiga returen i onclick, INTE
                disabled — en fokuserad nod som blir disabled tappar fokus
                lika säkert som span-bytet gjorde.
              -->
              <button
                class={['ruta', { klar: a.status === 'klar' }]}
                onclick={() => {
                  if (a.status === 'klar' || insp.markerar === a.id) return;
                  markeraKlar(a.id);
                }}
                aria-disabled={a.status === 'klar' || insp.markerar === a.id}
                aria-label={"Markera klar: " + (a.text || "")}
                title="Markera klar"
              >{#if a.status === 'klar'}✓{/if}</button>

              <div class="text">
                <p class={['titel', { avklarad: a.status === 'klar' }]}>{a.text || ''}</p>
                {#if meta(a)}<p class="meta">{meta(a)}</p>{/if}
              </div>

              <span class={['datum', { forsenad: a.overdue, idag: a.today }]}>
                {a.today ? 'Idag' : datumEtikett(a.due_date)}
              </span>
            </li>
          {/each}
        </ul>

        <div class="fot">
          <button class="ghost" onclick={exporteraIcs} disabled={insp.agendaExporterar}>
            {insp.agendaExporterar ? 'Exporterar …' : 'Exportera till kalender (.ics)'}
          </button>
        </div>
      {/if}
    </section>
  {/if}
{/if}

<style>
  /* Panelformen, delad av de tre B5-panelerna. Samma kort som
     Lektionskort.svelte:47-56: --surface, hårlinje, 4px. Gamla panelernas 16px
     hörn och --shadow-sm följer inte med (DESIGN.md, Flat-by-Default). */
  .panel {
    background: var(--surface);
    border: 1px solid var(--line);
    border-radius: 4px;
    padding: 16px 18px;
    margin-bottom: 14px;
  }

  /* margin: 0 nollar <h2>:ans 0.83em-marginaler, precis som .vecka i
     Kartotek.svelte:56 — annars bryts baslinjeraden i .huvud. */
  .rubrik {
    font-size: 1.125rem;
    font-weight: 600;
    color: var(--ink);
    margin: 0;
  }

  .huvud {
    display: flex;
    align-items: baseline;
    gap: 10px;
    width: 100%;
    background: none;
    border: 0;
    padding: 0;
    font-family: inherit;
    font-size: inherit;
    font-weight: inherit;
    color: inherit;
    text-align: left;
    cursor: pointer;
  }

  .antal {
    font-size: 0.72rem;
    font-weight: 400;
    color: var(--ink-3);
    font-variant-numeric: tabular-nums;
  }
  .antal .sen { color: var(--bad); }

  .chevron {
    margin-left: auto;
    font-size: 0.72rem;
    color: var(--ink-3);
    transition: transform 0.15s;
  }
  .chevron.upp { transform: rotate(180deg); }
  /* Samma hänsyn som Inspelning.svelte:222 och BoardPreview.svelte:222. */
  @media (prefers-reduced-motion: reduce) {
    .chevron { transition: none; }
  }

  /* Tomläget bär rubriken men ingen låda: ingen ram, ingen ytfärg, ingen
     radie. Bara marginalen som håller isär det från nästa block. */
  .tompanel { margin-bottom: 14px; }
  /* Samma typform som kartotekets egna tomtillstånd
     (InspelningarView.svelte:.tomt) — samma sorts besked ska se likadant ut. */
  .tomrad {
    font-size: 1.03rem;
    color: var(--ink-2);
    max-width: 52ch;
    margin: 6px 0 0;
  }

  .lista {
    list-style: none;
    margin: 14px 0 0;
    padding: 0;
    display: flex;
    flex-direction: column;
  }

  /* Hårlinjer mellan raderna i stället för gamla appens rutor med egen ram och
     egen bakgrund per rad. En lista är en lista. */
  .rad {
    display: flex;
    align-items: flex-start;
    gap: 10px;
    padding: 9px 0;
    border-top: 1px solid var(--line);
  }
  .rad:first-child { border-top: 0; }

  /* Den försenade raden markeras med en TONAD BAKGRUND, inte en border-left —
     DESIGN.md förbjuder accentstripen uttryckligen, och de två sista
     förekomsterna i frontenden togs bort (InspelningarView.svelte:364-369). */
  .rad.forsenad {
    background: color-mix(in srgb, var(--bad) 6%, transparent);
    margin: 0 -18px;
    padding-left: 18px;
    padding-right: 18px;
  }

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
    line-height: 1;
  }
  /* :disabled är ersatt av [aria-disabled="true"] rakt igenom — ruta är nu
     ALLTID en <button>, aldrig en <span>, och det native disabled-attributet
     används medvetet inte (det tar fokus med sig). Se onclick-kommentaren
     ovanför markupen. */
  .ruta:hover:not([aria-disabled="true"]) {
    border-color: var(--ok);
    background: color-mix(in srgb, var(--ok) 18%, transparent);
  }
  /* :not(.klar): en KLAR post är också aria-disabled, men ska inte dämpas —
     den bär redan sin egen fulla --ok-yta nedan. Utan undantaget vinner den
     här regeln över .klar:s opacitet (ingen sätts där) och släcker
     checkmarken till 0.5, en synlig regression mot span-varianten som aldrig
     matchade :disabled. */
  .ruta[aria-disabled="true"]:not(.klar) { cursor: default; opacity: 0.5; }
  .ruta.klar {
    display: flex;
    align-items: center;
    justify-content: center;
    border-color: var(--ok);
    background: var(--ok);
    color: var(--on-ok);
    font-size: 0.72rem;
    cursor: default;
  }

  .text { flex: 1; min-width: 0; }
  .titel {
    font-size: 1.03rem;
    color: var(--ink);
    margin: 0;
    overflow-wrap: anywhere;
  }
  .titel.avklarad { color: var(--ink-3); text-decoration: line-through; }
  .meta {
    font-size: 0.72rem;
    color: var(--ink-3);
    margin: 2px 0 0;
    overflow-wrap: anywhere;
  }

  .datum {
    flex: none;
    font-size: 0.72rem;
    font-weight: 500;
    color: var(--ink-3);
    font-variant-numeric: tabular-nums;
    padding-top: 3px;
  }
  .datum.forsenad { color: var(--bad); }
  .datum.idag { color: var(--accent); }

  .fot { display: flex; justify-content: flex-end; margin-top: 14px; }

  /* Identisk med .ghost i InspelningarView.svelte:412-421, som i sin tur är
     kopian av Korning.svelte:284-293. */
  .ghost {
    background: transparent;
    color: var(--ink-2);
    border: 1px solid var(--line-2);
    border-radius: 4px;
    padding: 8px 16px;
    font-family: inherit;
    font-size: inherit;
    cursor: pointer;
  }
  .ghost:hover:not(:disabled) { border-color: var(--ink); color: var(--ink); }
  .ghost:disabled { cursor: default; opacity: 0.6; }
</style>
