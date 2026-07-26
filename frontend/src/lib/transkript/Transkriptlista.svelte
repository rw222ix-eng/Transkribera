<script>
  import { tk } from './stores.svelte.js';
  import { fmtTid, aktuellRad } from './tid.js';
  import { hoppaTillRad } from './actions.js';
  import { styckaRad } from './sok.js';

  let { perRad, traffar } = $props();

  const aktuell = $derived(aktuellRad(tk.segment, tk.tid));

  function klick(i) {
    // En pågående textmarkering är inte ett hopp. Utan vakten blir varje
    // försök att kopiera ett citat en spolning.
    const markering = window.getSelection();
    if (markering && !markering.isCollapsed) return;
    hoppaTillRad(i);
  }

  /**
   * Skriver in radens text EN gång. Låter man Svelte rita om noden medan den
   * redigeras hoppar markören till början vid varje tangenttryck — samma
   * problem morphdom löste med data-eline (app.js:4252), löst på Sveltes sätt:
   * blocket renderar tomt och innehållet sätts här.
   */
  function fyll(el, i) {
    el.textContent = i in tk.andringar ? tk.andringar[i] : (tk.segment[i]?.text ?? '');
    return {};
  }

  let lista = $state(null);

  /**
   * Släpper följandet när LÄRAREN flyttar sig, aldrig när vi själva gör det.
   *
   * Lyssnarna bindes imperativt i en use:-action i stället för som
   * onwheel/onkeydown-attribut: som attribut hade de fällt
   * a11y_no_noninteractive_element_interactions på <ol>, och repot har noll
   * svelte-ignore. Det är dessutom sant — det här är gester, inte affordanser.
   *
   * scroll-eventet duger INTE: det kan inte skilja vår egen scrollIntoView
   * från lärarens, så följandet hade stängt av sig självt vid första raden.
   */
  function slappVidEgenScroll(el) {
    const NAVTANGENTER = ['ArrowUp', 'ArrowDown', 'PageUp', 'PageDown', 'Home', 'End'];
    const slapp = () => { tk.foljer = false; };
    // pointerdown fyras även när man klickar en rad — men radklicket kallar
    // hoppaTillRad, som sätter tillbaka foljer. Ordningen (pointerdown före
    // click) gör att återtagningen vinner.
    const paTangent = (e) => { if (NAVTANGENTER.includes(e.key)) tk.foljer = false; };

    el.addEventListener('wheel', slapp, { passive: true });
    el.addEventListener('touchmove', slapp, { passive: true });
    el.addEventListener('pointerdown', slapp);
    el.addEventListener('keydown', paTangent);
    return {
      destroy() {
        el.removeEventListener('wheel', slapp);
        el.removeEventListener('touchmove', slapp);
        el.removeEventListener('pointerdown', slapp);
        el.removeEventListener('keydown', paTangent);
      },
    };
  }

  $effect(() => {
    const i = aktuell;
    if (!tk.foljer || !lista || i < 0) return;
    const rad = lista.querySelector(`[data-rad="${i}"]`);
    rad?.scrollIntoView({ block: 'center', behavior: 'smooth' });
  });

  $effect(() => {
    const t = traffar[tk.traffIndex];
    if (!t || !lista) return;
    lista.querySelector(`[data-rad="${t.rad}"]`)?.scrollIntoView({ block: 'center', behavior: 'smooth' });
  });
</script>

