<script>
  // Genomsökningen. Speglar buildScanModel + scanTheater
  // (app/web/static/app.js:5036-5136), AVDEKORERAD enligt specens avsnitt 5:
  // ärlighetsprincipen behålls — verklig ordning, äkta träffantal, pacad
  // utrullning, två faser, progresslinje — men floaty, readsweep, scanBusy,
  // saturate-filtren och scale-transformerna följer inte med.
  import { sok } from './sok.svelte.js';
  import { rensaSokning } from './sokActions.js';
  import { parseCitat } from './citat.js';

  // Taket på antal kort. Fler än så säger inget mer om förloppet, och ett
  // rutnät på hundra rutor är inte längre en genomsökning utan en vägg.
  const MAX_KORT = 24;

  const plan = $derived(sok.skanPlan || []);

  // TVÅ FLAGGOR, TVÅ BETYDELSER — blanda inte ihop dem igen. sok.fragar
  // betyder "svaret strömmar fortfarande" (frågan är i luften); skannar
  // betyder "utrullningen av kort pågår fortfarande". De slocknar INTE
  // samtidigt: sokActions.js stoppar medvetet inte utrullningstimern vid
  // done, för svaret kan bli klart innan alla kort hunnit avslöjas
  // (no_hit_job och grenen utan installerad språkmodell svarar synkront,
  // ofta inom millisekunder — se sokActions.js:18-22). Allt som beskriver
  // UTRULLNINGENS FÖRLOPP (hur många kort som syns, korttillstånden, vilket
  // kort som är aktuellt, läsbordets tändning, träffräknarens "hittills")
  // läser skannar. Allt som beskriver att SVARET STRÖMMAR ("Skickar
  // frågan …", tänker-suffixet, läsbordets rubrik, citatfiltreringen) läser
  // sok.fragar. Speglar InspelningarView.svelte:s stadiekarta och gamla
  // appens tvådelade scanning-flagga (app.js:3403-3404).
  const skannar = $derived(sok.fragar || sok.skanVisade < plan.length);

  // Under utrullningen avslöjas korten i takt; är den klar visas alla.
  const visade = $derived(skannar ? Math.min(sok.skanVisade, plan.length) : plan.length);
  const utrullningKlar = $derived(plan.length > 0 && sok.skanVisade >= plan.length);

  // Läsbordet tänds när modellen valt sina källor OCH utrullningen hunnit
  // klart — annars hoppar blicken mellan två ytor som växer samtidigt.
  const lasbordPa = $derived(sok.laser.length > 0 && (utrullningKlar || !skannar));

  const ordtraffar = $derived(
    plan.slice(0, visade).filter((p) => (sok.skanTraffar[p.key] || 0) > 0).length,
  );

  const aktuell = $derived(
    skannar && !lasbordPa ? plan[Math.min(sok.skanVisade, plan.length - 1)] : null,
  );

  const kort = $derived.by(() => {
    const ut = plan.slice(0, MAX_KORT).map((p, i) => {
      const traffar = sok.skanTraffar[p.key] || 0;
      let stadie;
      let etikett;
      if (skannar && i === sok.skanVisade) {
        stadie = 'laser';
        etikett = 'Läser …';
      } else if (!skannar || i < sok.skanVisade) {
        stadie = traffar > 0 ? 'traff' : 'last';
        etikett = traffar > 0
          ? `● ${traffar} ${traffar === 1 ? 'träff' : 'träffar'}`
          : 'Läst ✓';
      } else {
        stadie = 'ko';
        etikett = 'I kö';
      }
      return { key: p.key, stadie, etikett, titel: p.name || '(namnlös)' };
    });
    const extra = Math.max(0, plan.length - MAX_KORT);
    if (extra > 0) {
      ut.push({
        key: '_fler',
        stadie: visade >= plan.length ? 'last' : 'ko',
        etikett: '',
        titel: `+ ${extra} till`,
      });
    }
    return ut;
  });

  // LÄSBORDET filtreras till de källor svaret FAKTISKT citerar när svaret är
  // klart. Under strömningen visas alla modellen läser. Gamla appen gör samma
  // filtrering (app.js:3797-3821) och av samma skäl: "bygger på dessa 3" när
  // bara en citeras är ett påstående som inte håller.
  const bordet = $derived.by(() => {
    if (sok.fragar || !sok.svar || !sok.kallor.length) return sok.laser;
    const citat = parseCitat(sok.svar, sok.kallor.length);
    if (!citat) return sok.kallor;
    return citat.refs.map((r) => sok.kallor[r.kallIndex]).filter(Boolean);
  });

  // Åt-sidan-räkningen utgår från ORDTRÄFFARNA, inte alla genomsökta:
  // inspelningar utan träff lades aldrig på läsbordet.
  const undanlagda = $derived(Math.max(0, ordtraffar - bordet.length));

  // "Ordträff", inte "träff". Gamla appens kommentar (app.js:5069-5071) säger
  // varför: siffrorna ska hänga ihop — genomsökte N → M ordträffar → svaret
  // bygger på K → la M−K åt sidan. "Träff" ensamt blandar ihop de tre talen.
  const traffEtikett = $derived(
    `${ordtraffar} ${
      ordtraffar === 1
        ? skannar ? 'ordträff hittills' : 'ordträff'
        : skannar ? 'ordträffar hittills' : 'ordträffar'
    }`,
  );

  const tanker = $derived(sok.fragar && utrullningKlar && !sok.svar);
  const meta = (s) => [s.group, s.course, s.datum].filter(Boolean).join(' · ');
