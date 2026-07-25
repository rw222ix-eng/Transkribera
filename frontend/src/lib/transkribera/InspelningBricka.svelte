<script>
  // Topbar-bricka som visar att en inspelning pågår, oavsett vilken flik
  // läraren står på. Gamla appen har ingen: setTab (app.js:602) byter flik utan
  // både spärr och indikator, så inspelningen fortsätter helt osynligt.
  // Inspelningen SKA fortsätta — det är hela poängen med en lektionsinspelning,
  // och att avbryta den vid ett flikbyte vore värre än defekten — men den får
  // inte vara osynlig. Brickan är den saknade indikatorn.
  //
  // Brickan är MEDVETET ingen live-region. Guidens enda role="status" är den
  // hoistade .fel-sr i TranskriberaView.svelte; två samtidigt muterande
  // regioner läses i oförutsägbar ordning. Texten här muterar dessutom varje
  // sekund — en live-region hade blivit en skärmläsare som räknar högt genom
  // hela lektionen. Tillståndet når skärmläsaren via widgetens egna knappar
  // ("Stoppa och lägg till", "Markera (2)") på källsteget.
  import { tr } from './stores.svelte.js';
  import { setTab } from '../shell/nav.svelte.js';
  import { goSource } from './actions.js';

  // Samma mm:ss som widgetens egen tid (Inspelning.svelte). Duplikationen är
  // avsiktlig: brickan lever i topbaren och måste fungera även när
  // <Inspelning /> är avmonterad — det är precis det läget den finns för.
  const tid = $derived.by(() => {
    const n = Math.max(0, Math.floor(tr.recElapsed || 0));
    return `${String(Math.floor(n / 60)).padStart(2, '0')}:${String(n % 60).padStart(2, '0')}`;
  });

  // goSource(), INTE nyTranskribering(): klicket ska ta läraren till källsteget
  // där Stoppa / Avbryt / Markera bor, utan att röra kön. Hon kan mycket väl
  // hålla på att bygga en kö medan lektionen spelas in — nyTranskribering
  // hade tömt den.
  function tillInspelningen() {
    setTab('transkribera');
    goSource();
  }
</script>

{#if tr.recording}
  <button type="button" class="bricka" title="Till inspelningen" onclick={tillInspelningen}>
    <span class="prick" aria-hidden="true"></span>
    <span class="txt">Spelar in</span>
    <span class="tid">{tid}</span>
  </button>
{/if}

<style>
  /* Samma pappersskikt och hårfina linje som widgetens .ruta, i topbarens
     mindre skala. 3px hörn — inom DESIGN.md:s 2-5px, och en aning mjukare än
     flikramens 5px så brickan läses som ett påhäng, inte som en fjärde flik. */
  .bricka {
    flex: 0 0 auto;
    display: inline-flex;
    align-items: center;
    gap: 8px;
    padding: 6px 12px;
    background: var(--surface);
    border: 1px solid var(--line);
    border-radius: 3px;
    font-family: inherit;
    font-size: 1.03rem;
    color: var(--ink);
    white-space: nowrap;
    cursor: pointer;
  }
  .bricka:hover { border-color: var(--line-2); }
  /* 8px bred, 4px radie = en exakt cirkel. Tokenet är var(--bad), som DESIGN.md
     reserverar för fel — se den utförliga motiveringen vid .prick i
     Inspelning.svelte. Kort: en bricka som inte omedelbart läses som "spelar
     in" fyller ingen funktion, och det är just den här pricken hela
     komponenten bygger sitt igenkänningsvärde på. Avsteget stannar vid
     pricken; resten av brickan är vanligt papper och bläck. */
  .prick {
    width: 8px;
    height: 8px;
    border-radius: 4px;
    background: var(--bad);
    flex: none;
    animation: pulsera 1.6s ease-in-out infinite;
  }
  /* Komponent-scopad, precis som widgetens. Gamla appens globala `pulse` i
     style.css hör till den gamla appen och får inte dupliceras hit. */
  @keyframes pulsera {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.35; }
  }
  @media (prefers-reduced-motion: reduce) {
    .prick { animation: none; }
  }
  .txt { color: var(--ink-2); }
  /* Siffrorna byts varje sekund. Tabulära siffror håller brickan stilla i
     stället för att låta topbaren rycka i bredd vid varje tick — och det görs
     med font-variant-numeric, inte genom att byta till var(--mono): brickan
     bär ett meningsfragment, och mono är reserverat för versala
     mikroetiketter. */
  .tid { color: var(--ink); font-variant-numeric: tabular-nums; }
</style>
