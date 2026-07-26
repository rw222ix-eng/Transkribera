<script>
  // Inspelningar-fliken: kartoteket över transkriberade lektioner. Speglar
  // viewRecordings (app/web/static/app.js:4776-4956), omstylad till
  // designsystemet — gamla vyn är ren inline-CSS med 9-14px hörn.
  import { untrack } from 'svelte';
  import { insp } from './stores.svelte.js';
  import {
    laddaLektioner,
    laddaOrg,
    kollaHistorik,
    startaRedigering,
    fragaRadera,
    avbrytRadera,
    bekraftaRadera,
  } from './actions.js';
  import Filterrad from './Filterrad.svelte';
  import Kartotek from './Kartotek.svelte';
  import RedigeraLektion from './RedigeraLektion.svelte';
  import { nav } from '../shell/nav.svelte.js';

  // Raderingsbekräftelsen är ett NATIVE <dialog>, byggt precis som
  // RedigeraLektion.svelte och av samma skäl — läs kommentarerna där, de gäller
  // ord för ord även här.
  //
  // Den var fram till nu en handgjord tabindex="-1"-div: ingen fokusfälla, inget
  // Escape, och fokus tappades till <body> när blocket avmonterades. Att just
  // den DESTRUKTIVA av vyns två rutor saknade allt det redigeringsdialogen fick
  // var inkonsekvensen B2-B5 annars ärvt.
  //
  // ALLTID MONTERAD, inte {#if}-grindad: avmonteras komponenten i
  // stängningsögonblicket hinner close() aldrig köras, och då uteblir
  // webbläsarens återställning av fokus till Radera-knappen som öppnade rutan —
  // exakt det tangentbordstapp bytet gjordes för att stoppa. Stängd är ett
  // <dialog> display:none och alltså borta ur både layout och
  // tillgänglighetsträd; den kostar ingenting att låta stå.
  //
  // nav.tab ÄR MED I VILLKORET av samma skäl som i RedigeraLektion: en förfader
  // med display:none gör att dialogen inte RITAS men lämnar den `open`, och
  // showModal() håller då fortfarande hela dokumentet inert. Appen slutar svara
  // utan att något på skärmen förklarar varför.
  let bekraftRuta = $state(null);
  $effect(() => {
    if (!bekraftRuta) return;
    if (insp.raderId !== null && nav.tab === 'inspelningar') {
      if (!bekraftRuta.open) {
        bekraftRuta.showModal();
        // Rutan själv, inte en knapp: då läses frågan och följderna innan
        // fokus står på något som går att trycka på. showModal() hade annars
        // fokuserat Avbryt direkt.
        bekraftRuta.focus();
      }
    } else if (bekraftRuta.open) {
      bekraftRuta.close();
    }
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
  //
  // kollaHistorik() ligger MED här, av samma skäl som de två andra: den mäter
  // hela arkivet mot hela historiken, och svaret ska vara färskt varje gång
  // läraren kommer hit — en lektion som just transkriberats kan vara precis den
  // som saknar rad.
  $effect(() => {
    if (nav.tab !== 'inspelningar') return;
    untrack(() => {
      laddaOrg();
      laddaLektioner();
      kollaHistorik();
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

  <Kartotek lektioner={synliga} onRedigera={startaRedigering} onRadera={fragaRadera} />

  <!--
    TVÅ TOMTILLSTÅND, MEDVETET ÅTSKILDA. Gamla vyn skiljer på dem
    (app.js:4903-4905 respektive :4949-4951) och det gör den här också: det
    första är "du har ingenting", det andra "du har saker men gömde dem". Slås
    de ihop får en lärare med fullt arkiv beskedet att hon aldrig spelat in
    något.

    FILTERTERMERNA I FÖRSTA VILLKORET är inte pynt. Efter Task 3 är
    insp.lessons inte hela arkivet utan arkivet EFTER serverfiltrering: klass
    och kurs ligger i querysträngen till /api/lessons, så att välja en klass
    utan lektioner sätter insp.lessons = []. Utan
    !insp.filterGroup && !insp.filterCourse hade just den läraren fått "Inga
    inspelningar än" — exakt den hopblandning det här steget finns för att
    förbjuda. MÅNADEN är lika medvetet FRÅNVARANDE: den filtrerar på klienten,
    så är listan tom kan den inte vara orsaken, och är listan inte tom faller
    fallet till andra grenen ändå.

    insp.laddar vaktar BÅDA grenarna, så inget av beskeden blinkar förbi under
    en omhämtning — och en omhämtning är precis vad ett klass- eller kursbyte
    utlöser.
  -->
  {#if !insp.laddar && !insp.lessons.length && !insp.filterGroup && !insp.filterCourse}
    <p class="tomt">
      Inga inspelningar än. Transkribera en lektion så dyker den upp här.
    </p>
  {:else if !insp.laddar && !synliga.length}
    <p class="tomt">Inga inspelningar matchar dina filter.</p>
  {/if}

  <!--
    ÄRLIGHETSVAKTEN. B1 släpper gamla appens "Tidigare körningar"-lista, som
    var det enda stället en historikpost UTAN lektionsrad syntes. En sådan post
    kan uppstå på riktigt: create_lesson ligger i ett try/except som bara
    loggar (server.py:682-696), uttryckligen för att en DB-miss aldrig ska
    fälla en lyckad transkribering. Hellre säga skillnaden med ett antal än att
    tyst dölja den.

    Ingen egen live-region och ingen role: raden är ett stillsamt konstaterande
    som ritas när vyn hämtas, inte ett svar på något läraren just gjorde. Vyns
    enda annonserande nod är p.fel-sr ovan, och så ska det förbli.

    Böjningen görs på BÅDA ställena. Briefens utkast böjde bara
    "inspelning(ar) finns" och lät andra meningen stå kvar i plural, vilket ger
    "1 inspelning finns ... De går att öppna" — fel numerus på ett pronomen som
    syftar tillbaka på ett ental.
  -->
  {#if insp.historikExtra}
    <p class="notis">
      {insp.historikExtra}
      {insp.historikExtra === 1 ? 'inspelning finns' : 'inspelningar finns'}
      i historiken men saknas i kartoteket.
      {insp.historikExtra === 1 ? 'Den går' : 'De går'} att öppna i den gamla appen.
    </p>
  {/if}

  <!--
    Vad B1 INTE gör, utskrivet i stället för antytt. Samma hållning som plan
    A3:s klarbesked: säg var läraren kan gå, navigera inte till en platshållare.
    Transkriptvyn kommer i B2 och lektionschatten i B4.
  -->
  <p class="senare">
    Att öppna en lektion — transkript, ljud och chatt — migreras i en senare
    plan. Tills dess finns den i den gamla appen.
  </p>

  <!--
    Raderingsbekräftelsen. MEDVETET ingen confirm(): den går varken att styla
    eller att testa, och den blockerar dessutom hela renderaren.

    Ligger HÄR, sist bland innehållet och intill den andra dialogen, i stället
    för ovanför kartoteket. Den gamla placeringen fanns för att en inmonterad div
    annars hamnade FÖRE kortet läraren just tryckte på i DOM-ordningen — ett
    Shift+Tab-tapp. Med showModal() lyfts rutan till top-layer och webbläsaren
    fokusfäller inuti den, så DOM-ordningen styr ingenting längre. Kvar är att de
    två alltid monterade dialogerna står tillsammans.

    aria-label och inte aria-labelledby på frågan: skärmläsaren läser namnet när
    fokus landar på rutan och sedan innehållet, så lektionsnamnet hörs ändå — en
    labelledby hade läst frågan två gånger. Samma val som RedigeraLektion.
  -->
  <dialog
    class="bekraft"
    aria-label="Bekräfta radering"
    tabindex="-1"
    bind:this={bekraftRuta}
    onclose={avbrytRadera}
  >
    <p class="fraga">Ta bort <strong>{insp.raderNamn}</strong>?</p>
    <p class="brod">
      Lektionen tas bort ur lektionsdatabasen och historiken, tillsammans med
      resultatmappen. Filer du själv sparat någon annanstans påverkas inte.
    </p>
    <!-- Radera är avstängd medan DELETE:et mot DEN HÄR lektionen är i luften.
         Ett andra DELETE mot samma lektion svarar 200 med folder_removed:
         false och är alltså helt tyst — läraren får ingen aning om att hon
         skickat två raderingar. Jämförelsen mot raderId, inte en
         sanningskontroll: insp.raderar bär id:t så att ett långsamt DELETE
         inte stänger av knappen för nästa lektion läraren hinner fråga om
         (flaggan står kvar genom laddaLektioner() efteråt). -->
    <div class="knappar">
      <button type="button" class="ghost" onclick={avbrytRadera}>Avbryt</button>
      <button
        type="button"
        class="ghost fara"
        onclick={bekraftaRadera}
        disabled={insp.raderar === insp.raderId}
      >
        Radera
      </button>
    </div>
  </dialog>

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

  /* Båda tomtillstånden bär samma form — skillnaden ligger i TEXTEN, inte i
     utseendet. Löpande text i typrampens brödstorlek, ingen ram och ingen
     ikon: ett tomt kartotek är ett normalläge, inte ett fel. */
  .tomt {
    font-size: 1.03rem;
    color: var(--ink-2);
    margin: 28px 0 0;
    max-width: 52ch;
  }
  /* Senare-raden är en fotnot till kartoteket — den beskriver planen, inte
     lektionerna. Mikrostorleken och --ink-3 håller den tillbakadragen. */
  .notis,
  .senare {
    margin: 18px 0 0;
    max-width: 62ch;
  }
  .senare {
    font-size: 0.72rem;
    color: var(--ink-3);
  }
  /* Ärlighetsvakten är däremot BRÖDTEXT: en hel mening som säger att något
     faktiskt saknas, och som läraren ska kunna läsa. 0.72rem/--ink-3 är
     reserverat för korta versala mikroetiketter (KLASS, KURS, MÅNAD,
     eyebrow:erna) — sätts löpande text i den rampen blir beskedet svårläst och
     ser dessutom ut som en etikett. Samma brödrytm som .lede och .tomt. */
  .notis {
    font-size: 1.03rem;
    color: var(--ink-2);
  }
  /* INGEN border-left-stripe här, och ingen på .bekraft nedan. DESIGN.md §6
     namnger mönstret uttryckligen: "Don't use a border-left/border-right
     colored stripe as an accent". De två var de ENDA förekomsterna i hela
     Svelte-frontenden. Vakten skiljs redan från senare-raden av brödstorleken
     och --ink-2 (se ovan); rutan nedan har redan en hel ram, och var(--bad) på
     rubriken bär allvaret. */
  /* Ingen egen skärm, inget z-index och ingen centrering: showModal() lyfter
     rutan till top-layer och webbläsarens <dialog>-regel
     (position: fixed; inset: 0; margin: auto) centrerar den. Formen är i övrigt
     densamma som .ruta i RedigeraLektion.svelte.

     color sätts UTTRYCKLIGEN — webbläsarens <dialog>-regel sätter
     color: CanvasText, som bryter arvet från body. Samma fälla som .ruta. */
  .bekraft {
    width: min(94vw, 460px);
    max-height: 90vh;
    overflow: auto;
    background: var(--surface);
    color: var(--ink);
    border: 1px solid var(--line);
    border-radius: 4px;
    box-shadow: var(--shadow);
    padding: 14px 16px;
  }
  /* Samma dimning och samma 42 % som redigeringsdialogens. */
  .bekraft::backdrop { background: color-mix(in srgb, var(--ink) 42%, transparent); }
  .bekraft:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
  /* Rubriken bär allvaret, i stället för den borttagna stripen. Kontrollmätt
     mot båda temana: #C8463A på #FFFFFF ger 4,78:1 och #E0796A på #1C1D15 ger
     5,75:1 — båda över AA:s 4,5:1 för brödtext. */
  .fraga { font-size: 1.03rem; color: var(--bad); margin: 0; overflow-wrap: anywhere; }
  /* BRÖDTEXT, inte etikett — meningen räknar upp vad som faktiskt raderas och
     är det enda läraren har att gå på innan hon trycker på en oåterkallelig
     knapp. 0.72rem/--ink-3 hör till de versala mikroetiketterna och gör just
     den här texten svårast att läsa av allt i vyn. */
  .brod { font-size: 1.03rem; color: var(--ink-2); margin: 6px 0 0; max-width: 62ch; }
  /* justify-content: flex-end speglar RedigeraLektion.svelte:277-284. Som
     inmonterat block i sidflödet var vänsterställt naturligt; som centrerad
     modal vid sidan av den andra dialogen blir skillnaden bara en synlig
     inkonsekvens mellan två rutor som ska se likadana ut. */
  .knappar {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    justify-content: flex-end;
    margin-top: 12px;
  }
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
