<script>
  // Kalenderförslaget — delas av BÅDA värdarna (lektionschatten och
  // arkivsvaret) via props i stället för att importera lektionschattens
  // store/actions rakt av: kalender/ har annars noll importer utanför sin
  // egen mapp, och den egenskapen ska gälla även UI-lagret. `onBesked`
  // ersätter det tidigare direktimporterade satBesked/annonsera-paret —
  // anroparen (Meddelandelista.svelte för 'lektion', Svar.svelte för
  // 'arkiv') avgör själv VAR beskedet ska synas.
  import { kal } from './stores.svelte.js';
  import { evDagar, isoEtikett, KLOCKSLAG } from './tid.js';
  import { avfarda, satTitel, satDag, satTid, laggTillHandelse, oppnaAnteckning, startaAnslutning } from './actions.js';

  let { vardnyckel, onBesked } = $props();

  // Idag som ISO — undre gräns för dagväljaren. Modellens egen instruktion
  // säger redan "datumet får aldrig ligga före idag" (llm_client._cal_instr),
  // men fältet ska hålla samma regel även när läraren väljer manuellt.
  const idag = evDagar()[0].iso;

  const f = $derived(kal.forslag[vardnyckel]);

  function paTitel(e) {
    satTitel(vardnyckel, e.currentTarget.value);
  }
  function paDag(e) {
    const iso = e.currentTarget.value;
    if (!iso) return;
    const etikett = isoEtikett(iso);
    if (etikett) satDag(vardnyckel, iso, etikett);
  }
  function paTid(e) {
    if (e.currentTarget.value) satTid(vardnyckel, e.currentTarget.value);
  }
  /** Snabbvalen nedanför tidfältet — samma sätta-tid som klockslagsfältet. */
  function paTidChip(t) {
    satTid(vardnyckel, t);
  }

  async function paLaggTill() {
    const titel = f ? f.titel : '';
    const r = await laggTillHandelse(vardnyckel);
    if (!r.ok) onBesked(r.fel, 'fel');
    else onBesked('Tillagd i Google Kalender — ' + titel, 'info');
  }

  /**
   * D-liknande fynd ur slutgranskningen: startaAnslutning() returnerar nu
   * loggaIn():s resultat (se actions.js) när klientfilen redan finns — den
   * här knappen är den enda platsen som annars körde den rakt mot onclick
   * och kastade bort svaret, så en misslyckad inloggning gav ingen
   * indikation alls.
   */
  async function paAnslut() {
    const r = await startaAnslutning();
    if (r && !r.ok) onBesked(r.fel, 'fel');
  }
</script>

