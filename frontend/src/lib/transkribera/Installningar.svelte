<script>
  // Guidens steg 2 — inställningar. Speglar viewTranscribe:s stepConfig-gren
  // (app/web/static/app.js:4472-4578), omstylad till designsystemet.
  import { tr, samladStatus } from './stores.svelte.js';
  import { goSource, startRun } from './actions.js';
  import Sprakval from './Sprakval.svelte';
  import Formatval from './Formatval.svelte';
  import Undertextval from './Undertextval.svelte';
  import Kolista from './Kolista.svelte';
  import { katalog } from './katalog.svelte.js';

  // tr.recording först: den är det enda av grindvillkoren läraren själv kan
  // åtgärda på plats, och den ska stå kvar tills hon gör det. De andra är
  // övergående (katalogen laddas) eller hör till en annan skärm.
  const startEtikett = $derived(
    tr.recording
      ? 'Stoppa inspelningen först'
      : !katalog.klar
        ? 'Laddar modeller …'
        : !tr.model
          ? 'Ladda ner en modell först'
          : tr.queue.length > 1
            ? 'Starta · ' + tr.queue.length + ' filer'
            : 'Starta transkribering',
  );
</script>

<p class="eyebrow">STEG 2 — INSTÄLLNINGAR</p>
<h1 class="display">Så ska det <span class="ser">låta</span></h1>
<p class="lede">
  Välj språk och format — rätt modell väljs automatiskt, allt körs lokalt på din dator.
</p>

<!--
  Synlig kopia av statusraden som TranskriberaView hoistar som en dold
  live-region (plan A2-fixrunda, punkt 1) — t.ex. downloadAudioModel i
  actions.js kan skriva hit medan läraren står här på steg 2. Riktig textnod,
  INTE CSS-genererat innehåll — se motiveringen i TranskriberaView.svelte.
  e2e-testerna skiljer den här synliga kopian från live-regionen via
  data-testid="statusrad" i stället för att leta upp texten två gånger.

  Raden bär HELA samladStatus(), alltså även tr.recError — inte bara
  tr.fileError. Utan det blev inspelningsfelet osynligt just när det betyder
  mest: faller den SISTA biten är sekvensen chunk fallerar → tr.recError sätts
  → slutforInspelning → addFiles sätter tr.step = 'config' (actions.js:33) →
  <Inspelning /> avmonteras med sin .rec-fel-rad. Beskedet försvann alltså i
  praktiken samma ögonblick det skrevs, och det är exakt fallet "filen köades
  med ett hål i ljudet". Skärmläsaren fick det ändå via den hoistade regionen;
  en seende lärare kunde missa det helt. Raden är fortfarande aria-hidden, så
  bara EN nod är exponerad för skärmläsare.

  class:info stängs av när tr.recError är satt: tr.fileNoteArt hör till
  filkanalen, och dess neutrala "info"-läge (dubblettbeskedet) får inte måla
  ett inspelningsfel som en lugn notis.
-->
<p class="fel" class:info={tr.fileNoteArt === 'info' && !tr.recError} aria-hidden="true" data-testid="statusrad">{samladStatus()}</p>

<div class="ko-huvud">
  <span class="label">Filer i kö</span>
  <span class="antal">{tr.queue.length}</span>
  <span class="spacer"></span>
  <button type="button" class="ghost" onclick={goSource}>Lägg till fler</button>
</div>

<Kolista />

<Sprakval />
<Formatval />
<Undertextval />

<div class="start">
  <!--
    tr.recording grindar starten, precis som den grindar "Nästa: inställningar"
    på steg 1 (TranskriberaView.svelte). Grinden där räcker INTE: addFiles sätter
    tr.step = 'config' ovillkorligt (actions.js), så "ett exempel", en länk eller
    en släppt fil tar guiden hit mitt i en pågående inspelning utan att passera
    den knappen.

    Utan den här raden startar alltså en körning medan mikrofonen är på: steg 3
    avmonterar <Inspelning />, så Stoppa / Avbryt / Markera försvinner, och
    inspelningen kan inte avslutas förrän körningen är klar. Stegindikatorn är
    inte klickbar under en körning och startRun returnerar tyst — läraren har
    ingen väg tillbaka till lektionen hon fortfarande spelar in.

    Grinden är en spärr, inte ett förbud: inspelningen fortsätter som vanligt,
    det är bara starten som väntar tills lektionen är stoppad och köad.
  -->
  <button
    type="button"
    class="primar"
    onclick={startRun}
    disabled={!katalog.klar || !tr.model || !tr.queue.length || tr.recording}
  >{startEtikett}</button>
</div>

<style>
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
  .lede { max-width: 62ch; color: var(--ink-2); margin: 0 0 28px; }
  .fel { color: var(--bad); margin: 0 0 20px; }
  .fel:empty { display: none; }
  .fel.info { color: var(--ink-3); }
  .ko-huvud {
    display: flex;
    align-items: baseline;
    gap: 12px;
    flex-wrap: wrap;
    margin-bottom: 4px;
  }
  .label {
    font-family: var(--mono);
    font-size: 0.72rem;
    font-weight: 500;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: var(--ink-3);
  }
  .antal { color: var(--ink); font-variant-numeric: tabular-nums; }
  .spacer { flex: 1; }
  .ghost {
    background: transparent;
    color: var(--ink);
    border: 1px solid var(--line-2);
    border-radius: 4px;
    padding: 7px 14px;
    font-family: inherit;
    font-size: inherit;
    cursor: pointer;
  }
  .start {
    display: flex;
    align-items: center;
    gap: 14px;
    flex-wrap: wrap;
    margin-top: 28px;
  }
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
