<script>
  // Inspelningar-fliken: kartoteket över transkriberade lektioner. Speglar
  // viewRecordings (app/web/static/app.js:4776-4956), omstylad till
  // designsystemet — gamla vyn är ren inline-CSS med 9-14px hörn.
  import { untrack } from 'svelte';
  import { insp } from './stores.svelte.js';
  import {
    laddaLektioner,
    laddaOrg,
    startaRedigering,
    fragaRadera,
    avbrytRadera,
    bekraftaRadera,
  } from './actions.js';
  import Filterrad from './Filterrad.svelte';
  import Kartotek from './Kartotek.svelte';
  import RedigeraLektion from './RedigeraLektion.svelte';
  import { nav } from '../shell/nav.svelte.js';

  // Fokusmål för raderingsbekräftelsen. $effect körs när blocket monterats in,
  // alltså efter att insp.raderId satts.
  let bekraftRuta = $state(null);
  $effect(() => {
    if (insp.raderId !== null) bekraftRuta?.focus();
  });

  // Hämtas vid varje NAVIGERING HIT, inte vid montering. KONTROLLERAT
  // (App.svelte:20-22): panelen står i markupen UTAN {#if} och göms bara med
  // hidden, så vyn monteras EN gång och avmonteras aldrig. En ren
  // monteringseffekt hade alltså kört vid appstart — innan läraren ens öppnat
  // fliken — och sedan aldrig mer: transkribera en lektion, byt hit, och den
  // saknas hela sessionen. Grindningen på nav.tab speglar app.js:606, som
  // anropar loadLessons(); loadOrg(); vid varje byte till recordings.
  //
  // Effekten spårar BARA nav.tab. untrack håller allt som laddaOrg och
  // laddaLektioner läser — insp.filterGroup, insp.filterCourse — utanför
  // beroendegrafen. Utan den spåras filtren, eftersom laddaLektioner läser dem
  // synkront före sitt första await och Sveltes spårning är dynamisk, inte
  // lexikal. Det vore fel på tre sätt: implicit reaktivitet är precis den fälla
  // specen varnar för, beroendet försvinner tyst om någon lägger en await före
  // prologen, och Task 3:s explicita await laddaLektioner() skulle bli en
  // dubbelhämtning i stället för enda vägen till en omhämtning vid filterbyte
  // — vilket den nu är.
  $effect(() => {
    if (nav.tab !== 'inspelningar') return;
    untrack(() => {
      laddaOrg();
      laddaLektioner();
    });
  });

  // MÅNADSFILTRET tillämpas HÄR, på klienten. Klass och kurs är redan
  // bortfiltrerade av servern innan listan kom hit — läggs de till här också
  // filtreras det två gånger, och en framtida läsare tror att omhämtningen är
  // överflödig och tar bort den.
  const synliga = $derived(
    insp.filterMonth
      ? insp.lessons.filter((l) => String(l.datum || '').slice(0, 7) === insp.filterMonth)
      : insp.lessons,
  );
</script>