</script>

<!--
  Luckan mellan klick och första scan_plan. Gamla appen renderar ingenting där
  (app.js:5097 returnerar tom sträng när planen är tom) — vanligtvis kort, men
  tyst. En stillsam rad är ärligare än en tom yta.
-->
{#if sok.fragar && !plan.length}
  <p class="notis">Skickar frågan …</p>
{/if}

{#if plan.length}
  <section class="genomsokning">
    <div class="status">
      <p class="ticker">
        <!--
          skannar && !lasbordPa, inte bara skannar. Gamla appen växlar tickern
          på buildScanModels HÄRLEDDA fält (app.js:5062: scanning = cfg.scanning
          && !deskOn), inte på den råa flaggan — samma sammansättning som
          aktuell ovan använder.

          Utan andra ledet påstår tickern "Söker igenom N inspelningar" så
          länge svaret strömmar, trots att utrullningen är klar och läsbordet
          under den redan säger "AI:n läser nu dessa N". Det är inte ett
          kantfall utan NORMALFALLET: skanningen tar högst 3,5 s medan
          LLM-svaret tar längre, så de två raderna hade motsagt varandra vid
          nästan varje fråga.
        -->
        {#if skannar && !lasbordPa}
          Söker igenom {plan.length} {plan.length === 1 ? 'inspelning' : 'inspelningar'}{aktuell &&
          aktuell.name
            ? ` — ${aktuell.name}`
            : ''}{tanker ? ' · tänker …' : ''}
        {:else if sok.fragaFel}
          <!--
            FYND 1 I SLUTGRANSKNINGEN. Ett error-event kan komma EFTER
            scan_plan, scan_result och deep_read redan emitterats — servern
            kastar t.ex. "Språkmodellen är inte installerad." (server.py:1591)
            EFTER deep_read, och streamPost:s syntetiska
            "Anslutningen till servern bröts." kan landa när som helst. Utan
            den här grenen faller tickern till else-grenen nedan (skannar är
            redan false här — se skannar-uttrycket ovan, som snäpps av
            error-hanteraren i sokActions.js) och visar "✓ Genomsökte" — en
            KVITTENS för en sökning som just kraschade, samtidigt som
            Svar.svelte visar felet. Det är inget kantfall: en installation
            utan Qwen3-14B hamnar här vid VARJE fråga.

            Texten påstår varken framgång ("✓ Genomsökte …") eller att
            sökningen fortfarande pågår ("Söker igenom …") — bara att den
            avbröts, och pekar mot felet som redan renderas i svarsytan.
          -->
          Genomsökningen avbröts — se felet nedan
        {:else}
          ✓ Genomsökte {plan.length} {plan.length === 1 ? 'inspelning' : 'inspelningar'}
        {/if}
      </p>
      <span class="antal">{traffEtikett}</span>
      <button class="ny" onclick={rensaSokning}>✕ Ny fråga</button>
    </div>

    <!-- Progresslinjen. 2px spår, ingen puls: tänker-läget bärs av tickerns
         suffix i stället för av en oändlig animation. -->
    <div class="spar">
      <!--
        scaleX, inte width. Att animera width är en layoutegenskap: varje bild
        i övergången tvingar fram en ny layoutberäkning, medan transform körs
        på kompositorn. Baren är full bredd och skalas ned i stället —
        transform-origin: left gör att den växer från vänsterkanten precis som
        förut.
      -->
      <div class="fyllnad" style:transform="scaleX({plan.length ? visade / plan.length : 0})"></div>
    </div>

    {#if sok.notis}
      <p class="notis">{sok.notis}</p>
    {/if}

    <ul class="rutnat">
      {#each kort as k (k.key)}
        <li class="ruta" data-scan={k.stadie}>
          <span class="titel">{k.titel}</span>
          {#if k.etikett}<span class="etikett">{k.etikett}</span>{/if}
        </li>
      {/each}
    </ul>

    <!--
      FYND 1 I SLUTGRANSKNINGEN: grindat på !sok.fragaFel. sok.laser
      (deep_read) kan redan vara ifyllt när error-eventet landar — samma
      ordning som tickerns fragaFel-gren ovan beskriver — så utan grinden
      hade läsbordet fortsatt visa "Svaret bygger på dessa N" för en fråga
      som aldrig fick ett svar. Ett påstått svar är inget svar.
    -->
    {#if !sok.fragaFel && (lasbordPa || (!skannar && bordet.length))}
      <p class="bordsrubrik">
        {#if sok.fragar}
          {bordet.length === 1 ? 'AI:n läser nu denna' : `AI:n läser nu dessa ${bordet.length}`}
        {:else}
          {bordet.length === 1
            ? 'Svaret bygger på denna'
            : `Svaret bygger på dessa ${bordet.length}`}
        {/if}
        {#if undanlagda > 0}<span class="aside"
            >… och la {undanlagda} {undanlagda === 1 ? 'ordträff' : 'ordträffar'} åt sidan</span
          >{/if}
      </p>
      <ul class="bordet">
        {#each bordet as s (s.lesson_id)}
          <li class="bordskort">
            <span class="titel">{s.name || '(namnlös)'}</span>
            {#if meta(s)}<span class="bordsmeta">{meta(s)}</span>{/if}
          </li>
        {/each}
      </ul>
    {/if}
  </section>
{/if}

<style>
  .genomsokning {
    background: var(--surface);
    border: 1px solid var(--line);
    border-radius: 4px;
    padding: 14px 16px;
    margin-top: 18px;
  }

  .status {
    display: flex;
    align-items: baseline;
    gap: 12px;
    flex-wrap: wrap;
  }
  .ticker {
    flex: 1;
    min-width: 0;
    font-size: 1.03rem;
    color: var(--ink-2);
    margin: 0;
    overflow-wrap: anywhere;
  }
  .antal {
    font-size: 0.72rem;
    color: var(--ink-3);
    font-variant-numeric: tabular-nums;
  }
  /* Identisk med .ghost i InspelningarView.svelte, som i sin tur är kopian av
     Korning.svelte:284-293. */
  .ny {
    background: transparent;
    color: var(--ink-2);
    border: 1px solid var(--line-2);
    border-radius: 4px;
    padding: 4px 12px;
    font-family: inherit;
    font-size: 0.72rem;
    cursor: pointer;
  }
  .ny:hover { border-color: var(--ink); color: var(--ink); }

  /* Samma form som progressbaren i Korning.svelte:232-239 och i
     Terminstrender.svelte: tunt spår, 2px radie, accentfyllning. */
  .spar {
    height: 2px;
    background: var(--track);
    border-radius: 2px;
    overflow: hidden;
    margin: 10px 0 0;
  }
  .fyllnad {
    width: 100%;
    height: 100%;
    background: var(--accent);
    border-radius: 2px;
    transform-origin: left center;
    transition: transform 0.32s cubic-bezier(0.2, 0.8, 0.25, 1);
  }
  @media (prefers-reduced-motion: reduce) {
    .fyllnad { transition: none; }
  }

  /* FYND 4 I SLUTGRANSKNINGEN: löptext ("Skickar frågan …", serverns
     log-meddelande via sok.notis — ibland en hel mening, t.ex. "Inga direkta
     ordträffar — läser mellan raderna och söker på närliggande begrepp …"),
     inte en mikroetikett. 0.72rem/--ink-3 är reserverat för korta versala
     etiketter (se .antal och .titel nedan) — samma argument som
     InspelningarView.svelte gjorde för sin egen .notis (ärlighetsvakten) och
     som ledde till att DEN höjdes till 1.03rem/--ink-2. Två .notis i samma vy
     med motsatt regel vore en inkonsekvens utan skäl; rättat hit i stället
     för att motivera en skillnad som inte finns. */
  .notis {
    font-size: 1.03rem;
    color: var(--ink-2);
    margin: 10px 0 0;
    max-width: 52ch;
  }

  .rutnat {
    list-style: none;
    margin: 12px 0 0;
    padding: 0;
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(120px, 1fr));
    gap: 6px;
  }

  /* FYRA KORTTILLSTÅND, burna av opacitet och hårlinjer. Gamla appens
     saturate(.5)-filter, 3px-ringar och streckade ramar följer inte med. */
  .ruta {
    display: flex;
    flex-direction: column;
    gap: 2px;
    min-width: 0;
    border: 1px solid var(--line);
    border-radius: 3px;
    padding: 6px 8px;
    background: var(--sunken);
    transition: opacity 0.35s ease, border-color 0.35s ease, background 0.35s ease;
  }
  .ruta[data-scan='ko'] { opacity: 0.5; }
  .ruta[data-scan='laser'] { border-color: var(--accent); }
  .ruta[data-scan='last'] { opacity: 0.45; }
  .ruta[data-scan='traff'] {
    border-color: var(--accent);
    background: var(--accent-weak);
  }
  .ruta[data-scan='traff'] .etikett { color: var(--accent); }
  @media (prefers-reduced-motion: reduce) {
    .ruta { transition: none; }
  }

  .titel {
    font-size: 0.72rem;
    color: var(--ink);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .etikett {
    font-size: 0.72rem;
    color: var(--ink-3);
    font-variant-numeric: tabular-nums;
  }

  .bordsrubrik {
    font-family: var(--mono);
    font-size: 0.72rem;
    font-weight: 500;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: var(--ink-3);
    margin: 18px 0 8px;
  }
  .aside { text-transform: none; letter-spacing: 0; font-family: var(--sans); }

  .bordet {
    list-style: none;
    margin: 0;
    padding: 0;
    display: flex;
    flex-direction: column;
    gap: 4px;
  }
  .bordskort {
    display: flex;
    align-items: baseline;
    gap: 10px;
    flex-wrap: wrap;
    border-top: 1px solid var(--line);
    padding: 7px 0 0;
  }
  .bordskort:first-child { border-top: 0; padding-top: 0; }
  .bordskort .titel { font-size: 1.03rem; white-space: normal; overflow-wrap: anywhere; }
  .bordsmeta {
    font-size: 0.72rem;
    color: var(--ink-3);
    font-variant-numeric: tabular-nums;
  }
</style>
