<script>
  import { chatt } from './stores.svelte.js';
  import { parseCitat } from './citat.js';
  import { vaxlaResonemang, valjCitat } from './actions.js';
  import { kal } from '../kalender/stores.svelte.js';
  import Forslagsbox from '../kalender/Forslagsbox.svelte';

  let lista = $state(null);
  let foljer = $state(true);

  // EN gång per meddelande, inte per render. Gamla appen kör parseChatCites
  // för alla meddelanden vid varje rAF-render (app.js:4197 → 1541), alltså
  // tiotals gånger i sekunden medan ett svar strömmar.
  const tolkade = $derived(
    chatt.trad.map((m) => (m.roll === 'modell' && m.text ? parseCitat(m.text, chatt.segment) : null)),
  );

  /**
   * Släpper autoscrollen när LÄRAREN flyttar sig, aldrig när vi själva gör
   * det. Lyssnarna bindes imperativt i stället för som onwheel-attribut: som
   * attribut fälls a11y_no_noninteractive_element_interactions på <ol>, och
   * repot har noll svelte-ignore. Det är dessutom sant — gester, inte
   * affordanser. scroll-eventet duger inte, det kan inte skilja vår egen
   * scrollning från lärarens.
   */
  function slappVidEgenScroll(el) {
    const NAVTANGENTER = ['ArrowUp', 'ArrowDown', 'PageUp', 'PageDown', 'Home', 'End'];
    const slapp = () => { foljer = false; };
    const paTangent = (e) => { if (NAVTANGENTER.includes(e.key)) foljer = false; };
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

  // Gamla appen renderar en markör <div data-follow="chatend"> (app.js:5257)
  // som INGEN kod läser — svaret växer under vikkanten. Stämpeln läses före
  // grinden: Sveltes spårning är dynamisk, så ett beroende som bara läses
  // efter en tidig return försvinner tyst.
  $effect(() => {
    const sista = chatt.trad[chatt.trad.length - 1];
    const stampel = chatt.trad.length + ':' + (sista ? sista.text.length : 0);
    if (foljer && lista && stampel) lista.scrollTop = lista.scrollHeight;
  });

  // En ny fråga betyder alltid att läraren vill se svaret.
  $effect(() => {
    if (chatt.skickar) foljer = true;
  });
</script>

<ol class="trad" bind:this={lista} use:slappVidEgenScroll aria-busy={chatt.skickar}>
  {#each chatt.trad as m, mi (mi)}
    <li class="rad" class:jag={m.roll === 'anvandare'}>
      {#if m.roll === 'anvandare'}
        <p class="fraga">{m.text}</p>
      {:else}
        {#if m.resonemang}
          <!-- Alltid en riktig knapp. Gamla appen använder <button> i stängt
               läge (app.js:5238) men en <div role="button"> utan
               tangentbordshanterare i öppet (app.js:5236), där Enter och
               mellanslag alltså inte gör någonting. -->
          <button
            type="button"
            class="res-knapp"
            aria-expanded={!!chatt.resonemangOppet[mi]}
            onclick={() => vaxlaResonemang(mi)}
          >{chatt.resonemangOppet[mi] ? 'Dölj resonemanget' : 'Visa resonemanget'}</button>
          {#if chatt.resonemangOppet[mi]}
            <p class="resonemang">{m.resonemang}</p>
          {/if}
        {/if}
        {#if m.text}
          <!-- Ren text, ingen markdown. ArkivAnswer.svelte:23 etablerade det
               för modellutdata, och hela frontend/src har noll @html.
               Citaten är knappar i textflödet, som sok.js styckar sökträffar
               i B2 — samma mönster, ingen HTML-injektion. -->
          <p class="svar">{#each tolkade[mi].bitar as bit, bi (bi)}{#if bit.citat}<button
                type="button"
                class="citat"
                class:vald={chatt.valtCitat && chatt.valtCitat.mi === mi && chatt.valtCitat.segIndex === bit.citat.segIndex}
                aria-pressed={!!(chatt.valtCitat && chatt.valtCitat.mi === mi && chatt.valtCitat.segIndex === bit.citat.segIndex)}
                aria-label="Visa källa {bit.citat.nummer} i transkriptet"
                onclick={() => valjCitat(mi, bit.citat.segIndex)}
              >{bit.citat.nummer}</button>{:else}{bit.text}{/if}{/each}</p>
        {:else if chatt.skickar}
          <p class="svar vantar">Söker i transkriptet …</p>
        {/if}
      {/if}
    </li>
  {/each}
</ol>

{#if kal.forslag}
  <Forslagsbox />
{/if}

<style>
  .trad {
    list-style: none;
    margin: 0;
    padding: 0;
    overflow-y: auto;
    flex: 1 1 auto;
    min-height: 0;
    display: flex;
    flex-direction: column;
    gap: 12px;
  }
  .rad { margin: 0; max-width: 68ch; }
  /* Lärarens egna frågor dras åt höger — enda skillnaden i form. Ingen
     färgad kant, DESIGN.md §Don't. */
  .rad.jag { align-self: flex-end; }
  .fraga {
    margin: 0;
    background: var(--sunken);
    border: 1px solid var(--line);
    border-radius: 4px;
    padding: 8px 12px;
  }
  .svar { margin: 0; overflow-wrap: anywhere; }
  .vantar { color: var(--ink-3); }
  .res-knapp {
    background: transparent;
    color: var(--ink-3);
    border: none;
    padding: 0 0 4px;
    font-family: inherit;
    font-size: 0.72rem;
    cursor: pointer;
    text-decoration: underline;
    text-underline-offset: 3px;
    display: block;
  }
  .res-knapp:hover { color: var(--ink-2); }
  .resonemang {
    margin: 0 0 8px;
    color: var(--ink-3);
    border-left: none;
    background: var(--sunken);
    border-radius: 3px;
    padding: 8px 10px;
  }
  /* Citatet är data i textflödet, inte en mikroetikett: sans med
     tabular-nums, aldrig var(--mono). DESIGN.md §181-183. */
  .citat {
    background: var(--accent-weak);
    color: var(--accent);
    border: 1px solid transparent;
    border-radius: 3px;
    padding: 0 5px;
    margin: 0 1px;
    font-family: inherit;
    font-size: 0.72rem;
    font-variant-numeric: tabular-nums;
    cursor: pointer;
    vertical-align: baseline;
  }
  .citat.vald { border-color: var(--accent); }
</style>
