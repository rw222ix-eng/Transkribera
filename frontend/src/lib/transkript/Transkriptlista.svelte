<script>
  import { tk } from './stores.svelte.js';
  import { fmtTid } from './tid.js';
</script>

<ol class="rader">
  <!-- Nyckeln är indexet. Listan byts ALLTID ut i sin helhet — segment sätts
       bara av actions vid öppning och efter ett lyckat sparande — så någon
       stabilare identitet finns inte att vinna något på. -->
  {#each tk.segment as s, i (i)}
    <li class="rad" data-rad={i}>
      <!-- Hela raden är EN knapp, inte ett <li onclick> med tidkoden som
           separat knapp som i gamla appen (app.js:5538 vs 5543-5549). Skälen:
           ett klick på ett icke-interaktivt element kräver svelte-ignore, och
           repot har noll sådana; en knapp per rad ger EN tabbstopp i stället
           för två; och det tillgängliga namnet blir tidkod plus text, vilket
           är bättre än "Hoppa till 05:12".
           user-select: text i CSS:en nedan håller markeringen vid liv. -->
      <button type="button" class="radknapp">
        <span class="tid">{fmtTid(s.start)}</span>
        <span class="text">{s.text}</span>
      </button>
    </li>
  {/each}
</ol>

<style>
  .rader {
    list-style: none;
    margin: 12px 0 0;
    padding: 0;
    overflow-y: auto;
    /* Listan är det som ska växa och skrolla i en flex-kolumn-dialog. */
    flex: 1 1 auto;
    min-height: 0;
  }
  .rad { margin: 0; }
  .radknapp {
    display: flex;
    align-items: baseline;
    gap: 12px;
    width: 100%;
    text-align: left;
    background: transparent;
    color: inherit;
    border: none;
    border-radius: 3px;
    padding: 5px 6px;
    font-family: inherit;
    font-size: inherit;
    line-height: inherit;
    cursor: pointer;
    /* Utan den här går transkriptet inte att markera med musen — knappar
       ärver user-select: none ur webbläsarens formulärregler. Lärare kopierar
       citat ur transkriptet. */
    user-select: text;
  }
  .radknapp:hover { background: var(--sunken); }
  /* Tidkoden är DATA, inte en mikroetikett: var(--sans) med tabular-nums,
     aldrig var(--mono). DESIGN.md §181-183, "The Mono-Is-Labels-Only Rule". */
  .tid {
    flex: 0 0 auto;
    font-family: var(--sans);
    font-size: 0.72rem;
    font-variant-numeric: tabular-nums;
    color: var(--ink-3);
  }
  .text { overflow-wrap: anywhere; }
</style>
