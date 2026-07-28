<script>
  // Transkriberingsguiden, steg 1 — Källa. Speglar viewTranscribe:s
  // stepSource-gren (app/web/static/app.js:4383-4470), omstylad till
  // designsystemet. Steg 2 kom i plan A2 (<Installningar />) och steg 3 i plan
  // A3 (<Korning />) — båda renderas ur stegväxlingen längst ned i den här
  // filen, så guiden är komplett fram till och med körningen.
  import { tr, samladStatus } from './stores.svelte.js';
  import { addSample, addSampleCorrupt, goConfig, loadAudioModel } from './actions.js';
  import Stegindikator from './Stegindikator.svelte';
  import Dropzone from './Dropzone.svelte';
  import LankFalt from './LankFalt.svelte';
  import Kolista from './Kolista.svelte';
  import Inspelning from './Inspelning.svelte';
  import Installningar from './Installningar.svelte';
  import Korning from './Korning.svelte';
  import { loadKatalog } from './katalog.svelte.js';

  // Katalogen och ljudmodellens status hämtas en gång när vyn monteras —
  // skalet håller vyn monterad hela sessionen, så det här körs inte om vid
  // flikbyten eller stegväxlingar. Ett fel i katalogen (offline eller
  // trasig hårdvaruskanning, se app/gpu_arbiter.py) skulle annars lämna
  // CTA:n i Installningar.svelte fastnad på "Laddar modeller …" utan
  // förklaring.
  // Skälet till att "Nästa: inställningar" är låst, i samma ordning som
  // knappens disabled-uttryck utvärderar villkoren. Pågående inspelning
  // först: den grindar även när kön INTE är tom, och är därför det svar som
  // faktiskt förklarar en låst knapp bredvid en fylld kö.
  const lasSkal = $derived(
    tr.recording
      ? 'Stoppa eller avbryt inspelningen först.'
      : !tr.queue.length
        ? 'Lägg till minst en fil, en länk eller en inspelning först.'
        : '',
  );

  $effect(() => {
    loadKatalog().then((ok) => {
      if (ok === false) {
        tr.fileNoteArt = 'fel';
        tr.fileError = 'Kunde inte läsa modellistan — starta om appen och försök igen.';
      }
    });
    loadAudioModel();
  });
</script>