<ol class="rader" bind:this={lista} use:slappVidEgenScroll>
  <!-- Nyckeln är indexet. Listan byts ALLTID ut i sin helhet — segment sätts
       bara av actions vid öppning och efter ett lyckat sparande — så någon
       stabilare identitet finns inte att vinna något på. -->
  {#each tk.segment as s, i (i)}
    <li class="rad" class:aktuell={!tk.redigerar && i === aktuell} data-rad={i}>
      {#if tk.redigerar}
        <!-- contenteditable kan inte bo i en knapp, och det finns inget att
             hoppa till här ändå: ljudet pausas när redigeringen slås på. -->
        <div class="radrad">
          <span class="tid">{fmtTid(s.start)}</span>
          <div
            class="text redigerbar"
            contenteditable="true"
            role="textbox"
            aria-label="Rad {i + 1}"
            use:fyll={i}
            oninput={(e) => (tk.andringar[i] = e.currentTarget.textContent)}
          ></div>
        </div>
      {:else}
        <!-- Hela raden är EN knapp, inte ett <li onclick> med tidkoden som
             separat knapp som i gamla appen (app.js:5538 vs 5543-5549). Skälen:
             ett klick på ett icke-interaktivt element kräver svelte-ignore, och
             repot har noll sådana; en knapp per rad ger EN tabbstopp i stället
             för två; och det tillgängliga namnet blir tidkod plus text, vilket
             är bättre än "Hoppa till 05:12".
             user-select: text i CSS:en nedan håller markeringen vid liv. -->
        <button type="button" class="radknapp" onclick={() => klick(i)}>
          <span class="tid">{fmtTid(s.start)}</span>
          <span class="text">{#each styckaRad(s.text, perRad.get(i), tk.traffIndex) as bit}{#if bit.traff}<mark class:aktuell={bit.aktuell}>{bit.text}</mark>{:else}{bit.text}{/if}{/each}</span>
        </button>
      {/if}
    </li>
  {/each}
</ol>

<!-- ALLTID monterad (inte {#if}-grindad som planen anger) — se motiveringen
     vid .folj-rad nedan. class:dold döljer den utan att avmontera. -->
<div class="folj-rad" class:dold={tk.foljer}>
  <button type="button" class="ghost" onclick={() => (tk.foljer = true)}>Följ uppspelningen</button>
</div>

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
  /* Bara bakgrunden, ingen färgad vänsterkant — DESIGN.md §Don't. */
  .rad.aktuell .radknapp { background: var(--accent-weak); }
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
  .radrad {
    display: flex;
    align-items: baseline;
    gap: 12px;
    padding: 5px 6px;
  }
  .redigerbar {
    flex: 1 1 auto;
    border: 1px solid var(--line-2);
    border-radius: 3px;
    padding: 4px 6px;
  }
  .redigerbar:focus-visible { border-color: var(--accent); }
  mark {
    background: color-mix(in srgb, var(--warn) 26%, transparent);
    color: inherit;
    border-radius: 2px;
  }
  /* aktuell delar accent-weak/accent-paret med mark i
     frontend/src/lib/arkiv/Snippet.svelte:39-44 — appens signal för "det här
     är den aktiva träffen", inte bara en träff bland andra. */
  mark.aktuell { background: var(--accent-weak); color: var(--accent); }
  /*
   * ALLTID monterad (class:dold i stället för {#if !tk.foljer} som planen
   * anger, docs/superpowers/plans/2026-07-26-transkribera-B2-transkriptvyn.md,
   * Task 6 steg 3). UPPTÄCKT UNDER IMPLEMENTATIONEN (avviker alltså från
   * planen), i två steg:
   *
   * 1. Montera/avmontera raden ändrar <dialog>:ens innehållshöjd. <dialog>
   *    är position: fixed och centreras av webbläsaren med margin: auto — en
   *    höjdändring FLYTTAR HELA RUTAN. Ett vanligt radklick (pointerdown
   *    släpper följandet, click kallar hoppaTillRad som tar tillbaka det)
   *    hinner då flytta raden undan musen mellan pointerdown och click, och
   *    klicket missar helt. Uppmätt: rutans höjd växte 250,7px → 298,7px och
   *    toppen flyttade 234,7px → 210,7px (exakt halva höjdökningen) — ett
   *    äkta felklick, inte bara ett testartefakt, eftersom musen INTE flyttar
   *    sig bara för att sidan gör det. Test "ett klick var som helst på
   *    raden hoppar dit" (task 5) fångade detta.
   *
   * 2. Försöket att lösa (1) med position: absolute (knappen läggs OVANPÅ
   *    listan i stället för att skjuta den) bytte ut det felet mot ett värre:
   *    stripen låg då över HELA sista radens bredd och tystade varje klick
   *    och varje textmarkeringsdrag som passerade den — testet "en
   *    textmarkering hindrar hoppet" (task 5) började då HOPPA i stället för
   *    att markera, eftersom dragets väg korsade knappens klickbara yta och
   *    bröt webbläsarens markeringsalgoritm.
   *
   * Lösningen är alltså inte att flytta raden ur flödet utan att aldrig ändra
   * dess NÄRVARO: höjden är konstant redan från montering, och tk.foljer
   * växlar bara synligheten. visibility: hidden (inte display: none) behåller
   * platsen — ingen höjdändring, alltså ingen omcentrering — och tar samtidigt
   * bort knappen ur tillgänglighetsträdet och tabbordningen, så
   * getByRole(...).toHaveCount(0) fortfarande stämmer när man följer.
   */
  .folj-rad {
    margin-top: 8px;
  }
  .folj-rad.dold {
    visibility: hidden;
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
</style>