<section class="view">
  <p class="eyebrow">INSPELNINGAR</p>
  <h1 class="display">Dina <span class="ser">lektioner</span></h1>
  <p class="lede">
    Allt som transkriberats, samlat per vecka. Ljudet och texten ligger kvar på
    din egen dator.
  </p>

  <!--
    Vyns egen live-region. Permanent i DOM:en och bara visuellt klippt — aldrig
    {#if}-grindad och aldrig display:none. Det mönstret har underkänts fyra
    gånger i den här migrationen: en region som monteras in samtidigt som sin
    text annonseras inte pålitligt, och display:none tar bort noden ur
    tillgänglighetsträdet så role="status" aldrig kan annonsera mutationen.

    ATT VARJE VY HAR EN EGEN ÄR RÄTT, inte en dubblett. App.svelte göms per
    flik med hidden (.pane[hidden] { display: none }), inte genom att
    avmontera, så alla vyers paneler ligger kvar i DOM:en samtidigt — men en
    dold panel är display:none och alltså borta ur tillgänglighetsträdet, så
    bara den synliga fliken kan annonsera. A4:s nodidentitetsspärr i
    e2e/transkribera-kalla.spec.mjs räknade från början [role="status"] över
    HELA sidan och fällde därför den här noden; den är nu avgränsad till den
    synliga panelen, vilket är vad den hela tiden menade.
  -->
  <p class="fel-sr" role="status">{insp.fel}</p>

  <Filterrad />

  <!--
    SYNLIG kopia av live-regionen ovan. Task 1 levererade bara den klippta
    regionen, och den når skärmläsare men ingen annan — Task 4 är den första
    som skriver riktiga fel hit, bland dem DELETE-ets 409 ("kunde inte radera
    mappen — en fil kan vara öppen"). Backend lämnar då MEDVETET både lektionen
    och historikposten intakta (server.py:1027-1035), så sväljs beskedet står
    kortet kvar efter nästa hämtning utan förklaring.

    aria-hidden och UTAN egen roll: bara live-regionen ovan ska annonseras.
    Två annonserande noder i samma vy läses i oförutsägbar ordning — det är
    precis vad antalsspärren i e2e/transkribera-kalla.spec.mjs finns för.
    Samma mönster som TranskriberaView.svelte:118. Riktig textnod, inte
    content: attr(...), så den går att markera, kopiera och Ctrl+F-söka.

    :empty-regeln ligger på DEN HÄR kopian, aldrig på live-regionen —
    display:none tar bort noden ur tillgänglighetsträdet, och då kan
    role="status" inte längre annonsera mutationen.

    TESTID:T ÄR "insp-statusrad", inte "statusrad" som Task 4:s brief skrev.
    Skälet är MÄTT, inte antaget: TranskriberaView bär redan
    data-testid="statusrad", och App.svelte:16-27 håller ALLA paneler monterade
    (bara hidden). En andra nod med samma id ger därför strict mode violation i
    de befintliga spärrarna, som lokaliserar den osäkrat:
    transkribera-kalla.spec.mjs:50, :64, :137-139 och
    transkribera-inspelning.spec.mjs:919. Kört och verifierat: "strict mode
    violation: getByTestId('statusrad') resolved to 2 elements", 2 fällda
    tester. Ett per-vy-id är dessutom vad de här id:na faktiskt är, och det
    lämnar de gröna spärrarna orörda i stället för att skriva om dem.
  -->
  <p class="fel" aria-hidden="true" data-testid="insp-statusrad">{insp.fel}</p>

  <!--
    Raderingsbekräftelsen. MEDVETET ingen confirm(): den går varken att styla
    eller att testa, och den blockerar dessutom hela renderaren. Blocket ligger
    ovanför kartoteket och tar fokus när det öppnas — annars hamnar det före
    kortet läraren just tryckte på i DOM-ordningen, och en tangentbordsanvändare
    skulle behöva backa med Shift+Tab för att hitta det.
  -->
  {#if insp.raderId !== null}
    <div class="bekraft" tabindex="-1" bind:this={bekraftRuta}>
      <p class="fraga">Ta bort <strong>{insp.raderNamn}</strong>?</p>
      <p class="brod">
        Lektionen tas bort ur lektionsdatabasen och historiken, tillsammans med
        resultatmappen. Filer du själv sparat någon annanstans påverkas inte.
      </p>
      <!-- Radera är avstängd medan DELETE:et är i luften. Ett andra DELETE mot
           samma lektion svarar 200 med folder_removed: false och är alltså helt
           tyst — läraren får ingen aning om att hon skickat två raderingar. -->
      <div class="knappar">
        <button type="button" class="ghost" onclick={avbrytRadera}>Avbryt</button>
        <button type="button" class="ghost fara" onclick={bekraftaRadera} disabled={insp.raderar}>
          Radera
        </button>
      </div>
    </div>
  {/if}

  <Kartotek lektioner={synliga} onRedigera={startaRedigering} onRadera={fragaRadera} />

  <!--
    ALLTID monterad, MEDVETET inte {#if}-grindad. Dialogen är ett native
    <dialog> som öppnas och stängs med showModal()/close() ur en effekt som
    speglar insp.editId — avmonteras komponenten i stängningsögonblicket hinner
    close() aldrig köras, och då uteblir webbläsarens återställning av fokus
    till knappen som öppnade den. Fokus hade i stället hamnat på <body>, vilket
    är precis det tangentbordstapp fokusfällan finns för att undvika.

    Stängd är ett <dialog> display:none och alltså borta ur både layout och
    tillgänglighetsträd — den kostar ingenting att låta stå.
  -->
  <RedigeraLektion />
</section>

<style>
  .view { max-width: 860px; margin: 0 auto; padding: 56px 24px 96px; }
  .eyebrow {
    font-family: var(--mono);
    font-size: 0.72rem;
    font-weight: 500;
    letter-spacing: 0.08em;
    color: var(--ink-3);
    margin: 0 0 14px;
  }
  .display {
    font-family: var(--sans);
    font-weight: 700;
    font-size: 1.5rem;
    line-height: 1.15;
    letter-spacing: -0.02em;
    color: var(--ink);
    margin: 0 0 10px;
  }
  .display .ser {
    font-family: var(--serif);
    font-style: italic;
    font-weight: 400;
    font-size: 2.375rem;
    line-height: 1.05;
    letter-spacing: -0.01em;
  }
  /* Klippande teknik — noden finns kvar i tillgänglighetsträdet men upptar
     ingen synlig plats, till skillnad från display:none. Identisk med
     TranskriberaView.svelte:197. */
  .fel-sr {
    position: absolute;
    width: 1px;
    height: 1px;
    overflow: hidden;
    clip-path: inset(50%);
    white-space: nowrap;
  }
  .lede {
    font-size: 1.03rem;
    color: var(--ink-2);
    margin: 0 0 26px;
    max-width: 52ch;
  }
  /* Den SYNLIGA felraden. :empty-regeln hör hemma här och ingen annanstans —
     se kommentaren vid noden. Identisk med .fel i TranskriberaView.svelte:192. */
  .fel { color: var(--bad); margin: 14px 0 0; }
  .fel:empty { display: none; }

  .bekraft {
    margin-top: 16px;
    background: var(--surface);
    border: 1px solid var(--line);
    border-left: 3px solid var(--bad);
    border-radius: 4px;
    padding: 14px 16px;
  }
  .bekraft:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
  .fraga { font-size: 1.03rem; color: var(--ink); margin: 0; overflow-wrap: anywhere; }
  .brod { font-size: 0.72rem; color: var(--ink-3); margin: 6px 0 0; max-width: 62ch; }
  .knappar { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 12px; }
  /* Identisk med .ghost i frontend/src/lib/transkribera/Korning.svelte:284-293. */
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
  /* Raderingen bär färgen, inte en egen form — samma grepp som på kortet. */
  .fara { color: var(--bad); }
  /* Väntläget ska SYNAS, annars ser en avstängd knapp bara trasig ut. */
  .ghost:disabled { opacity: 0.55; cursor: default; }
</style>