{#if f}
  <section class="box" aria-label="Kalenderförslag">
    <p class="eyebrow">Förslag → Kalender</p>

    {#if f.tillagd}
      <p class="klar">
        Tillagd i Google Kalender — {f.titel}
        {#if f.lank}
          <a href={f.lank} target="_blank" rel="noopener noreferrer">Öppna i Google Kalender</a>
        {/if}
      </p>
    {:else}
      <input
        class="falt titelfalt"
        type="text"
        value={f.titel}
        oninput={paTitel}
        aria-label="Titel på händelsen"
      />

      <div class="tidrad">
        <input
          class="falt datumfalt"
          type="date"
          value={f.startIso || idag}
          min={idag}
          onchange={paDag}
          aria-label="Datum"
        />
        <input
          class="falt tidfalt"
          type="time"
          value={(f.nar || '').slice(-5) || '08:00'}
          onchange={paTid}
          aria-label="Tid"
        />
        {#if f.slutDag}<span class="slut">→ {f.slutDag}</span>{/if}
      </div>

      <!-- Snabbval för vanliga lektionstider, BREDVID klockslagsfältet — inte
           i stället för det. Listan (tid.js:KLOCKSLAG) är delvis dött veten-
           skap (rekon §12.2: hårdkodad utan koppling till lärarens faktiska
           schema) men rimliga genvägar för de flesta ändå.

           aria-label INNEHÅLLER MEDVETET INTE ordet "tid": kalender.spec.mjs
           och inspelningar-fraga.spec.mjs läser tidfältet med
           getByLabel("Tid"), som matchar VARJE aria-label vars text
           innehåller "tid" (case-insensitive substräng, oavsett element) —
           "Vanliga lektionstider" gjorde precis det och gav "strict mode
           violation: resolved to 2 elements". Tandkontrollerat. -->
      <ul class="tidchips" aria-label="Snabbval för klockslag">
        {#each KLOCKSLAG as t (t)}
          <li>
            <button
              type="button"
              class="chip"
              aria-pressed={(f.nar || '').slice(-5) === t}
              onclick={() => paTidChip(t)}
            >{t}</button>
          </li>
        {/each}
      </ul>

      <!-- Klippt förhandsvisning, inte redigering direkt i boxen — klick
           öppnar AnteckningModal.svelte, som läser OCH redigerar samma fält
           i ett större textfält. Speglar gamla appens mönster (en klippt
           preview öppnade läsmodalen, app.js:5397) men slår ihop läs- och
           redigeringsläget till EN modal (descModalFor behövs inte — den
           delade modalen vet vilket förslag den redigerar via
           kal.anteckningOppen, se stores.svelte.js). -->
      <button type="button" class="anteckningsforhandsvisning" onclick={() => oppnaAnteckning(vardnyckel)}>
        {#if f.anteckning}
          <span class="klippt">{f.anteckning}</span>
        {:else}
          <span class="tom">Lägg till en anteckning …</span>
        {/if}
      </button>

      <!-- LÖPANDE TEXT, inte en mikroetikett: den kan bära serverns hela
           hjälptext (kal.hint, t.ex. "Ingen OAuth-klientfil hittades — …"),
           och en versal mono-MENING bryter DESIGN.md:s Mono-Is-Labels-Only-
           regel lika mycket som en versal mono-etikett med bara ett par ord
           inte gör. -->
      <p class="status" class:ansluten={kal.ansluten === true}>
        {#if kal.ansluten === null}
          Kontrollerar Google-anslutningen …
        {:else if kal.ansluten}
          Ansluten till Google Kalender
        {:else}
          Inte ansluten till Google Kalender{kal.hint ? ' — ' + kal.hint : ' ännu'}
        {/if}
      </p>
      {#if kal.ansluten === false}
        <button type="button" class="anslut" onclick={paAnslut}>Anslut Google-konto</button>
      {/if}

      <div class="knappar">
        <!-- INTE avstängd av kal.ansluten (B:s Kalenderforslag.svelte:106
             gjorde det, disabled={... || calAnsluten !== true}) — provat och
             backat: A:s EGEN e2e-täckning (kalender.spec.mjs, "'Lägg till'
             mot ett fejkat /api/calendar/event — lyckat och ett 400-fel" och
             D11-testet) klickar medvetet UTAN att först stubba
             /api/calendar/status, just för att bevisa att ett obekräftat
             klick ger serverns EGNA felmeddelande via onBesked i stället för
             att tyst blockeras. /api/calendar/status går mot den RIKTIGA
             backenden i de testerna (kommentaren högst upp i den filen), så
             kal.ansluten där är miljöberoende — en klientspärr på den hade
             gjort testernas utfall lika miljöberoende. Tandkontrollerat: satte
             tillbaka spärren, båda testerna föll (strict-avstängd knapp,
             timeout). Kvar är bara busy-spärren, som redan fanns. -->
        <button type="button" class="primar" disabled={f.upptagen} onclick={paLaggTill}>
          {f.upptagen ? 'Lägger till …' : 'Lägg till'}
        </button>
        <!-- Avfärda inaktiveras medan en begäran är i luften, av samma
             skäl som kalender/actions.js:laggTillHandelse beskriver: gamla
             appens dismissEvent (app.js:2703) kunde köras UTAN att kolla
             busy, så en händelse kunde skapas i Google efter att förslaget
             redan setts som avfärdat i UI:t. Det kvarstår fortfarande om
             läraren stänger hela chatten mitt i — se laggTillHandelse. -->
        <button type="button" class="ghost" disabled={f.upptagen} onclick={() => avfarda(vardnyckel)}>Avfärda</button>
      </div>

      <p class="hjalp">
        Ändra via chatten — "flytta till onsdag 14:30", "kortare titel" eller "pågå till fredag" för flera dagar.
      </p>
    {/if}
  </section>
{/if}

<style>
  .box {
    flex: 0 0 auto;
    border: 1px dashed var(--line-2);
    background: var(--sunken);
    border-radius: 5px;
    padding: 12px 14px;
    margin-top: 10px;
  }
  .eyebrow {
    font-family: var(--mono);
    font-size: 0.72rem;
    font-weight: 500;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: var(--ink-3);
    margin: 0 0 8px;
  }
  .klar {
    margin: 0;
    color: var(--ok);
    font-weight: 500;
  }
  .klar a {
    color: inherit;
    margin-left: 6px;
  }

  /* Receptet är Skrivrad.svelte:53-65:s (frontend/src/lib/lektionschatt/Skrivrad.svelte). */
  .falt {
    background: var(--surface);
    color: var(--ink);
    border: 1px solid var(--line-2);
    border-radius: 3px;
    padding: 8px 10px;
    font-family: inherit;
    font-size: 1.03rem;
    line-height: 1.45;
  }
  .falt:focus-visible { border-color: var(--accent); }
  .titelfalt { width: 100%; box-sizing: border-box; font-weight: 500; }

  .tidrad {
    display: flex;
    align-items: center;
    gap: 8px;
    flex-wrap: wrap;
    margin-top: 8px;
  }
  /* Datum och tider är data, inte etiketter: sans med tabular-nums, aldrig
     var(--mono) — DESIGN.md §Typography. */
  .datumfalt,
  .tidfalt {
    font-variant-numeric: tabular-nums;
  }
  .slut {
    color: var(--ink-2);
    font-variant-numeric: tabular-nums;
  }

  /* Snabbvalen för klockslag — samma chip-form som FragekortModal.svelte:s
     alternativknappar, i miniatyr. */
  .tidchips {
    list-style: none;
    display: flex;
    flex-wrap: wrap;
    gap: 5px;
    margin: 6px 0 0;
    padding: 0;
  }
  .chip {
    background: var(--surface);
    color: var(--ink-2);
    border: 1px solid var(--line-2);
    border-radius: 3px;
    padding: 3px 9px;
    font-family: inherit;
    font-size: 0.72rem;
    font-variant-numeric: tabular-nums;
    cursor: pointer;
  }
  .chip:hover { border-color: var(--ink-3); color: var(--ink); }
  .chip[aria-pressed='true'] {
    background: var(--accent-weak);
    color: var(--accent);
    border-color: var(--accent);
  }

  /* Klippt förhandsvisning i stället för ett fält — en riktig knapp, inte
     ett <p>: den ÖPPNAR AnteckningModal.svelte, en handling, inte bara
     text. */
  .anteckningsforhandsvisning {
    display: block;
    width: 100%;
    box-sizing: border-box;
    text-align: left;
    background: var(--surface);
    color: var(--ink);
    border: 1px solid var(--line-2);
    border-radius: 3px;
    padding: 8px 10px;
    margin-top: 8px;
    font-family: inherit;
    font-size: 1.03rem;
    line-height: 1.45;
    cursor: pointer;
  }
  .anteckningsforhandsvisning:focus-visible { border-color: var(--accent); }
  .klippt {
    display: -webkit-box;
    -webkit-line-clamp: 3;
    line-clamp: 3;
    -webkit-box-orient: vertical;
    overflow: hidden;
  }
  .tom { color: var(--ink-3); }

  /* Löpande text — se markup-kommentaren om varför den inte längre är
     var(--mono) i versaler. */
  .status {
    font-size: 1.03rem;
    color: var(--ink-2);
    max-width: 52ch;
    margin: 10px 0 0;
  }
  .status.ansluten { color: var(--ok); }
  /* Egen knapp under statusraden — en handlingstext som "Anslut
       Google-konto" hör inte till statusradens röst. Liten, tillbaka-
       dragen: det här är en sekundär genväg, inte huvudhandlingen
       (Lägg till). */
  .anslut {
    display: block;
    background: transparent;
    color: var(--accent);
    border: none;
    padding: 4px 0 0;
    margin: 0;
    font-family: inherit;
    font-size: 0.72rem;
    text-decoration: underline;
    text-underline-offset: 3px;
    cursor: pointer;
  }

  .knappar {
    display: flex;
    align-items: center;
    gap: 8px;
    margin-top: 10px;
  }
  /* Identisk med .primar i frontend/src/lib/transkribera/Korning.svelte:286-296. */
  .primar {
    background: var(--btn-bg);
    color: var(--btn-fg);
    border: none;
    border-radius: 4px;
    padding: 9px 16px;
    font-family: inherit;
    font-size: inherit;
    font-weight: 500;
    cursor: pointer;
  }
  .primar:disabled { opacity: 0.55; cursor: default; }
  /* Identisk med .ghost i frontend/src/lib/transkribera/Korning.svelte:297-306. */
  .ghost {
    background: transparent;
    color: var(--ink);
    border: 1px solid var(--line-2);
    border-radius: 4px;
    padding: 9px 16px;
    font-family: inherit;
    font-size: inherit;
    cursor: pointer;
  }
  .ghost:disabled { opacity: 0.55; cursor: default; }

  .hjalp {
    font-size: 0.72rem;
    color: var(--ink-3);
    margin: 8px 0 0;
  }
</style>