<section class="view">
  <Stegindikator />

  <!--
    En enda hoistad live-region bär texten för skärmläsare, oavsett vilket
    steg läraren står på — annars hinner ett fel som skrivs medan hon står på
    steg 2 (t.ex. downloadAudioModel i actions.js) aldrig annonseras. Noden
    är permanent i DOM:en (aldrig {#if}) och bara VISUELLT gömd med en
    klippande teknik — INTE display:none, som tar bort den ur
    tillgänglighetsträdet och gör att role="status" inte längre kan
    annonsera mutationen (plan A2-fixrunda, punkt 1).
    Varje steg renderar därutöver sin egen SYNLIGA kopia av samma text, nära
    fältet den gäller, markerad aria-hidden="true" — bara live-regionen ovan
    ska annonseras, inte båda. Sammanvävningen görs av samladStatus() i
    stores.svelte.js, så att region och kopia inte kan divergera.

    Regionen bär BÅDA felkanalerna: guidens tr.fileError och inspelningens
    tr.recError. Inspelningen får medvetet ingen egen live-region — en region
    som monteras in i DOM:en samtidigt som sin text annonseras inte pålitligt
    (samma mönster som fälldes i A2 och i A3:s slutgranskning), och två
    samtidigt muterande role="status" läses dessutom i oförutsägbar ordning.

    NÄR BÅDA ÄR SATTA VÄVS DE SAMMAN — ingen av dem väljs bort. En tidigare
    version valde en av dem med "tr.recError || tr.fileError" och tystade
    därmed hela filkanalen: tr.recError nollställs BARA i startRecording och
    cancelRecording (inspelning.js), alltså bara när läraren själv
    trycker en knapp. Ett getUserMedia-fel eller ett misslyckat slutförande
    blev därför stående resten av sessionen, och så länge det stod kvar
    utvärderades uttrycket till samma sträng oavsett vad som hände med
    tr.fileError — textnoden muterade inte, och role="status" annonserade
    ingenting. Konkret felfall: mikrofonen blockeras på steg 1, läraren lägger
    till en fil och går till steg 2, "Ladda ner modell" faller och
    actions.js skriver tr.fileError — och beskedet nådde aldrig fram. Det är
    exakt scenariot regionen hoistades för. Widgeten är dessutom avmonterad på
    steg 2, så det klibbiga tr.recError var samtidigt osynligt på skärmen
    medan det tystade den enda skärmläsarkanalen.

    Priset för sammanvävningen är en längre uppläsning när båda kanalerna står
    satta samtidigt. Det är en dubblering, inte en tyst förlust — rätt håll att
    fela åt. Växer felkanalerna bortom två bör det här göras om till en riktig
    meddelandekö i stället för en filter/join.

    Hur segmenten fogas ihop (och varför punkten trimmas på alla utom det
    sista) står vid samladStatus() i stores.svelte.js.
  -->
  <p class="fel-sr" role="status">{samladStatus()}</p>

  {#if tr.step === 'source'}
    <p class="eyebrow">STEG 1 — KÄLLA</p>
    <h1 class="display">Vad vill du <span class="ser">transkribera?</span></h1>
    <p class="lede">
      Dra in en eller flera filer, eller välj från datorn — allt körs på din egen dator.
    </p>

    <Dropzone />
    <LankFalt />

    <p class="prova">
      Eller prova med
      <button type="button" class="lank" onclick={addSample}>ett exempel</button>
      <button type="button" class="lank" onclick={addSampleCorrupt}>skadad_inspelning.m4a</button>
    </p>

    <Inspelning />

    <!--
      Synlig kopia av live-regionen ovan, i den position raden hade före
      hoisten till plan A2-fixrunda: direkt under källfälten. Riktig textnod,
      INTE CSS-genererat innehåll (content: attr(...)) — det gick inte att
      markera, kopiera eller Ctrl+F-söka, och skulle försvinna helt spårlöst
      om stilmallen någonsin saknades vid paketering. Raden är redan
      aria-hidden så skärmläsare struntar i den; det är live-regionen ovan
      som annonseras. e2e-testerna skiljer den här synliga kopian från
      live-regionen via data-testid="statusrad" i stället för att leta upp
      texten två gånger (se e2e/transkribera-kalla.spec.mjs).

      HÄR — och bara här — bär den synliga kopian enbart tr.fileError, inte
      samladStatus(). Skälet: <Inspelning /> är monterad precis ovanför på det
      här steget och visar tr.recError på sin egen .rec-fel-rad. Vävde den
      här raden in inspelningsfelet också skulle det stå två gånger på
      skärmen, med tre raders mellanrum. Steg 2 har inte den raden — där
      renderas samladStatus(), se Installningar.svelte.
    -->
    <p class={['fel', { info: tr.fileNoteArt === 'info' }]} aria-hidden="true" data-testid="statusrad">{tr.fileError}</p>

    {#if tr.queue.length}
      <div class="ko-wrap">
        <Kolista />
      </div>
      <p class="antal">{tr.queue.length} {tr.queue.length === 1 ? 'fil' : 'filer'} i kön.</p>
    {/if}

    <p class="vidare">
      <!--
        tr.recording grindar knappen: ligger redan en fil i kön går det annars
        att lämna steg 1 MITT I en pågående inspelning. Steg 2 avmonterar
        <Inspelning />, men modultillståndet i inspelning.js lever kvar
        — mikrofonen är på, timern tickar, bitarna POSTas var fjärde sekund och
        beforeunload-vakten blockerar sidstängning utan att något syns som
        förklarar varför. Widgetens egna knappar (Stoppa / Avbryt) är då enda
        vägen ur läget, och de är inte längre monterade.
      -->
      <button
        type="button"
        class="primar"
        disabled={!tr.queue.length || tr.recording}
        aria-describedby={lasSkal ? 'nasta-skal' : undefined}
        onclick={goConfig}
      >Nästa: inställningar</button>
      <!--
        SKÄLET TILL LÅSNINGEN, utskrivet. En grå knapp utan förklaring är
        appens enda ställe där läraren kan bli stående utan att veta varför —
        Planering skriver redan ut sitt skäl ("Beskriv momentet ovan så kan
        tavlan skrivas", BuildPanel.svelte), och det här är samma mönster på
        samma sorts knapp.

        INGEN role och ingen live-region: raden är en statisk förklaring av
        vad knappen väntar på, inte ett svar på något läraren just gjorde.
        Vyns enda annonserande nod är p.fel-sr ovan, och så ska det förbli
        (samma hållning som ärlighetsvakten i InspelningarView.svelte).

        aria-describedby knyter den till knappen i stället: en skärmläsare som
        landar på den låsta knappen får skälet uppläst direkt efter namnet,
        vilket är precis när det behövs.
      -->
      {#if lasSkal}
        <span class="skal" id="nasta-skal">{lasSkal}</span>
      {/if}
    </p>
  {:else if tr.step === 'config'}
    <Installningar />
  {:else}
    <Korning />
  {/if}
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
  .lede { max-width: 62ch; color: var(--ink-2); margin: 0; }
  .prova { color: var(--ink-3); margin: 20px 0 0; display: flex; gap: 12px; flex-wrap: wrap; }
  .lank {
    border: none;
    background: transparent;
    color: var(--ink-2);
    font-family: inherit;
    font-size: inherit;
    padding: 0;
    cursor: pointer;
    text-decoration: underline;
    text-underline-offset: 3px;
  }
  .lank:hover { color: var(--ink); }
  .fel { color: var(--bad); margin: 14px 0 0; }
  .fel:empty { display: none; }
  .fel.info { color: var(--ink-3); }
  /* Klippande teknik — noden finns kvar i tillgänglighetsträdet men upptar
     ingen synlig plats, till skillnad från display:none. */
  .fel-sr {
    position: absolute;
    width: 1px;
    height: 1px;
    overflow: hidden;
    clip-path: inset(50%);
    white-space: nowrap;
  }
  .ko-wrap { margin: 20px 0 0; }
  .antal { color: var(--ink-3); margin: 10px 0 0; }
  /* Knapp och skäl på samma baslinjerad, inte skälet under: raden ska läsas
     som "knappen väntar på det här", inte som en ny brödtextrad. */
  .vidare {
    margin: 24px 0 0;
    display: flex;
    align-items: center;
    gap: 14px;
    flex-wrap: wrap;
  }
  .skal { color: var(--ink-3); }
  .primar {
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
  .primar:disabled { opacity: 0.55; cursor: default; }
</style>
